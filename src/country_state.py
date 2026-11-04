"""Country and date selection shared by both pages."""

from __future__ import annotations

CONTEXT_KEY = "spotify_chart_context"


def initialize_context(state, snapshot_date: str, valid_codes) -> dict:
    valid = set(valid_codes)
    previous = state.get(CONTEXT_KEY, {})
    context = {"version": 1, "snapshot_date": snapshot_date,
               "country_a": previous.get("country_a"), "country_b": previous.get("country_b")}
    for slot in ("country_a", "country_b"):
        if context[slot] not in valid:
            context[slot] = None
    if context["country_a"] == context["country_b"]:
        context["country_b"] = None
    state[CONTEXT_KEY] = context
    return dict(context)


def select_country(state, slot: str, code: str | None, valid_codes) -> str | None:
    if slot not in {"country_a", "country_b"}:
        raise ValueError("Unknown country selection slot")
    if code is not None and code not in set(valid_codes):
        return "This country has no eligible chart on the selected date."
    context = dict(state[CONTEXT_KEY])
    other = "country_b" if slot == "country_a" else "country_a"
    if code is not None and context[other] == code:
        return "Country A and Country B must be different. Choose another country."
    context[slot] = code
    state[CONTEXT_KEY] = context
    return None


def reset_context(state) -> None:
    context = dict(state[CONTEXT_KEY])
    context.update(country_a=None, country_b=None)
    state[CONTEXT_KEY] = context


def get_chart_context(state) -> dict:
    return dict(state[CONTEXT_KEY])
