from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol
from uuid import uuid4

import httpx

from hardon_bot.config import Settings


class PaymentProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Checkout:
    payment_id: str
    url: str


class Gateway(Protocol):
    async def create(self, order_id: str, amount: Decimal, description: str) -> Checkout: ...
    async def is_paid(self, payment_id: str) -> bool: ...


class _HttpGateway:
    def __init__(self, timeout: float = 20) -> None:
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Не удалось связаться с платёжным сервисом") from exc
        return self._check(response)

    @staticmethod
    def _check(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PaymentProviderError("Платёжный сервис вернул некорректный ответ") from exc
        if not response.is_success:
            raise PaymentProviderError("Платёжный сервис отклонил запрос")
        return payload


class CryptoPayGateway(_HttpGateway):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.base_url = "https://pay.crypt.bot/api"

    async def create(self, order_id: str, amount: Decimal, description: str) -> Checkout:
        body: dict[str, Any] = {
            "currency_type": "fiat",
            "fiat": self.settings.crypto_pay_fiat,
            "amount": str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "description": description[:1024],
            "payload": order_id,
            "expires_in": 3600,
            "allow_comments": False,
            "allow_anonymous": False,
        }
        if self.settings.crypto_pay_assets:
            body["accepted_assets"] = ",".join(self.settings.crypto_pay_assets)
        data = await self.request(
            "POST",
            f"{self.base_url}/createInvoice",
            headers={"Crypto-Pay-API-Token": self.settings.crypto_pay_token},
            json=body,
        )
        result = data.get("result") or {}
        url = result.get("bot_invoice_url") or result.get("mini_app_invoice_url")
        if data.get("ok") is not True or not result.get("invoice_id") or not url:
            raise PaymentProviderError("Crypto Pay не создал счёт")
        return Checkout(str(result["invoice_id"]), str(url))

    async def is_paid(self, payment_id: str) -> bool:
        data = await self.request(
            "GET",
            f"{self.base_url}/getInvoices",
            headers={"Crypto-Pay-API-Token": self.settings.crypto_pay_token},
            params={"invoice_ids": payment_id},
        )
        if data.get("ok") is not True:
            raise PaymentProviderError("Не удалось получить статус Crypto Pay")
        result = data.get("result") or []
        if isinstance(result, dict):
            invoices = result.get("items", [])
        elif isinstance(result, list):
            invoices = result
        else:
            invoices = []
        return any(str(item.get("invoice_id")) == payment_id and item.get("status") == "paid" for item in invoices)


class PayHotGateway(_HttpGateway):
    def __init__(self, settings: Settings, payment_method: str, currency: str | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.payment_method = payment_method
        self.currency = currency or settings.payhot_currency
        self.base_url = "https://app.pay.hot/api/v2"

    def _headers(self, order_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.payhot_api_key}",
            "Idempotency-Key": f"hardon-{order_id}",
        }

    async def create(self, order_id: str, amount: Decimal, description: str) -> Checkout:
        minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        body = {
            "merchant_order_reference": order_id,
            "amount_minor": str(minor),
            "currency": self.currency,
            "payment_method": self.payment_method,
        }
        data = await self.request(
            "POST",
            f"{self.base_url}/payments",
            headers={**self._headers(order_id), "Content-Type": "application/json"},
            json=body,
        )
        payment = data.get("payment") or data
        checkout = data.get("checkout") or {}
        payment_id = payment.get("id")
        url = checkout.get("url")
        if not payment_id or not url:
            raise PaymentProviderError("PayHot не вернул ссылку оплаты")
        return Checkout(str(payment_id), str(url))

    async def is_paid(self, payment_id: str) -> bool:
        data = await self.request(
            "GET",
            f"{self.base_url}/payments/{payment_id}",
            headers={"Authorization": f"Bearer {self.settings.payhot_api_key}"},
        )
        payment = data.get("payment") or data
        return payment.get("status") == "succeeded"


class XRocketGateway(_HttpGateway):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.base_url = "https://pay.api.xrocket.exchange/api/v1"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.xrocket_api_token}"}

    async def create(self, order_id: str, amount: Decimal, description: str) -> Checkout:
        body = {
            "priceAmount": str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "priceCurrency": self.settings.xrocket_price_currency,
            "payCurrencies": list(self.settings.xrocket_pay_currencies),
            "clientInvoiceId": order_id,
            "description": description[:1000],
            "expiresIn": 3600000,
        }
        data = await self.request(
            "POST", f"{self.base_url}/invoices", headers=self._headers(), json=body
        )
        links = data.get("links") or {}
        url = links.get("telegramBotLink") or data.get("url")
        payment_id = data.get("id")
        if not payment_id or not url:
            raise PaymentProviderError("xRocket не вернул ссылку оплаты")
        return Checkout(str(payment_id), str(url))

    async def is_paid(self, payment_id: str) -> bool:
        data = await self.request(
            "GET", f"{self.base_url}/invoices", headers=self._headers(), params={"ids": payment_id}
        )
        invoices = data.get("items") or data.get("invoices") or data.get("result") or []
        if isinstance(invoices, dict):
            invoices = [invoices]
        return any(
            str(item.get("id")) == payment_id and item.get("status") == "paid"
            for item in invoices
        )


def gateway_for(settings: Settings, provider: str) -> Gateway:
    if provider == "cryptobot" and settings.crypto_pay_token:
        return CryptoPayGateway(settings)
    if provider == "payhot_sbp" and settings.payhot_api_key:
        return PayHotGateway(settings, "sbp")
    if provider == "payhot_card" and settings.payhot_api_key:
        return PayHotGateway(settings, "card")
    if provider == "payhot_crypto" and settings.payhot_api_key:
        return PayHotGateway(settings, "crypto", settings.payhot_crypto_currency)
    if provider == "xrocket" and settings.xrocket_api_token:
        return XRocketGateway(settings)
    raise PaymentProviderError("Этот способ оплаты пока не настроен")


async def close_gateway(gateway: Gateway) -> None:
    close = getattr(gateway, "close", None)
    if close:
        await close()


def new_order_id() -> str:
    return uuid4().hex
