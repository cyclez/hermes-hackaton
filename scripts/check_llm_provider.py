from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.llm_client import LLMClient
from src.server.config import Settings


def main() -> None:
    settings = Settings.load()
    provider = settings.llm_provider.lower()
    print(f"llm_provider={provider}")
    print(f"citizens_model={settings.citizens_model}")
    print(f"mayor_model={settings.mayor_model}")
    print(f"llm_temperature={settings.llm_temperature}")
    print(f"llm_max_tokens={settings.llm_max_tokens}")

    if provider == "ollama":
        client = LLMClient(settings)
        models = client.list_ollama_models()
        print(f"ollama_base_url={settings.ollama_base_url}")
        print(f"models={','.join(models)}")
        required = {settings.citizens_model, settings.mayor_model}
        missing = sorted(model for model in required if model not in models)
        if missing:
            raise SystemExit(f"missing_models={','.join(missing)}")
        print("llm_provider_check=ok")
        return

    if provider == "openrouter":
        print(f"openrouter_base_url={settings.openrouter_base_url}")
        print(f"openrouter_key_present={bool(settings.openrouter_api_key)}")
        print(f"openrouter_reasoning_effort={settings.openrouter_reasoning_effort}")
        if not settings.openrouter_api_key:
            raise SystemExit("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter.")
        print("llm_provider_check=ok")
        return

    raise SystemExit(f"unsupported_llm_provider={settings.llm_provider}")


if __name__ == "__main__":
    main()
