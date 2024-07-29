from sqlalchemy import BigInteger, Boolean, Column, String
from sqlalchemy_utils import EncryptedType

from bot.config import get_secret_key
from bot.db.base import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, unique=True, autoincrement=False)
    github_token = Column(EncryptedType(String(300), get_secret_key()))
    note_file = Column(String(300))
    notes_repository = Column(String(50))
    notes_branch = Column(String(50))
    assets_folder = Column(String(300))
    is_registered = Column(Boolean(False))
