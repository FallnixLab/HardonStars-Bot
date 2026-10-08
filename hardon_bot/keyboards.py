from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy:stars"),
             InlineKeyboardButton(text="💎 Telegram Premium", callback_data="buy:premium")],
            [InlineKeyboardButton(text="💠 Баланс TON", callback_data="section:ton"),
             InlineKeyboardButton(text="👤 Профиль", callback_data="section:profile")],
            [InlineKeyboardButton(text="ℹ️ Информация", callback_data="section:info"),
             InlineKeyboardButton(text="✨ Наши проекты", callback_data="section:projects")],
            [InlineKeyboardButton(text="🛡 Поддержка", callback_data="info:support")],
        ]
    )


def information_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Инструкция", callback_data="info:instructions"),
             InlineKeyboardButton(text="📑 Правила", callback_data="info:rules")],
            [InlineKeyboardButton(text="ⓘ Политика", callback_data="info:privacy"),
             InlineKeyboardButton(text="☑️ Соглашение", callback_data="info:terms")],
            [InlineKeyboardButton(text="💳 Способы оплаты", callback_data="section:payments")],
            [InlineKeyboardButton(text="▣ Реклама", callback_data="info:advertising")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="home")],
        ]
    )


def stars_amounts() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="50 ⭐", callback_data="stars:50"),
             InlineKeyboardButton(text="100 ⭐", callback_data="stars:100")],
            [InlineKeyboardButton(text="250 ⭐", callback_data="stars:250"),
             InlineKeyboardButton(text="500 ⭐", callback_data="stars:500")],
            [InlineKeyboardButton(text="✍️ Свое количество", callback_data="stars:custom")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="home")],
        ]
    )


def premium_durations() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="3 месяца", callback_data="premium:3"),
             InlineKeyboardButton(text="6 месяцев", callback_data="premium:6")],
            [InlineKeyboardButton(text="12 месяцев", callback_data="premium:12")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="home")],
        ]
    )


def payment_methods() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="pay:telegram_stars")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="home")],
        ]
    )


def terms_consent(terms_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if terms_url:
        rows.append([InlineKeyboardButton(text="📑 Открыть соглашение", url=terms_url)])
    rows.append([InlineKeyboardButton(text="✅ Принимаю условия", callback_data="terms:accept")])
    rows.append([InlineKeyboardButton(text="↩️ В меню", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_link(order_id: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти к оплате", url=url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check:{order_id}")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
        ]
    )


def external_link(label: str, url: str, callback: str = "home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, url=url)],
            [InlineKeyboardButton(text="↩️ В меню", callback_data=callback)],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ В меню", callback_data="home")]]
    )


def back_to_info() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ К информации", callback_data="section:info")]]
    )
