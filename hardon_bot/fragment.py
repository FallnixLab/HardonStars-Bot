from __future__ import annotations

import asyncio

from hardon_bot.config import Settings
from hardon_bot.database import Order


class FragmentDeliveryError(RuntimeError):
    pass


class FragmentDelivery:
    """Thin async wrapper around Fragment API's published Python client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def deliver(self, order: Order) -> None:
        if not self.settings.fragment_enabled or not self.settings.fragment_wallet_seed:
            raise FragmentDeliveryError("Fragment API не настроен")
        if order.product == "ton":
            raise FragmentDeliveryError(
                "В используемом Fragment SDK пока не настроен метод выдачи TON"
            )
        try:
            await asyncio.to_thread(self._deliver_sync, order)
        except Exception as exc:
            # Do not retry automatically: a timeout may happen after the provider
            # accepted the transaction. The paid order is sent for manual review.
            raise FragmentDeliveryError(type(exc).__name__) from exc

    def _deliver_sync(self, order: Order) -> None:
        try:
            from fragment_api import FragmentAPIClient
        except ImportError as exc:
            raise FragmentDeliveryError("Не установлен fragment-stars-api") from exc

        client = FragmentAPIClient(
            base_url=self.settings.fragment_base_url,
            timeout=30,
            poll_timeout=300,
        )
        if order.product == "stars":
            result = client.buy_stars(
                order.target.lstrip("@"),
                order.quantity,
                seed=self.settings.fragment_wallet_seed,
                wait=True,
            )
        elif order.product == "premium":
            result = client.buy_premium(
                order.target.lstrip("@"),
                order.quantity,
                seed=self.settings.fragment_wallet_seed,
                wait=True,
            )
        else:
            raise FragmentDeliveryError("Неизвестный продукт")

        if not getattr(result, "success", False):
            raise FragmentDeliveryError("Fragment API не подтвердил выполнение заказа")
