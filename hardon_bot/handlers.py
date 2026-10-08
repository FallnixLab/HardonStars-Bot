from __future__ import annotations

import logging
import re
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, Message, MessageEntity, PreCheckoutQuery

from hardon_bot.config import Settings
from hardon_bot.database import Database, Order
from hardon_bot.emoji import CUSTOM_EMOJI, rich_text
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
    stars_amounts,
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
async def show_menu(message: Message, name: str | None = None) -> None:
    prefix = name or "друг"
    text, entities = rich_text(
        [
            ("✨ Привет, ", None), (prefix, None),
            ("!\n\nДобро пожаловать в Hardon Stars. Здесь можно оформить заказ на звёзды и Telegram Premium.", None),
        ]
    )
    await message.answer(text, entities=entities, reply_markup=main_menu())


async def ask_target(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderForm.waiting_target)
    await message.answer(
        "Отправьте username получателя Telegram, например @username. Перед оплатой проверьте его ещё раз.",
        reply_markup=back_to_menu(),
    )


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
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "buy:stars")
async def choose_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(product="stars")
    await callback.message.answer("Выберите количество Telegram Stars:", reply_markup=stars_amounts())
    await callback.answer()


@router.callback_query(F.data == "buy:premium")
async def choose_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(product="premium")
    await callback.message.answer("Выберите срок Telegram Premium:", reply_markup=premium_durations())
    await callback.answer()


@router.callback_query(F.data == "section:ton")
async def ton_section(callback: CallbackQuery) -> None:
    text, entities = rich_text(
        [
            ("💠 Раздел «Баланс TON»\n\n", None),
            ("Экран и кнопка уже предусмотрены. Пополнение будет активировано после подтверждения метода выдачи TON в Fragment API.", None),
        ]
    )
    await callback.message.answer(text, entities=entities, reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("stars:"))
async def stars_quantity(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await state.set_state(OrderForm.waiting_custom_stars)
        await callback.message.answer("Введите количество звёзд числом от 50 до 10 000, кратным 50.")
    else:
        quantity = int(value)
        await state.update_data(product="stars", quantity=quantity)
        await ask_target(callback.message, state)
    await callback.answer()


@router.message(OrderForm.waiting_custom_stars)
async def custom_stars(message: Message, state: FSMContext) -> None:
    try:
        quantity = int((message.text or "").strip())
    except ValueError:
        quantity = 0
    if quantity < 50 or quantity > 10_000 or quantity % 50:
        await message.answer("Нужно число от 50 до 10 000, кратное 50. Попробуйте ещё раз.")
        return
    await state.update_data(product="stars", quantity=quantity)
    await ask_target(message, state)


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
        await message.answer("Нужен username Telegram от 5 до 32 символов: @username")
        return
    await state.update_data(target=target.lstrip("@"))
    await state.set_state(OrderForm.waiting_payment)
    data = await state.get_data()
    product = str(data.get("product"))
    quantity = int(data.get("quantity", 0))
    if not settings.terms_url:
        await message.answer(
            "Перед приёмом оплаты настройте полное пользовательское соглашение и TERMS_URL в .env.",
            reply_markup=back_to_menu(),
        )
        return
    if not await db.has_accepted_terms(message.from_user.id):
        await message.answer(
            "Перед заказом прочитайте пользовательское соглашение. Для цифровых товаров в Telegram доступна оплата только Telegram Stars.",
            reply_markup=terms_consent(settings.terms_url),
        )
        return
    await show_payment_choice(message, settings, product, quantity, target.lstrip("@"))


async def show_payment_choice(
    message: Message, settings: Settings, product: str, quantity: int, target: str
) -> None:
    stars_price = settings.xtr_price(product, quantity)
    price_text = f"Цена: {stars_price} Telegram Stars." if stars_price > 0 else "Цена ещё не настроена."
    await message.answer(
        f"Заказ: {PRODUCT_NAMES.get(product, product)}, {quantity}"
        f"{' шт.' if product == 'stars' else ' мес.' if product == 'premium' else ' TON'}.\n"
        f"Получатель: @{target}\n{price_text}\n\nВыберите оплату:",
        reply_markup=payment_methods(),
    )


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
            await callback.message.answer(
                "Покупки временно закрыты: настройте и подтвердите подключение Fragment API перед приёмом оплат.",
                reply_markup=back_to_menu(),
            )
            await callback.answer()
            return
        data = await state.get_data()
        product, quantity = str(data.get("product", "")), int(data.get("quantity", 0))
        target = str(data.get("target", ""))
        price = settings.xtr_price(product, quantity)
        if price <= 0:
            await callback.message.answer("Цена в Telegram Stars ещё не настроена в .env.")
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
        await message.answer("Платёж получен, но заказ не найден. Напишите в поддержку.")
        return
    if payment.currency != "XTR" or payment.total_amount != int(Decimal(order.price)):
        await message.answer("Сумма платежа не совпала с заказом. Напишите в поддержку.")
        return
    await db.mark_paid(order.id, payment.telegram_payment_charge_id)
    order = await db.get_order(order.id)
    if not order:
        return
    result = await fulfill_paid_order(order=order, db=db, fragment=fragment)
    await message.answer(result, reply_markup=back_to_menu())


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
        await callback.message.answer("Оплата подтверждена, поддержка проверяет выдачу заказа.")
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
        await callback.message.answer("Не удалось получить статус. Попробуйте проверить ещё раз позже.")
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
    await callback.message.answer(result, reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "section:profile")
async def profile(callback: CallbackQuery, db: Database) -> None:
    user = callback.from_user
    await db.upsert_user(user.id, user.username, user.full_name)
    total, delivered, pending = await db.stats(user.id)
    recent = await db.recent_orders(user.id, 5)
    lines = [
        "👤 Ваш профиль",
        f"ID: {user.id}",
        f"Username: @{user.username}" if user.username else "Username: не задан",
        f"Заказов: {total} · выдано: {delivered} · в обработке: {pending}",
    ]
    if recent:
        lines.append("\nПоследние заказы:")
        for order in recent:
            lines.append(
                f"• {PRODUCT_NAMES.get(order.product, order.product)} × {order.quantity} — {order.status}"
            )
    else:
        lines.append("\nПока заказов нет.")
    await callback.message.answer("\n".join(lines), reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "section:payments")
async def payments_info(callback: CallbackQuery) -> None:
    parts = [
        ("Доступные способы оплаты:\n\n", None),
        ("🚀", CUSTOM_EMOJI["xrocket"]), (" xRocket\n", None),
        ("🤖", CUSTOM_EMOJI["cryptobot"]), (" CryptoBot\n", None),
        ("🏦", CUSTOM_EMOJI["payhot_sbp"]), (" PayHot · СБП\n", None),
        ("💳", CUSTOM_EMOJI["payhot_card"]), (" PayHot · карта\n", None),
        ("💎", CUSTOM_EMOJI["payhot_crypto"]), (" PayHot · криптовалюта\n", None),
        ("⭐ Telegram Stars\n\n", None),
        ("Для Stars и Premium внутри Telegram используется только Telegram Stars (XTR).\n\nCryptoBot, PayHot и xRocket можно подключать для физических товаров или продаж вне Telegram. ЕРИП в предоставленной PayHot API-спецификации не указан.", None),
    ]
    text, entities = rich_text(parts)
    await callback.message.answer(text, entities=entities, reply_markup=back_to_info())
    await callback.answer()


@router.callback_query(F.data == "section:info")
async def information(callback: CallbackQuery) -> None:
    await callback.message.answer("ℹ️ Информация:", reply_markup=information_menu())
    await callback.answer()


@router.callback_query(F.data == "section:projects")
async def projects(callback: CallbackQuery, settings: Settings) -> None:
    sentence = "Hardon — создаем лучшие IT-решения для вашего удобства и безопасности!"
    text, entities = rich_text([("✨ ", None), (sentence, None)])
    entities.append(
        MessageEntity(type="bold", offset=3, length=len(sentence.encode("utf-16-le")) // 2)
    )
    await callback.message.answer(
        text,
        entities=entities,
        reply_markup=external_link("🔗Hardon Project", settings.projects_url),
    )
    await callback.answer()


@router.message(Command("paysupport", "support"))
async def paysupport(message: Message, settings: Settings) -> None:
    text = "По вопросам оплаты и заказов обратитесь в поддержку."
    if settings.support_url:
        await message.answer(text, reply_markup=external_link("🛡 Открыть поддержку", settings.support_url))
    else:
        await message.answer(text + " Ссылка пока не настроена; добавьте SUPPORT_URL в .env.")


@router.message(Command("terms"))
async def terms_command(message: Message, settings: Settings) -> None:
    if settings.terms_url:
        await message.answer("Пользовательское соглашение:", reply_markup=external_link("📑 Открыть соглашение", settings.terms_url))
    else:
        await message.answer("Настройте полное пользовательское соглашение и TERMS_URL в .env.")


@router.callback_query(F.data.startswith("info:"))
async def info(callback: CallbackQuery, settings: Settings) -> None:
    section = callback.data.split(":", 1)[1]
    pages = {
        "instructions": (
            "📖 Инструкция",
            "1. Выберите товар и срок или количество.\n2. Введите username получателя.\n3. Выберите способ оплаты.\n4. После оплаты нажмите «Проверить оплату».\n\nВыдача начинается после подтверждения платежа.",
            settings.instructions_url,
        ),
        "rules": (
            "📑 Правила",
            "Перед оплатой внимательно проверяйте username получателя. Заказы обрабатываются после подтверждения платежа. Если возникла ошибка или задержка, обратитесь в поддержку и укажите номер заказа.",
            settings.rules_url,
        ),
        "privacy": (
            "ⓘ Политика конфиденциальности",
            "Для работы сервиса сохраняются ваш Telegram ID, username, сведения о заказе и идентификатор платежа. Платёжные секреты и данные банковских карт бот не запрашивает. Полный текст политики можно открыть по кнопке ниже.",
            settings.privacy_url,
        ),
        "terms": (
            "☑️ Пользовательское соглашение",
            "Создавая заказ, вы подтверждаете правильность данных получателя и выбранного товара. Условия оплаты, выдачи и возврата должны быть опубликованы в полном тексте соглашения.",
            settings.terms_url,
        ),
        "advertising": (
            "▣ Реклама",
            "Информация о рекламе и размещении доступна по кнопке ниже.",
            settings.advertising_url,
        ),
        "support": (
            "🛡 Поддержка",
            "Если с заказом возникла проблема, напишите в поддержку. Приложите номер заказа из сообщения об оплате.",
            settings.support_url,
        ),
    }
    title, body, url = pages.get(section, ("Раздел", "Материал не найден.", ""))
    return_callback = "home" if section == "support" else "section:info"
    if url:
        keyboard = external_link("🔗 Открыть", url, callback=return_callback)
    else:
        keyboard = back_to_menu() if section == "support" else back_to_info()
        if section in {"support", "advertising"}:
            body += "\n\nСсылка пока не настроена. Добавьте её в .env."
    await callback.message.answer(f"{title}\n\n{body}", reply_markup=keyboard)
    await callback.answer()


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Выберите действие в меню ниже.", reply_markup=main_menu())
