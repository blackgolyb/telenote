import asyncio
from io import BytesIO
import logging
from pathlib import Path
import sys

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types.callback_query import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType,
)
import github

from bot.middlewares import DbSessionMiddleware
from bot.services.user_dal import UserDAL
from bot.services.note_appender import NoteUser
from bot.config import config
from bot.services.utils import batch

form_router = Router()


class RegisterForm(StatesGroup):
    register_start = State()
    github_username = State()
    github_token = State()
    note_path = State()
    current_note_path = State()
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


# @form_router.message()
async def receive_first_message(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    if user is not None:
        await state.set_state(RegisterForm.register_end)
        await message.answer(
            f"Hi, {html.quote(message.from_user.full_name)}!\nThe message has been sent",
            reply_markup=ReplyKeyboardRemove(),
        )
        note_user = NoteUser(user)
        await note_user.append_note(message.text)
        return

    await state.set_state(RegisterForm.register_start)
    await message.answer(
        f"Nice to meet you, {html.quote(message.from_user.full_name)}!\nLet's get started with registration before sending notes",
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
    await state.set_state(RegisterForm.github_token)
    await message.answer(
        # "What is your github username?",
        # reply_markup=ReplyKeyboardRemove(),
        "Please enter your github token for notes reposytory?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.github_username)
async def process_github_username(message: Message, state: FSMContext) -> None:
    try:
        github_username = message.text
        g = github.Github(github_username)
    except github.GithubException:
        await message.answer(
            "Github username is incorrect. Try again.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    repos_names = [repo.name for repo in g.get_user().get_repos()]
    repos_names_keyboard = [KeyboardButton(text=name) for name in repos_names]

    await state.update_data(github_username=github_username)
    await state.set_state(RegisterForm.notes_repository)

    await message.answer(
        "What is your notes repository?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                repos_names_keyboard,
            ],
            resize_keyboard=True,
        ),
    )


@form_router.message(RegisterForm.github_token)
async def process_github_token(message: Message, state: FSMContext) -> None:
    github_token = message.text

    try:
        g = github.Github(github_token)
    except github.GithubException:
        await message.answer(
            "Github token is incorrect. Try again.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    github_username = g.get_user().login
    repos_names = [repo.name for repo in g.get_user().get_repos()]
    repos_names_keyboard = [KeyboardButton(text=name) for name in repos_names]

    keyboard = batch(repos_names_keyboard, 3)

    # await message.bot.delete_message(message.chat.id, message.message_id)
    await state.update_data(github_username=github_username)
    await state.update_data(github_token=github_token)
    await state.set_state(RegisterForm.notes_repository)

    await message.answer("Your token has been deleted for security reasons")
    await message.answer(
        f"Your github username is {html.quote(github_username)}.\nWhat is your notes repository?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
        ),
    )


@form_router.message(RegisterForm.notes_repository)
async def process_notes_repository(message: Message, state: FSMContext) -> None:
    register_data = await state.get_data()
    github_token = register_data.get("github_token")
    g = github.Github(github_token)

    repository = message.text
    github_username = g.get_user().login
    repository_fullname = f"{github_username}/{repository}"

    repo = g.get_repo(repository_fullname)
    all_branches = [branch.name for branch in repo.get_branches()]
    branches_keyboard = [KeyboardButton(text=branch) for branch in all_branches]
    keyboard = batch(branches_keyboard, 3)

    await state.update_data(notes_repository=repository)
    await state.set_state(RegisterForm.notes_branch)
    await message.answer(
        "What is your notes branch?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
        ),
    )


class GithubFileSelection(object):
    def __init__(self, token, repository, branch) -> None:
        self.repository = repository
        self.branch = branch
        self.github = github.Github(token)
        self.username = self.github.get_user().login

    def __init_subclass__(cls, **kwargs) -> None:
        if "prefix" not in kwargs:
            raise ValueError(
                f"We also recommend to use short prefix name\n"
                f"prefix required, usage example: "
                f"`class {cls.__name__}(GithubFileSelection, prefix='my_file_selection'): ...`"
            )
        prefix = kwargs.pop("prefix")
        cls.__prefix__ = prefix
        GithubFileSelection._init_callbacks(cls, prefix)
        super().__init_subclass__(**kwargs)

    @classmethod
    def _init_callbacks(cls, sub_cls, prefix):
        class BackNavigationCallback(CallbackData, prefix=f"{prefix}_nb"):
            path: str

        class SelectNavigationCallback(CallbackData, prefix=f"{prefix}_ns"):
            path: str

        class NavigationCallback(CallbackData, prefix=f"{prefix}_n"):
            path: str

        sub_cls.BackNavigationCallback = BackNavigationCallback
        sub_cls.SelectNavigationCallback = SelectNavigationCallback
        sub_cls.NavigationCallback = NavigationCallback

    @property
    def full_repository(self):
        return f"{self.username}/{self.repository}"

    @property
    def remote_repository(self):
        return self.github.get_repo(self.full_repository)

    @staticmethod
    def get_parent_path(path):
        path = Path(path)
        parent = str(path.parent)
        return parent if parent != "." else "/"

    async def get_contents_by_path(self, file_path="/"):
        return self.remote_repository.get_contents(file_path, ref=self.branch)

    async def get_selection_keyboard(self, file_path="/"):
        file_contents = await self.get_contents_by_path(file_path)
        result = {}

        if not isinstance(file_contents, list) and file_contents.type == "dir":
            file_contents = [file_contents]

        if isinstance(file_contents, list):
            if file_path == "/":
                options_keyboards = []
            else:
                print(file_path, self.get_parent_path(file_path))
                options_keyboards = [
                    [
                        InlineKeyboardButton(
                            text="<- Back",
                            callback_data=self.BackNavigationCallback(
                                path=self.get_parent_path(file_path)
                            ).pack(),
                        ),
                    ]
                ]

            dirs_contents = list(
                filter(lambda content: content.type == "dir", file_contents)
            )
            files_contents = list(
                filter(lambda content: content.type == "file", file_contents)
            )

            def create_dirs_btn(content):
                return InlineKeyboardButton(
                    text=f"📁  {content.name}",
                    callback_data=self.NavigationCallback(path=content.path).pack(),
                )

            def create_file_btn(content):
                return InlineKeyboardButton(
                    text=f"🗎  {content.name}",
                    callback_data=self.NavigationCallback(path=content.path).pack(),
                )

            dirs_contents_keyboards = [
                create_dirs_btn(content) for content in dirs_contents
            ]
            files_contents_keyboards = [
                create_file_btn(content) for content in files_contents
            ]

            files_keyboards = [*dirs_contents_keyboards, *files_contents_keyboards]
            files_keyboards = batch(files_keyboards, 3)

            keyboard = [
                *files_keyboards,
                *options_keyboards,
            ]

            result["text"] = "Choose directory or file."
            result["keyboard"] = InlineKeyboardMarkup(
                inline_keyboard=keyboard,
            )
        else:
            keyboard = [
                [
                    InlineKeyboardButton(
                        text="<- Back",
                        callback_data=self.BackNavigationCallback(
                            path=self.get_parent_path(file_path)
                        ).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Select",
                        callback_data=self.SelectNavigationCallback(
                            path=file_path
                        ).pack(),
                    ),
                ],
            ]
            result["text"] = f"Do you want to choose this file: {file_path}"
            result["keyboard"] = InlineKeyboardMarkup(
                inline_keyboard=keyboard,
            )

        return result


class NoteFileSelector(GithubFileSelection, prefix="nfs"):
    ...


@form_router.message(RegisterForm.notes_branch)
async def process_notes_branch(message: Message, state: FSMContext) -> None:
    branch = message.text
    await state.update_data(notes_branch=branch)
    await state.set_state(RegisterForm.note_path)

    register_data = await state.get_data()
    selector = NoteFileSelector(
        token=register_data.get("github_token"),
        repository=register_data.get("notes_repository"),
        branch=branch,
    )
    answer_data = await selector.get_selection_keyboard()

    await message.answer(
        "And finally, in which file would you like to store your notes?",
        reply_markup=ReplyKeyboardRemove(),
    )

    await message.answer(
        answer_data["text"],
        reply_markup=answer_data["keyboard"],
    )


@form_router.callback_query(NoteFileSelector.NavigationCallback.filter())
async def process_note_path(
    query: CallbackQuery,
    callback_data: NoteFileSelector.NavigationCallback,
    state: FSMContext,
) -> None:
    register_data = await state.get_data()
    selector = NoteFileSelector(
        token=register_data.get("github_token"),
        repository=register_data.get("notes_repository"),
        branch=register_data.get("notes_branch"),
    )
    answer_data = await selector.get_selection_keyboard(callback_data.path)

    await query.message.edit_text(
        answer_data["text"], reply_markup=answer_data["keyboard"]
    )


@form_router.callback_query(NoteFileSelector.BackNavigationCallback.filter())
async def process_note_path_back(
    query: CallbackQuery,
    callback_data: NoteFileSelector.BackNavigationCallback,
    state: FSMContext,
) -> None:
    register_data = await state.get_data()
    selector = NoteFileSelector(
        token=register_data.get("github_token"),
        repository=register_data.get("notes_repository"),
        branch=register_data.get("notes_branch"),
    )
    answer_data = await selector.get_selection_keyboard(callback_data.path)

    await query.message.edit_text(
        answer_data["text"], reply_markup=answer_data["keyboard"]
    )


@form_router.callback_query(NoteFileSelector.SelectNavigationCallback.filter())
async def process_note_path_select(
    query: CallbackQuery,
    callback_data: NoteFileSelector.SelectNavigationCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(note_path=callback_data.path)
    await state.set_state(RegisterForm.register_end)

    register_data = await state.get_data()

    dal = UserDAL(session)
    await dal.create_user(
        user_id=query.from_user.id,
        github_token=register_data.get("github_token"),
        notes_branch=register_data.get("notes_branch"),
        notes_repository=register_data.get("notes_repository"),
        note_path=register_data.get("note_path"),
    )

    await query.answer(
        "Ok all finished!",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(RegisterForm.register_end, F.text)
async def add_note(message: Message, state: FSMContext, session: AsyncSession) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    note_user = NoteUser.create_from_orm(user)
    await note_user.append_note(message.text)


@form_router.message(RegisterForm.register_end, F.photo)
async def upload_photo(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    note_user = NoteUser.create_from_orm(user)

    photo = await message.bot.get_file(message.photo[-1].file_id)
    photo_b = await message.bot.download_file(photo.file_path)
    # photo.

    # photo_b = BytesIO()
    # photo_b.write(photo.getvalue())
    # photo_b.seek(0)

    await note_user.upload_photo(photo_b)


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
