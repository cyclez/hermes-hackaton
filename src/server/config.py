from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_env_layers(env_path: str | Path = ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (Path(".env.example"), Path(".env.local"), Path(env_path)):
        values.update(_load_env_file(path))
    return values


def _env(name: str, env_file: dict[str, str], default: str = "") -> str:
    return os.getenv(name) or env_file.get(name) or default


def _env_int(name: str, env_file: dict[str, str], default: int) -> int:
    value = _env(name, env_file, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, env_file: dict[str, str], default: float) -> float:
    value = _env(name, env_file, str(default))
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, env_file: dict[str, str], default: bool) -> bool:
    value = _env(name, env_file, "true" if default else "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    ollama_base_url: str
    openrouter_base_url: str
    openrouter_api_key: str
    openrouter_reasoning_effort: str
    llm_temperature: float
    llm_max_tokens: int
    learning_max_tokens: int
    learning_max_iterations: int
    enable_postgame_training: bool
    citizens_model: str
    mayor_model: str
    citizen_count: int
    citizen_worker_count: int
    max_concurrent_llm_calls: int
    run_target: str
    worker_ssh_target: str
    season_seconds: int
    mayor_tick_seconds: int
    server_tick_seconds: float
    min_decision_interval: float
    database_url: str
    database_url_unpooled: str

    @classmethod
    def load(cls, env_path: str | Path = ".env") -> "Settings":
        env_file = _load_env_layers(env_path)
        database_url = (
            _env("DATABASE_URL", env_file)
            or _env("POSTGRES_URL", env_file)
            or _env("DATABASE_URL_UNPOOLED", env_file)
        )
        return cls(
            llm_provider=_env("LLM_PROVIDER", env_file, "ollama"),
            ollama_base_url=_env("OLLAMA_BASE_URL", env_file, "http://localhost:11434").rstrip("/"),
            openrouter_base_url=_env("OPENROUTER_BASE_URL", env_file, "https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_api_key=_env("OPENROUTER_API_KEY", env_file),
            openrouter_reasoning_effort=_env("OPENROUTER_REASONING_EFFORT", env_file, "none").lower(),
            llm_temperature=max(0.0, min(_env_float("LLM_TEMPERATURE", env_file, 0.2), 2.0)),
            llm_max_tokens=max(32, _env_int("LLM_MAX_TOKENS", env_file, 220)),
            learning_max_tokens=max(256, _env_int("LEARNING_MAX_TOKENS", env_file, 1024)),
            learning_max_iterations=max(2, _env_int("LEARNING_MAX_ITERATIONS", env_file, 6)),
            enable_postgame_training=_env_bool("ENABLE_POSTGAME_TRAINING", env_file, True),
            citizens_model=_env("CITIZENS_MODEL", env_file, "llama3.2:1b"),
            mayor_model=_env("MAYOR_MODEL", env_file, "llama3.2:1b"),
            citizen_count=max(1, _env_int("CITIZEN_COUNT", env_file, 5)),
            citizen_worker_count=max(1, _env_int("CITIZEN_WORKER_COUNT", env_file, 2)),
            max_concurrent_llm_calls=max(1, _env_int("MAX_CONCURRENT_LLM_CALLS", env_file, 3)),
            run_target=_env("RUN_TARGET", env_file, "local"),
            worker_ssh_target=_env("WORKER_SSH_TARGET", env_file, "root@127.0.0.1"),
            season_seconds=max(60, _env_int("SEASON_SECONDS", env_file, 600)),
            mayor_tick_seconds=max(1, _env_int("MAYOR_TICK_SECONDS", env_file, 10)),
            server_tick_seconds=max(0.1, _env_float("SERVER_TICK_SECONDS", env_file, 1.0)),
            min_decision_interval=max(1.0, _env_float("MIN_DECISION_INTERVAL", env_file, 10.0)),
            database_url=database_url,
            database_url_unpooled=_env("DATABASE_URL_UNPOOLED", env_file),
        )
