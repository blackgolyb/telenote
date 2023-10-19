import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.middlewares import DbSessionMiddleware
from bot.services.user_dal import UserDAL
from bot.services.note_appender import NoteUser
from bot.config import config

form_router = Router()


class RegisterForm(StatesGroup):
    register_start = State()
    github_username = State()
    github_token = State()
    note_path = State()
    notes_repository = State()
    notes_branch = State()
    register_end = State()


@form_router.message(CommandStart())
async def command_start(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    if user is not None:
        await state.set_state(RegisterForm.register_end)
        await message.answer(
            f"Hi {html.quote(message.from_user.full_name)}!\nYou are already registered",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.set_state(RegisterForm.register_start)
    await message.answer(
        f"Nice to meet you, {html.quote(message.from_user.full_name)}!\nLet's get started with registration",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="Register"),
                ]
            ],
            resize_keyboard=True,
        ),
    )


@form_router.message(Command("cancel"))
@form_router.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await message.answer(
        "Cancelled.",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.register_start)
async def process_register_start(message: Message, state: FSMContext) -> None:
    await state.set_state(RegisterForm.github_username)
    await message.answer(
        "What is your github username?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.github_username)
async def process_github_username(message: Message, state: FSMContext) -> None:
    await state.update_data(github_username=message.text)
    await state.set_state(RegisterForm.notes_repository)
    await message.answer(
        "What is your notes repository?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.notes_repository)
async def process_notes_repository(message: Message, state: FSMContext) -> None:
    await state.update_data(notes_repository=message.text)
    await state.set_state(RegisterForm.github_token)
    await message.answer(
        "Please enter your github token for notes reposytory?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.github_token)
async def process_github_token(message: Message, state: FSMContext) -> None:
    await state.update_data(github_token=message.text)
    await state.set_state(RegisterForm.notes_branch)
    await message.answer(
        "What is your notes branch?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="main"),
                ]
            ],
            resize_keyboard=True,
        ),
    )


@form_router.message(RegisterForm.notes_branch)
async def process_notes_branch(message: Message, state: FSMContext) -> None:
    await state.update_data(notes_branch=message.text)
    await state.set_state(RegisterForm.note_path)
    await message.answer(
        "And finally, in which file would you like to store your notes?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.note_path)
async def process_note_path(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.update_data(note_path=message.text)
    await state.set_state(RegisterForm.register_end)

    register_data = await state.get_data()
    dal = UserDAL(session)
    await dal.create_user(
        user_id=message.from_user.id,
        github_token=register_data.get("github_token"),
        github_username=register_data.get("github_username"),
        notes_branch=register_data.get("notes_branch"),
        notes_repository=register_data.get("notes_repository"),
        note_path=register_data.get("note_path"),
    )

    await message.answer(
        "Ok all finished!",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.register_end)
async def process_register_end(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    note_user = NoteUser(user)
    await note_user.append_note(message.text)


async def main():
    print(config.db.db_url)
    engine = create_async_engine(url=config.db.db_url, echo=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(token=config.bot.token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker))
    # Automatically reply to all callbacks
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    dp.include_router(form_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
