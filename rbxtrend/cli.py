"""Command line interface.

    python -m rbxtrend collect          one collection pass
    python -m rbxtrend watch            collect forever, every 2h
    python -m rbxtrend report           emerging games, ranked by acceleration
    python -m rbxtrend genres           mechanic share and its direction
    python -m rbxtrend status           how much data you actually have

--db and -v are accepted on either side of the subcommand, so both of these
work and mean the same thing:

    python -m rbxtrend -v collect
    python -m rbxtrend collect -v
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import analyze, db
from .api import Client
from .collect import collect_once


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_collect(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    client = Client()
    countries = args.countries.split(",") if args.countries else ["all"]
    written = collect_once(conn, client, countries)
    print(f"wrote {written} snapshots")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    client = Client()
    countries = args.countries.split(",") if args.countries else ["all"]
    interval = args.interval * 3600
    while True:
        try:
            collect_once(conn, client, countries)
        except Exception as exc:  # keep the loop alive across transient failures
            logging.exception("collection failed: %s", exc)
        logging.info("sleeping %.1fh", args.interval)
        time.sleep(interval)


def cmd_report(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    metrics = analyze.compute(conn, window_days=args.window, min_playing=args.min_playing)

    if not metrics:
        print("No metrics yet. Run `collect` a few times first -- acceleration")
        print("needs at least 6 snapshots per game to mean anything.")
        return 1

    rows = analyze.emerging(metrics, max_age_days=args.max_age, limit=args.limit)
    if not rows:
        print("Nothing accelerating in this window. Widen --max-age or --window.")
        return 0

    print(f"\nEmerging  (window={args.window}d, age<={args.max_age}d, n={len(metrics)} games)\n")
    header = f"{'accel':>7} {'vel':>6} {'CCU':>8} {'age_d':>6} {'churn':>7} {'like':>5}  name"
    print(header)
    print("-" * len(header))
    for m in rows:
        age = f"{m.age_days:.0f}" if m.age_days is not None else "-"
        churn = f"{m.churn_ratio:.0f}" if m.churn_ratio is not None else "-"
        like = f"{m.like_ratio:.2f}" if m.like_ratio is not None else "-"
        tags = ",".join(m.tags[:2])
        print(
            f"{m.acceleration:>+7.3f} {m.velocity:>+6.2f} {m.playing:>8,} "
            f"{age:>6} {churn:>7} {like:>5}  {m.name[:42]}  [{tags}]"
        )

    print("\naccel > 0 means growth is still speeding up.")
    print("churn = visits per current CCU; high means the thumbnail beats the game.")
    return 0


def cmd_genres(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    series = analyze.genre_share(conn, days=args.window)

    if not series:
        print("No data yet. Run `collect` first.")
        return 1

    ranked = []
    for tag, points in series.items():
        latest = points[-1][1]
        slope = analyze.trend_direction(points)
        ranked.append((tag, latest, slope, len(points)))

    ranked.sort(key=lambda r: r[1], reverse=True)

    print(f"\nMechanic share of tracked CCU  (last {args.window}d)\n")
    print(f"{'share':>7} {'trend/d':>9} {'pts':>5}  mechanic")
    print("-" * 40)
    for tag, share, slope, n in ranked:
        arrow = "up" if slope > 0.001 else ("down" if slope < -0.001 else "flat")
        print(f"{share:>6.1%} {slope:>+9.4f} {n:>5}  {tag:<14} {arrow}")

    print("\nShares sum above 100% because a game can hold several tags.")
    print("Direction matters more than level: a falling share on a big mechanic")
    print("means the audience is rotating out before the raw numbers show it.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    games = len(db.tracked_universe_ids(conn))
    snaps = db.snapshot_count(conn)
    stamps = db.distinct_timestamps(conn)
    print(f"database      : {args.db}")
    print(f"games tracked : {games}")
    print(f"snapshots     : {snaps}")
    print(f"passes        : {len(stamps)}")
    if stamps:
        print(f"first pass    : {stamps[0]}")
        print(f"last pass     : {stamps[-1]}")
    if len(stamps) < 6:
        print(f"\nNeed ~6 passes before acceleration is meaningful. {6 - len(stamps)} to go.")
    return 0


def _common_flags() -> argparse.ArgumentParser:
    """Flags accepted both globally and per subcommand.

    Two argparse traps are being avoided here.

    First, `parents=` copies action objects by *reference*, so a single shared
    parser instance would let one parser's set_defaults mutate every other
    parser's default. Hence a fresh parser per call.

    Second, every default is SUPPRESS. Without that, an unspecified flag on the
    subparser writes its default into the namespace and clobbers a value already
    set at the top level -- so `--db x report` would silently fall back to the
    default database. Real defaults are applied after parsing instead.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=argparse.SUPPRESS)
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
    return common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rbxtrend", description="Roblox trend tracker", parents=[_common_flags()]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="one collection pass", parents=[_common_flags()])
    p.add_argument("--countries", default="all", help="comma separated, e.g. all,US,BR")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("watch", help="collect on a loop", parents=[_common_flags()])
    p.add_argument("--countries", default="all")
    p.add_argument("--interval", type=float, default=2.0, help="hours between passes")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("report", help="emerging games by acceleration", parents=[_common_flags()])
    p.add_argument("--window", type=float, default=3.0, help="days of history to fit")
    p.add_argument("--max-age", type=float, default=60.0, help="max game age in days")
    p.add_argument("--min-playing", type=int, default=50)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("genres", help="mechanic share over time", parents=[_common_flags()])
    p.add_argument("--window", type=float, default=14.0)
    p.set_defaults(func=cmd_genres)

    p = sub.add_parser("status", help="data coverage", parents=[_common_flags()])
    p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)

    # Applied here rather than via set_defaults, for the reason in _common_flags.
    args.db = getattr(args, "db", "rbxtrend.db")
    args.verbose = getattr(args, "verbose", False)

    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
