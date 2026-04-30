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
- The Vite/React UI polls `/api/*` every few seconds and renders:
  - city header / Heat state
  - citizen grid
  - Mayor panel
  - event feeds
  - recent agent decision logs

## Runtime Defaults

The checked-in default profile is `.env.example`:

- `LLM_PROVIDER=openrouter`
- `CITIZENS_MODEL=moonshotai/kimi-k2.6`
- `MAYOR_MODEL=moonshotai/kimi-k2.6`
- `CITIZEN_COUNT=5`
- `CITIZEN_WORKER_COUNT=5`
- `MAX_CONCURRENT_LLM_CALLS=5`
- `LLM_MAX_TOKENS=2048`

Ollama remains supported by switching `LLM_PROVIDER=ollama` and setting the model names accordingly.

## Run Locally

1. Create `.env` from `.env.example` and fill at least:
   - `DATABASE_URL`
   - provider credentials if using OpenRouter
2. Start the backend:

```bash
uvicorn src.server.app:app --port 8000
```

3. Start the UI:

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
