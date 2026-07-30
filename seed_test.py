"""Seeds the database with synthetic games so you can verify the metrics behave
before trusting them on real data.

    python seed_test.py --db test.db
    python -m rbxtrend --db test.db report
    python -m rbxtrend --db test.db genres

Expected: 'Rolling Rarity Legends' should top the emerging list (its growth
accelerates), 'Flat Old Tycoon' should not appear at all (flat), and 'Fading
Simulator' should be absent from emerging despite high CCU (decelerating).
"""

from __future__ import annotations

import argparse
import datetime as dt
import math

from rbxtrend import db, genres

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
PASSES = 24          # 24 passes
INTERVAL_H = 2.0     # every 2h -> 2 days of history


def curve(kind: str, i: int, n: int) -> int:
    """CCU at pass i out of n."""
    t = i / (n - 1)
    if kind == "accelerating":
        return int(400 * math.exp(3.2 * t * t))       # convex: speeding up
    if kind == "decelerating":
        return int(90_000 * (1 + 0.9 * math.log1p(3 * t)))  # concave: slowing
    if kind == "flat":
        return int(25_000 + 300 * math.sin(6 * t))
    if kind == "dying":
        return int(60_000 * math.exp(-1.1 * t))
    raise ValueError(kind)


FIXTURES = [
    # (universe_id, name, description, curve, age_days, visits_multiplier)
    (1, "Rolling Rarity Legends", "Roll for 1 in 1,000,000 auras and collect them", "accelerating", 12, 90),
    (2, "Fading Simulator", "Pet simulator with rebirth and hatch eggs", "decelerating", 400, 800),
    (3, "Flat Old Tycoon", "Build a base tycoon empire factory", "flat", 900, 500),
    (4, "Steal a Brainrot Clone", "Steal brainrot from other bases and raid", "dying", 200, 1200),
    (5, "Deep Sea Fishing Idle", "Fishing idle clicker, gold per second", "accelerating", 30, 120),
    (6, "Cursed Nights Horror", "Survive the nights, escape the scary forest", "flat", 150, 300),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="test.db")
    args = parser.parse_args()

    conn = db.connect(args.db)
    conn.execute("DELETE FROM snapshots")
    conn.execute("DELETE FROM games")

    for uid, name, desc, kind, age_days, vmult in FIXTURES:
        created = (NOW - dt.timedelta(days=age_days)).isoformat()
        tags = genres.classify(name, desc)
        db.upsert_game(
            conn,
            {
                "universe_id": uid,
                "root_place_id": uid * 10,
                "name": name,
                "description": desc,
                "creator": "TestStudio",
                "created": created,
                "updated": NOW.isoformat(),
                "genre": "All",
                "tags": genres.tags_to_string(tags),
            },
            NOW.isoformat(),
        )
        print(f"{name:<28} -> {tags}")

        for i in range(PASSES):
            ts = NOW - dt.timedelta(hours=INTERVAL_H * (PASSES - 1 - i))
            playing = curve(kind, i, PASSES)
            db.insert_snapshot(
                conn,
                {
                    "universe_id": uid,
                    "ts": ts.replace(microsecond=0).isoformat(),
                    "playing": playing,
                    "visits": playing * vmult,
                    "favorites": playing * 3,
                    "upvotes": playing * 8,
                    "downvotes": playing,
                },
            )

    conn.commit()
    print(f"\nseeded {len(FIXTURES)} games x {PASSES} passes into {args.db}")


if __name__ == "__main__":
    main()
