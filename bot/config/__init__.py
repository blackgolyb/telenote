from .config_loader import Config, load_config

config: Config = load_config()


def get_secret_key() -> str:
    return config.core.secret_key


def get_db_url() -> str:
    return str(config.db.url)


__all__ = ["config", "get_secret_key", "get_db_url"]
