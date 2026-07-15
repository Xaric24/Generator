"""Fast unit tests for deck-building filters (no network required)."""

from backend.engine import categorize, land_fits_color_identity, toggle_block


def card(name="Test Card", oracle="", card_type="Sorcery", **overrides):
    value = {
        "name": name, "oracle": oracle, "type": card_type,
        "is_land": "Land" in card_type, "is_basic": False,
        "is_mdfc": False, "produced_mana": [],
    }
    value.update(overrides)
    return value


def test_disable_tutors_blocks_type_specific_tutors():
    tutor = card(oracle="Search your library for a creature card, reveal it, put it into your hand, then shuffle.")
    assert "Tutor" in categorize(tutor)
    assert toggle_block(tutor, {"no_tutors": True}) == "tutors disabled"


def test_disable_tutors_does_not_block_basic_land_ramp():
    ramp = card(oracle="Search your library for a basic land card, put it onto the battlefield, then shuffle.")
    assert "Ramp" in categorize(ramp)
    assert "Tutor" not in categorize(ramp)
    assert toggle_block(ramp, {"no_tutors": True}) is None


def test_mono_green_rejects_urborg_and_yavimaya():
    urborg = card("Urborg, Tomb of Yawgmoth", card_type="Legendary Land", produced_mana=["B"])
    yavimaya = card("Yavimaya, Cradle of Growth", card_type="Legendary Land", produced_mana=["G"])
    assert not land_fits_color_identity(urborg, ["G"])
    assert not land_fits_color_identity(yavimaya, ["G"])


def test_land_must_produce_a_commander_color_when_colored():
    black_land = card("Black Utility Land", card_type="Land", produced_mana=["B"])
    green_land = card("Green Utility Land", card_type="Land", produced_mana=["G"])
    assert not land_fits_color_identity(black_land, ["G"])
    assert land_fits_color_identity(green_land, ["G"])


def test_mono_white_rejects_fetches_that_cannot_find_plains():
    bad_fetch = card(
        "Bloodstained Mire",
        oracle="{T}, Pay 1 life, Sacrifice this land: Search your library for a Swamp or Mountain card, put it onto the battlefield, then shuffle.",
        card_type="Land",
    )
    good_fetch = card(
        "Arid Mesa",
        oracle="{T}, Pay 1 life, Sacrifice this land: Search your library for a Mountain or Plains card, put it onto the battlefield, then shuffle.",
        card_type="Land",
    )
    assert not land_fits_color_identity(bad_fetch, ["W"])
    assert land_fits_color_identity(good_fetch, ["W"])


def test_mono_white_rejects_generic_rainbow_lands_but_allows_commander_lands():
    city = card("City of Brass", oracle="{T}: Add one mana of any color.", card_type="Land", produced_mana=list("WUBRG"))
    command_tower = card(
        "Command Tower",
        oracle="{T}: Add one mana of any color in your commander's color identity.",
        card_type="Land",
        produced_mana=list("WUBRG"),
    )
    assert not land_fits_color_identity(city, ["W"])
    assert land_fits_color_identity(command_tower, ["W"])
