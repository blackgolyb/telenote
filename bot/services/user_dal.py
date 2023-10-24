from sqlalchemy import select

from bot.db.models import User


class BaseDAL(object):
    def __init__(self, session):
        self.session = session


class UserDAL(BaseDAL):
    async def create_user(
        self,
        user_id: int,
        github_token: str,
        note_path: str,
        notes_repository: str,
        notes_branch: str,
    ):
        await self.session.merge(
            User(
                user_id=user_id,
                github_token=github_token,
                note_path=note_path,
                notes_repository=notes_repository,
                notes_branch=notes_branch,
            )
        )
        await self.session.commit()

    async def get_user_by_id(self, user_id: int) -> User:
        query = select(User).where(User.user_id == user_id)
        res = await self.session.execute(query)
        user_row = res.fetchone()
        if user_row is not None:
            return user_row[0]
