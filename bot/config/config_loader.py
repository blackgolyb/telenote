from pathlib import Path
from typing import Optional

from envparse import Env
from pydantic import (
    BaseModel,
    Field,
    PostgresDsn,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_FOLDER = Path(__file__).parent.parent.parent


def get_model_config(**kwargs):
    return SettingsConfigDict(
        env_nested_delimiter="__",
        case_sensitive=False,
        **kwargs,
    )


class DB(BaseSettings):
    driver: str
    host: str
    port: int
    user: str
    password: str
    db: str

    url: Optional[PostgresDsn] = Field(None, validate_default=True)

    model_config = get_model_config(env_prefix="POSTGRES_")

    @field_validator("url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], values: ValidationInfo) -> str:
        if isinstance(v, str):
            return v

        return PostgresDsn.build(
            scheme=f"postgresql+{values.data.get('driver')}",
            username=values.data.get("user"),
            password=values.data.get("password"),
            host=f"{values.data.get('host')}:{values.data.get('port')}",
            path=f"{values.data.get('db') or ''}",
        )


class Bot(BaseModel):
    token: str


class Core(BaseModel):
    secret_key: str


class Config(BaseSettings):
    bot: Bot
    db: DB = Field(default_factory=DB)
    core: Core = Field(default_factory=Core)

    model_config = get_model_config()


def load_env_by_env_type(
    env: Env,
    env_type: str,
    certs_folder: Path,
) -> None:
    env_file_name = f".env.{env_type.lower()}"
    env_file = certs_folder / env_file_name

    if env_file.exists():
        env.read_envfile(env_file)
    else:
        raise FileNotFoundError(f"Environment file not found: {env_file}")


def load_config() -> Config:
    env = Env()
    env_type = env.str("ENV_TYPE", default="dev")
    load_env_by_env_type(env, env_type, PROJECT_FOLDER / "certs")

    return Config()
