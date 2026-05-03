from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.server.learning_resume import resume_learning_for_game


def _clear_screen() -> None:
    print("\033[2J\033[H", end="", flush=True)


def _progress(event: dict) -> None:
    phase = event.get("phase")
    if phase == "planned":
        total = int(event.get("total_agents") or 0)
        print(f"[resume] game={event['game_id']} planned_agents={total}", flush=True)
        return
    if phase == "start":
        if event["role"] == "citizen":
            print(
                f"[finalizer] learning citizen {event['agent_id']} "
                f"behavior={event['behavior']} game={event['game_id']}",
                flush=True,
            )
        else:
            print(
                f"[finalizer] learning mayor behavior={event['behavior']} "
                f"game={event['game_id']}",
                flush=True,
            )
        return
    if phase == "done":
        row = event["row"]
        if event["role"] == "citizen":
            print(
                f"[finalizer] learned citizen {event['agent_id']} "
                f"decision={row['decision']} ok={row['ok']} game={event['game_id']}",
                flush=True,
            )
        else:
            print(
                f"[finalizer] learned mayor decision={row['decision']} "
                f"ok={row['ok']} game={event['game_id']}",
                flush=True,
            )
        return
    if phase == "completed":
        print(f"[finalizer] learning completed for game {event['game_id']}", flush=True)
        return
    if phase == "failed":
        print(
            f"[finalizer] learning failed for game {event['game_id']}: {event.get('error')}",
            flush=True,
        )
        return


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
    _clear_screen()
    print(
        f"[resume] starting game={args.game_id} include_existing={args.include_existing} "
        f"skip={','.join(args.skip) if args.skip else '-'}",
        flush=True,
    )
    print("[resume] loading terminal packet and fetching evidence...", flush=True)
    result = await resume_learning_for_game(
        args.game_id,
        skip=set(args.skip),
        include_existing=args.include_existing,
        progress_callback=_progress,
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
