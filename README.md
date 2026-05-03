# hermes-hackaton

Hermes-backed hackathon simulation/game built around isolated citizen agents and a competing Mayor agent in one shared city state.

## Current Repo Behavior

- The FastAPI app in `src/server/app.py` starts a fresh game at process startup and launches in-process background loops for:
  - the server tick/game loop
  - citizen worker loops
  - the Mayor loop
- Citizens run through isolated Hermes `AIAgent` instances rooted in `.runtime/hermes-profiles/`.
- Citizen decisions are queued in Postgres job rows and consumed by citizen workers.
- Mayor decisions currently run on a timed loop every `MAYOR_TICK_SECONDS`; they are not queued as Mayor jobs yet.
- Post-game learning can run after terminal games and write back into each agent's profile-local playbook skill in a bounded `Learned Patterns` section. It is controlled by `ENABLE_POSTGAME_TRAINING`.
- The Vite/React UI polls `/api/*` every few seconds and renders:
  - city header / Heat state
  - citizen grid
  - Mayor panel
  - event feeds
  - recent agent decision logs
  - live post-game training status

## Runtime Defaults

The checked-in default profile is `.env.example`:

- `LLM_PROVIDER=openrouter`
- `CITIZENS_MODEL=deepseek/deepseek-v3.2`
- `MAYOR_MODEL=moonshotai/kimi-k2.6`
- `CITIZEN_COUNT=10`
- `CITIZEN_WORKER_COUNT=10`
- `MAX_CONCURRENT_LLM_CALLS=10`
- `LLM_MAX_TOKENS=2048`
- `LEARNING_MAX_TOKENS=1024`
- `LEARNING_MAX_ITERATIONS=6`
- `ENABLE_POSTGAME_TRAINING=true`

Ollama remains supported by switching `LLM_PROVIDER=ollama` and setting the model names accordingly.

## Run Locally

1. Create `.env` from `.env.example` and fill at least:
   - `DATABASE_URL`
   - provider credentials if using OpenRouter
2. Pick a launch mode.

Full backend + UI, quiet agent-focused logs:

```bash
./scripts/start-agents-view.sh
```

Full backend + UI, auto-run multiple games with restart after training:

```bash
./scripts/start-agents-view.sh --run 10
```

Backend only, quiet logs, with reload:

```bash
uvicorn src.server.app:app --reload --no-access-log
```

Backend only, quiet logs, no reload:

```bash
uvicorn src.server.app:app --no-access-log
```

Backend only, simpler explicit port start:

```bash
uvicorn src.server.app:app --port 8000
```

3. Start the UI separately when not using `start-agents-view.sh`:

```bash
cd src/ui
npm run dev
```

4. Open `http://localhost:5173`

## Verification

Run the local test suite with:

```bash
./.venv/bin/python -m unittest discover -s tests -q
```
