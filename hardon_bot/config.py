from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv

load_dotenv()


def _decimal(name: str, default: str = "0") -> Decimal:
    value = os.getenv(name, default).strip()
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_path: str
    support_url: str
    advertising_url: str
    terms_url: str
    privacy_url: str
    instructions_url: str
    rules_url: str
    projects_url: str

    fragment_wallet_seed: str
    fragment_base_url: str
    fragment_enabled: bool

    crypto_pay_token: str
    crypto_pay_fiat: str
    crypto_pay_assets: tuple[str, ...]

    payhot_api_key: str
    payhot_currency: str
    payhot_crypto_currency: str

    xrocket_api_token: str
    xrocket_price_currency: str
    xrocket_pay_currencies: tuple[str, ...]

    star_rub_price: Decimal
    premium_3m_rub_price: Decimal
    premium_6m_rub_price: Decimal
    premium_12m_rub_price: Decimal
    ton_rub_price: Decimal

    star_xtr_price: int
    premium_3m_xtr_price: int
    premium_6m_xtr_price: int
    premium_12m_xtr_price: int
    ton_xtr_price: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bot_token=os.getenv("BOT_TOKEN", "").strip(),
            database_path=os.getenv("DATABASE_PATH", "data/hardon.sqlite3").strip(),
            support_url=os.getenv("SUPPORT_URL", "").strip(),
            advertising_url=os.getenv("ADVERTISING_URL", "").strip(),
            terms_url=os.getenv("TERMS_URL", "").strip(),
            privacy_url=os.getenv("PRIVACY_URL", "").strip(),
            instructions_url=os.getenv("INSTRUCTIONS_URL", "").strip(),
            rules_url=os.getenv("RULES_URL", "").strip(),
            projects_url=os.getenv("PROJECTS_URL", "https://project.hardon.cc/").strip(),
            fragment_wallet_seed=os.getenv("FRAGMENT_WALLET_SEED", "").strip(),
            fragment_base_url=os.getenv(
                "FRAGMENT_API_BASE_URL", "https://fragment-api.ydns.eu:8443"
            ).strip().rstrip("/"),
            fragment_enabled=os.getenv("FRAGMENT_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            crypto_pay_token=os.getenv("CRYPTO_PAY_API_TOKEN", "").strip(),
            crypto_pay_fiat=os.getenv("CRYPTO_PAY_FIAT", "RUB").strip().upper(),
            # Crypto Pay defaults to every supported crypto asset when this is empty.
            crypto_pay_assets=_csv("CRYPTO_PAY_ACCEPTED_ASSETS", ""),
            payhot_api_key=os.getenv("PAYHOT_API_KEY", "").strip(),
            payhot_currency=os.getenv("PAYHOT_CURRENCY", "RUB").strip().upper(),
            payhot_crypto_currency=os.getenv("PAYHOT_CRYPTO_CURRENCY", "RUB").strip().upper(),
            xrocket_api_token=os.getenv("XROCKET_API_TOKEN", "").strip(),
            xrocket_price_currency=os.getenv("XROCKET_PRICE_CURRENCY", "RUB").strip().upper(),
            xrocket_pay_currencies=_csv("XROCKET_PAY_CURRENCIES", ""),
            star_rub_price=_decimal("PRICE_STAR_RUB"),
            premium_3m_rub_price=_decimal("PRICE_PREMIUM_3M_RUB"),
            premium_6m_rub_price=_decimal("PRICE_PREMIUM_6M_RUB"),
            premium_12m_rub_price=_decimal("PRICE_PREMIUM_12M_RUB"),
            ton_rub_price=_decimal("PRICE_TON_RUB"),
            star_xtr_price=int(os.getenv("PRICE_STAR_XTR", "0")),
            premium_3m_xtr_price=int(os.getenv("PRICE_PREMIUM_3M_XTR", "0")),
            premium_6m_xtr_price=int(os.getenv("PRICE_PREMIUM_6M_XTR", "0")),
            premium_12m_xtr_price=int(os.getenv("PRICE_PREMIUM_12M_XTR", "0")),
            ton_xtr_price=int(os.getenv("PRICE_TON_XTR", "0")),
        )

    def rub_price(self, product: str, quantity: int) -> Decimal:
        if product == "stars":
            return self.star_rub_price * quantity
        if product == "premium":
            return {
                3: self.premium_3m_rub_price,
                6: self.premium_6m_rub_price,
                12: self.premium_12m_rub_price,
            }.get(quantity, Decimal("0"))
        if product == "ton":
            return self.ton_rub_price * quantity
        return Decimal("0")

    def xtr_price(self, product: str, quantity: int) -> int:
        if product == "stars":
            return self.star_xtr_price * quantity
        if product == "premium":
            return {
                3: self.premium_3m_xtr_price,
                6: self.premium_6m_xtr_price,
                12: self.premium_12m_xtr_price,
            }.get(quantity, 0)
        if product == "ton":
            return self.ton_xtr_price * quantity
        return 0


settings = Settings.from_env()
