import asyncio
import logging
import os
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
)
import github

# import whisper

from bot.middlewares import DbSessionMiddleware
from bot.db.user_dal import UserDAL
from bot.services.note_appender import NoteUser
from bot.config import config
from bot.services.utils import batch

# model_size = "base"
# whisper_model = whisper.load_model(model_size)
form_router = Router()


class RegisterForm(StatesGroup):
    register_start = State(state=False)
    github_username = State()
    github_token = State()
    note_file = State()
    current_note_file = State()
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

    await state.update_data(register_start=True)
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
        github_user = g.get_user()
        github_username = github_user.login
    except github.GithubException:
        await message.answer(
            "Github token is incorrect. Try again.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    repos_names = [repo.name for repo in github_user.get_repos()]
    repos_names_keyboard = [KeyboardButton(text=name) for name in repos_names]

    keyboard = batch(repos_names_keyboard, 3)

    await message.bot.delete_message(message.chat.id, message.message_id)
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


class GithubFileSelector(object):
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
                f"`class {cls.__name__}(GithubFileSelector, prefix='my_file_selector'): ...`"
            )
        prefix = kwargs.pop("prefix")
        cls.__prefix__ = prefix
        GithubFileSelector._init_callbacks(cls, prefix)
        super().__init_subclass__(**kwargs)

    @classmethod
    def _init_callbacks(cls, sub_cls, prefix):
        class SelectNavigationCallback(CallbackData, prefix=f"{prefix}_s"):
            path: str

        class NavigationCallback(CallbackData, prefix=f"{prefix}_n"):
            path: str

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
                options_keyboards = [
                    [
                        InlineKeyboardButton(
                            text="<- Back",
                            callback_data=self.NavigationCallback(
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

            result["text"] = (
                "Choose directory or file.\n" f"Current directory: {file_path}"
            )
            result["keyboard"] = InlineKeyboardMarkup(
                inline_keyboard=keyboard,
            )
        else:
            keyboard = [
                [
                    InlineKeyboardButton(
                        text="<- Back",
                        callback_data=self.NavigationCallback(
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


class NoteFileSelector(GithubFileSelector, prefix="nfs"):
    ...


class GithubFolderSelection(object):
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
                f"`class {cls.__name__}(GithubFolderSelection, prefix='my_folder_selector'): ...`"
            )
        prefix = kwargs.pop("prefix")
        cls.__prefix__ = prefix
        GithubFolderSelection._init_callbacks(cls, prefix)
        super().__init_subclass__(**kwargs)

    @classmethod
    def _init_callbacks(cls, sub_cls, prefix):
        class SelectNavigationCallback(CallbackData, prefix=f"{prefix}_s"):
            path: str

        class NavigationCallback(CallbackData, prefix=f"{prefix}_n"):
            path: str

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

        if not isinstance(file_contents, list):
            raise ValueError("file_contents can not be file")

        if file_path == "/":
            options_keyboards = [
                [
                    InlineKeyboardButton(
                        text="Select",
                        callback_data=self.SelectNavigationCallback(
                            path=file_path
                        ).pack(),
                    ),
                ]
            ]
        else:
            options_keyboards = [
                [
                    InlineKeyboardButton(
                        text="<- Back",
                        callback_data=self.NavigationCallback(
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

        dirs_contents = list(
            filter(lambda content: content.type == "dir", file_contents)
        )

        def create_dirs_btn(content):
            return InlineKeyboardButton(
                text=f"📁  {content.name}",
                callback_data=self.NavigationCallback(path=content.path).pack(),
            )

        files_keyboards = [create_dirs_btn(content) for content in dirs_contents]
        files_keyboards = batch(files_keyboards, 3)

        keyboard = [
            *files_keyboards,
            *options_keyboards,
        ]

        result["text"] = f"Choose directory.\nCurrent directory: {file_path}"
        result["keyboard"] = InlineKeyboardMarkup(
            inline_keyboard=keyboard,
        )
        ...

        return result


class AssentFolderSelector(GithubFolderSelection, prefix="afs"):
    ...


@form_router.message(RegisterForm.notes_branch)
async def process_notes_branch(message: Message, state: FSMContext) -> None:
    branch = message.text
    await state.update_data(notes_branch=branch)
    await state.set_state(RegisterForm.note_file)

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
async def process_note_file_navigate(
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


@form_router.callback_query(NoteFileSelector.SelectNavigationCallback.filter())
async def process_note_file_select(
    query: CallbackQuery,
    callback_data: NoteFileSelector.SelectNavigationCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(note_file=callback_data.path)
    await state.set_state(RegisterForm.register_end)

    register_data = await state.get_data()

    dal = UserDAL(session)
    await dal.create_user(
        user_id=query.from_user.id,
        github_token=register_data.get("github_token"),
        notes_branch=register_data.get("notes_branch"),
        notes_repository=register_data.get("notes_repository"),
        note_file=register_data.get("note_file"),
        assets_folder="/",
        is_registered=False,
    )

    # user = await dal.get_user_by_id(query.from_user.id)
    # print(user.github_token)

    await query.message.answer(
        "Ok all finished!",
        reply_markup=ReplyKeyboardRemove(),
    )


async def navigate_assets_folder(user_id: int, path: str, session: AsyncSession):
    dal = UserDAL(session)
    user = await dal.get_user_by_id(user_id)
    selector = AssentFolderSelector(
        token=user.github_token,
        repository=user.notes_repository,
        branch=user.notes_branch,
    )
    return await selector.get_selection_keyboard(path)


@form_router.message(Command("set_assets_folder"))
async def set_assets_folder(message: Message, session: AsyncSession) -> None:
    answer_data = await navigate_assets_folder(message.from_user.id, "/", session)

    await message.answer(
        "In which folder would you like to store your assets?",
        reply_markup=ReplyKeyboardRemove(),
    )

    await message.answer(
        answer_data["text"],
        reply_markup=answer_data["keyboard"],
    )


@form_router.callback_query(AssentFolderSelector.NavigationCallback.filter())
async def navigate_assets_folder_handler(
    query: CallbackQuery,
    callback_data: AssentFolderSelector.NavigationCallback,
    session: AsyncSession,
) -> None:
    answer_data = await navigate_assets_folder(
        query.from_user.id, callback_data.path, session
    )

    await query.message.edit_text(
        answer_data["text"], reply_markup=answer_data["keyboard"]
    )


@form_router.callback_query(AssentFolderSelector.SelectNavigationCallback.filter())
async def select_assets_folder(
    query: CallbackQuery,
    callback_data: AssentFolderSelector.SelectNavigationCallback,
    session: AsyncSession,
) -> None:
    dal = UserDAL(session)
    # User = await dal.get_user_by_id(query.from_user.id)
    # await User.update_data(assets_folder=callback_data.path)

    await query.message.answer(
        callback_data.path,
        reply_markup=ReplyKeyboardRemove(),
    )


class RegistrationVerifier(object):
    def __init__(self, registration_verified_filter):
        self.registration_verified_filter = registration_verified_filter

    def __call__(self, observer, *filters, **kwargs):
        def decorator(func):
            func_observer = observer(
                self.registration_verified_filter, *filters, **kwargs
            )
            func_observer(func)

            @observer(*filters, **kwargs)
            async def wrap(
                message: Message,
                state: FSMContext,
                session: AsyncSession,
            ) -> None:
                dal = UserDAL(session)
                user = await dal.get_user_by_id(message.from_user.id)
                if user is None:
                    await message.answer("Please register first.")
                    return

                await state.set_state(RegisterForm.register_end)
                await func(message=message, session=session, state=state)

            return wrap

        return decorator


verify_register = RegistrationVerifier(RegisterForm.register_end)


@verify_register(form_router.message, F.text)
async def add_note(message: Message, session: AsyncSession, **kwargs) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    note_user = NoteUser.create_from_orm(user)
    await note_user.append_note(message.text)


@verify_register(form_router.message, F.photo)
async def upload_photo(message: Message, session: AsyncSession, **kwargs) -> None:
    dal = UserDAL(session)
    user = await dal.get_user_by_id(message.from_user.id)
    note_user = NoteUser.create_from_orm(user)

    for message_photo in message.photo:
        photo = await message.bot.get_file(message_photo[-1].file_id)
        photo_b = await message.bot.download_file(photo.file_path)

        await note_user.upload_photo(photo_b)


# @verify_register(form_router.message, F.voice)
# async def add_note_from_voice(
#     message: Message, session: AsyncSession, **kwargs
# ) -> None:
#     dal = UserDAL(session)
#     user = await dal.get_user_by_id(message.from_user.id)
#     note_user = NoteUser.create_from_orm(user)

#     fname = f"{message.from_user.id}_{message.message_id}.mp3"
#     voice = await message.bot.get_file(message.voice.file_id)
#     await message.bot.download_file(voice.file_path, fname)

#     result = whisper_model.transcribe(fname)
#     os.remove(fname)

#     await note_user.append_note(result["text"])


async def main():
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
