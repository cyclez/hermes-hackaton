from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.llm_client import LLMClient
from src.server.config import Settings


def main() -> None:
    settings = Settings.load()
    client = LLMClient(settings)
    models = client.list_ollama_models()
    print(f"ollama_base_url={settings.ollama_base_url}")
    print(f"models={','.join(models)}")
    required = {settings.citizens_model, settings.mayor_model}
    missing = sorted(model for model in required if model not in models)
    if missing:
        raise SystemExit(f"missing_models={','.join(missing)}")
    print("ollama_check=ok")


if __name__ == "__main__":
    main()
