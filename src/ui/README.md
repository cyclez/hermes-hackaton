# UI

This is the Vite/React admin panel for the current simulation runtime.

## Current Behavior

- Runs on port `5173` via Vite.
- Proxies `/api` requests to `http://localhost:8000`.
- Polls the backend for:
  - city state
  - filtered event feeds
  - latest Mayor decree
  - recent agent logs

## Commands

```bash
npm run dev
npm run build
npm run lint
```

## Main Surface

The current UI renders:

- city header / Heat gauge
- citizen grid
- Mayor panel
- citizen, Mayor, and system feeds
- agent console/log panels
