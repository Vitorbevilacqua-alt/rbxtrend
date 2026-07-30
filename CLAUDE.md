# rbxtrend — working agreement

Tracks Roblox discovery charts over time to answer one question: **which mechanic
is gaining attention right now, and which is quietly rotating out.**

It exists because a personal Roblox recommendation feed is personalized. Play RNG
games and it shows RNG games, which feels like market data and isn't. This is the
correction for that. Any change that makes the tool easier to confuse with the
feed is a regression.

---

## Constraints learned the hard way

Each of these cost a debugging cycle. Please don't undo them.

**1. Batch endpoints cap at 50 ids, not 100.**
`games.roblox.com/v1/games` and `/games/votes` return `400 Too many universe IDs
were requested` above 50. This is undocumented; it's just what the server
enforces. `MAX_IDS_PER_REQUEST` in `api.py` is not a tunable.

**2. `REQUEST_DELAY = 1.2` is deliberate.**
Roblox rate limits by IP. A scraper that gets blocked collects nothing, which is
strictly worse than a slow one. Do not lower it to "speed up" a run that already
takes 40 seconds.

**3. Checkpoint the WAL before committing the database.**
`db.checkpoint()` runs at the end of every `collect_once`. Without it the newest
rows live in the `-wal` sidecar, and committing only the `.db` to git silently
loses the most recent pass — exactly the data that mattered. Verified: with the
checkpoint, the `.db` alone contains everything.

**4. The argparse `parents=` setup is not over-engineered.**
`parents=` copies action objects *by reference*. A single shared parser instance
lets one parser's `set_defaults` mutate every other parser's default, so
`--db x report` silently fell back to the default database. Hence a fresh parser
per call and `SUPPRESS` on every default, with real defaults applied after
parsing. Simplifying this reintroduces a bug that fails silently.

**5. `.gitignore` ignores `*.db` but allows `!data/*.db`.**
Local databases stay out of git. The CI-collected one is the whole point of the
Actions run and must be tracked.

**6. Never merge the local and CI databases.**
They're separate on purpose — the point is comparing whether a datacenter IP can
sustain collection at all, versus a residential one. Merging destroys the
experiment.

---

## Metric design

Raw CCU answers the wrong question. A game at 300k flat describes the past; a
game at 4k doubling daily describes the future.

| Metric | Definition | Why |
|---|---|---|
| `velocity` | OLS slope of log(playing) per day | Log makes it scale-free, so 500→2,000 ranks fairly against 50k→200k |
| `acceleration` | velocity(recent half) − velocity(older half) | The leading indicator. Turns positive *before* a game charts, which is the entire point of the tool |
| `churn_ratio` | visits ÷ current CCU | High means people click in and leave: a thumbnail outperforming its own game. Separates a real hit from a marketing spike |

Acceleration needs ~6 passes per game to mean anything; genre trend needs 4–5
days. Reports that run on thinner data should say so rather than print noise.

In `genre_share`, shares intentionally sum above 100% — a game tagged `rng` and
`tycoon` counts toward both. It measures attention, not partition. It's also
CCU-weighted, so a handful of giants dominate; that's correct but means a
mechanic can look healthy purely because one enormous title props it up.

---

## Conventions

- Standard library plus `requests`. Resist adding pandas for something a
  20-line OLS already does.
- Type hints throughout, `from __future__ import annotations`.
- The collector is deliberately dumb: it records, it does not judge. All
  interpretation lives in `analyze.py`, so metric changes never require
  re-collection.
- Fail loudly on schema surprises. These endpoints are public but not
  contractually stable; silently recording zeros is worse than crashing.
- One bad chunk must not kill a scheduled run. Log it, skip those ids, continue.
- Comments explain *why*, not *what*.

## Editing `genres.py`

Keyword classification, weighted toward the title (descriptions are keyword soup
written for search; titles are what the game actually is). It's approximate and
meant to be edited — add patterns as you notice misses. Adding a tag changes
future classification only, so re-run `collect` before reading genre trends.

---

## Related repo

`rbx-core` — the reusable Roblox game foundation this research feeds into. It has
its own CLAUDE.md with its own invariants. **Kept deliberately separate**: each
game title is a fork of that core, and a monorepo would destroy the property that
makes title #10 cost two days instead of two weeks.
