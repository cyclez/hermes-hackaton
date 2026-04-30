from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.server.learning_resume import resume_learning_for_game


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume interrupted Hermes cross-game learning for a finalized game.")
    parser.add_argument("game_id", help="Finalized game id to resume.")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Agent ids to skip, e.g. citizen-004 citizen-005 mayor.",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Rerun agents that already have durable *_learning decision-log rows.",
    )
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    result = await resume_learning_for_game(
        args.game_id,
        skip=set(args.skip),
        include_existing=args.include_existing,
    )
    print(
        "learning_resume "
        f"game_id={result['game_id']} "
        f"results={len(result['results'])} "
        f"completed=true"
    )
    for row in result["results"]:
        print(f"- {row['role']} {row['agent_id']} ok={row['ok']}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
