from sqlalchemy import Column, BigInteger, String, Boolean
from sqlalchemy_utils import EncryptedType

from bot.db.base import Base
from bot.config import config


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, unique=True, autoincrement=False)
    github_token = Column(EncryptedType(String(300), config.general.secret_key))
    note_file = Column(String(300))
    notes_repository = Column(String(50))
    notes_branch = Column(String(50))
    assets_folder = Column(String(300))
    is_registered = Column(Boolean(False))
