import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Searcher:
    id: str
    name: str
    search_url: str
    webhook_url: str


@dataclass(frozen=True)
class PipelineConfig:
    check_interval_minutes: int
    searchers: tuple["Searcher", ...]


class ConfigError(Exception):
    pass


def load_config(config_path: str = "config.json") -> PipelineConfig:
    """
    Load and validate config.json.
    Calls load_dotenv() so .env is honoured.
    Raises ConfigError on any validation failure.
    """
    load_dotenv()

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {config_path!r}")
    except OSError as exc:
        raise ConfigError(f"Could not read config file {config_path!r}: {exc}")
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in config file {config_path!r}: {exc}"
        )

    # Validate check_interval_minutes (Req 1.5, 1.6)
    if "check_interval_minutes" not in data:
        check_interval_minutes = 5
    else:
        interval = data["check_interval_minutes"]
        # Explicitly reject bools (isinstance(True, int) is True in Python)
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise ConfigError(
                f"'check_interval_minutes' must be an integer in [1, 1440], got: {interval!r}"
            )
        if not (1 <= interval <= 1440):
            raise ConfigError(
                f"'check_interval_minutes' must be in [1, 1440], got: {interval}"
            )
        check_interval_minutes = interval

    # Validate searchers key exists and is a non-empty list (Req 1.7)
    searchers_raw = data.get("searchers")
    if not isinstance(searchers_raw, list) or len(searchers_raw) == 0:
        raise ConfigError(
            "'searchers' must be a non-empty array in config file"
        )

    # Validate each searcher entry (Req 1.8, 1.9)
    required_fields = ("id", "name", "search_url", "discord_webhook_env")
    for i, entry in enumerate(searchers_raw):
        if not isinstance(entry, dict):
            raise ConfigError(
                f"Searcher at index {i} must be a JSON object, got: {type(entry).__name__!r}"
            )
        for field in required_fields:
            value = entry.get(field)
            if value is None:
                raise ConfigError(
                    f"Searcher at index {i} is missing required field {field!r}"
                )
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(
                    f"Searcher at index {i} has an empty or non-string value for field {field!r}"
                )

    # Check for duplicate ids (Req 1.10)
    seen_ids: dict[str, int] = {}
    duplicate_ids = []
    for i, entry in enumerate(searchers_raw):
        searcher_id = entry["id"]
        if searcher_id in seen_ids:
            if searcher_id not in duplicate_ids:
                duplicate_ids.append(searcher_id)
        else:
            seen_ids[searcher_id] = i
    if duplicate_ids:
        raise ConfigError(
            f"Duplicate Searcher id(s) found in config: {duplicate_ids!r}"
        )

    # Resolve discord_webhook_env → webhook_url for every Searcher (Req 1.11, 2.1, 2.2)
    searchers: list[Searcher] = []
    for entry in searchers_raw:
        env_var_name = entry["discord_webhook_env"]
        webhook_url = os.environ.get(env_var_name, "")
        if not webhook_url or not webhook_url.strip():
            raise ConfigError(
                f"Searcher {entry['id']!r}: environment variable {env_var_name!r} is absent or empty"
            )
        searchers.append(
            Searcher(
                id=entry["id"],
                name=entry["name"],
                search_url=entry["search_url"],
                webhook_url=webhook_url,
            )
        )

    return PipelineConfig(
        check_interval_minutes=check_interval_minutes,
        searchers=tuple(searchers),
    )
