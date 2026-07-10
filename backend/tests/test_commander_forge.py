"""Backend tests for Commander Forge AI.

Covers: commander autocomplete, single card lookup, deck generation across
multiple modes/toggles/locks, 5-color CI, budget mode, no_two_card_combos toggle,
theme mode, moxfield export round-trip, deck improvement flow, deck list/get.

NOTE: /api/generate hits Scryfall live API and can take 20-90s. Timeouts are
set generously (up to 180s per call).
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to reading frontend/.env if REACT_APP_BACKEND_URL not exported
    try:
        from pathlib import Path
        for line in Path("/app/frontend/.env").read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
    except Exception:
        pass

API = f"{BASE_URL}/api"

# Timeouts (seconds)
FAST_T = 30
GEN_T = 180


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ------------------------------------------------------------------ health
class TestHealth:
    def test_root(self, sess):
        r = sess.get(f"{API}/", timeout=FAST_T)
        assert r.status_code == 200
        data = r.json()
        assert data.get("app") == "Commander Forge AI"
        assert "ai_available" in data


# ------------------------------------------------------------------ commanders search
class TestCommanderSearch:
    def test_search_krenko(self, sess):
        r = sess.get(f"{API}/commanders/search", params={"q": "krenko"}, timeout=FAST_T)
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) > 0
        joined = " | ".join(data["results"]).lower()
        assert "krenko" in joined

    def test_search_short_query_empty(self, sess):
        r = sess.get(f"{API}/commanders/search", params={"q": "a"}, timeout=FAST_T)
        assert r.status_code == 200
        assert r.json()["results"] == []


# ------------------------------------------------------------------ card lookup
class TestCardLookup:
    def test_card_sol_ring(self, sess):
        r = sess.get(f"{API}/card", params={"name": "Sol Ring"}, timeout=FAST_T)
        assert r.status_code == 200
        c = r.json()
        assert c["name"] == "Sol Ring"
        assert c.get("image")
        assert c.get("oracle")
        # price may be None but key should exist
        assert "price" in c
        assert c["legal"] is True

    def test_card_not_found(self, sess):
        r = sess.get(f"{API}/card", params={"name": "ZZZ_ThisCardShouldNotExist_XYZ"}, timeout=FAST_T)
        assert r.status_code == 404


# ------------------------------------------------------------------ helpers
def _assert_valid_100(result, params_note=""):
    """Common assertions on a /api/generate result."""
    assert "cards" in result, f"missing cards; keys={list(result.keys())}"
    cards = result["cards"]
    assert len(cards) == 100, f"[{params_note}] expected 100 cards, got {len(cards)}"
    val = result.get("validation", {})
    assert val.get("valid") is True, f"[{params_note}] validation issues: {val.get('issues')}"
    issues = val.get("issues", [])
    joined = " ".join(issues).lower()
    assert "off-color" not in joined and "off color" not in joined, f"off-color issue: {issues}"
    assert "illegal" not in joined and "banned" not in joined, f"illegal/banned issue: {issues}"
    assert "singleton" not in joined, f"singleton issue: {issues}"
    # required shape
    for key in ("combos", "nonbos", "simulation", "quality", "moxfield",
                "categories", "curve", "sources", "deck_id"):
        assert key in result, f"[{params_note}] missing key '{key}' in response"
    assert isinstance(result["combos"], dict)
    assert isinstance(result["nonbos"], list) or isinstance(result["nonbos"], dict)
    assert isinstance(result["moxfield"], str) and result["moxfield"].strip()


def _post_generate(sess, payload):
    r = sess.post(f"{API}/generate", json=payload, timeout=GEN_T)
    assert r.status_code == 200, f"generate failed {r.status_code}: {r.text[:500]}"
    return r.json()


# ------------------------------------------------------------------ generate: core
class TestGenerateCore:
    def test_generate_krenko_optimized(self, sess, request):
        payload = {"commander": "Krenko, Mob Boss", "mode": "optimized", "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "krenko/optimized")
        request.config.cache.set("deck_id_krenko", result["deck_id"])

    def test_generate_5color_atraxa(self, sess):
        payload = {"commander": "Atraxa, Grand Unifier", "mode": "optimized", "land_count": 36}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "atraxa/5c")
        # verify all cards are within 5c CI (which is WUBRG) - trivially all cards fit
        ci = set(result["commander"]["color_identity"])
        assert ci == set("WUBRG")
        for c in result["cards"]:
            assert set(c["color_identity"]).issubset(ci), f"off-color: {c['name']}"


# ------------------------------------------------------------------ generate: budget
class TestGenerateBudget:
    def test_budget_and_max_price(self, sess):
        payload = {"commander": "Krenko, Mob Boss", "mode": "budget",
                   "budget": 100, "max_price_per_card": 5, "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "krenko/budget")
        # No single nonbasic > $5 (owned is empty here)
        offenders = [(c["name"], c["price"]) for c in result["cards"]
                     if not c.get("is_basic") and (c.get("price") or 0) > 5]
        assert not offenders, f"cards exceed max_price_per_card: {offenders[:5]}"
        # total_price for nonbasics within budget
        assert result["total_price"] <= 100, f"total_price {result['total_price']} > budget 100"


# ------------------------------------------------------------------ generate: no two-card combos
class TestGenerateNoTwoCardCombos:
    def test_no_two_card_combos_toggle(self, sess):
        payload = {"commander": "Krenko, Mob Boss", "mode": "br3",
                   "toggles": {"no_two_card_combos": True}, "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "krenko/br3/no_2c_combos")
        included = result["combos"].get("included", [])
        two_card = [c for c in included if c.get("kind") == "two-card"]
        assert not two_card, f"expected no two-card combos, got {two_card}"


# ------------------------------------------------------------------ generate: locks/excludes/bans
class TestGenerateLocksExcludesBans:
    def test_locks_excludes_bans(self, sess):
        payload = {
            "commander": "Krenko, Mob Boss", "mode": "optimized", "land_count": 34,
            "locks": ["Sol Ring"],
            "excludes": ["Lightning Bolt"],
            "local_bans": ["Dockside Extortionist"],
        }
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "krenko/locks-excludes-bans")
        names = {c["name"] for c in result["cards"]}
        assert "Sol Ring" in names, "locked Sol Ring missing"
        assert "Lightning Bolt" not in names, "excluded Lightning Bolt present"
        assert "Dockside Extortionist" not in names, "locally banned Dockside present"


# ------------------------------------------------------------------ generate: theme mode
class TestGenerateTheme:
    def test_theme_goblin(self, sess):
        payload = {"commander": "Krenko, Mob Boss", "mode": "theme",
                   "theme": "goblin", "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "krenko/theme=goblin")

    def test_theme_cascade_averna(self, sess):
        payload = {"commander": "Averna, Chaos Bloom", "mode": "theme",
                   "theme": "cascade", "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "averna/theme=cascade")
        cascade_cards = [c["name"] for c in result["cards"]
                         if "cascade" in (c.get("oracle") or "").lower()
                         or "discover" in (c.get("oracle") or "").lower()]
        assert len(cascade_cards) >= 8, f"expected cascade theme cards, got {cascade_cards}"


# ------------------------------------------------------------------ moxfield export round-trip
class TestMoxfieldExport:
    def test_moxfield_sums_to_100(self, sess):
        payload = {"commander": "Krenko, Mob Boss", "mode": "optimized", "land_count": 34}
        result = _post_generate(sess, payload)
        _assert_valid_100(result, "moxfield-export")
        mox = result["moxfield"]
        assert mox.startswith("Commander"), f"moxfield should start with 'Commander' header: {mox[:60]!r}"
        total = 0
        line_re = re.compile(r"^(\d+)\s+(.+?)(?:\s+\([A-Za-z0-9]+\)\s*\S*)?$")
        for line in mox.splitlines():
            line = line.strip()
            if not line or line.lower() in ("commander", "deck"):
                continue
            m = line_re.match(line)
            if not m:
                # unexpected line
                pytest.fail(f"unparseable moxfield line: {line!r}")
            total += int(m.group(1))
        assert total == 100, f"moxfield lines sum to {total}, expected 100"


# ------------------------------------------------------------------ /api/improve
class TestImprove:
    def test_improve_flow(self, sess):
        decklist = "\n".join([
            "1 Krenko, Mob Boss",
            "1 Sol Ring",
            "1 Arcane Signet",
            "1 Goblin Chieftain",
            "1 Goblin King",
            "1 Impact Tremors",
            "1 Skirk Prospector",
            "1 Lightning Bolt",
            "1 Command Tower",
            "20 Mountain",
        ])
        r = sess.post(f"{API}/improve", json={"decklist": decklist, "commander": "Krenko, Mob Boss"},
                      timeout=GEN_T)
        assert r.status_code == 200, f"improve failed: {r.status_code} {r.text[:400]}"
        result = r.json()
        for k in ("issues", "cuts", "adds", "power_estimate", "combos", "nonbos"):
            assert k in result, f"improve response missing key '{k}'"
        assert isinstance(result["cuts"], list)
        assert isinstance(result["adds"], list)
        assert isinstance(result["issues"], list)
        assert "score" in result["power_estimate"]
        assert "band" in result["power_estimate"]


# ------------------------------------------------------------------ deck persistence
class TestDeckPersistence:
    def test_list_and_get(self, sess, request):
        # relies on TestGenerateCore having run
        deck_id = request.config.cache.get("deck_id_krenko", None)
        if not deck_id:
            # generate a quick one
            payload = {"commander": "Krenko, Mob Boss", "mode": "optimized", "land_count": 34}
            r = sess.post(f"{API}/generate", json=payload, timeout=GEN_T)
            assert r.status_code == 200
            deck_id = r.json()["deck_id"]
        # list
        r = sess.get(f"{API}/decks", timeout=FAST_T)
        assert r.status_code == 200
        docs = r.json()["decks"]
        assert isinstance(docs, list)
        assert any(d.get("_id") == deck_id for d in docs), "generated deck not in list"
        # get
        r = sess.get(f"{API}/decks/{deck_id}", timeout=FAST_T)
        assert r.status_code == 200
        data = r.json()
        assert data.get("count") == 100
        assert len(data["cards"]) == 100

    def test_get_missing_deck_404(self, sess):
        r = sess.get(f"{API}/decks/does-not-exist-xyz", timeout=FAST_T)
        assert r.status_code == 404
