# party-matchmaker

A ticket from a live 6v6 game: replace the matchmaker that turns a queue snapshot into matches.

## What it tests

The agent writes `/app/matcher.py`, which reads a queue snapshot (parties of 1 to 6 players, accepted regions, enqueue time, per player skill) and writes 6v6 matches. The grader runs it on nine hidden seeded snapshots, from a 7 party edge case up to 400 parties, with different skill gap limits, region mixes, skill spreads and rates of duplicate player tickets.

Each output must pass every hard rule (each party kept together on one team, exact team sizes, region accepted by every party, team average skill gap under the limit, no party or player used twice). The score (players matched, weighted up by wait time, minus a small imbalance penalty) must reach 97% of a reference matcher's score on every snapshot. Each run has a 30 second limit on one core.

## Why it's hard

It's a set packing problem with a balance side constraint. Team sizes have to add up to exactly 6 from party sizes, multi region parties can go to several pools, and stale duplicate tickets make some parties mutually exclusive. Plain greedy approaches strand big parties without fillers or fail the balance check and throw the match away. On the hidden set, a reasonable greedy matcher (longest waiters first, put each party on the weaker team) scores 36% to 58% of the reference, and a one pass "build the best match around each long waiter" approach lands between 80% and 98%, so it fails too.

## How the bar was set

The reference is deterministic, so the expected scores are baked into the verifier. During authoring it was rerun with about 10x the search budget (more starts, wider candidate pools, deeper search) and that only moved scores by under 1% in either direction, so 97% leaves headroom and still keeps weak heuristics out. A loose upper bound (best possible player values per connected region group, ignoring party shapes and balance) sits a few percent above the reference on the larger queues and further above on small ones, where region groups leave remainders.

## Failure modes it catches

- Splitting a party across teams, or teams that aren't exactly 6
- Ignoring region lists, or picking a region one party doesn't accept
- Matching the same player twice through two different tickets
- Skipping the balance check, or checking totals against the average based limit
- Too slow on the 400 party queue
- Matching well below what's achievable
