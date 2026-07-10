# Commander Forge AI

Generate the strongest, most coherent **Magic: The Gathering Commander (EDH)** deck for any
legal commander — with deterministic legality/rules validation, real card data from Scryfall,
combo detection via Commander Spellbook, nonbo analysis, Monte-Carlo opening-hand simulation,
deck-quality scoring, an AI-written primer, and a Moxfield-ready export.

## Overview

Commander Forge AI takes a commander + your constraints (power level, budget, social rules,
locks/excludes/house-bans) and produces a **legal, validated 100-card singleton deck** built
around a coherent archetype. Every card carries a selection score and a human-readable reason.
The build then audits the list for combos and nonbos, simulates opening hands, and scores the
deck across 11 dimensions.

**The LLM never determines legality or rules.** All legality, color-identity, singleton, budget,
category, combo-presence, and count checks are performed by deterministic Python. The AI layer
only interprets archetypes, picks between packages, and writes the primer — and the whole app
runs in a full-featured **deterministic mode** when no AI key is configured.

## Features

- Commander search with Scryfall autocomplete, image & Oracle text.
- 7 generation modes: **Best Possible, Optimized, BR3, BR4/High-Power, cEDH, Budget, Theme**.
- Strict color-identity enforcement + current Commander banned list (via Scryfall `legal:commander`).
- Singleton construction with basic-land & multi-copy-card exceptions.
- Budget mode: total budget + max price/card + owned-card exclusions; **never silently exceeds budget**.
- Social-rule toggles: disable two-card infinites, fast mana, tutors, mass land destruction,
  stax, extra turns, theft.
- Locked cards, excluded cards, and a per-playgroup local ban list.
- Category tracking (ramp, draw, removal, wipes, counters, tutors, protection, recursion, …).
- Mana-base generation (nonbasic duals + basics distributed by colored pips).
- **Combo audit** through Commander Spellbook (`find-my-combos`) with a curated offline fallback,
  including near-combos (one piece missing) and automatic removal of two-card infinites on request.
- **Nonbo analysis** with severity (Critical / Significant / Situational).
- Monte-Carlo opening-hand simulation (keepable %, mulligan rate, ramp-in-hand, screw/flood).
- 11-axis deck-quality report with evidence per score + power-level warnings.
- Deck **Improvement** mode: paste a decklist → cuts, adds, combos, nonbos, power estimate.
- Exports: Moxfield plain text, JSON, CSV.

## Architecture

```
frontend/  React 19 SPA (CRA + Tailwind + shadcn/ui + Recharts + Framer Motion)
backend/
  server.py        FastAPI routes + background-job runner for generation
  scryfall.py      Scryfall provider: Mongo cache, throttle, retries, offline fallback
  engine.py        Deck engine: scoring, assembly, mana base, validation, sim, export, improve
  combos.py        Commander Spellbook adapter + curated combos + nonbo rules
  llm_service.py   Provider-agnostic AI layer (Emergent key / Gemini / OpenAI / Anthropic) + fallback
MongoDB    scryfall_cache (cached cards/queries), decks (generated decks)
```

Generation runs as a **background job** (POST `/api/generate` → `job_id`, poll
`/api/generate/status/{job_id}`) so long AI+data builds are never cut off by proxy timeouts.
On Vercel/serverless, generation runs synchronously inside the request and returns the completed
result directly because request-lifetime functions cannot reliably continue background tasks after
the response.

## Technology choices

- **FastAPI + Python** for the backend — best fit for the scoring/simulation workload and async
  Scryfall I/O.
- **React** SPA for a dense, responsive analytics UI.
- **MongoDB** (via Motor) for cached card data & saved decks — matches the platform runtime.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/` | Health + `ai_available` flag |
| GET | `/api/commanders/search?q=` | Commander autocomplete |
| GET | `/api/card?name=` | Normalized card data |
| POST | `/api/generate` | Start a generation job → `{job_id}` |
| GET | `/api/generate/status/{job_id}` | Poll status/progress/result |
| POST | `/api/improve` | Analyze a pasted decklist |
| GET | `/api/decks` | List saved decks |
| GET | `/api/decks/{id}` | Fetch a saved deck |

## Local setup

```bash
# Backend
pip install -r backend/requirements.txt
copy backend\.env.example backend\.env      # set MONGO_URL / DB_NAME; optionally add an AI key
# Frontend
cd frontend
yarn install
```

Services are managed by supervisor in this environment:
`sudo supervisorctl restart backend frontend`.

## Environment variables

See `backend/.env.example`. `MONGO_URL` and `DB_NAME` are required. AI keys are optional —
without them the app runs deterministically. Provide a `GEMINI_API_KEY`, `OPENAI_API_KEY`, or
`ANTHROPIC_API_KEY` to enable AI analysis & primers.
A free-tier Google Gemini key from https://aistudio.google.com/apikey works well.

For GitHub Pages, set the repository variable `REACT_APP_BACKEND_URL` to the deployed API origin,
for example `https://your-vercel-project.vercel.app`. Do not include `/api`.

## Deployment

### GitHub Pages frontend

This repo includes `.github/workflows/pages.yml`. In the GitHub repository:

1. Open Settings -> Pages.
2. Set Source to GitHub Actions.
3. Add a repository variable named `REACT_APP_BACKEND_URL` with your API origin.
4. Push to `main`; the workflow builds `frontend/` and publishes `frontend/build`.

The React build is configured for `https://xaric24.github.io/Generator`.

### Vercel FastAPI backend

The root `pyproject.toml`, `vercel.json`, and `requirements.txt` are for deploying the backend as
a Vercel Python/FastAPI function with entrypoint `backend.server:app`.

Set these Vercel environment variables:

- `MONGO_URL`
- `DB_NAME`
- `CORS_ORIGINS=https://xaric24.github.io,https://xaric24.github.io/generator`
- Optional: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL`

The Vercel deployment uses the root `requirements.txt`, which intentionally contains only the
runtime packages required by the serverless API.

## AI-provider configuration

`llm_service.py` auto-selects a provider by key presence (Gemini → OpenAI → Anthropic).
Override the model with `LLM_MODEL`. Archetype analysis uses the primary model;
the primer uses a faster/cheaper model to keep latency and cost low.

## Testing

```bash
cd /app && pytest backend/tests -v          # unit + integration
```
Automated tests mock external services so they do not depend on live APIs.

## Data-source attribution

- Card data & prices: **[Scryfall](https://scryfall.com)** (API, cached & throttled per their guidelines).
- Combo data: **[Commander Spellbook](https://commanderspellbook.com)** `find-my-combos` API.
- Popularity ordering uses Scryfall's `order=edhrec` sort. Popularity is **not** treated as proof
  a card belongs — synergy scoring can outrank a more popular but less relevant card.

## Known limitations

- Universes Beyond exclusion toggle is best-effort.
- Partner / Background co-commander selection is single-commander today.
- Simulation is a goldfish opening-hand model (London mulligan assumptions shown with results),
  not a full game engine.
- With a very small AI key budget the app transparently falls back to deterministic analysis.

## Troubleshooting

- **502 on generate**: generation is a background job; the UI polls `/api/generate/status/{job_id}`.
- **AI not used**: check key balance; `GET /api/` reports `ai_available`. Deterministic mode still
  produces full decks.
- **Backend not starting**: `tail -n 100 /var/log/supervisor/backend.*.log`.
