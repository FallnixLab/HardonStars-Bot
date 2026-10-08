from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Order:
    id: str
    user_id: int
    product: str
    target: str
    quantity: int
    price: str
    currency: str
    provider: str
    provider_payment_id: str | None
    checkout_url: str | None
    status: str
    created_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    terms_accepted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(telegram_id),
                    product TEXT NOT NULL,
                    target TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_payment_id TEXT,
                    checkout_url TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivery_error TEXT
                );
                CREATE INDEX IF NOT EXISTS orders_user_created
                    ON orders(user_id, created_at DESC);
                """
            )
            # Keep existing local databases compatible with the consent gate.
            columns = await (await db.execute("PRAGMA table_info(users)")).fetchall()
            if not any(column[1] == "terms_accepted_at" for column in columns):
                await db.execute("ALTER TABLE users ADD COLUMN terms_accepted_at TEXT")
            await db.commit()

    async def upsert_user(self, telegram_id: int, username: str | None, full_name: str) -> None:
        now = utc_now()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO users(telegram_id, username, full_name, created_at, last_seen_at)
                   VALUES(?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET
                     username=excluded.username, full_name=excluded.full_name,
                     last_seen_at=excluded.last_seen_at""",
                (telegram_id, username, full_name, now, now),
            )
            await db.commit()

    async def has_accepted_terms(self, telegram_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT terms_accepted_at FROM users WHERE telegram_id=?", (telegram_id,)
            )
            row = await cursor.fetchone()
            return bool(row and row[0])

    async def accept_terms(self, telegram_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET terms_accepted_at=? WHERE telegram_id=?",
                (utc_now(), telegram_id),
            )
            await db.commit()

    async def create_order(self, order: Order) -> None:
        now = utc_now()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO orders
                   (id, user_id, product, target, quantity, price, currency, provider,
                    provider_payment_id, checkout_url, status, created_at, updated_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.id, order.user_id, order.product, order.target, order.quantity,
                    order.price, order.currency, order.provider, order.provider_payment_id,
                    order.checkout_url, order.status, now, now,
                ),
            )
            await db.commit()

    @staticmethod
    def _order(row: aiosqlite.Row | tuple) -> Order:
        return Order(*row[:12])

    async def get_order(self, order_id: str) -> Order | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, user_id, product, target, quantity, price, currency, provider,
                          provider_payment_id, checkout_url, status, created_at
                   FROM orders WHERE id=?""",
                (order_id,),
            )
            row = await cursor.fetchone()
            return self._order(row) if row else None

    async def set_checkout(self, order_id: str, provider_payment_id: str, checkout_url: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE orders SET provider_payment_id=?, checkout_url=?, status='pending',
                   updated_at=? WHERE id=? AND status='created'""",
                (provider_payment_id, checkout_url, utc_now(), order_id),
            )
            await db.commit()

    async def set_failed(self, order_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET status='failed', updated_at=? WHERE id=? AND status='created'",
                (utc_now(), order_id),
            )
            await db.commit()

    async def mark_paid(self, order_id: str, payment_id: str | None = None) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """UPDATE orders SET status='paid', provider_payment_id=COALESCE(?, provider_payment_id),
                   updated_at=? WHERE id=? AND status='pending'""",
                (payment_id, utc_now(), order_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def claim_delivery(self, order_id: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE orders SET status='delivering', updated_at=? WHERE id=? AND status='paid'",
                (utc_now(), order_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def mark_delivered(self, order_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET status='fulfilled', updated_at=? WHERE id=? AND status='delivering'",
                (utc_now(), order_id),
            )
            await db.commit()

    async def mark_delivery_issue(self, order_id: str, error: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE orders SET status='paid_issue', delivery_error=?, updated_at=?
                   WHERE id=? AND status='delivering'""",
                (error[:300], utc_now(), order_id),
            )
            await db.commit()

    async def stats(self, telegram_id: int) -> tuple[int, int, int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN status='fulfilled' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status IN ('pending', 'paid', 'delivering', 'paid_issue') THEN 1 ELSE 0 END)
                   FROM orders WHERE user_id=?""",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return tuple(int(value or 0) for value in row)  # type: ignore[return-value]

    async def recent_orders(self, telegram_id: int, limit: int = 5) -> list[Order]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, user_id, product, target, quantity, price, currency, provider,
                          provider_payment_id, checkout_url, status, created_at
                   FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
                (telegram_id, limit),
            )
            return [self._order(row) for row in await cursor.fetchall()]
