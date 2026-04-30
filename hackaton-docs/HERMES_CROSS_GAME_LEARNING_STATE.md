# Hermes Cross-Game Learning State

Date: 2026-04-30

This note preserves the current design state for enabling Hermes Agent memory and learning across repeated 10-minute OptimiCity games.

## Goal

Make decision logs worth analyzing by letting each Hermes-backed actor accumulate private gameplay knowledge across games.

The target is not offline model training. The target is profile-scoped Hermes learning:

- each citizen keeps private memories across games
- the Mayor keeps its own adversarial memories across games
- normal gameplay turns remain strict protocol JSON
- learning happens after a game ends, through a separate memory-enabled Hermes turn

## Current Runtime Facts

- Runtime agents use `AIAgent` from local pinned `hermes-agent/`.
- Each citizen has an isolated Hermes home under `.runtime/hermes-profiles/<citizen-id>/`.
- Mayor has `.runtime/hermes-profiles/mayor/`.
- Those profile directories already contain `memories/`, `sessions/`, `SOUL.md`, `behavior.txt`, and `config.yaml`.
- No current profile has useful `MEMORY.md` or `USER.md` yet.
- Current gameplay runner disables learning:
  - `skip_memory=True`
  - `enabled_toolsets=["_game_output_only_"]`
  - `memory` is listed in blocked toolsets
- Hermes built-in memory writes to profile-local `memories/MEMORY.md` and `memories/USER.md`.
- Hermes loads built-in memory into the system prompt as a frozen snapshot at session start / prompt build.
- A memory written during one session is durable immediately, but naturally affects the next rebuilt session/game.

## Design Decision

Do not expose the `memory` tool during normal citizen or Mayor gameplay decisions.

Reason:

- gameplay calls must return one protocol JSON object
- exposing tools during those calls risks tool calls or non-JSON responses
- first-pass JSON validity is still important

Instead, add a separate **game-end learning turn**.

## Game-End Learning Turn

When a 10-minute game reaches a real terminal condition, the server should run a learning pass.

Manual stop/restart of an unfinished game is treated as an aborted/debug run and should not write long-term lessons.

Current terminal outcome rule:

- Mayor wins only when Heat reaches `100`.
- Citizens win every other terminal outcome, including timeout below `100` and Heat reaching `0`.
- Finalizer reason values currently include `heat_maxed`, `heat_depleted`, and `timeout_survived`.

For each citizen:

- gather only that citizen's own decisions and outcomes
- include its action counts, caught/uncaught outcomes, trace/STK/SHIVA/status context, Mayor actions targeting it, and final game result
- do not include other citizens' private state or hidden reasoning

For Mayor:

- gather decree history, targets, caught evidence, pressure outcomes, Heat trajectory, and final game result
- include broad citizen response patterns only at the adversarial-control level

The server should compute evidence, not lessons.

No `lesson_candidates` in the first implementation. The evidence should be factual and compact. Hermes decides what, if anything, is worth saving.

## Evidence Visibility Contract

Training evidence must not break the in-game information boundary. Citizens do not receive an omniscient post-game packet.

Citizen learning evidence is limited to what that citizen could legitimately know during or after the game:

1. Their own decision logs: prompt/observation, chosen action/mode/HOLD, and rationale.
2. Their own private state snapshots: STK, SHIVA, trace, mode, queued mode, statuses, and cooldown.
3. Their own allowed and affordable actions at decision time.
4. Their own server catch result only when knowable through their own/public event stream.
5. Public Heat values.
6. Public final game result: winner and server-coded reason only.
7. Mayor actions that visibly affected them through their own statuses, such as JAILED, JAMMED, or SURVEILLED.
8. Their own blocked states, such as JAILED, JAMMED, SLEEP, or cooldown.

Citizen learning evidence must not include:

1. Other citizens' private state.
2. Other citizens' decisions unless the public feed already exposed them in-game.
3. Mayor private context or dossiers.
4. Mayor rationale.
5. Full decree target lists.
6. Hidden server catch probabilities if not exposed to the citizen.
7. Dossiers or caught evidence about other citizens.
8. Aggregates across all citizens that reveal hidden behavior.
9. Effective-Mayor-strategy analysis.
10. Omniscient post-game causal explanations.

Mayor learning evidence may include adversarial-control evidence visible to the Mayor role:

1. Its own decrees and rationales.
2. Dossiers and caught evidence.
3. Citizen snapshots already included in Mayor context.
4. Public or recent citizen actions.
5. Heat trajectory.
6. Final game result.
7. Aggregates based only on Mayor-visible information.

Implementation consequence:

- `build_citizen_learning_evidence(citizen_id, ...)` must build a strict private/visible-only packet.
- `build_mayor_learning_evidence(...)` may build a broader Mayor-visible adversarial packet.
- There must be no shared omniscient packet sent to citizens.

## Learning Prompt Shape

```text
The 10-minute OptimiCity game has ended.

Review the evidence summary below. Save at most 3 durable gameplay lessons using the memory tool.

Rules:
- Only save lessons supported by evidence.
- Do not save raw logs, game IDs, timestamps, or one-off state.
- Phrase uncertain lessons as hypotheses.
- If nothing durable was learned, do not call memory.

Evidence JSON:
...
```

## Runner Shape

Add a separate learning-agent constructor rather than changing gameplay agent behavior.

Learning agent settings:

- same profile `HERMES_HOME`
- same model/provider credentials
- `skip_memory=False`
- `enabled_toolsets=["memory"]`
- no terminal, file, browser, web, delegation, code execution, skills, or session search
- `max_iterations` around `4` to `6`
- `skip_context_files=True`
- same profile doctrine/persona via `ephemeral_system_prompt`

Pseudo-structure:

```python
def learn_citizen_from_game(
    self,
    *,
    citizen_id: str,
    behavior: str,
    evidence: dict,
    game_id: str,
) -> dict:
    profile_dir = ensure_citizen_profile(...)
    agent = self._make_learning_agent(
        session_id=f"{citizen_id}-learning-{game_id}",
        profile_dir=profile_dir,
        model=self.settings.citizens_model,
        system_prompt=_citizen_prompt(behavior),
    )
    result = agent.run_conversation(
        user_message=_game_learning_prompt(evidence),
        conversation_history=None,
    )
    agent.shutdown_memory_provider(result.get("messages") or [])
    return result
```

## Evidence Builder Shape

Evidence builders should be pure functions with no LLM calls.

For citizens:

- filter decision logs where `role == "citizen"` and `agent_id == citizen_id`
- correlate with events for caught/uncaught outcomes
- summarize by action, mode, status, trace buckets, and punishment pressure
- cap notable turns to a small number

For Mayor:

- filter Mayor decision logs and decree events
- summarize decree counts, target counts, post-decree effects, and final Heat outcome
- identify repeated ineffective or effective pressure patterns as evidence only

## Server Orchestration

At game end, after the finalizer has frozen the terminal packet:

```python
async def run_game_learning_pass(store, runner, game_id):
    state = await store.load_state(game_id)
    events = await store.get_events(game_id, limit=2000)
    logs = runner.log_store.read_entries(game_id, limit=2000)

    for citizen in state.citizens.values():
        evidence = build_citizen_learning_evidence(...)
        await loop.run_in_executor(
            None,
            lambda: runner.learn_citizen_from_game(...),
        )

    mayor_evidence = build_mayor_learning_evidence(...)
    await loop.run_in_executor(
        None,
        lambda: runner.learn_mayor_from_game(...),
    )
```

The learning pass should respect the existing rule that blocking LLM calls run through `run_in_executor`.

## Expected Effect

After game N:

- learning turn writes compact lessons into `.runtime/hermes-profiles/<agent>/memories/MEMORY.md`

During game N+1:

- new or rebuilt Hermes agents load `MEMORY.md`
- memory appears in the system prompt
- decisions can reflect prior games
- durable decision logs become meaningful as traces of learned behavior

## Constraints To Preserve

- Keep citizen memories isolated per profile.
- Do not create shared writable doctrine memory.
- Do not let citizens learn other citizens' private state.
- Do not store raw logs, game IDs, or transient timestamps in memory.
- Keep normal gameplay calls strict JSON-only.
- Keep `_profile_lock` / `HERMES_HOME` swap serialization.
- Keep blocking Hermes calls outside the asyncio event loop.
- Preserve blocked-citizen `allowed_actions == []` behavior.

## Open Design Questions

- Should failed or interrupted games produce separate debug evidence without updating memory?
- Should the Mayor learn from full game evidence while citizens receive only private evidence?
- Should the first implementation use only built-in `MEMORY.md`, or also configure a local external provider like `holographic` later?
- How should the UI expose whether an agent learned anything after a game?

## Implemented Finalization Slice

Current implementation, before memory learning:

- `src/server/game_finalizer.py` owns the single idempotent finalizer.
- Terminal marker: `.runtime/finalized-games/<game_id>/finalized.json`.
- Frozen packet: `.runtime/finalized-games/<game_id>/terminal-packet.json`.
- Packet includes outcome, reason, final Heat/time, citizen snapshots, recent events, recent dossiers, and decision-log path/count.
- The game loop finalizes on already-finished state and on a tick that crosses the terminal condition.
- A terminal tick no longer enqueues new citizen decision jobs.
- Citizen jobs claimed after the game has finished are completed without calling the LLM or mutating state.
- Mayor decrees that return after the game has finished are skipped before mutating state.
- Mayor wins only if Heat reaches `100`; timeout below `100` is `winner="citizens"` with `reason="timeout_survived"`.
- `/api/server/restart` on an unfinished game does not finalize the old game.
- `/api/server/stop` shuts down the backend and is not a finalization/learning trigger.
- No Hermes memory mutation exists yet.

Tests:

- `tests/test_game_finalizer.py` covers unfinished skip, terminal packet/idempotency, pre-terminal restart skip, terminal tick no-enqueue, and stale citizen worker no-mutation.

## Next Implementation Slice

1. Add evidence builder functions from `terminal-packet.json` plus full decision logs/events.
2. Add `learn_citizen_from_game` and `learn_mayor_from_game` to `HermesAgentRunner`.
3. Add `_make_learning_agent` with memory enabled and only the memory tool exposed.
4. Trigger learning pass only from the completed-game finalizer.
5. Log learning attempts separately or include them in decision logs with `role="learning"`.
6. Verify `MEMORY.md` appears per profile after one completed game.
7. Verify the next game prompt/logs include prior learned memory.
