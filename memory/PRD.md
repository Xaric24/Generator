# Commander Forge AI — PRD & Build Log

## Original problem statement
Build "Commander Forge AI": a production-ready app that generates the strongest, most coherent
100-card Magic: The Gathering Commander (EDH) deck around a user-selected commander. Deterministic
legality/validation, Scryfall card data, Commander Spellbook combo detection, nonbo analysis,
Monte-Carlo simulation, deck-quality scoring, AI primer, Moxfield export, and a deck-improvement
flow. Modes: Best Possible, Optimized, BR3, BR4, cEDH, Budget, Theme.

## User choices
- AI layer: **Emergent Universal LLM key** (deterministic fallback when unavailable).
- Card data: **Scryfall live API + local caching**.
- Scope: deck generation **and** deck improvement.
- Combos: **Commander Spellbook** (curated offline fallback).
- Demo commander: Krenko, Mob Boss (mono-R Goblins); Atraxa (5c) also verified.

## Architecture
- Frontend: React 19 SPA (Tailwind + shadcn/ui + Recharts + Framer Motion), "Arcane Terminal" dark theme.
- Backend: FastAPI. `scryfall.py` (cached provider), `engine.py` (scoring/assembly/validation/sim/
  export/improve), `combos.py` (Spellbook + curated + nonbo), `llm_service.py` (multi-provider AI + fallback).
- MongoDB: `scryfall_cache`, `decks`.
- Generation = background job with progress polling (avoids 60s ingress timeout).

## Core requirements (static)
- Exactly 100 cards, singleton (with exceptions), strict color identity, banned-list legal.
- Never exceed budget; respect locks/excludes/local bans/toggles.
- Deterministic validation must pass before returning a deck; auto-repair otherwise.

## Implemented (2026-06-10)
- Scryfall provider with Mongo cache, throttle, retries, offline fallback. [DONE]
- Commander search, card lookup. [DONE]
- Deck engine: mode-based targets, hybrid AI+deterministic synergy, category fill, mana base,
  singleton/CI/budget enforcement, exactly-100 guarantee. [DONE]
- Budget total-cap enforcement (swap expensive → cheap/basics). [DONE]
- Combo audit (Spellbook + curated) + two-card-combo removal on toggle + near-combos. [DONE]
- Nonbo analysis with severity. [DONE]
- Monte-Carlo opening-hand simulation. [DONE]
- 11-axis quality scoring with evidence + power warnings. [DONE]
- AI archetype analysis + primer (multi-provider, deterministic fallback). [DONE]
- Deck improvement endpoint (cuts/adds/power/combos/nonbos). [DONE]
- Exports: Moxfield / JSON / CSV; Moxfield round-trips to 100 cards. [DONE]
- Full UI: builder panel + 11-tab results with sidebar nav, radar & bar charts, hover card previews. [DONE]

## Verified end-to-end
- Optimized (AI on): 100 cards, valid, archetype + 8 Spellbook combos. ✓
- Budget ($100 cap, $5/card): valid, total $98.53. ✓
- BR3 + disable two-card infinites + locks/excludes/local-bans: 0 two-card combos, constraints honored. ✓
- Atraxa 5-color: 100, valid, CI respected. ✓
- Moxfield export = 100 cards. ✓
- Improve flow returns cuts/adds/power estimate. ✓

## Backlog / next
- P1: Partner / Background / Friends-Forever multi-commander selection UI + pooled color identity.
- P1: Jobify `/api/improve` (parity with generate) for very large lists.
- P2: Archidekt/MTGO/Arena export formats; printable primer PDF.
- P2: Manual card replace → re-optimize in-place from the decklist tab.
- P2: EDHREC per-commander synergy adapter (user-provided export) to enrich scoring.
- P2: pytest suite expansion + CI (unit tests scaffolded in backend/tests).
