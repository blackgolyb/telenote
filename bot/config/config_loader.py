from dataclasses import dataclass
from envparse import Env


@dataclass
class Bot:
    token: str


@dataclass
class General:
    secret_key: str


@dataclass
class DB:
    host: str
    port: int
    name: str
    user: str
    password: str

    class Config:
        db_type: str = "postgresql"
        db_interface: str = "psycopg"

    @property
    def db_url(self):
        url_fmt = "{db_type}+{db_interface}://{user}:{password}@{host}:{port}/{db_name}"

        return url_fmt.format(
            db_type=self.Config.db_type,
            db_interface=self.Config.db_interface,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            db_name=self.name,
        )


@dataclass
class Config:
    bot: Bot
    db: DB
    general: General


def load_config() -> Config:
    env = Env()
    env.read_envfile()

    return Config(
        bot=Bot(token=env.str("BOT_TOKEN")),
        db=DB(
            host=env.str("DB_HOST"),
            port=env.str("DB_PORT"),
            name=env.str("DB_NAME"),
            user=env.str("DB_USER"),
            password=env.str("DB_PASSWORD"),
        ),
        general=General(secret_key=env.str("SECRET_KEY")),
    )
