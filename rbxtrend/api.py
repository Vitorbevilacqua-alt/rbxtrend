"""Thin client over Roblox's public web APIs.

None of these require authentication, but none are contractually stable either.
They are the same endpoints the website itself calls. If a schema changes under
you, that is expected -- fail loudly rather than silently recording zeros.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Iterable, Iterator

import requests

log = logging.getLogger(__name__)

EXPLORE_BASE = "https://apis.roblox.com/explore-api/v1"
GAMES_BASE = "https://games.roblox.com/v1"

# Roblox rate limits aggressively by IP. This is deliberately conservative --
# a scraper that gets you blocked collects nothing.
REQUEST_DELAY = 1.2
MAX_RETRIES = 4

# The batch endpoints reject more than 50 ids per call with a 400. This is not
# documented anywhere; it is just what the server enforces.
MAX_IDS_PER_REQUEST = 50


class RobloxAPIError(RuntimeError):
    pass


class Client:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                # Roblox blocks obviously-default UA strings.
                "User-Agent": "rbxtrend/0.1 (research; contact via github)",
            }
        )
        # The explore API wants a stable session id per browsing session.
        self.session_id = str(uuid.uuid4())

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = REQUEST_DELAY
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20)
            except requests.RequestException as exc:
                log.warning("request error (%s/%s): %s", attempt, MAX_RETRIES, exc)
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code == 429:
                log.warning("rate limited, backing off %.1fs", delay)
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code >= 500:
                log.warning("server error %s (%s/%s)", resp.status_code, attempt, MAX_RETRIES)
                time.sleep(delay)
                delay *= 2
                continue

            if not resp.ok:
                raise RobloxAPIError(f"{resp.status_code} for {url}: {resp.text[:200]}")

            time.sleep(REQUEST_DELAY)
            return resp.json()

        raise RobloxAPIError(f"gave up on {url} after {MAX_RETRIES} attempts")

    # --- Discovery ---------------------------------------------------------

    def get_sorts(self, country: str = "all", device: str = "computer") -> list[dict[str, Any]]:
        """The chart rows on the Roblox home page (Popular, Up-and-Coming, etc)."""
        data = self._get(
            f"{EXPLORE_BASE}/get-sorts",
            {"sessionId": self.session_id, "device": device, "country": country},
        )
        return data.get("sorts", [])

    def get_sort_content(
        self, sort_id: str, country: str = "all", device: str = "computer"
    ) -> list[dict[str, Any]]:
        """The games inside one chart row."""
        data = self._get(
            f"{EXPLORE_BASE}/get-sort-content",
            {
                "sessionId": self.session_id,
                "sortId": sort_id,
                "device": device,
                "country": country,
            },
        )
        return data.get("games", [])

    # --- Game details ------------------------------------------------------

    def get_games(self, universe_ids: Iterable[int]) -> list[dict[str, Any]]:
        """Batch game details, chunked to the server's id limit."""
        out: list[dict[str, Any]] = []
        for chunk in _chunked(list(universe_ids), MAX_IDS_PER_REQUEST):
            try:
                data = self._get(
                    f"{GAMES_BASE}/games", {"universeIds": ",".join(str(i) for i in chunk)}
                )
            except RobloxAPIError as exc:
                # One bad chunk should not cost the whole pass. This runs on a
                # schedule; losing 50 games beats losing the run.
                log.error("game detail chunk failed, skipping %d ids: %s", len(chunk), exc)
                continue
            out.extend(data.get("data", []))
        return out

    def get_votes(self, universe_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
        """Returns {universe_id: (upvotes, downvotes)}. Missing ids are simply absent."""
        out: dict[int, tuple[int, int]] = {}
        for chunk in _chunked(list(universe_ids), MAX_IDS_PER_REQUEST):
            try:
                data = self._get(
                    f"{GAMES_BASE}/games/votes",
                    {"universeIds": ",".join(str(i) for i in chunk)},
                )
            except RobloxAPIError as exc:
                log.error("vote chunk failed, skipping %d ids: %s", len(chunk), exc)
                continue
            for row in data.get("data", []):
                out[int(row["id"])] = (int(row["upVotes"]), int(row["downVotes"]))
        return out


def _chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
