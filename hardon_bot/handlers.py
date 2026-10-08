from __future__ import annotations

import logging
import re
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, LinkPreviewOptions, Message, PreCheckoutQuery

from hardon_bot.config import Settings
from hardon_bot.database import Database, Order
from hardon_bot.emoji import CUSTOM_EMOJI, MESSAGE_CUSTOM_EMOJI, RichTextPart, rich_text
from hardon_bot.fragment import FragmentDelivery, FragmentDeliveryError
from hardon_bot.keyboards import (
    back_to_info,
    back_to_menu,
    external_link,
    information_menu,
    main_menu,
    pay_link,
    payment_methods,
    premium_durations,
    profile_actions,
    stars_amounts,
    stars_recipient_actions,
    terms_consent,
)
from hardon_bot.payments import (
    PaymentProviderError,
    close_gateway,
    gateway_for,
    new_order_id,
)

log = logging.getLogger(__name__)
router = Router(name="shop")


class OrderForm(StatesGroup):
    waiting_custom_stars = State()
    waiting_target = State()
    waiting_payment = State()


PRODUCT_NAMES = {"stars": "Telegram Stars", "premium": "Telegram Premium", "ton": "TON"}


def icon(key: str, fallback: str) -> tuple[str, str | None]:
    return fallback, MESSAGE_CUSTOM_EMOJI.get(key)


def bold(value: str) -> RichTextPart:
    return value, None, "bold"


def text_link(value: str, url: str) -> RichTextPart:
    return value, None, None, url


async def answer_rich(
    message: Message,
    parts: list[RichTextPart],
    *,
    reply_markup=None,
    disable_link_preview: bool = False,
) -> None:
    text, entities = rich_text(parts)
    await message.answer(
        text,
        entities=entities,
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True) if disable_link_preview else None,
    )


async def answer_notice(
    message: Message,
    key: str,
    glyph: str,
    text: str,
    *,
    reply_markup=None,
) -> None:
    await answer_rich(message, [icon(key, glyph), (" ", None), (text, None)], reply_markup=reply_markup)


async def answer_delivery_result(message: Message, result: str) -> None:
    if result.startswith("Оплата подтверждена, товар выдан"):
        key, glyph, title = "accept", "✅", "Оплата подтверждена — заказ выдан"
        body = "Спасибо за покупку! Если у вас возник вопрос по этому заказу, обратитесь в поддержку и укажите его номер."
    elif "требует проверки поддержки" in result:
        key, glyph, title = "support", "🛡", "Оплата найдена, нужна проверка"
        body = "Заказ сохранён, но автоматическая выдача требует проверки. Повторно оплачивать его не нужно; обратитесь в поддержку и укажите номер заказа."
    else:
        key, glyph, title = "check", "🔄", "Статус заказа обновлён"
        body = "Заказ уже обрабатывается или выдан. Если товар не поступил, сообщите в поддержку номер заказа."
    await answer_rich(message, [icon(key, glyph), (" ", None), bold(title), ("\n\n", None), (body, None)], reply_markup=back_to_menu())


async def show_menu(message: Message, name: str | None = None) -> None:
    prefix = name or "друг"
    text, entities = rich_text(
        [
            icon("projects", "✨"), (" Привет, ", None), (prefix, None),
            ("!\n\n", None), bold("Добро пожаловать в Hardon Stars!"),
            ("\n\n", None),
            ("Покупайте Telegram Stars и Telegram Premium для своего аккаунта или укажите username получателя. В меню также доступны профиль, баланс TON, информация о сервисе и поддержка.", None),
            ("\n\n", None), icon("instructions", "📖"),
            (" Выберите нужный раздел ниже.", None),
        ]
    )
    await message.answer(text, entities=entities, reply_markup=main_menu())


async def ask_target(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderForm.waiting_target)
    await answer_rich(
        message,
        [
            icon("profile", "👤"), (" ", None), bold("Кому отправить заказ?"),
            ("\n\nОтправьте username получателя Telegram, например @username. Проверьте написание: после оплаты заказ будет оформлен для указанного аккаунта.", None),
        ],
        reply_markup=back_to_menu(),
    )


async def ask_stars_recipient(
    message: Message, state: FSMContext, example_username: str | None = None
) -> None:
    await state.update_data(product="stars")
    await state.set_state(OrderForm.waiting_target)
    example = f"@{example_username}" if example_username else "@username"
    await answer_rich(
        message,
        [
            icon("stars", "⭐"), (" ", None), bold("Покупка звёзд"),
            ("\n\n", None), icon("globe", "🌐"),
            (" Пришлите username пользователя, которому будем дарить звёзды:\n", None),
            icon("down", "👇"), (" Пример: ", None), text_link(example, f"https://t.me/{example.lstrip('@')}"),
            ("\n\nМожно указать свой username вручную или нажать «Купить для себя».", None),
        ],
        reply_markup=stars_recipient_actions(),
        disable_link_preview=True,
    )


async def ask_stars_quantity(
    message: Message, state: FSMContext, *, custom_entry: bool = False
) -> None:
    data = await state.get_data()
    target = str(data.get("target", ""))
    target_label = str(data.get("target_label") or f"@{target}")
    await state.set_state(OrderForm.waiting_custom_stars)
    parts: list[RichTextPart] = [
        icon("stars", "⭐"), (" ", None), bold("Покупка звёзд"),
        ("\n\n> ", None), icon("profile", "👤"), (" ", None), bold("Получатель: "),
        text_link(target_label, f"https://t.me/{target}"),
        ("\n\n", None), icon("accept", "✅"), (" Минимум: 50 звёзд\n", None),
        icon("accept", "✅"), (" Максимум (за один заказ): 10 000 звёзд\n\n", None),
    ]
    if custom_entry:
        parts.extend([icon("custom_amount", "✍️"), (" Введите количество звёзд от 50 до 10 000, кратное 50.", None)])
        keyboard = back_to_menu()
    else:
        parts.extend([icon("custom_amount", "✍️"), (" Введите количество звёзд для покупки или выберите вариант ниже.", None)])
        keyboard = stars_amounts()
    await answer_rich(message, parts, reply_markup=keyboard, disable_link_preview=True)


def is_username(value: str) -> bool:
    return bool(re.fullmatch(r"@?[A-Za-z0-9_]{5,32}", value.strip()))


def product_description(order: Order) -> str:
    if order.product == "stars":
        return f"{order.quantity} Telegram Stars для {order.target}"
    if order.product == "premium":
        return f"Telegram Premium на {order.quantity} мес. для {order.target}"
    return f"Пополнение TON для {order.target} ({order.quantity} TON)"


async def fulfill_paid_order(
    *, order: Order, db: Database, fragment: FragmentDelivery
) -> str:
    if not await db.claim_delivery(order.id):
        return "Заказ уже обрабатывается или выдан."
    try:
        await fragment.deliver(order)
    except FragmentDeliveryError as exc:
        await db.mark_delivery_issue(order.id, str(exc))
        log.warning("Paid order %s needs manual delivery review (%s)", order.id, type(exc).__name__)
        return "Оплата найдена, но выдача товара требует проверки поддержки. Ваш заказ сохранён."
    await db.mark_delivered(order.id)
    return "Оплата подтверждена, товар выдан. Спасибо за покупку!"


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    await state.clear()
    if message.from_user:
        await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await show_menu(message, message.from_user.first_name if message.from_user else None)


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await answer_rich(callback.message, [icon("projects", "✨"), (" ", None), bold("Главное меню"), ("\n\nВыберите услугу или откройте нужный раздел.", None)], reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "buy:stars")
async def choose_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ask_stars_recipient(callback.message, state, callback.from_user.username)
    await callback.answer()


@router.callback_query(F.data == "buy:premium")
async def choose_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(product="premium")
    await answer_rich(callback.message, [icon("premium", "💎"), (" ", None), bold("Telegram Premium"), ("\n\nВыберите срок подписки. На следующем шаге укажите Telegram username, для которого оформляется заказ.", None)], reply_markup=premium_durations())
    await callback.answer()


@router.callback_query(F.data == "section:ton")
async def ton_section(callback: CallbackQuery) -> None:
    text, entities = rich_text(
        [
            icon("ton", "💠"), (" ", None), bold("Баланс TON"),
            ("\n\nВ этом разделе будут отображаться доступный баланс и операции с TON. Автоматическая выдача TON пока не подключена: перед запуском нужно настроить и проверить соответствующий сценарий в Fragment API.\n\n", None),
            icon("info", "ℹ️"), (" После настройки здесь появятся доступные суммы, курс и подтверждение операции.", None),
        ]
    )
    await callback.message.answer(text, entities=entities, reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("stars:"))
async def stars_quantity(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings
) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "self":
        user = callback.from_user
        if not user.username:
            await callback.answer("Сначала добавьте username в настройках Telegram", show_alert=True)
            return
        await state.update_data(product="stars", target=user.username, target_label=user.full_name)
        await ask_stars_quantity(callback.message, state)
        await callback.answer()
        return
    data = await state.get_data()
    if not data.get("target"):
        await callback.answer("Сначала выберите получателя", show_alert=True)
        await ask_stars_recipient(callback.message, state, callback.from_user.username)
        return
    if value == "custom":
        await ask_stars_quantity(callback.message, state, custom_entry=True)
    else:
        quantity = int(value)
        await state.update_data(product="stars", quantity=quantity)
        await continue_to_checkout(callback.message, state, db, settings)
    await callback.answer()


@router.message(OrderForm.waiting_custom_stars)
async def custom_stars(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    try:
        quantity = int((message.text or "").strip())
    except ValueError:
        quantity = 0
    if quantity < 50 or quantity > 10_000 or quantity % 50:
        await answer_rich(message, [icon("stars", "⭐"), (" ", None), bold("Некорректное количество"), ("\n\nВведите от 50 до 10 000 звёзд, кратно 50. Например, 150 или 1 250.", None)])
        return
    data = await state.get_data()
    if not data.get("target"):
        await ask_stars_recipient(message, state, message.from_user.username if message.from_user else None)
        return
    await state.update_data(product="stars", quantity=quantity)
    await continue_to_checkout(message, state, db, settings)


@router.callback_query(F.data.startswith("premium:"))
async def premium_duration(callback: CallbackQuery, state: FSMContext) -> None:
    months = int(callback.data.split(":", 1)[1])
    if months not in {3, 6, 12}:
        await callback.answer("Недоступный срок", show_alert=True)
        return
    await state.update_data(product="premium", quantity=months)
    await ask_target(callback.message, state)
    await callback.answer()


@router.message(OrderForm.waiting_target)
async def receive_target(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    target = (message.text or "").strip()
    if not is_username(target):
        await answer_notice(message, "profile", "👤", "Нужен Telegram username длиной от 5 до 32 символов, например @username. Проверьте, что вы отправили именно имя пользователя, а не отображаемое имя.")
        return
    clean_target = target.lstrip("@")
    await state.update_data(target=clean_target, target_label=f"@{clean_target}")
    data = await state.get_data()
    product = str(data.get("product"))
    if product == "stars":
        await ask_stars_quantity(message, state)
        return
    await continue_to_checkout(message, state, db, settings)


async def continue_to_checkout(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    await state.set_state(OrderForm.waiting_payment)
    data = await state.get_data()
    product = str(data.get("product", ""))
    quantity = int(data.get("quantity", 0))
    target = str(data.get("target", ""))
    if not settings.terms_url:
        await answer_rich(message, [icon("agreement", "☑️"), (" ", None), bold("Заказ временно недоступен"), ("\n\nПеред приёмом оплаты необходимо опубликовать пользовательское соглашение и указать ссылку TERMS_URL в файле .env.", None)], reply_markup=back_to_menu())
        return
    if not message.from_user or not await db.has_accepted_terms(message.from_user.id):
        await answer_rich(message, [icon("agreement", "☑️"), (" ", None), bold("Перед заказом ознакомьтесь с условиями"), ("\n\nДля цифровых товаров, оформляемых внутри Telegram, используется оплата Telegram Stars. Откройте соглашение и подтвердите согласие, чтобы продолжить.", None)], reply_markup=terms_consent(settings.terms_url))
        return
    await show_payment_choice(message, settings, product, quantity, target)


async def show_payment_choice(
    message: Message, settings: Settings, product: str, quantity: int, target: str
) -> None:
    stars_price = settings.xtr_price(product, quantity)
    price_text = f"{stars_price} Telegram Stars" if stars_price > 0 else "не настроена"
    product_icon, product_glyph = ("stars", "⭐") if product == "stars" else ("premium", "💎")
    unit = "шт." if product == "stars" else "мес." if product == "premium" else "TON"
    await answer_rich(message, [
        icon(product_icon, product_glyph), (" ", None), bold("Проверьте заказ"),
        (f"\n\nТовар: {PRODUCT_NAMES.get(product, product)}\nКоличество: {quantity} {unit}\nПолучатель: @{target}\nЦена: {price_text}.", None),
        ("\n\n", None), icon("payments", "💳"), (" Выберите доступный способ оплаты ниже.", None),
        ("\nПосле оплаты заказ отправится на обработку. Сохраняйте сообщение с деталями платежа.", None),
    ], reply_markup=payment_methods())


@router.callback_query(OrderForm.waiting_payment, F.data == "terms:accept")
async def accept_terms(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if not settings.terms_url:
        await callback.answer("Соглашение ещё не настроено", show_alert=True)
        return
    await db.accept_terms(callback.from_user.id)
    data = await state.get_data()
    product = str(data.get("product", ""))
    quantity = int(data.get("quantity", 0))
    target = str(data.get("target", ""))
    await show_payment_choice(callback.message, settings, product, quantity, target)
    await callback.answer("Условия приняты")


@router.callback_query(OrderForm.waiting_payment, F.data.startswith("pay:"))
async def select_payment(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot,
    fragment: FragmentDelivery,
) -> None:
    provider = callback.data.split(":", 1)[1]
    if not settings.terms_url or not await db.has_accepted_terms(callback.from_user.id):
        await callback.answer("Сначала откройте и примите пользовательское соглашение", show_alert=True)
        return
    if provider == "telegram_stars":
        if not settings.fragment_enabled or not settings.fragment_wallet_seed:
            await answer_rich(callback.message, [icon("payments", "💳"), (" ", None), bold("Оплата временно недоступна"), ("\n\nПодключение Fragment API ещё не настроено или не подтверждено. Заказ не создан и средства не списаны. Попробуйте позже или обратитесь в поддержку.", None)], reply_markup=back_to_menu())
            await callback.answer()
            return
        data = await state.get_data()
        product, quantity = str(data.get("product", "")), int(data.get("quantity", 0))
        target = str(data.get("target", ""))
        price = settings.xtr_price(product, quantity)
        if price <= 0:
            await answer_rich(callback.message, [icon("info", "ℹ️"), (" ", None), bold("Цена пока не настроена"), ("\n\nДля этого товара укажите стоимость в Telegram Stars в файле .env. Заказ не создан.", None)])
            await callback.answer()
            return
        order_id = new_order_id()
        order = Order(
            id=order_id, user_id=callback.from_user.id, product=product, target=target,
            quantity=quantity, price=str(price), currency="XTR", provider="telegram_stars",
            provider_payment_id=None, checkout_url=None, status="pending", created_at="",
        )
        await db.create_order(order)
        title = PRODUCT_NAMES.get(product, "Hardon Stars")[:32]
        description = product_description(order)[:255]
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title,
            description=description,
            payload=order_id,
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
            provider_token="",
        )
        await state.clear()
        await callback.answer()
        return
    if provider != "telegram_stars":
        await callback.answer(
            "Звёзды и Premium — цифровые товары. Внутри Telegram для них доступна только оплата Telegram Stars.",
            show_alert=True,
        )
        return


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, db: Database) -> None:
    order = await db.get_order(query.invoice_payload)
    valid = bool(
        order
        and order.user_id == query.from_user.id
        and order.provider == "telegram_stars"
        and order.status == "pending"
        and order.currency == "XTR"
        and query.currency == "XTR"
        and int(Decimal(order.price)) == query.total_amount
    )
    if valid:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Счёт уже недействителен. Создайте новый заказ.")


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, db: Database, fragment: FragmentDelivery
) -> None:
    payment = message.successful_payment
    order = await db.get_order(payment.invoice_payload)
    if not order or order.user_id != message.from_user.id:
        await answer_rich(message, [icon("support", "🛡"), (" ", None), bold("Платёж получен, заказ не найден"), ("\n\nНе создавайте повторный платёж. Напишите в поддержку и приложите квитанцию Telegram Stars и время оплаты.", None)], reply_markup=back_to_menu())
        return
    if payment.currency != "XTR" or payment.total_amount != int(Decimal(order.price)):
        await answer_rich(message, [icon("support", "🛡"), (" ", None), bold("Сумма платежа не совпала с заказом"), ("\n\nПлатёж зафиксирован для проверки. Напишите в поддержку и укажите номер заказа.", None)], reply_markup=back_to_menu())
        return
    await db.mark_paid(order.id, payment.telegram_payment_charge_id)
    order = await db.get_order(order.id)
    if not order:
        return
    result = await fulfill_paid_order(order=order, db=db, fragment=fragment)
    await answer_delivery_result(message, result)


@router.callback_query(F.data.startswith("check:"))
async def check_payment(
    callback: CallbackQuery, db: Database, settings: Settings, fragment: FragmentDelivery
) -> None:
    order_id = callback.data.split(":", 1)[1]
    order = await db.get_order(order_id)
    if not order or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.status in {"fulfilled", "delivering"}:
        await callback.answer("Заказ уже обработан", show_alert=True)
        return
    if order.status == "paid_issue":
        await answer_rich(callback.message, [icon("support", "🛡"), (" ", None), bold("Оплата подтверждена"), ("\n\nЗаказ передан на проверку выдачи. Повторно оплачивать его не нужно; поддержка проверит статус.", None)])
        await callback.answer()
        return
    if order.status != "pending" or not order.provider_payment_id:
        await callback.answer("Заказ сейчас нельзя проверить", show_alert=True)
        return
    try:
        gateway = gateway_for(settings, order.provider)
    except PaymentProviderError:
        await callback.answer("Платёжный сервис не настроен", show_alert=True)
        return
    try:
        paid = await gateway.is_paid(order.provider_payment_id)
    except PaymentProviderError:
        paid = False
        await answer_notice(callback.message, "check", "🔄", "Не удалось получить статус оплаты. Попробуйте проверить ещё раз немного позже.")
    finally:
        await close_gateway(gateway)
    if not paid:
        await callback.answer("Оплата пока не подтверждена", show_alert=True)
        return
    await db.mark_paid(order.id, order.provider_payment_id)
    order = await db.get_order(order.id)
    if not order:
        await callback.answer()
        return
    result = await fulfill_paid_order(order=order, db=db, fragment=fragment)
    await answer_delivery_result(callback.message, result)
    await callback.answer()


@router.callback_query(F.data == "section:profile")
async def profile(callback: CallbackQuery, db: Database) -> None:
    user = callback.from_user
    await db.upsert_user(user.id, user.username, user.full_name)
    total, delivered, pending = await db.stats(user.id)
    recent = await db.recent_orders(user.id, 5)
    parts: list[RichTextPart] = [
        icon("profile", "👤"), (" ", None), bold("Ваш профиль"),
        ("\n\n", None), icon("user_id", "👤"), (f" Telegram ID: {user.id}\n", None),
        icon("username", "👤"), (f" Username: @{user.username}" if user.username else " Username: не задан", None),
        ("\n", None), icon("balance", "➕"), (" Баланс: пока не подключён", None),
        ("\n", None), icon("orders", "⭐"), (f" Заказов: {total} · выдано: {delivered} · в обработке: {pending}", None),
    ]
    if recent:
        parts.extend([("\n\n", None), icon("check", "🔄"), (" ", None), bold("Последние заказы"), ("\n", None)])
        for order in recent:
            product_key, glyph = {"stars": ("stars", "⭐"), "premium": ("premium", "💎"), "ton": ("ton", "💠")}.get(order.product, ("info", "ℹ️"))
            parts.extend([icon(product_key, glyph), (f" {PRODUCT_NAMES.get(order.product, order.product)} × {order.quantity} — {order.status}\n", None)])
    else:
        parts.extend([("\n\n", None), icon("info", "ℹ️"), (" Пока заказов нет. После оформления они появятся в этом разделе.", None)])
    await answer_rich(callback.message, parts, reply_markup=profile_actions())
    await callback.answer()


@router.callback_query(F.data == "balance:topup")
async def balance_topup(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    text_parts: list[RichTextPart] = [
        icon("balance", "➕"), (" ", None), bold("Пополнение баланса"),
        ("\n\nВнутренний баланс пока не активирован, поэтому пополнение и списание средств недоступны. Чтобы включить эту функцию, нужно определить валюту баланса, правила конвертации и платёжные методы, а затем проверить зачисление по уведомлению платёжного сервиса.", None),
    ]
    if settings.support_url:
        keyboard = external_link(
            "Написать в поддержку",
            settings.support_url,
            callback="section:profile",
            back_label="В профиль",
        )
    else:
        keyboard = back_to_menu()
    if not settings.support_url:
        text_parts.extend([("\n\n", None), icon("info", "ℹ️"), (" Ссылка на поддержку пока не настроена. Её можно добавить через SUPPORT_URL в .env.", None)])
    await answer_rich(callback.message, text_parts, reply_markup=keyboard)


@router.callback_query(F.data == "section:payments")
async def payments_info(callback: CallbackQuery) -> None:
    parts = [
        icon("payments", "💳"), (" ", None), bold("Способы оплаты"),
        ("\n\n", None),
        ("🚀", CUSTOM_EMOJI["xrocket"]), (" xRocket\n", None),
        ("🤖", CUSTOM_EMOJI["cryptobot"]), (" CryptoBot\n", None),
        ("🏦", CUSTOM_EMOJI["payhot_sbp"]), (" PayHot · СБП\n", None),
        ("💳", CUSTOM_EMOJI["payhot_card"]), (" PayHot · карта\n", None),
        ("💎", CUSTOM_EMOJI["payhot_crypto"]), (" PayHot · криптовалюта\n", None),
        icon("stars", "⭐"), (" Telegram Stars (XTR)\n\n", None),
        icon("info", "ℹ️"), (" Для покупки цифровых товаров внутри Telegram сейчас используется Telegram Stars. Остальные способы приведены как планируемые или внешние интеграции и не будут доступны для оплаты, пока их подключение не завершено.\n\n", None),
        icon("info", "ℹ️"), (" PayHot ЕРИП пока не добавлен: сначала требуется отдельная инструкция/API-доступ от провайдера и Premium emoji для этого способа.", None),
    ]
    text, entities = rich_text(parts)
    await callback.message.answer(text, entities=entities, reply_markup=back_to_info())
    await callback.answer()


@router.callback_query(F.data == "section:info")
async def information(callback: CallbackQuery) -> None:
    await answer_rich(callback.message, [icon("info", "ℹ️"), (" ", None), bold("Информация о сервисе Hardon Stars"), ("\n\n", None), icon("globe", "🌐"), (" Hardon Stars позволяет оформить Telegram Stars и Telegram Premium для себя или другого пользователя. В профиле можно посмотреть сведения об аккаунте и заказах, а здесь — ознакомиться с правилами, инструкцией, политикой конфиденциальности, соглашением и вариантами оплаты.\n\n", None), icon("down", "👇"), (" Выберите нужный раздел ниже:", None)], reply_markup=information_menu())
    await callback.answer()


@router.callback_query(F.data == "section:projects")
async def projects(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    sentence = "Hardon — создаем лучшие IT-решения для вашего удобства и безопасности!"
    text, entities = rich_text([icon("projects", "✨"), (" ", None), (sentence, None, "bold")])
    project_url = settings.projects_url or "https://project.hardon.cc/"
    await callback.message.answer(
        text,
        entities=entities,
        reply_markup=external_link("Hardon Project", project_url),
    )


@router.message(Command("paysupport", "support"))
async def paysupport(message: Message, settings: Settings) -> None:
    parts: list[RichTextPart] = [icon("headset", "🎧"), (" ", None), bold("Служба поддержки"), ("\n\nЕсли у вас возникли вопросы, проблемы с заказом или вы нашли ошибку, свяжитесь с нами по кнопке ниже. В сообщении укажите номер заказа, кратко опишите ситуацию и приложите подтверждение оплаты, если вопрос связан с платежом.\n\nОбычно отвечаем в течение 24 часов. По спорным заказам не создавайте повторную оплату до ответа специалиста.", None)]
    if settings.support_url:
        await answer_rich(message, parts, reply_markup=external_link("Открыть поддержку", settings.support_url))
    else:
        parts.extend([("\n\n", None), icon("info", "ℹ️"), (" Ссылка пока не настроена. Добавьте SUPPORT_URL в .env.", None)])
        await answer_rich(message, parts)


@router.message(Command("terms"))
async def terms_command(message: Message, settings: Settings) -> None:
    if settings.terms_url:
        await answer_rich(message, [icon("agreement", "☑️"), (" ", None), bold("Пользовательское соглашение"), ("\n\nПеред использованием сервиса ознакомьтесь с условиями оформления, оплаты и выдачи заказов.", None)], reply_markup=external_link("Открыть соглашение", settings.terms_url))
    else:
        await answer_rich(message, [icon("agreement", "☑️"), (" ", None), bold("Соглашение ещё не настроено"), ("\n\nОпубликуйте полный текст пользовательского соглашения и добавьте его адрес в TERMS_URL в файле .env.", None)])


@router.callback_query(F.data.startswith("info:"))
async def info(callback: CallbackQuery, settings: Settings) -> None:
    section = callback.data.split(":", 1)[1]
    pages = {
        "instructions": (
            "instructions", "📖", "Инструкция",
            "1. Выберите Telegram Stars или Telegram Premium в главном меню.\n2. Для Stars укажите количество, а для Premium — срок подписки.\n3. Введите username получателя и внимательно проверьте его.\n4. Прочитайте пользовательское соглашение, откройте его и подтвердите согласие.\n5. Проверьте товар, получателя и стоимость в карточке заказа.\n6. Оплатите заказ доступным способом и дождитесь подтверждения.\n\nПосле подтверждения заказ передаётся на выдачу. Если статус не обновился или товар не поступил, обратитесь в поддержку и приложите номер заказа.",
            settings.instructions_url,
        ),
        "rules": (
            "rules", "📑", "Правила сервиса",
            "Перед оплатой проверяйте тип товара, срок или количество и Telegram username получателя. После подтверждения платежа заказ передаётся на обработку. Не отправляйте несколько одинаковых платежей, если проверка статуса задерживается.\n\nПри ошибке, спорной оплате или задержке напишите в поддержку и укажите номер заказа. Не присылайте пароли, коды входа Telegram, seed-фразы и полные данные банковской карты.",
            settings.rules_url,
        ),
        "privacy": (
            "privacy", "ⓘ", "Политика конфиденциальности",
            "Для работы Hardon Stars обрабатываются Telegram ID, username (если он задан), имя профиля, сведения о заказах и технические идентификаторы платежей. Эти данные нужны для оформления, учёта и поддержки заказов.\n\nБот не запрашивает пароль Telegram, коды подтверждения, seed-фразы или полные данные банковской карты. Полный текст политики и сведения о сроках хранения данных откройте по кнопке ниже.",
            settings.privacy_url,
        ),
        "terms": (
            "agreement", "☑️", "Пользовательское соглашение",
            "Перед созданием заказа проверьте получателя, товар, количество или срок и цену. Подтверждая условия, вы соглашаетесь с опубликованными правилами сервиса.\n\nПорядок оплаты, выдачи, обработки спорных ситуаций и возвратов должен быть указан в полном тексте соглашения по ссылке ниже.",
            settings.terms_url,
        ),
        "advertising": (
            "advertising", "▣", "Реклама и сотрудничество",
            "По вопросам рекламы, партнёрских публикаций и сотрудничества свяжитесь с нами по ссылке ниже. В обращении укажите площадку, формат размещения, примерные сроки и контакт для ответа.\n\nЕсли отдельная ссылка не настроена, запросите актуальные контакты у службы поддержки.",
            settings.advertising_url,
        ),
        "support": (
            "headset", "🎧", "Служба поддержки",
            "Если у вас возникли вопросы, проблемы с пополнением или заказом либо вы нашли ошибку, воспользуйтесь кнопкой ниже.\n\nОбычно отвечаем в течение 24 часов. По вопросам оплаты или выдачи приложите номер заказа, время платежа и краткое описание ситуации. Не отправляйте пароли, коды Telegram или платёжные секреты.",
            settings.support_url,
        ),
    }
    icon_key, glyph, title, body, url = pages.get(section, ("info", "ℹ️", "Раздел", "Материал не найден. Вернитесь в информацию и выберите доступный раздел.", ""))
    return_callback = "home" if section == "support" else "section:info"
    if url:
        keyboard = external_link("Открыть ссылку", url, callback=return_callback)
    else:
        keyboard = back_to_menu() if section == "support" else back_to_info()
        if section in {"support", "advertising"}:
            body += "\n\nСсылка пока не настроена. Добавьте её в соответствующую переменную .env."
    await answer_rich(callback.message, [icon(icon_key, glyph), (" ", None), bold(title), ("\n\n", None), (body, None)], reply_markup=keyboard)
    await callback.answer()


@router.message()
async def fallback(message: Message) -> None:
    await answer_rich(message, [icon("info", "ℹ️"), (" ", None), bold("Выберите действие"), ("\n\nИспользуйте кнопки главного меню, чтобы открыть нужный раздел, посмотреть заказы или перейти к покупке.", None)], reply_markup=main_menu())
