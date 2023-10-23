from io import BytesIO
from pathlib import Path
from datetime import datetime
import github
from github.ContentFile import ContentFile
from github.Repository import Repository

from bot.db.models import User


class NoteUser(object):
    def __init__(self, github_token, notes_repository, notes_branch, note_path=None):
        self.github_repo = notes_repository
        self.note_path = note_path
        self.branch = notes_branch
        self.github = github.Github(github_token)
        self.github_username = self.github.get_user().login

    @classmethod
    def create_from_orm(cls, user: User):
        return cls(
            github_token=user.github_token,
            notes_repository=user.notes_repository,
            notes_branch=user.notes_branch,
            note_path=user.note_path,
        )

    @property
    def repository(self):
        return f"{self.github_username}/{self.github_repo}"

    @property
    def remote_repo(self):
        return self.github.get_repo(self.repository)

    async def append_note(self, note_content):
        adder = NoteAdder(self.remote_repo, self.note_path, self.branch)
        await adder(note_content)

    async def upload_photo(self, photo: BytesIO, assets_folder=""):
        time_now = datetime.now()
        formatted_time = time_now.strftime("%H_%M_%S")
        photo_name = f"from_telegram_{formatted_time}.jpg"
        photo_path = str(Path(assets_folder) / photo_name)

        created_file = self.remote_repo.create_file(
            path=photo_path,
            message=f"Upload photo from telegram: {formatted_time}",
            content=photo.read(),
            branch=self.branch,
        )

        branch_refs = self.remote_repo.get_git_ref(f"heads/{self.branch}")
        branch_refs.edit(sha=created_file["commit"].sha)

    async def get_contents_by_path(self, file_path=""):
        return self.remote_repo.get_contents(file_path, ref=self.branch)


class NoteAdder(object):
    APPEND_FORMAT = "{prev}\n{new}"

    def __init__(self, remote_repo: Repository, file_path: str, branch: str):
        self.remote_repo = remote_repo
        self.file_path = file_path
        self.branch = branch

    def commit_and_push_elements(
        self,
        elements,
        commit_message: str = "Append data",
    ):
        branch_sha = self.remote_repo.get_branch(self.branch).commit.sha
        base_tree = self.remote_repo.get_git_tree(sha=branch_sha)
        tree = self.remote_repo.create_git_tree(elements, base_tree)
        parent = self.remote_repo.get_git_commit(sha=branch_sha)
        commit = self.remote_repo.create_git_commit(commit_message, tree, [parent])
        branch_refs = self.remote_repo.get_git_ref(f"heads/{self.branch}")
        branch_refs.edit(sha=commit.sha)

    def get_changes_element(self, content):
        """get changes element of file after append new content"""

        prev_content_file: ContentFile = self.remote_repo.get_contents(
            self.file_path, ref=self.branch
        )
        prev_content = prev_content_file.decoded_content
        prev_content = prev_content.decode("utf-8")

        formatted_content = self.APPEND_FORMAT.format(prev=prev_content, new=content)
        blob = self.remote_repo.create_git_blob(formatted_content, "utf-8")

        element = github.InputGitTreeElement(
            path=self.file_path, mode="100644", type="blob", sha=blob.sha
        )

        return element

    async def append_data(self, content):
        element = self.get_changes_element(content)
        self.commit_and_push_elements([element])

    async def __call__(self, content):
        await self.append_data(content)
