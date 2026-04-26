import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    db_path: Path


DEFAULT_DB_PATH = "~/.local/share/uspto/trademarks.db"


def load_config() -> Config:
    # python-dotenv walks UP from the importing file's location to find .env;
    # existing env vars take precedence (override=False by default).
    load_dotenv()
    api_key = os.environ.get("USPTO_API_KEY")
    if not api_key:
        raise ConfigError(
            "USPTO_API_KEY is not set.\n"
            "  • Local dev: copy .env.example to .env and fill it in\n"
            "  • Otherwise: export USPTO_API_KEY=...\n"
            "Get a free key at https://data.uspto.gov/"
        )
    db_path = Path(
        os.environ.get("USPTO_DB_PATH") or DEFAULT_DB_PATH
    ).expanduser().resolve()
    return Config(api_key=api_key, db_path=db_path)
