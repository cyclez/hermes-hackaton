#!/usr/bin/env bash
set -euo pipefail

python3 scripts/check_llm_provider.py
python3 scripts/run_live_phase4_eval.py
