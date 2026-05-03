from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


INVALID_COMBINATIONS = [
    ("JAILED", "SURVEILLED"),
    ("JAILED", "MOST_WANTED"),
    ("JAILED", "GHOSTED"),
    ("JAILED", "PROTECTED"),
    ("JAILED", "JAMMED"),
    ("JAMMED", "SURVEILLED"),
    ("MOST_WANTED", "SURVEILLED"),
]


def fetch_state(base_url: str) -> dict[str, Any]:
    with urlopen(f"{base_url.rstrip('/')}/api/state", timeout=3) as response:
        return json.load(response)


def find_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for citizen_id, citizen in (state.get("citizens") or {}).items():
        statuses = [status.get("effect") for status in (citizen.get("statuses") or []) if status.get("effect")]
        status_set = set(statuses)
        matched = [list(combo) for combo in INVALID_COMBINATIONS if combo[0] in status_set and combo[1] in status_set]
        if matched:
            violations.append(
                {
                    "citizen_id": citizen_id,
                    "statuses": statuses,
                    "matched_rules": matched,
                    "heat": state.get("heat"),
                    "game_hour": state.get("game_hour"),
                }
            )
    return violations


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch live game state for impossible citizen status combinations.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL. Default: http://localhost:8000")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds. Default: 1.0")
    parser.add_argument("--once", action="store_true", help="Check one snapshot and exit.")
    args = parser.parse_args()

    last_signature: tuple | None = None

    while True:
        try:
            state = fetch_state(args.base_url)
        except URLError as exc:
            print(f"[watch-status-invariants] {utc_now()} backend unavailable: {exc}", file=sys.stderr, flush=True)
            if args.once:
                return 1
            time.sleep(max(args.interval, 1.0))
            continue

        violations = find_violations(state)
        signature = tuple(
            (item["citizen_id"], tuple(item["statuses"]), tuple(tuple(rule) for rule in item["matched_rules"]))
            for item in violations
        )

        if violations and signature != last_signature:
            print(json.dumps(
                {
                    "ts": utc_now(),
                    "game_id": state.get("game_id"),
                    "heat": state.get("heat"),
                    "game_hour": state.get("game_hour"),
                    "violations": violations,
                },
                indent=2,
            ), flush=True)

        if not violations and last_signature:
            print(
                f"[watch-status-invariants] {utc_now()} violations cleared for game {state.get('game_id')}.",
                flush=True,
            )

        last_signature = signature if violations else None

        if args.once:
            return 0 if not violations else 2

        time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
