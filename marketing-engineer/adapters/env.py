"""`.env` loading and backend selection. Never echoes a value: errors name variables only."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping, TypeVar

from dotenv import load_dotenv

ME_DIR = Path(__file__).resolve().parent.parent  # marketing-engineer/
T = TypeVar("T")


class MissingEnvVar(RuntimeError):
    """A job needs a variable that is unset. The message names the variable, never a value."""


class UnknownBackend(ValueError):
    """An env var selects a backend this adapter does not know."""


def load_env(path: Path | None = None) -> Path | None:
    """Load marketing-engineer/.env (or `path`) into os.environ without overriding what is set.

    Returns the file loaded, or None when it does not exist (scripts/dev_db.sh creates it).
    """
    env_file = path or ME_DIR / ".env"
    if not env_file.exists():
        return None
    load_dotenv(env_file, override=False)
    return env_file


def require(job: str, *names: str) -> dict[str, str]:
    """Return the named variables for `job`; raise MissingEnvVar naming every unset one."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise MissingEnvVar(
            f"job {job!r} needs {', '.join(missing)}; set it in marketing-engineer/.env (see .env.example)"
        )
    return {n: os.environ[n] for n in names}


def dev_root() -> Path:
    """Directory for dev-backend state (DEV_ROOT, default marketing-engineer/.dev). Git-ignored."""
    root = Path(os.environ.get("DEV_ROOT") or ".dev")
    if not root.is_absolute():
        root = ME_DIR / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def choose_backend(var: str, choices: Mapping[str, Callable[[], T]], default: str | None = None) -> T:
    """Instantiate the backend named by env var `var`; unknown values raise naming the variable."""
    value = os.environ.get(var) or default
    if value not in choices:
        raise UnknownBackend(f"{var}={value!r} is not one of {sorted(choices)}")
    return choices[value]()


def not_built(var: str, value: str, ticket: str) -> Callable[[], T]:
    """Factory entry for a live backend that a later ticket delivers."""
    def _raise() -> T:
        raise NotImplementedError(f"{var}={value} is the live backend; it lands in {ticket} (go-live swap)")
    return _raise
