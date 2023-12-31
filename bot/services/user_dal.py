from sqlalchemy import select, update

from bot.db.models import User


class BaseDAL(object):
    def __init__(self, session):
        self.session = session


class UserDAL(BaseDAL):
    async def create_user(self, user_id: int, **kwargs) -> None:
        new_user = User(
            user_id=user_id,
            **kwargs,
        )
        self.session.add(new_user)
        await self.session.flush()

    async def get_user_by_id(self, user_id: int) -> User:
        query = select(User).where(User.user_id == user_id)
        res = await self.session.execute(query)
        user_row = res.fetchone()
        if user_row is not None:
            return user_row[0]

    async def update_user(self, user_id: int, **kwargs) -> None:
        query = (
            update(User)
            .where(User.user_id == user_id)
            .values(kwargs)
            .returning(User.user_id)
        )
        await self.db_session.execute(query)
