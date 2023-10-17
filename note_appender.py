import datetime
import os

import github
from github.ContentFile import ContentFile
from github.Repository import Repository


class NoteAppender(object):
    APPEND_FORMAT = "{prev}\n{new}"

    def __init__(self, remote_repo: Repository, file_path: str):
        self.remote_repo = remote_repo
        self.file_path = file_path

    def commit_and_push_elements(
        self,
        elements,
        commit_message: str = "Append data",
    ):
        branch_sha = self.remote_repo.get_branch(branch).commit.sha
        base_tree = self.remote_repo.get_git_tree(sha=branch_sha)
        tree = self.remote_repo.create_git_tree(elements, base_tree)
        parent = self.remote_repo.get_git_commit(sha=branch_sha)
        commit = self.remote_repo.create_git_commit(commit_message, tree, [parent])
        branch_refs = self.remote_repo.get_git_ref(f"heads/{branch}")
        branch_refs.edit(sha=commit.sha)

    def get_changes_element(self, content):
        """get changes element of file after append new content"""

        prev_content_file: ContentFile = remote_repo.get_contents(self.file_path)
        prev_content = prev_content_file.decoded_content
        prev_content = prev_content.decode("utf-8")

        formated_content = self.APPEND_FORMAT.format(prev=prev_content, new=content)
        blob = self.remote_repo.create_git_blob(formated_content, "utf-8")

        element = github.InputGitTreeElement(
            path=self.file_path, mode="100644", type="blob", sha=blob.sha
        )

        return element

    def append_data(self, content):
        element = self.get_changes_element(content)
        self.commit_and_push_elements([element])

    def __call__(self, content):
        self.append_data(content)


if __name__ == "__main__":
    repo_token = os.environ["INPUT_REPO_TOKEN"]
    branch = "main"
    repository = "blackgolyb/test-telenotes"

    gh = github.Github(repo_token)
    remote_repo = gh.get_repo(repository)

    appender = NoteAppender(remote_repo, "01.txt")
    appender(f"test in: {datetime.datetime.now()}")
