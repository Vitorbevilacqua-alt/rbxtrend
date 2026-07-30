"""Derived metrics.

The point of this module is that raw CCU is almost useless for the decision you
actually care about, which is "what is gaining attention right now". A game at
300k CCU that is flat tells you the past. A game at 4k CCU doubling every day
tells you the future.

Three metrics carry the weight:

  velocity      slope of log(playing) per day. Log makes it scale-free, so a
                500 -> 2,000 game ranks against a 50k -> 200k game on equal terms.

  acceleration  change in velocity between the older and newer half of the
                window. This is the early-warning signal -- it turns positive
                before a game reaches the charts, which is the entire point.

  churn_ratio   visits per current CCU. High means lots of people click in and
                leave: a thumbnail that outperforms its own game. Low means
                sticky. Useful for telling a real hit from a marketing spike.
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
from dataclasses import dataclass
from typing import Sequence

from . import genres


@dataclass
class GameMetrics:
    universe_id: int
    name: str
    tags: list[str]
    playing: int
    visits: int
    favorites: int
    age_days: float | None
    velocity: float          # log-CCU per day
    acceleration: float      # change in velocity across the window
    churn_ratio: float | None
    like_ratio: float | None
    samples: int


def _parse_ts(value: str) -> dt.datetime:
    value = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _slope_per_day(points: Sequence[tuple[float, float]]) -> float:
    """Ordinary least squares slope. x in days, y in log units."""
    n = len(points)
    if n < 2:
        return 0.0
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in points)
    den = sum((x - mean_x) ** 2 for x, _ in points)
    if den == 0:
        return 0.0
    return num / den


def compute(conn: sqlite3.Connection, window_days: float = 3.0, min_playing: int = 50) -> list[GameMetrics]:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=window_days)).isoformat()

    rows = conn.execute(
        """
        SELECT g.universe_id, g.name, g.tags, g.created,
               s.ts, s.playing, s.visits, s.favorites, s.upvotes, s.downvotes
        FROM games g
        JOIN snapshots s ON s.universe_id = g.universe_id
        WHERE s.ts >= ?
        ORDER BY g.universe_id, s.ts
        """,
        (cutoff,),
    ).fetchall()

    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["universe_id"], []).append(row)

    now = dt.datetime.now(dt.timezone.utc)
    out: list[GameMetrics] = []

    for uid, series in grouped.items():
        latest = series[-1]
        playing = latest["playing"] or 0
        if playing < min_playing:
            continue

        # Convert to (days_ago_relative, log(playing)) pairs.
        t0 = _parse_ts(series[0]["ts"])
        points = [
            ((_parse_ts(r["ts"]) - t0).total_seconds() / 86400.0, math.log(max(r["playing"] or 1, 1)))
            for r in series
        ]

        velocity = _slope_per_day(points)

        # Acceleration: split the window, compare slopes. Needs enough samples
        # on each side to mean anything.
        acceleration = 0.0
        if len(points) >= 6:
            mid = len(points) // 2
            acceleration = _slope_per_day(points[mid:]) - _slope_per_day(points[:mid])

        age_days = None
        if latest["created"]:
            try:
                age_days = (now - _parse_ts(latest["created"])).total_seconds() / 86400.0
            except ValueError:
                pass

        visits = latest["visits"] or 0
        churn_ratio = (visits / playing) if playing else None

        up, down = latest["upvotes"], latest["downvotes"]
        like_ratio = None
        if up is not None and down is not None and (up + down) > 0:
            like_ratio = up / (up + down)

        out.append(
            GameMetrics(
                universe_id=uid,
                name=latest["name"] or "",
                tags=genres.string_to_tags(latest["tags"]),
                playing=playing,
                visits=visits,
                favorites=latest["favorites"] or 0,
                age_days=age_days,
                velocity=velocity,
                acceleration=acceleration,
                churn_ratio=churn_ratio,
                like_ratio=like_ratio,
                samples=len(series),
            )
        )

    return out


def emerging(
    metrics: list[GameMetrics], max_age_days: float = 60.0, limit: int = 25
) -> list[GameMetrics]:
    """Young games whose growth is still speeding up. The watchlist."""
    candidates = [
        m
        for m in metrics
        if m.acceleration > 0
        and m.velocity > 0
        and (m.age_days is None or m.age_days <= max_age_days)
    ]
    candidates.sort(key=lambda m: (m.acceleration, m.velocity), reverse=True)
    return candidates[:limit]


def genre_share(conn: sqlite3.Connection, days: float = 14.0) -> dict[str, list[tuple[str, float]]]:
    """Share of total CCU held by each mechanic tag, per snapshot timestamp.

    This is the answer to "is RNG still hot or already saturated" -- a rising
    line means the mechanic is absorbing attention, a falling one means the
    audience is rotating out even if absolute numbers still look fine.
    """
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()

    rows = conn.execute(
        """
        SELECT s.ts, s.playing, g.tags
        FROM snapshots s
        JOIN games g ON g.universe_id = s.universe_id
        WHERE s.ts >= ? AND s.playing IS NOT NULL
        """,
        (cutoff,),
    ).fetchall()

    by_ts: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}

    for row in rows:
        ts = row["ts"]
        playing = float(row["playing"] or 0)
        totals[ts] = totals.get(ts, 0.0) + playing
        bucket = by_ts.setdefault(ts, {})
        for tag in genres.string_to_tags(row["tags"]):
            # A game tagged rng+tycoon contributes to both. Shares intentionally
            # sum to more than 1; we care about direction, not partition.
            bucket[tag] = bucket.get(tag, 0.0) + playing

    series: dict[str, list[tuple[str, float]]] = {}
    for ts in sorted(by_ts):
        total = totals.get(ts, 0.0)
        if total <= 0:
            continue
        for tag, value in by_ts[ts].items():
            series.setdefault(tag, []).append((ts, value / total))

    return series


def trend_direction(points: list[tuple[str, float]]) -> float:
    """Slope of a share series. Positive means the mechanic is gaining ground."""
    if len(points) < 3:
        return 0.0
    t0 = _parse_ts(points[0][0])
    xy = [((_parse_ts(ts) - t0).total_seconds() / 86400.0, value) for ts, value in points]
    return _slope_per_day(xy)
