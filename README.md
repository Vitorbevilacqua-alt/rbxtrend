# rbxtrend

Tracks Roblox discovery charts over time and answers one question: **which
mechanic is gaining attention right now, and which is quietly rotating out.**

Raw CCU can't answer that. A game at 300k flat tells you the past. A game at 4k
doubling daily tells you the future. This tool measures the second thing.

## Install

```bash
pip install -r requirements.txt
```

Only dependency is `requests`.

## Use

```bash
python -m rbxtrend collect          # one pass
python -m rbxtrend status           # how much data you have
python -m rbxtrend report           # emerging games, ranked by acceleration
python -m rbxtrend genres           # mechanic share and direction
```

**Acceleration needs about 6 passes to mean anything, and the genre trend needs
several days.** A single run tells you almost nothing — that is the nature of a
derivative, not a bug.

### Running it continuously

```bash
python -m rbxtrend watch --interval 2
```

Or, better on Windows, schedule it so it survives reboots:

```powershell
schtasks /create /tn "rbxtrend" /tr "python -m rbxtrend collect" /sc hourly /mo 2
```

Two-hour intervals are plenty. CCU is noisy on shorter horizons and you'd just
spend rate limit on nothing.

### Regional slices

```bash
python -m rbxtrend collect --countries all,US,BR
```

Worth doing. What trends in Brazil and what trends in the US are not the same
list, and the payout per Robux isn't the same either.

## Reading the output

| Metric | Meaning |
|---|---|
| `accel` | Change in growth rate across the window. **Positive means still speeding up** — this is the early-warning signal, it turns before a game hits the charts. |
| `vel` | Slope of log(CCU) per day. Log makes it scale-free, so 500→2,000 ranks against 50k→200k fairly. |
| `churn` | Visits per current CCU. High means people click in and leave: a thumbnail outperforming its own game. Low means sticky. |
| `like` | Upvote ratio. Below ~0.85 in this market usually signals something is broken. |

In `genres`, **direction beats level**. A mechanic sitting at 40% share with a
negative trend is a worse bet than one at 8% and climbing — you'd be entering as
the audience leaves.

Note that share is CCU-weighted, so a handful of giants dominate the percentages.
That's intentional (it measures attention, not game count), but it means a
mechanic can look healthy purely because one enormous title is propping it up.
Cross-check against the `report` list before concluding anything.

## Verify before trusting

```bash
python seed_test.py --db test.db
python -m rbxtrend --db test.db report --window 2 --max-age 1000
```

Seeds synthetic games with known curves. The two accelerating fixtures should
surface; the flat, decelerating, and dying ones should not. If that holds, the
math is wired correctly.

## Caveats

- These endpoints are public but **not contractually stable**. They're what the
  website itself calls. If Roblox changes a schema, collection fails loudly
  rather than silently recording zeros — that's deliberate.
- Rate limiting is conservative (1.2s between requests, exponential backoff on
  429). Don't lower it. A scraper that gets your IP blocked collects nothing.
- Classification in `genres.py` is keyword matching on title and description,
  weighted toward the title. It's approximate. Add patterns as you notice
  misses — that file is meant to be edited.
- **Coverage is limited to what discovery surfaces plus whatever you've already
  seen.** Games that never chart anywhere never enter the database. That's
  acceptable for trend detection and useless for a census.

## Why this exists

Your own Roblox recommendation feed is personalized. If you play RNG games it
shows you RNG games, which feels like market data and isn't. This is the
correction for that.
