"""Collection pass.

Each run: walk the discovery charts to find candidate games, merge them with
everything already tracked, then record one snapshot row per game.

Run this on a schedule. Two-hour intervals are plenty -- CCU is noisy on
shorter horizons and you will spend your rate limit on nothing.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3

from . import db, genres
from .api import Client, RobloxAPIError

log = logging.getLogger(__name__)


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def discover(client: Client, countries: list[str] | None = None) -> set[int]:
    """Universe ids currently surfaced anywhere on the discovery charts."""
    found: set[int] = set()
    for country in countries or ["all"]:
        try:
            sorts = client.get_sorts(country=country)
        except RobloxAPIError as exc:
            log.error("get_sorts failed for %s: %s", country, exc)
            continue

        log.info("country=%s sorts=%d", country, len(sorts))
        for sort in sorts:
            sort_id = sort.get("sortId")
            if not sort_id:
                continue
            try:
                games = client.get_sort_content(sort_id, country=country)
            except RobloxAPIError as exc:
                log.warning("sort %s failed: %s", sort_id, exc)
                continue
            for game in games:
                uid = game.get("universeId")
                if uid:
                    found.add(int(uid))
            log.debug("sort=%s games=%d", sort.get("topic"), len(games))
    return found


def collect_once(
    conn: sqlite3.Connection, client: Client, countries: list[str] | None = None
) -> int:
    now = _utcnow()

    discovered = discover(client, countries)
    known = set(db.tracked_universe_ids(conn))
    targets = sorted(discovered | known)

    if not targets:
        log.warning("nothing to collect")
        return 0

    log.info("discovered=%d known=%d targets=%d", len(discovered), len(known), len(targets))

    details = client.get_games(targets)
    votes = client.get_votes([d["id"] for d in details])

    written = 0
    for game in details:
        uid = int(game["id"])
        name = game.get("name") or ""
        description = game.get("description") or ""
        tags = genres.classify(name, description)

        db.upsert_game(
            conn,
            {
                "universe_id": uid,
                "root_place_id": game.get("rootPlaceId"),
                "name": name,
                "description": description[:2000],
                "creator": (game.get("creator") or {}).get("name"),
                "created": game.get("created"),
                "updated": game.get("updated"),
                "genre": game.get("genre"),
                "tags": genres.tags_to_string(tags),
            },
            now,
        )

        up, down = votes.get(uid, (None, None))
        db.insert_snapshot(
            conn,
            {
                "universe_id": uid,
                "ts": now,
                "playing": game.get("playing"),
                "visits": game.get("visits"),
                "favorites": game.get("favoritedCount"),
                "upvotes": up,
                "downvotes": down,
            },
        )
        written += 1

    conn.commit()
    log.info("wrote %d snapshots at %s", written, now)
    return written
