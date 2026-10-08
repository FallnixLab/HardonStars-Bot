from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from hardon_bot.emoji import BUTTON_CUSTOM_EMOJI


def _button(
    label: str,
    fallback_emoji: str,
    *,
    style: str = "primary",
    icon_key: str | None = None,
    **action: Any,
) -> InlineKeyboardButton:
    emoji_id = BUTTON_CUSTOM_EMOJI.get(icon_key or "")
    text = label if emoji_id else f"{fallback_emoji} {label}"
    fields: dict[str, Any] = {"text": text, "style": style, **action}
    if emoji_id:
        fields["icon_custom_emoji_id"] = emoji_id
    return InlineKeyboardButton(**fields)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Купить звёзды", "⭐", style="success", icon_key="stars", callback_data="buy:stars"),
                _button("Telegram Premium", "💎", style="success", icon_key="premium", callback_data="buy:premium"),
            ],
            [
                _button("Баланс TON", "💠", icon_key="ton", callback_data="section:ton"),
                _button("Профиль", "👤", icon_key="profile", callback_data="section:profile"),
            ],
            [
                _button("Информация", "ℹ️", icon_key="info", callback_data="section:info"),
                _button("Поддержка", "🛡", icon_key="support", callback_data="info:support"),
            ],
            [_button("Наши проекты", "✨", icon_key="projects", callback_data="section:projects")],
        ]
    )


def information_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Инструкция", "📖", icon_key="instructions", callback_data="info:instructions"),
                _button("Правила", "📑", icon_key="rules", callback_data="info:rules"),
            ],
            [
                _button("Политика", "ⓘ", icon_key="privacy", callback_data="info:privacy"),
                _button("Соглашение", "☑️", icon_key="agreement", callback_data="info:terms"),
            ],
            [_button("Способы оплаты", "💳", icon_key="payments", callback_data="section:payments")],
            [_button("Реклама", "▣", icon_key="advertising", callback_data="info:advertising")],
            [_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def stars_amounts() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("50", "⭐", icon_key="stars", callback_data="stars:50"),
                _button("100", "⭐", icon_key="stars", callback_data="stars:100"),
            ],
            [
                _button("250", "⭐", icon_key="stars", callback_data="stars:250"),
                _button("500", "⭐", icon_key="stars", callback_data="stars:500"),
            ],
            [_button("Свое количество", "✍️", icon_key="custom_amount", callback_data="stars:custom")],
            [_button("Назад", "↩️", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def stars_recipient_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Купить для себя", "👤", style="success", icon_key="profile", callback_data="stars:self"),
                _button("Назад", "↩️", style="danger", icon_key="back", callback_data="home"),
            ],
        ]
    )


def premium_durations() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("3 месяца", "💎", style="success", icon_key="premium", callback_data="premium:3"),
                _button("6 месяцев", "💎", style="success", icon_key="premium", callback_data="premium:6"),
            ],
            [_button("12 месяцев", "💎", style="success", icon_key="premium", callback_data="premium:12")],
            [_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def payment_methods() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Telegram Stars", "⭐", style="success", icon_key="stars", callback_data="pay:telegram_stars")],
            [_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def profile_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Пополнить баланс", "➕", style="success", icon_key="balance", callback_data="balance:topup")],
            [_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def terms_consent(terms_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if terms_url:
        rows.append([_button("Открыть соглашение", "📑", icon_key="agreement", url=terms_url)])
    rows.append([_button("Принимаю условия", "✅", style="success", icon_key="accept", callback_data="terms:accept")])
    rows.append([_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_link(order_id: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Перейти к оплате", "🔗", style="success", icon_key="pay", url=url)],
            [_button("Проверить оплату", "🔄", icon_key="check", callback_data=f"check:{order_id}")],
            [_button("В меню", "🏠", style="danger", icon_key="back", callback_data="home")],
        ]
    )


def external_link(
    label: str,
    url: str,
    callback: str = "home",
    back_label: str = "В меню",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(label, "🔗", icon_key="link", url=url)],
            [_button(back_label, "↩️", style="danger", icon_key="back", callback_data=callback)],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("В меню", "↩️", style="danger", icon_key="back", callback_data="home")]]
    )


def back_to_info() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("К информации", "↩️", style="danger", icon_key="back", callback_data="section:info")]]
    )
