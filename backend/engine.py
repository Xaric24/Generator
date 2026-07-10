"""Deck generation engine: scoring, assembly, validation, simulation, export."""
import random
import logging

logger = logging.getLogger("engine")

BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
          "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
          "Snow-Covered Mountain", "Snow-Covered Forest"}
MULTI_COPY = {"Persistent Petitioners", "Rat Colony", "Relentless Rats", "Shadowborn Apostle",
              "Dragon's Approach", "Seven Dwarves", "Slime Against Humanity", "Templar Knight",
              "Cid, Timeless Artificer"}
COLOR_TO_BASIC = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}

FAST_MANA = {"Sol Ring", "Mana Crypt", "Mana Vault", "Grim Monolith", "Chrome Mox", "Mox Diamond",
             "Mox Opal", "Jeweled Lotus", "Dark Ritual", "Cabal Ritual", "Lion's Eye Diamond",
             "Lotus Petal", "Ancient Tomb", "Mishra's Workshop", "Simian Spirit Guide"}
STAX = {"Winter Orb", "Static Orb", "Stasis", "Tangle Wire", "Rule of Law", "Archon of Emeria",
        "Thalia, Guardian of Thraben", "Sphere of Resistance", "Trinisphere", "Blood Moon",
        "Back to Basics", "Root Maze", "Hokori, Dust Drinker", "Winter Moon", "Null Rod",
        "Stony Silence", "Drannith Magistrate"}

MODE_TARGETS = {
    "best": dict(ramp=11, draw=10, removal=8, wipe=3, counter=4, tutor=5),
    "optimized": dict(ramp=10, draw=10, removal=8, wipe=3, counter=3, tutor=3),
    "br3": dict(ramp=9, draw=10, removal=9, wipe=3, counter=3, tutor=1),
    "br4": dict(ramp=11, draw=9, removal=8, wipe=3, counter=4, tutor=5),
    "cedh": dict(ramp=13, draw=10, removal=7, wipe=2, counter=6, tutor=8),
    "budget": dict(ramp=10, draw=10, removal=9, wipe=3, counter=3, tutor=2),
    "theme": dict(ramp=9, draw=9, removal=8, wipe=3, counter=3, tutor=2),
}
OTAG = {"ramp": "otag:ramp", "draw": "otag:card-advantage", "removal": "otag:removal",
        "wipe": "otag:board-wipe", "counter": "otag:counterspell", "tutor": "otag:tutor"}


def norm_card(c):
    """Normalize a Scryfall card object."""
    img = None
    if c.get("image_uris"):
        img = c["image_uris"].get("normal") or c["image_uris"].get("small")
    elif c.get("card_faces") and c["card_faces"][0].get("image_uris"):
        img = c["card_faces"][0]["image_uris"].get("normal")
    oracle = c.get("oracle_text") or ""
    if not oracle and c.get("card_faces"):
        oracle = " // ".join(f.get("oracle_text", "") for f in c["card_faces"])
    price = None
    try:
        price = float((c.get("prices") or {}).get("usd") or 0) or None
    except Exception:
        price = None
    tl = c.get("type_line") or ""
    return {
        "name": c["name"], "mana_cost": c.get("mana_cost") or "",
        "cmc": c.get("cmc", 0) or 0, "type": tl, "oracle": oracle,
        "color_identity": c.get("color_identity") or [], "colors": c.get("colors") or [],
        "keywords": c.get("keywords") or [], "image": img, "price": price,
        "legal": (c.get("legalities") or {}).get("commander") == "legal",
        "edhrec": c.get("edhrec_rank", 999999) or 999999, "layout": c.get("layout", "normal"),
        "set": (c.get("set") or "").upper(), "cn": c.get("collector_number", ""),
        "is_land": "Land" in tl, "is_basic": c["name"] in BASICS,
        "is_mdfc": c.get("layout") in ("modal_dfc", "transform") and "Land" in " ".join(
            f.get("type_line", "") for f in c.get("card_faces", [])),
    }


def ci_query(ci):
    if not ci:
        return "id:colorless"
    return f"id<={''.join(ci)}"


import re
_ADD_RE = re.compile(r"add (?:one|two|three|four|five|\{|an amount|.{0,8}mana)")
_TUTOR_RE = re.compile(r"search your library for (?:a card|.{0,30}card,? .{0,20}(?:hand|battlefield))")


def is_mana_source(card):
    o = card["oracle"].lower()
    if card["is_land"]:
        return True
    return bool(_ADD_RE.search(o)) and "{t}" in o or "add one mana of any" in o


def categorize(card):
    o, tl = card["oracle"].lower(), card["type"].lower()
    cats = []
    if "land" in tl:
        cats.append("Lands")
        if card.get("is_mdfc"):
            cats.append("MDFC")
    if is_mana_source(card) and not card["is_land"]:
        cats.append("Ramp")
    if "search your library for" in o and ("basic land" in o or "land card" in o) and "battlefield" in o:
        cats.append("Ramp")
    if "draw" in o and "card" in o:
        cats.append("Card Draw")
    if ("destroy target" in o or "exile target" in o) and "land" not in o.split("target", 1)[-1][:12]:
        cats.append("Removal")
    if "destroy all" in o or "each player sacrifices" in o or ("exile all" in o):
        cats.append("Board Wipe")
    if "counter target" in o:
        cats.append("Counterspell")
    if _TUTOR_RE.search(o):
        cats.append("Tutor")
    if "hexproof" in o or "indestructible" in o or "protection" in o or "shroud" in o:
        cats.append("Protection")
    if "from your graveyard" in o or "return target" in o and "graveyard" in o:
        cats.append("Recursion")
    if card["name"] in FAST_MANA:
        cats.append("Fast Mana")
    if card["name"] in STAX:
        cats.append("Stax")
    if not cats:
        cats.append("Payoff/Synergy" if not card["is_land"] else "Lands")
    return list(dict.fromkeys(cats))


def toggle_block(card, tg):
    """Return reason string if card should be blocked by a toggle, else None."""
    o = card["oracle"].lower()
    if tg.get("no_fast_mana") and card["name"] in FAST_MANA:
        return "fast mana disabled"
    if tg.get("no_stax") and card["name"] in STAX:
        return "stax disabled"
    if tg.get("no_tutors") and "Tutor" in categorize(card):
        return "tutors disabled"
    if tg.get("no_extra_turns") and "take an extra turn" in o:
        return "extra turns disabled"
    if tg.get("no_theft") and ("gain control of target" in o or "gains control" in o):
        return "theft disabled"
    if tg.get("no_mld") and ("destroy all lands" in o or "each player sacrifices a land" in o):
        return "mass land destruction disabled"
    return None


def passes_filters(card, ci, budget, params):
    """Return (ok, reason_if_blocked)."""
    if not card["legal"]:
        return False, "not commander-legal / banned"
    if not set(card["color_identity"]).issubset(set(ci)):
        return False, "off color identity"
    nm = card["name"]
    if nm in params["excludes"]:
        return False, "excluded by user"
    if nm in params["local_bans"]:
        return False, "on local ban list"
    tb = toggle_block(card, params["toggles"])
    if tb:
        return False, tb
    maxp = params.get("max_price_per_card")
    if maxp and not (nm in params["owned"] or card["is_basic"]) and (card["price"] or 0) > maxp:
        return False, f"exceeds max price/card (${maxp})"
    return True, None


def score_card(card, synergy_names, mode, ci):
    s = 40.0
    reasons = []
    if card["name"] in synergy_names:
        s += 30
        reasons.append("core synergy piece for the archetype")
    rank = card["edhrec"]
    if rank < 500:
        s += 18; reasons.append("premier staple (very high EDHREC usage)")
    elif rank < 2000:
        s += 12; reasons.append("strong widely-played card")
    elif rank < 8000:
        s += 6
    cats = categorize(card)
    if "Ramp" in cats:
        reasons.append("accelerates mana / fixes colors")
    if "Card Draw" in cats:
        reasons.append("provides card advantage")
    if "Removal" in cats or "Board Wipe" in cats:
        reasons.append("interaction / removal")
    if mode in ("cedh", "best", "br4"):
        if card["cmc"] <= 2 and not card["is_land"]:
            s += 6; reasons.append("low mana value fits high-power curve")
        if card["cmc"] >= 6 and not card["is_land"]:
            s -= 6
    if mode == "budget" and card["price"]:
        s += max(0, 8 - card["price"])
    if not reasons:
        reasons.append("supports the game plan")
    return round(min(100, max(1, s)), 1), "; ".join(reasons[:3])


async def _deterministic_synergy(sf, cmd, ci, params, mode):
    """Derive synergy cards from commander creature types / theme without an LLM."""
    queries = []
    theme = (params.get("theme") or "").strip().lower()
    tl = cmd["type"].lower()
    subtypes = []
    if "—" in cmd["type"]:
        subtypes = [s for s in cmd["type"].split("—")[1].strip().split() if s.istitle() or True]
        subtypes = cmd["type"].split("—")[1].strip().split()
    creature_types = [s for s in subtypes if s not in ("Warrior", "Soldier", "Wizard", "Cleric",
                                                        "Scout", "Rogue", "Shaman", "Artificer",
                                                        "Advisor", "Noble", "Peasant")] or subtypes
    for st in creature_types[:2]:
        queries.append(f"t:{st.lower()} {ci_query(ci)} legal:commander -is:funny")
    o = cmd["oracle"].lower()
    theme_map = {
        "artifact": "t:artifact -t:land", "token": "o:\"create\" o:\"token\"",
        "counter": "o:\"+1/+1 counter\"", "graveyard": "o:graveyard", "sacrifice": "o:sacrifice",
        "spellslinger": "(t:instant or t:sorcery)", "landfall": "o:landfall",
        "lifegain": "o:\"gain life\"", "energy": "o:\"{E}\"", "dragon": "t:dragon",
        "elf": "t:elf", "goblin": "t:goblin", "vampire": "t:vampire", "zombie": "t:zombie",
        "reanimator": "o:\"return target creature card\" o:graveyard",
        "voltron": "(t:equipment or t:aura)", "aristocrats": "o:\"whenever\" o:\"dies\"",
    }
    if theme and theme in theme_map:
        queries.insert(0, f"{theme_map[theme]} {ci_query(ci)} legal:commander -is:funny")
    else:
        for k, q in theme_map.items():
            if k in o:
                queries.append(f"{q} {ci_query(ci)} legal:commander -is:funny")
                break
    if not queries:
        queries.append(f"{ci_query(ci)} legal:commander -t:land -is:funny")
    maxp = params.get("max_price_per_card")
    seen, out = set(), []
    for q in queries:
        if maxp:
            q += f" usd<={maxp}"
        try:
            cards = await sf.search(q, limit=40, order="edhrec")
        except Exception:
            cards = []
        for c in cards:
            nc = norm_card(c)
            if nc["name"] in seen or nc["is_land"]:
                continue
            ok, _ = passes_filters(nc, ci, None, params)
            if ok:
                seen.add(nc["name"])
                out.append(nc)
            if len(out) >= 50:
                break
        if len(out) >= 50:
            break
    return out


async def _fetch_category(sf, tag, ci, params, need, exclude_names):
    q = f"{OTAG[tag]} {ci_query(ci)} legal:commander -t:land -is:funny"
    maxp = params.get("max_price_per_card")
    if maxp:
        q += f" usd<={maxp}"
    try:
        cards = await sf.search(q, limit=need + 30, order="edhrec")
    except Exception:
        cards = []
    out = []
    for c in cards:
        nc = norm_card(c)
        if nc["name"] in exclude_names:
            continue
        ok, _ = passes_filters(nc, ci, None, params)
        if ok:
            out.append(nc)
        if len(out) >= need:
            break
    return out


def color_pips(cards):
    counts = {c: 0 for c in "WUBRG"}
    for card in cards:
        for ch in card["mana_cost"]:
            if ch in counts:
                counts[ch] += 1
    return counts


async def generate(sf, db, params, progress=None):
    def _p(msg):
        if progress:
            progress(msg)
    _p("Validating commander...")
    ci_name = params["commander"]
    raw = await sf.named(ci_name) or await sf.fuzzy(ci_name)
    if not raw:
        return {"error": f"Commander '{ci_name}' not found on Scryfall."}
    cmd = norm_card(raw)
    tl = cmd["type"].lower()
    can_cmd = ("legendary" in tl and "creature" in tl) or "can be your commander" in cmd["oracle"].lower()
    if not can_cmd:
        return {"error": f"{cmd['name']} is not a legal commander."}
    ci = cmd["color_identity"]
    mode = params["mode"]
    seed = params.get("seed")
    if seed is not None:
        random.seed(seed)

    from llm_service import analyze_and_suggest, build_primer
    _p("Analyzing commander & ranking archetypes...")
    analysis = await analyze_and_suggest(raw, mode, params.get("theme"))
    synergy_names = [n for n in analysis.get("cards", []) if n != cmd["name"]]
    det_synergy = []
    if not synergy_names:
        _p("Deriving synergy package...")
        det_synergy = await _deterministic_synergy(sf, cmd, ci, params, mode)
        synergy_names = [c["name"] for c in det_synergy]
        analysis["cards"] = synergy_names

    # Resolve synergy + locked names in one collection call
    resolved = {c["name"]: c for c in det_synergy}
    to_resolve = [n for n in dict.fromkeys(synergy_names + params["locks"]) if n not in resolved]
    if to_resolve:
        for c in await sf.collection(to_resolve):
            nc = norm_card(c)
            resolved[nc["name"]] = nc
    synergy_set = set(synergy_names)

    budget = params.get("budget")
    deck = {cmd["name"]: cmd}
    reasons = {cmd["name"]: (100.0, "Your chosen commander — the centerpiece of the strategy.")}

    def add(card, forced=False):
        nm = card["name"]
        if nm in deck:
            return False
        ok, why = passes_filters(card, ci, budget, params)
        if not ok and not forced:
            return False
        sc, rz = score_card(card, synergy_set, mode, ci)
        deck[nm] = card
        reasons[nm] = (sc if not forced else max(sc, 60), rz)
        return True

    # locked cards first (forced-in, kept even if suboptimal)
    for nm in params["locks"]:
        if nm in resolved:
            add(resolved[nm], forced=True)

    land_count = params.get("land_count") or 32
    targets = dict(MODE_TARGETS.get(mode, MODE_TARGETS["optimized"]))
    if "U" not in ci:
        targets["counter"] = 0
    nonland_target = 99 - land_count

    # 1) synergy core (non-land), best first by edhrec
    core = sorted([resolved[n] for n in synergy_names if n in resolved and not resolved[n]["is_land"]],
                  key=lambda c: c["edhrec"])
    for c in core:
        if len([1 for x in deck.values() if not x["is_land"]]) - 1 >= nonland_target - 22:
            break
        add(c)

    # 2) staples + category fill
    _p("Adding staples, ramp & interaction...")
    staples = ["Sol Ring", "Arcane Signet", "Command Tower"]
    for c in await sf.collection(staples):
        add(norm_card(c))

    def cat_count(cat):
        return sum(1 for x in deck.values() if cat in categorize(x))

    catmap = [("Ramp", "ramp"), ("Card Draw", "draw"), ("Removal", "removal"),
              ("Board Wipe", "wipe"), ("Counterspell", "counter"), ("Tutor", "tutor")]
    for cat, tkey in catmap:
        need = targets.get(tkey, 0) - cat_count(cat)
        if need <= 0:
            continue
        for nc in await _fetch_category(sf, tkey, ci, params, need + 5, set(deck.keys())):
            if cat_count(cat) >= targets.get(tkey, 0):
                break
            add(nc)

    # 3) top-up nonland to target with more synergy/staple cards from edhrec
    def nonland_n():
        return sum(1 for x in deck.values() if not x["is_land"]) - 1  # exclude commander
    if nonland_n() < nonland_target:
        pool = await sf.search(f"{ci_query(ci)} legal:commander -t:land -is:funny", limit=180, order="edhrec")
        for c in pool:
            if nonland_n() >= nonland_target:
                break
            add(norm_card(c))

    # 4) trim nonland if over
    while nonland_n() > nonland_target:
        cand = [n for n, c in deck.items() if not c["is_land"] and n != cmd["name"]
                and n not in params["locks"]]
        worst = min(cand, key=lambda n: reasons[n][0])
        del deck[worst]; del reasons[worst]

    # 5) mana base — nonbasic duals then basics by pips
    _p("Assembling mana base...")
    nonbasic_target = max(0, land_count - _basics_needed(land_count, ci))
    land_q = f"type:land -type:basic {ci_query(ci)} legal:commander -is:funny"
    maxp = params.get("max_price_per_card")
    if maxp:
        land_q += f" usd<={maxp}"
    duals = await sf.search(land_q, limit=nonbasic_target + 25, order="edhrec")
    for c in duals:
        if sum(1 for x in deck.values() if x["is_land"]) >= nonbasic_target:
            break
        nc = norm_card(c)
        ok, _ = passes_filters(nc, ci, budget, params)
        if ok:
            add(nc)
    # basics
    _add_basics(deck, reasons, ci, land_count)

    # 6) enforce exactly 100
    _enforce_100(deck, reasons, ci, cmd, params)

    # 6b) enforce total budget (never silently exceed)
    if budget:
        await _enforce_budget(sf, deck, reasons, ci, cmd, params, budget)

    cards = list(deck.values())
    # combos + nonbos
    _p("Scanning combos & nonbos...")
    from combos import find_combos, analyze_nonbos
    names = [c["name"] for c in cards]
    combo_res = await find_combos(names, db)
    if params["toggles"].get("no_two_card_combos"):
        cards, combo_res = _strip_two_card(cards, combo_res, deck, reasons, cmd, params)
        names = [c["name"] for c in cards]
    nonbos = analyze_nonbos(cards)

    _p("Running simulations & validation...")
    validation = validate(cards, cmd, ci, params, budget)
    sim = simulate(cards, cmd)
    quality = quality_scores(cards, cmd, ci, combo_res, sim, analysis)
    warnings = power_warnings(cards, mode, combo_res)
    _p("Writing deck primer...")
    primer = await build_primer(raw, cards, analysis["archetype"], analysis["strategy"],
                                combo_res["included"])

    out_cards = []
    for c in cards:
        sc, rz = reasons.get(c["name"], (50, "supports the plan"))
        out_cards.append({**c, "categories": categorize(c), "score": sc, "reason": rz,
                          "in_synergy": c["name"] in synergy_set})
    out_cards.sort(key=lambda c: (c["is_land"], -c["score"]))

    return {
        "commander": {**cmd, "categories": ["Commander"]},
        "archetype": analysis["archetype"], "strategy": analysis["strategy"],
        "secondary": analysis.get("secondary", ""), "wincons": analysis.get("wincons", []),
        "ai_used": analysis.get("ai", True) is not False and bool(synergy_names),
        "cards": out_cards, "combos": combo_res, "nonbos": nonbos,
        "validation": validation, "simulation": sim, "quality": quality,
        "warnings": warnings, "primer": primer,
        "categories": _category_breakdown(out_cards),
        "curve": _mana_curve(out_cards), "sources": _mana_sources(cards, ci),
        "types": _type_breakdown(out_cards),
        "total_price": round(sum((c["price"] or 0) for c in cards if not c["is_basic"]), 2),
        "moxfield": export_moxfield(cards, cmd),
        "count": len(cards),
    }


def _basics_needed(land_count, ci):
    n = max(1, len(ci))
    return min(land_count, max(6, n * 3))


def _add_basics(deck, reasons, ci, land_count):
    have_lands = sum(1 for c in deck.values() if c["is_land"])
    need = land_count - have_lands
    if need <= 0:
        return
    colors = [c for c in ci if c in COLOR_TO_BASIC] or ["C"]
    pips = color_pips([c for c in deck.values() if not c["is_land"]])
    total = sum(pips[c] for c in colors if c in pips) or 1
    for i, col in enumerate(colors):
        share = max(1, round(need * (pips.get(col, 1) / total))) if col != "C" else need
        bname = COLOR_TO_BASIC.get(col, "Wastes")
        for _ in range(share):
            if sum(1 for c in deck.values() if c["is_land"]) >= land_count:
                break
            key = f"{bname}#{sum(1 for k in deck if k.startswith(bname))}"
            deck[key] = {"name": bname, "mana_cost": "", "cmc": 0, "type": "Basic Land",
                         "oracle": f"({col}: Add {col}.)", "color_identity": [], "colors": [],
                         "keywords": [], "image": None, "price": None, "legal": True,
                         "edhrec": 999999, "layout": "normal", "set": "", "cn": "",
                         "is_land": True, "is_basic": True, "is_mdfc": False}
            reasons[key] = (30.0, "Basic land for mana base.")
    # fill remainder with first color basic
    while sum(1 for c in deck.values() if c["is_land"]) < land_count:
        col = colors[0]
        bname = COLOR_TO_BASIC.get(col, "Wastes")
        key = f"{bname}#{sum(1 for k in deck if k.startswith(bname))}"
        deck[key] = {"name": bname, "mana_cost": "", "cmc": 0, "type": "Basic Land",
                     "oracle": "", "color_identity": [], "colors": [], "keywords": [],
                     "image": None, "price": None, "legal": True, "edhrec": 999999,
                     "layout": "normal", "set": "", "cn": "", "is_land": True,
                     "is_basic": True, "is_mdfc": False}
        reasons[key] = (30.0, "Basic land for mana base.")


def _enforce_budget_total(deck, owned):
    return sum((c["price"] or 0) for c in deck.values()
               if not c["is_basic"] and c["name"] not in owned)


async def _enforce_budget(sf, deck, reasons, ci, cmd, params, budget):
    """Trim expensive non-locked cards (swapping for cheap alternatives / basics) until <= budget."""
    owned = params["owned"]
    q = f"{ci_query(ci)} legal:commander -t:land -is:funny usd<=2"
    try:
        pool = await sf.search(q, limit=90, order="edhrec")
    except Exception:
        pool = []
    cheap = []
    for c in pool:
        nc = norm_card(c)
        ok, _ = passes_filters(nc, ci, None, params)
        if ok and nc["name"] not in deck:
            cheap.append(nc)
    guard = 0
    while _enforce_budget_total(deck, owned) > budget and guard < 80:
        guard += 1
        cand = [(n, c) for n, c in deck.items() if not c["is_basic"] and n != cmd["name"]
                and n not in params["locks"] and (c["price"] or 0) > 0 and n not in owned]
        if not cand:
            break
        wname, wcard = max(cand, key=lambda kv: kv[1]["price"] or 0)
        del deck[wname]; reasons.pop(wname, None)
        replaced = False
        if not wcard["is_land"]:
            while cheap:
                rc = cheap.pop(0)
                if rc["name"] in deck:
                    continue
                sc, rz = score_card(rc, set(), params.get("mode", "budget"), ci)
                deck[rc["name"]] = rc
                reasons[rc["name"]] = (sc, "Budget-friendly replacement — " + rz)
                replaced = True
                break
        if not replaced:
            _add_basics(deck, reasons, ci, sum(1 for c in deck.values() if c["is_land"]) + 1)
    _enforce_100(deck, reasons, ci, cmd, params)


def _enforce_100(deck, reasons, ci, cmd, params):
    while len(deck) > 100:
        cand = [n for n, c in deck.items() if not c["is_basic"] and n != cmd["name"]
                and n.split("#")[0] not in params["locks"]]
        if not cand:
            # remove a basic
            b = next((n for n, c in deck.items() if c["is_basic"]), None)
            if b:
                del deck[b]; reasons.pop(b, None)
                continue
            break
        worst = min(cand, key=lambda n: reasons[n][0])
        del deck[worst]; reasons.pop(worst, None)
    if len(deck) < 100:
        _add_basics(deck, reasons, ci, params.get("land_count", 32) + (100 - len(deck)))


def _strip_two_card(cards, combo_res, deck, reasons, cmd, params):
    remove = set()
    for combo in combo_res["included"]:
        if combo.get("kind") == "two-card":
            pieces = [c for c in combo["cards"] if c in deck and c != cmd["name"]
                      and c not in params["locks"]]
            if pieces:
                remove.add(sorted(pieces, key=lambda n: reasons.get(n, (0,))[0])[0])
    for nm in remove:
        deck.pop(nm, None); reasons.pop(nm, None)
    _add_basics(deck, reasons, cmd["color_identity"], params.get("land_count", 32))
    _enforce_100(deck, reasons, cmd["color_identity"], cmd, params)
    cards = list(deck.values())
    combo_res = dict(combo_res)
    combo_res["included"] = [c for c in combo_res["included"]
                             if not (c.get("kind") == "two-card" and set(c["cards"]) & remove)]
    combo_res["removed_two_card"] = sorted(remove)
    return cards, combo_res


def validate(cards, cmd, ci, params, budget):
    issues = []
    if len(cards) != 100:
        issues.append(f"Deck has {len(cards)} cards, expected 100.")
    seen = {}
    for c in cards:
        if c["is_basic"] or c["name"] in MULTI_COPY:
            continue
        seen[c["name"]] = seen.get(c["name"], 0) + 1
    dupes = [n for n, k in seen.items() if k > 1]
    if dupes:
        issues.append(f"Singleton violation: {', '.join(dupes)}")
    off = [c["name"] for c in cards if not set(c["color_identity"]).issubset(set(ci))]
    if off:
        issues.append(f"Off-color-identity cards: {', '.join(off[:5])}")
    illegal = [c["name"] for c in cards if not c["legal"] and not c["is_basic"]]
    if illegal:
        issues.append(f"Illegal/banned cards: {', '.join(illegal[:5])}")
    bad_ex = [c["name"] for c in cards if c["name"] in params["excludes"]]
    if bad_ex:
        issues.append(f"Excluded cards present: {', '.join(bad_ex)}")
    bad_ban = [c["name"] for c in cards if c["name"] in params["local_bans"]]
    if bad_ban:
        issues.append(f"Local-banned cards present: {', '.join(bad_ban)}")
    missing_locks = [n for n in params["locks"] if not any(c["name"] == n for c in cards)]
    if missing_locks:
        issues.append(f"Locked cards missing: {', '.join(missing_locks)}")
    total = sum((c["price"] or 0) for c in cards if not c["is_basic"]
                and c["name"] not in params["owned"])
    if budget and total > budget:
        issues.append(f"Budget exceeded: ${total:.2f} > ${budget:.2f}")
    lands = sum(1 for c in cards if c["is_land"])
    if lands < 30:
        issues.append(f"Only {lands} lands — mana base may be unstable.")
    return {"valid": len(issues) == 0, "issues": issues,
            "checks": {"count": len(cards), "lands": lands, "singleton": not dupes,
                       "color_identity": not off, "legal": not illegal,
                       "budget_ok": not (budget and total > budget)}}


def simulate(cards, cmd, trials=2000, hand=7):
    lib = [c for c in cards if c["name"] != cmd["name"]]
    lands = [c for c in lib if c["is_land"]]
    sources = [c for c in lib if is_mana_source(c)]
    ramp = [c for c in lib if "Ramp" in categorize(c)]
    keep, land_sum, ramp_hits, flood, screw = 0, 0, 0, 0, 0
    for _ in range(trials):
        h = random.sample(lib, hand)
        nl = sum(1 for c in h if c["is_land"])
        land_sum += nl
        if 2 <= nl <= 5:
            keep += 1
        if nl <= 1:
            screw += 1
        if nl >= 6:
            flood += 1
        if any(c in h for c in ramp) or any(c["is_land"] for c in h) and any(
                c in h for c in sources if not c["is_land"]):
            if any(c in h for c in ramp):
                ramp_hits += 1
    return {"trials": trials, "hand_size": hand,
            "avg_lands": round(land_sum / trials, 2),
            "keepable_pct": round(100 * keep / trials, 1),
            "mulligan_pct": round(100 * (trials - keep) / trials, 1),
            "ramp_in_hand_pct": round(100 * ramp_hits / trials, 1),
            "flood_pct": round(100 * flood / trials, 1),
            "screw_pct": round(100 * screw / trials, 1),
            "total_lands": len(lands), "total_mana_sources": len(sources),
            "assumptions": "London mulligan, 7-card hands, uniform random draws, no scry/mull adjustments."}


def quality_scores(cards, cmd, ci, combo_res, sim, analysis):
    ramp = sum(1 for c in cards if "Ramp" in categorize(c))
    draw = sum(1 for c in cards if "Card Draw" in categorize(c))
    removal = sum(1 for c in cards if "Removal" in categorize(c) or "Board Wipe" in categorize(c))
    syn = sum(1 for c in cards if c["name"] in set(analysis.get("cards", [])))
    lands = sum(1 for c in cards if c["is_land"])
    avg_cmc = round(sum(c["cmc"] for c in cards if not c["is_land"]) /
                    max(1, sum(1 for c in cards if not c["is_land"])), 2)
    def clamp(v):
        return int(max(5, min(100, v)))
    return {
        "Commander Synergy": {"score": clamp(50 + syn * 2.2), "evidence": f"{syn} cards flagged as core synergy."},
        "Strategy Cohesion": {"score": clamp(45 + syn * 2), "evidence": f"Archetype: {analysis['archetype']}."},
        "Mana Efficiency": {"score": clamp(120 - avg_cmc * 14), "evidence": f"Avg nonland MV {avg_cmc}."},
        "Mana Consistency": {"score": clamp(sim["keepable_pct"]), "evidence": f"{sim['keepable_pct']}% keepable hands, {lands} lands."},
        "Card Advantage": {"score": clamp(40 + draw * 5), "evidence": f"{draw} card-advantage sources."},
        "Interaction": {"score": clamp(35 + removal * 5), "evidence": f"{removal} removal/wrath effects."},
        "Resilience": {"score": clamp(40 + (draw + removal) * 3), "evidence": "Based on draw + interaction density."},
        "Win-Condition Quality": {"score": clamp(50 + len(analysis.get("wincons", [])) * 8 + len(combo_res["included"]) * 6), "evidence": f"{len(combo_res['included'])} combos, {len(analysis.get('wincons', []))} named wincons."},
        "Combo Quality": {"score": clamp(30 + len(combo_res["included"]) * 12), "evidence": f"{len(combo_res['included'])} combos detected."},
        "Opening-Hand Consistency": {"score": clamp(sim["keepable_pct"]), "evidence": f"Mulligan rate {sim['mulligan_pct']}%."},
        "Ramp Density": {"score": clamp(30 + ramp * 6), "evidence": f"{ramp} ramp pieces."},
    }


def power_warnings(cards, mode, combo_res):
    w = []
    names = {c["name"] for c in cards}
    two = [c for c in combo_res["included"] if c.get("kind") == "two-card"]
    if two and mode in ("br3", "optimized", "budget"):
        w.append({"level": "high", "text": f"Deck contains {len(two)} easy two-card combo(s) — may exceed the target power level."})
    fm = names & FAST_MANA
    if len(fm) >= 3 and mode in ("br3",):
        w.append({"level": "medium", "text": f"Substantial fast mana ({', '.join(sorted(fm))}) for a BR3 table."})
    stax = names & STAX
    if stax and mode in ("br3", "optimized"):
        w.append({"level": "medium", "text": f"Stax pieces present: {', '.join(sorted(stax))}."})
    if any("destroy all lands" in (c["oracle"] or "").lower() for c in cards):
        w.append({"level": "high", "text": "Deck contains mass land destruction."})
    tutors = sum(1 for c in cards if "Tutor" in categorize(c))
    if tutors >= 6 and mode not in ("cedh",):
        w.append({"level": "medium", "text": f"High tutor density ({tutors}) increases consistency and power."})
    return w


def _category_breakdown(cards):
    out = {}
    for c in cards:
        for cat in c["categories"]:
            out[cat] = out.get(cat, 0) + 1
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def _mana_curve(cards):
    buckets = {str(i): 0 for i in range(8)}
    buckets["7+"] = 0
    for c in cards:
        if c["is_land"]:
            continue
        v = int(c["cmc"])
        buckets["7+" if v >= 7 else str(v)] = buckets.get("7+" if v >= 7 else str(v), 0) + 1
    return [{"cmc": k, "count": v} for k, v in buckets.items() if k != "7+"] + [{"cmc": "7+", "count": buckets["7+"]}]


def _mana_sources(cards, ci):
    src = {c: 0 for c in ci}
    for c in cards:
        if not is_mana_source(c):
            continue
        o = c["oracle"]
        for col in ci:
            sym = "{" + col + "}"
            if sym in o or ("any color" in o.lower()) or ("any type" in o.lower()):
                src[col] = src.get(col, 0) + 1
    return [{"color": k, "count": v} for k, v in src.items()]


def _type_breakdown(cards):
    out = {}
    for c in cards:
        base = c["type"].split("—")[0].strip()
        for t in ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment",
                  "Planeswalker", "Battle", "Land"]:
            if t in base:
                out[t] = out.get(t, 0) + 1
                break
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def export_moxfield(cards, cmd):
    lines = ["Commander"]
    lines.append(_line(cmd))
    lines.append("")
    lines.append("Deck")
    basics = {}
    others = []
    for c in cards:
        if c["name"] == cmd["name"]:
            continue
        if c["is_basic"]:
            basics[c["name"]] = basics.get(c["name"], 0) + 1
        else:
            others.append(c)
    others.sort(key=lambda c: c["name"])
    for c in others:
        lines.append(_line(c))
    for name, n in sorted(basics.items()):
        lines.append(f"{n} {name}")
    return "\n".join(lines)


def _line(c):
    if c.get("set") and c.get("cn"):
        return f"1 {c['name']} ({c['set']}) {c['cn']}"
    return f"1 {c['name']}"


async def improve_deck(sf, db, params):
    """Analyze a pasted decklist and suggest cuts/adds."""
    text = params["decklist"]
    names, counts = _parse_decklist(text)
    resolved = {}
    for c in await sf.collection(list(names)):
        nc = norm_card(c)
        resolved[nc["name"]] = nc
    cmd_name = params.get("commander") or _guess_commander(names, resolved)
    cmd = resolved.get(cmd_name)
    if not cmd:
        raw = await sf.fuzzy(cmd_name) if cmd_name else None
        cmd = norm_card(raw) if raw else None
    ci = cmd["color_identity"] if cmd else []
    cards = [resolved[n] for n in names if n in resolved]
    total = sum(counts.get(n, 1) for n in names)
    issues = []
    if total != 100:
        issues.append(f"Deck has {total} cards (expected 100).")
    off = [c["name"] for c in cards if cmd and not set(c["color_identity"]).issubset(set(ci))]
    if off:
        issues.append(f"Off-color-identity: {', '.join(off[:8])}")
    illegal = [c["name"] for c in cards if not c["legal"] and not c["is_basic"]]
    if illegal:
        issues.append(f"Banned/illegal: {', '.join(illegal[:8])}")
    lands = sum(counts.get(c["name"], 1) for c in cards if c["is_land"])
    ramp = sum(1 for c in cards if "Ramp" in categorize(c))
    draw = sum(1 for c in cards if "Card Draw" in categorize(c))
    removal = sum(1 for c in cards if "Removal" in categorize(c) or "Board Wipe" in categorize(c))
    combo_res = await find_combos_wrapper(sf, db, [c["name"] for c in cards])
    from combos import analyze_nonbos
    nonbos = analyze_nonbos(cards)

    cuts, adds = [], []
    if lands < 34:
        adds.append({"card": "+ lands", "reason": f"Only {lands} lands; add {34 - lands} more for consistency."})
    if ramp < 8:
        adds.append({"card": "More ramp", "reason": f"Only {ramp} ramp pieces; aim for 8-11."})
    if draw < 8:
        adds.append({"card": "More card draw", "reason": f"Only {draw} draw sources; aim for 8-12."})
    if removal < 6:
        adds.append({"card": "More interaction", "reason": f"Only {removal} removal effects; aim for 8+."})
    # cut weakest by edhrec among nonland non-basic (never the commander)
    cmd_nm = cmd["name"] if cmd else None
    weak = sorted([c for c in cards if not c["is_land"] and not c["is_basic"] and c["name"] != cmd_nm],
                  key=lambda c: c["edhrec"], reverse=True)[:8]
    for c in weak:
        cuts.append({"card": c["name"], "reason": f"Low overall usage (EDHREC rank {c['edhrec']}); "
                     f"weakest link — consider a higher-synergy replacement."})
    # concrete category adds from scryfall
    if cmd and lands >= 30:
        if ramp < 8:
            for nc in await _fetch_category(sf, "ramp", ci, _blank_params(), 4, names):
                adds.append({"card": nc["name"], "reason": "Efficient ramp within your colors."})
        if draw < 8:
            for nc in await _fetch_category(sf, "draw", ci, _blank_params(), 4, names):
                adds.append({"card": nc["name"], "reason": "Reliable card advantage within your colors."})

    power = _estimate_power(cards, combo_res, ramp, removal)
    return {"commander": cmd, "total": total, "lands": lands, "ramp": ramp, "draw": draw,
            "removal": removal, "issues": issues, "combos": combo_res, "nonbos": nonbos,
            "cuts": cuts, "adds": adds, "power_estimate": power,
            "curve": _mana_curve(cards)}


async def find_combos_wrapper(sf, db, names):
    from combos import find_combos
    return await find_combos(names, db)


def _estimate_power(cards, combo_res, ramp, removal):
    two = sum(1 for c in combo_res["included"] if c.get("kind") == "two-card")
    fm = len({c["name"] for c in cards} & FAST_MANA)
    tutors = sum(1 for c in cards if "Tutor" in categorize(c))
    score = 4 + two * 1.2 + min(3, fm * 0.6) + min(2, tutors * 0.3) + min(1, ramp / 12)
    score = min(10, round(score, 1))
    band = "Casual (1-4)" if score < 5 else ("Mid/High (5-7)" if score < 8 else "cEDH-adjacent (8-10)")
    return {"score": score, "band": band}


def _blank_params():
    return {"excludes": set(), "local_bans": set(), "owned": set(), "toggles": {}, "max_price_per_card": None}


def _parse_decklist(text):
    import re
    names, counts = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower() in ("commander", "deck", "sideboard", "considering", "tokens", "maybeboard"):
            continue
        m = re.match(r"^(\d+)x?\s+(.+?)(?:\s+\([A-Za-z0-9]+\)\s*\S*)?$", line)
        if not m:
            m2 = re.match(r"^(.+?)(?:\s+\([A-Za-z0-9]+\)\s*\S*)?$", line)
            if m2:
                nm = m2.group(1).strip()
                if nm and nm not in names:
                    names.append(nm)
                counts[nm] = counts.get(nm, 0) + 1
            continue
        n, nm = int(m.group(1)), m.group(2).strip()
        nm = nm.split(" // ")[0]
        if nm not in names:
            names.append(nm)
        counts[nm] = counts.get(nm, 0) + n
    return names, counts


def _guess_commander(names, resolved):
    for n in names:
        c = resolved.get(n)
        if c and "legendary" in c["type"].lower() and "creature" in c["type"].lower():
            return n
    return names[0] if names else None
