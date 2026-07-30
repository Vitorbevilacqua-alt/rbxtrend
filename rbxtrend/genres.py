"""Mechanic classification.

Roblox's own `genre` field is near useless -- almost everything is "All" or
"Adventure". What we actually want to know is which *mechanic* is absorbing
attention this month, so we classify on name + description keywords.

A game can carry several tags. "Build a base RNG" is both rng and tycoon, and
that combination is itself the signal worth watching.
"""

from __future__ import annotations

import re

# Order matters only for readability; all patterns are evaluated.
PATTERNS: dict[str, list[str]] = {
    "rng": [
        r"\brng\b",
        r"\b1\s*in\s*[\d,.]+",          # "1 in 1,000,000"
        r"\b1/[\d,.]+\s*(k|m|b|t|qn)?\b",
        r"\broll(ing|s)?\b",
        r"\baura(s)?\b",
        r"\bluck\b",
        r"\brarit(y|ies)\b",
    ],
    "incremental": [
        r"\bincremental\b",
        r"\bidle\b",
        r"\bclicker\b",
        r"\bper\s*sec(ond)?\b",
        r"/s\b",
        r"\brebirth\b",
        r"\bprestige\b",
    ],
    "tycoon": [r"\btycoon\b", r"\bbuild a\b", r"\bfactory\b", r"\bempire\b", r"\bfarm\b"],
    "simulator": [r"\bsimulator\b", r"\bsim\b"],
    "collection": [
        r"\bcollect(ion|ing|ibles)?\b",
        r"\bcard(s)?\b",
        r"\bpet(s)?\b",
        r"\bhatch\b",
        r"\begg(s)?\b",
        r"\bindex\b",
        r"\bbestiary\b",
    ],
    "steal_pvp": [r"\bsteal\b", r"\braid(ing)?\b", r"\brob\b", r"\bheist\b"],
    "horror": [r"\bhorror\b", r"\bsurviv(e|al)\b", r"\bnight(s)?\b", r"\bescape\b", r"\bscary\b"],
    "fighting": [r"\bfight(ing)?\b", r"\bcombat\b", r"\bblade\b", r"\bpunch\b", r"\bbattlegrounds?\b"],
    "fishing": [r"\bfish(ing)?\b"],
    "obby": [r"\bobby\b", r"\bparkour\b", r"\btower of\b", r"\bonly up\b"],
    "roleplay": [r"\brole ?play\b", r"\brp\b", r"\bbrookhaven\b", r"\bcity life\b", r"\bfamily\b"],
    "anime": [r"\banime\b", r"\bmanga\b", r"\bninja\b", r"\bsaiyan\b", r"\bshinobi\b"],
    "brainrot": [r"\bbrainrot\b", r"\bskibidi\b", r"\bsigma\b", r"\brizz\b", r"\bmewing\b"],
    "dungeon": [r"\bdungeon\b", r"\braid boss\b", r"\bboss(es)?\b"],
    "sports": [r"\bfootball\b", r"\bsoccer\b", r"\bbasketball\b", r"\brac(e|ing)\b"],
}

_COMPILED = {
    tag: [re.compile(p, re.IGNORECASE) for p in patterns] for tag, patterns in PATTERNS.items()
}


def classify(name: str, description: str = "") -> list[str]:
    """Returns the mechanic tags matching this game, most specific first."""
    # Weight the title far more than the description: descriptions are keyword
    # soup written for search, titles are what the game actually is.
    haystack = f"{name} {name} {name} {description[:600]}"
    tags = [tag for tag, regexes in _COMPILED.items() if any(r.search(haystack) for r in regexes)]
    return tags or ["unclassified"]


def tags_to_string(tags: list[str]) -> str:
    return ",".join(tags)


def string_to_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [t for t in value.split(",") if t]
