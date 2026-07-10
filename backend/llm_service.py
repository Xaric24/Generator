"""LLM layer for archetype selection, synergy card suggestions, and primer.
Falls back to deterministic behaviour when no key is configured."""
import os
import json
import logging
import asyncio
import requests

logger = logging.getLogger("llm")

# Priority: user-supplied provider key -> Emergent universal key
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")

if GEMINI_KEY:
    KEY, PROVIDER, MODEL = GEMINI_KEY, "gemini", os.environ.get("LLM_MODEL", "gemini-2.5-flash")
elif OPENAI_KEY:
    KEY, PROVIDER, MODEL = OPENAI_KEY, "openai", os.environ.get("LLM_MODEL", "gpt-4.1-mini")
elif ANTHROPIC_KEY:
    KEY, PROVIDER, MODEL = ANTHROPIC_KEY, "anthropic", os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
else:
    KEY, PROVIDER, MODEL = EMERGENT_KEY, "anthropic", "claude-sonnet-4-6"

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    HAVE_LIB = True
except Exception:  # pragma: no cover
    HAVE_LIB = False


def available():
    return bool(KEY) and (HAVE_LIB or PROVIDER in {"gemini", "openai", "anthropic"})


async def _chat(system, prompt, session, model=None):
    if HAVE_LIB:
        chat = LlmChat(api_key=KEY, session_id=session, system_message=system).with_model(
            PROVIDER, model or MODEL)
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp if isinstance(resp, str) else str(resp)
    selected_model = model or MODEL
    if PROVIDER == "openai":
        return await asyncio.to_thread(_chat_openai, system, prompt, selected_model)
    if PROVIDER == "gemini":
        return await asyncio.to_thread(_chat_gemini, system, prompt, selected_model)
    if PROVIDER == "anthropic":
        return await asyncio.to_thread(_chat_anthropic, system, prompt, selected_model)
    raise RuntimeError("No supported LLM adapter is available")


def _chat_openai(system, prompt, model):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.35,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _chat_gemini(system, prompt, model):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": KEY},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.35},
        },
        timeout=60,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _chat_anthropic(system, prompt, model):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={
            "model": model,
            "system": system,
            "max_tokens": 1600,
            "temperature": 0.35,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return "".join(part.get("text", "") for part in r.json().get("content", []) if part.get("type") == "text")


def _extract_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    return None


async def analyze_and_suggest(commander, mode, theme):
    """Return dict: archetype, strategy, secondary, wincons[], cards[] (real card names)."""
    if not available():
        return _fallback_analysis(commander, mode, theme)
    ci = "/".join(commander.get("color_identity") or []) or "Colorless"
    system = ("You are a world-class Magic: The Gathering Commander (EDH) deckbuilding expert. "
              "You only suggest real, existing, Commander-legal Magic cards. Respond ONLY with JSON.")
    prompt = f"""Commander: {commander['name']}
Type: {commander.get('type_line')}
Color identity: {ci}
Oracle text: {commander.get('oracle_text')}
Power mode: {mode}
Theme constraint: {theme or 'none'}

Choose the single strongest coherent archetype for this commander at the "{mode}" power level.
If a theme constraint is provided, treat it as mandatory: the archetype and most suggested synergy
cards must directly support that theme even if the commander also has other obvious subthemes.
Then list 55-65 REAL Magic cards (exact Oracle names) that form the synergy core, payoffs, win conditions,
and key support for that plan. STRICTLY stay within the color identity ({ci}). Do NOT list basic lands,
generic staples like Sol Ring/Arcane Signet (they are auto-added), or off-color cards.
Return JSON:
{{"archetype":"...","strategy":"2-3 sentence plan","secondary":"backup plan",
"wincons":["...","..."],"cards":["Exact Card Name", ...]}}"""
    try:
        raw = await _chat(system, prompt, f"analyze-{commander['name']}")
        data = _extract_json(raw)
        if data and data.get("cards"):
            data.setdefault("archetype", "Synergy Midrange")
            return data
    except Exception as e:
        logger.warning("LLM analyze failed: %s", e)
    return _fallback_analysis(commander, mode, theme)


PROVIDER_FAST = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4.1-mini",
                 "gemini": "gemini-2.5-flash"}


async def build_primer(commander, deck, archetype, strategy, combos):
    if not available():
        return _fallback_primer(commander, archetype, strategy)
    key_cards = [c["name"] for c in deck if not c["is_land"]][:35]
    combo_txt = "; ".join(f"{'+'.join(c['cards'])} ({c.get('result','')})" for c in combos[:5]) or "none"
    system = "You are an expert MTG Commander coach. Write a CONCISE deck primer in markdown (## headers). Under 450 words total."
    prompt = f"""Deck led by {commander['name']} — archetype: {archetype}.
Strategy: {strategy}
Detected combos: {combo_txt}
Key cards: {', '.join(key_cards)}

Write these short sections (## headers, 1-2 sentences each): Summary, Commander Role,
Primary Strategy, Early Game, Mid Game, Late Game, Win Conditions, Combo Lines, Mulligan Guide,
Protection Plan, Weak Matchups, Upgrade Options. Be specific to THIS list. Keep it tight."""
    try:
        return await _chat(system, prompt, f"primer-{commander['name']}",
                           model=PROVIDER_FAST.get(PROVIDER))
    except Exception as e:
        logger.warning("LLM primer failed: %s", e)
        return _fallback_primer(commander, archetype, strategy)


def _fallback_analysis(commander, mode, theme):
    return {
        "archetype": (theme.title() if theme else "Synergy Value") + " Commander",
        "strategy": f"Leverage {commander['name']}'s abilities with efficient ramp, card advantage and "
                    f"interaction, then close with resilient threats.",
        "secondary": "Grind incremental value and win through combat or accumulated advantage.",
        "wincons": ["Commander-driven advantage", "Efficient beaters", "Value engine overwhelm"],
        "cards": [], "ai": False,
    }


def _fallback_primer(commander, archetype, strategy):
    return f"""## Summary
A deterministic {archetype} build for **{commander['name']}**.

## Primary Strategy
{strategy}

## Early Game
Deploy ramp and mana rocks; develop toward casting the commander on curve.

## Mid Game
Establish your engine, protect the commander, and interact with opposing threats.

## Late Game
Convert accumulated advantage into a win via your primary win conditions.

## Mulligan Guide
Keep hands with 3-4 lands, at least one ramp piece, and an early play.

*(AI primer unavailable — deterministic summary shown.)*"""
