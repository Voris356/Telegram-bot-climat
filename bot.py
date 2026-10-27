"""Telegram-бот для заявок и ответов по услугам кондиционеров."""

import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

from service_content import FAQ, SERVICES, build_welcome


load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("climate_bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
COMPANY_NAME = os.getenv("BUSINESS_NAME", "Сервис кондиционеров").strip()
SERVICE_CITY = os.getenv("SERVICE_CITY", "").strip()
SERVICE_PHONE = os.getenv("SERVICE_PHONE", "").strip()


def parse_admin_chat_id(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError("ADMIN_CHAT_ID должен быть целым числом.") from exc


ADMIN_CHAT_ID = parse_admin_chat_id(os.getenv("ADMIN_CHAT_ID", ""))
router = Router()


class RequestForm(StatesGroup):
    consent = State()
    name = State()
    phone = State()
    address = State()
    details = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Установка", callback_data="service:installation"
                ),
                InlineKeyboardButton(text="Ремонт", callback_data="service:repair"),
            ],
            [
                InlineKeyboardButton(
                    text="Заправка фреоном", callback_data="service:freon"
                ),
                InlineKeyboardButton(
                    text="Профилактика", callback_data="service:maintenance"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Как выбрать кондиционер?", callback_data="faq:choose"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Не охлаждает", callback_data="faq:not_cooling"
                ),
                InlineKeyboardButton(text="О фреоне", callback_data="faq:freon"),
            ],
            [
                InlineKeyboardButton(text="Цены", callback_data="faq:price"),
                InlineKeyboardButton(
                    text="Оставить заявку", callback_data="request:consultation"
                ),
            ],
        ]
    )


def service_actions(service_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оставить заявку",
                    callback_data=f"request:{service_key}",
                )
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="main")],
        ]
    )


def faq_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Задать вопрос мастеру",
                    callback_data="request:consultation",
                )
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="main")],
        ]
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Согласен, продолжить", callback_data="privacy:accept"
                ),
                InlineKeyboardButton(
                    text="Отмена", callback_data="privacy:decline"
                ),
            ]
        ]
    )


def skip_keyboard(field_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить", callback_data=f"skip:{field_name}"
                )
            ]
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Отправить номер телефона",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def valid_phone(value: str) -> bool:
    value = value.strip()
    if not re.fullmatch(r"\+?[\d\s().-]{7,24}", value):
        return False
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 15


def single_line(value: str) -> str:
    """Убрать управляющие переводы строк из полей заявки."""
    return " ".join(value.split())


async def show_main_menu(message: Message, state: FSMContext | None = None) -> None:
    if state is not None:
        await state.clear()
    await message.answer(
        build_welcome(COMPANY_NAME, SERVICE_CITY, SERVICE_PHONE),
        reply_markup=main_menu(),
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Выберите услугу или вопрос в меню. Чтобы прервать заполнение заявки, "
        "отправьте /cancel.",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Заполнение заявки отменено. Ваши данные не отправлены.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Можно выбрать другую услугу:", reply_markup=main_menu())


@router.message(Command("id"))
async def chat_id_handler(message: Message) -> None:
    await message.answer(
        f"ID этого чата: {message.chat.id}\n"
        "Владелец бота может указать этот ID в настройке ADMIN_CHAT_ID, "
        "чтобы получать заявки."
    )


@router.callback_query(F.data == "main")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer(
            build_welcome(COMPANY_NAME, SERVICE_CITY, SERVICE_PHONE),
            reply_markup=main_menu(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("service:"))
async def service_handler(callback: CallbackQuery) -> None:
    service_key = callback.data.split(":", maxsplit=1)[1]
    service = SERVICES.get(service_key)
    if not service:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    if callback.message:
        await callback.message.answer(
            f"{service.title}\n\n{service.description}",
            reply_markup=service_actions(service_key),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("faq:"))
async def faq_handler(callback: CallbackQuery) -> None:
    faq_key = callback.data.split(":", maxsplit=1)[1]
    answer = FAQ.get(faq_key)
    if not answer:
        await callback.answer("Ответ не найден.", show_alert=True)
        return
    if callback.message:
        await callback.message.answer(answer, reply_markup=faq_actions())
    await callback.answer()


async def begin_request(
    callback: CallbackQuery, state: FSMContext, service_key: str
) -> None:
    if service_key not in SERVICES:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    if ADMIN_CHAT_ID is None:
        if callback.message:
            await callback.message.answer(
                "Приём заявок пока не подключён. Пожалуйста, попробуйте позже."
            )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(
        service_key=service_key,
        customer_user_id=callback.from_user.id,
        customer_username=callback.from_user.username or "",
    )
    await state.set_state(RequestForm.consent)
    if callback.message:
        await callback.message.answer(
            "Для заявки бот попросит имя, телефон и адрес. "
            "После вашего согласия данные будут отправлены владельцу бота "
            "только для ответа по этой заявке. Бот не сохраняет заявки в своей "
            "базе данных.\n\nПродолжить?",
            reply_markup=consent_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("request:"))
async def request_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    service_key = callback.data.split(":", maxsplit=1)[1]
    await begin_request(callback, state, service_key)


@router.callback_query(F.data == "privacy:accept")
async def consent_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != RequestForm.consent.state:
        await callback.answer("Начните заявку из меню.", show_alert=True)
        return
    await state.set_state(RequestForm.name)
    if callback.message:
        await callback.message.answer("Как к вам обращаться?")
    await callback.answer()


@router.callback_query(F.data == "privacy:decline")
async def decline_consent_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer(
            "Понял, заявку не создаю. Ваши данные не отправлены.",
            reply_markup=main_menu(),
        )
    await callback.answer()


@router.message(RequestForm.name)
async def name_handler(message: Message, state: FSMContext) -> None:
    name = single_line(message.text or "")
    if not 2 <= len(name) <= 100:
        await message.answer("Введите имя длиной от 2 до 100 символов.")
        return
    await state.update_data(customer_name=name)
    await state.set_state(RequestForm.phone)
    await message.answer(
        "Отправьте номер телефона кнопкой или напишите его сообщением.",
        reply_markup=phone_keyboard(),
    )


@router.message(RequestForm.phone)
async def phone_handler(message: Message, state: FSMContext) -> None:
    if message.contact:
        if (
            message.contact.user_id is not None
            and message.contact.user_id != message.from_user.id
        ):
            await message.answer(
                "Пожалуйста, отправьте свой номер или напишите его вручную."
            )
            return
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    if not valid_phone(phone):
        await message.answer(
            "Не удалось распознать номер. Отправьте его в международном формате "
            "или нажмите кнопку ниже.",
            reply_markup=phone_keyboard(),
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(RequestForm.address)
    await message.answer(
        "Укажите адрес или район, где находится кондиционер. "
        "Точный адрес можно пропустить.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Если пока не хотите указывать адрес:", reply_markup=skip_keyboard("address"))


@router.message(RequestForm.address)
async def address_handler(message: Message, state: FSMContext) -> None:
    address = single_line(message.text or "")
    if not address:
        await message.answer("Напишите адрес/район или нажмите «Пропустить».")
        return
    if len(address) > 300:
        await message.answer("Сократите адрес до 300 символов.")
        return
    await state.update_data(address=address)
    await ask_details(message, state)


async def ask_details(message: Message, state: FSMContext) -> None:
    await state.set_state(RequestForm.details)
    await message.answer(
        "Коротко опишите задачу или симптомы. Можно пропустить.",
        reply_markup=skip_keyboard("details"),
    )


@router.callback_query(F.data == "skip:address")
async def skip_address_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if await state.get_state() != RequestForm.address.state:
        await callback.answer()
        return
    if callback.message:
        await ask_details(callback.message, state)
    await callback.answer()


async def submit_request(
    message: Message, state: FSMContext, bot: Bot, details: str
) -> None:
    data = await state.get_data()
    service = SERVICES.get(data.get("service_key", "consultation"))
    if ADMIN_CHAT_ID is None or service is None:
        await state.clear()
        await message.answer(
            "Не удалось передать заявку. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    user = message.from_user
    customer_username = data.get("customer_username", "")
    username = f"@{customer_username}" if customer_username else "не указан"
    customer_user_id = data.get("customer_user_id")
    if customer_user_id is None:
        customer_user_id = user.id if user else message.chat.id
    lines = [
        "Новая заявка из Telegram-бота",
        f"Услуга: {service.title}",
        f"Имя: {single_line(data.get('customer_name', ''))}",
        f"Телефон: {single_line(data.get('phone', ''))}",
        f"Адрес/район: {single_line(data.get('address') or 'не указан')}",
        f"Описание: {single_line(details or 'не указано')}",
        f"Telegram: {single_line(username)}",
        f"Chat ID клиента: {customer_user_id}",
    ]

    try:
        await bot.send_message(ADMIN_CHAT_ID, "\n".join(lines))
    except TelegramAPIError:
        logger.exception("Не удалось передать заявку в чат владельца")
        await state.clear()
        await message.answer(
            "Не удалось доставить заявку владельцу бота. "
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    await message.answer(
        "Заявка передана владельцу бота. Он свяжется с вами по указанному номеру.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Чем ещё помочь?", reply_markup=main_menu())


@router.message(RequestForm.details)
async def details_handler(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    details = (message.text or "").strip()
    if len(details) > 1000:
        await message.answer("Сократите описание до 1000 символов.")
        return
    await submit_request(message, state, bot, details)


@router.callback_query(F.data.startswith("skip:"))
async def skip_handler(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    if callback.data != "skip:details":
        await callback.answer()
        return
    if await state.get_state() != RequestForm.details.state:
        await callback.answer()
        return
    if callback.message:
        await submit_request(callback.message, state, bot, "")
    await callback.answer()


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.answer(
        "Я помогу с установкой, ремонтом, заправкой и профилактикой кондиционеров. "
        "Выберите услугу или вопрос в меню.",
        reply_markup=main_menu(),
    )


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан TELEGRAM_BOT_TOKEN. Добавьте токен бота в секреты окружения."
        )

    bot = Bot(token=BOT_TOKEN)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    try:
        me = await bot.get_me()
        logger.info("Бот запущен: @%s", me.username or "без username")
        if ADMIN_CHAT_ID is None:
            logger.warning(
                "ADMIN_CHAT_ID не задан: ответы доступны, приём заявок выключен."
            )
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (RuntimeError, TelegramAPIError) as error:
        logger.error("%s", error)
        raise SystemExit(1) from error
