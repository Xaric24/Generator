"""Combo detection (Commander Spellbook + curated) and nonbo analysis."""
import asyncio
import logging
import requests

logger = logging.getLogger("combos")
SPELLBOOK = "https://backend.commanderspellbook.com/find-my-combos"

# Curated fallback combos: (frozenset of card names, description, kind, result)
CURATED = [
    (["Thassa's Oracle", "Demonic Consultation"], "Exile your library naming a card not in deck, then Thassa's Oracle wins.", "two-card", "Win the game"),
    (["Thassa's Oracle", "Tainted Pact"], "Exile library with Tainted Pact, Thassa's Oracle wins.", "two-card", "Win the game"),
    (["Laboratory Maniac", "Demonic Consultation"], "Empty library, draw to win with Lab Man.", "two-card", "Win the game"),
    (["Isochron Scepter", "Dramatic Reversal"], "Imprint Dramatic Reversal, untap nonland mana rocks for infinite mana.", "two-card", "Infinite mana"),
    (["Dockside Extortionist", "Temur Sabertooth"], "Bounce Dockside repeatedly for infinite treasures (with enough artifacts).", "two-card", "Infinite mana"),
    (["Mikaeus, the Unhallowed", "Walking Ballista"], "Ballista dies with undying, returns with +1/+1, ping infinitely.", "two-card", "Infinite damage"),
    (["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"], "Copy Conscripts to untap Kiki, make infinite hasty tokens.", "two-card", "Infinite tokens"),
    (["Splinter Twin", "Deceiver Exarch"], "Enchant Exarch, make infinite hasty copies.", "two-card", "Infinite tokens"),
    (["Basalt Monolith", "Rings of Brighthearth"], "Copy the untap ability for infinite colorless mana.", "two-card", "Infinite mana"),
    (["Grand Architect", "Pili-Pala"], "Infinite colorless mana via untap loop.", "two-card", "Infinite mana"),
    (["Deadeye Navigator", "Peregrine Drake"], "Soulbond, blink Drake for infinite mana.", "two-card", "Infinite mana"),
    (["Sanguine Bond", "Exquisite Blood"], "Life gain/loss loop drains all opponents.", "two-card", "Win the game"),
    (["Heliod, Sun-Crowned", "Walking Ballista"], "Lifelink pings add counters back to Ballista, infinite damage.", "two-card", "Infinite damage"),
    (["Mind Over Matter", "Temple Bell"], "Discard to untap, draw whole deck.", "two-card", "Infinite draw"),
    (["Food Chain", "Squee, the Immortal"], "Cast Squee from exile repeatedly for infinite creature mana.", "two-card", "Infinite mana"),
]


async def find_combos(names, db):
    """Query Commander Spellbook; fall back to curated on failure."""
    result = {"source": "commander-spellbook", "included": [], "almost": []}
    try:
        payload = {"main": [{"card": n, "quantity": 1} for n in names]}
        r = await asyncio.to_thread(
            lambda: requests.post(SPELLBOOK, json=payload,
                                  headers={"User-Agent": "CommanderForgeAI/1.0"}, timeout=25))
        if r.status_code == 200:
            data = r.json()
            for c in data.get("results", {}).get("included", [])[:40]:
                result["included"].append(_norm_sb(c))
            for c in data.get("results", {}).get("almostIncluded", [])[:15]:
                result["almost"].append(_norm_sb(c, almost=True))
            if result["included"] or result["almost"]:
                return result
    except Exception as e:
        logger.warning("spellbook failed: %s", e)
    # curated fallback
    result["source"] = "curated"
    nameset = set(names)
    for cards, desc, kind, res in CURATED:
        have = [c for c in cards if c in nameset]
        if len(have) == len(cards):
            result["included"].append({"cards": cards, "description": desc, "kind": kind,
                                        "result": res, "prerequisite": "", "steps": desc})
        elif len(have) == len(cards) - 1:
            missing = [c for c in cards if c not in nameset]
            result["almost"].append({"cards": cards, "missing": missing, "description": desc,
                                     "kind": kind, "result": res})
    return result


def _norm_sb(c, almost=False):
    uses = [u.get("card", {}).get("name", "") for u in c.get("uses", [])]
    produces = [p.get("feature", {}).get("name", "") for p in c.get("produces", [])]
    kind = "two-card" if len(uses) == 2 else ("three-card" if len(uses) == 3 else f"{len(uses)}-card")
    out = {"cards": uses, "kind": kind, "result": ", ".join(produces),
           "prerequisite": c.get("notablePrerequisites", "") or c.get("easyPrerequisites", ""),
           "steps": c.get("description", ""), "description": ", ".join(produces)}
    if almost:
        have = set(c.get("_have", []))
        out["missing"] = [u for u in uses][-1:]  # spellbook already knows; keep last
    return out


# --- Nonbo rules: card name -> (conflict detector, severity, message) ---
NONBO_CARDS = {
    "Cursed Totem": ("dorks", "Significant", "Cursed Totem disables your mana dorks' abilities."),
    "Torpor Orb": ("etb", "Critical", "Torpor Orb disables your creatures' ETB triggers."),
    "Hushwing Gryff": ("etb", "Critical", "Hushwing Gryff disables creature ETB triggers."),
    "Rule of Law": ("storm", "Significant", "Rule of Law limits you to one spell per turn."),
    "Blood Moon": ("greedy", "Significant", "Blood Moon turns your nonbasics into Mountains."),
    "Back to Basics": ("greedy", "Significant", "Back to Basics taps your nonbasic lands."),
    "Grafdigger's Cage": ("gy", "Significant", "Grafdigger's Cage stops your graveyard recursion & tutoring to battlefield."),
    "Rest in Peace": ("gy", "Critical", "Rest in Peace exiles graveyards, disabling your recursion plan."),
    "Stony Silence": ("artifacts", "Critical", "Stony Silence shuts off your artifact mana abilities."),
    "Karn, the Great Creator": ("artifacts", "Situational", "Karn stops opponents' and your own activated artifact abilities."),
    "Null Rod": ("artifacts", "Critical", "Null Rod disables your mana rocks' abilities."),
}


def analyze_nonbos(cards):
    """cards: list of dicts with name, oracle, type. Returns list of nonbo findings."""
    text_blob = " ".join((c.get("oracle") or "") for c in cards).lower()
    types = " ".join((c.get("type") or "") for c in cards).lower()
    names = {c["name"] for c in cards}
    dork_count = sum(1 for c in cards if "creature" in (c.get("type") or "").lower()
                     and "{t}: add" in (c.get("oracle") or "").lower())
    rock_count = sum(1 for c in cards if "artifact" in (c.get("type") or "").lower()
                     and "add" in (c.get("oracle") or "").lower() and "{t}" in (c.get("oracle") or "").lower())
    etb_count = text_blob.count("enters, ") + text_blob.count("enters the battlefield")
    gy_signals = ("from your graveyard" in text_blob) or ("return target creature card" in text_blob)
    nonbasic_count = sum(1 for c in cards if "land" in (c.get("type") or "").lower()
                         and "basic" not in (c.get("type") or "").lower())
    findings = []
    checks = {
        "dorks": dork_count >= 4, "rocks": rock_count >= 4, "artifacts": rock_count >= 4,
        "etb": etb_count >= 6, "gy": gy_signals, "greedy": nonbasic_count >= 12,
        "storm": "storm" in text_blob or text_blob.count("whenever you cast") >= 3,
    }
    for name, (flag, sev, msg) in NONBO_CARDS.items():
        if name in names and checks.get(flag):
            findings.append({"card": name, "severity": sev, "message": msg})
    # structural nonbos
    sac_payoff = "whenever" in text_blob and "dies" in text_blob
    sac_outlet = "sacrifice a creature" in text_blob or "sacrifice another" in text_blob
    if sac_payoff and not sac_outlet:
        findings.append({"card": "Sacrifice theme", "severity": "Situational",
                         "message": "Death-trigger payoffs present but few sacrifice outlets detected."})
    reanim = "return target creature card" in text_blob and "graveyard" in text_blob
    big_targets = sum(1 for c in cards if "creature" in (c.get("type") or "").lower() and (c.get("cmc", 0) or 0) >= 6)
    if reanim and big_targets < 3:
        findings.append({"card": "Reanimation", "severity": "Situational",
                         "message": "Reanimation effects present but few high-value reanimation targets."})
    return findings
