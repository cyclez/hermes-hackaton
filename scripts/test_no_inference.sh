#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/run_deterministic_sim.py
