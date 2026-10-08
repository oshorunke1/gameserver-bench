# Match rules

Every match is 6v6: two teams of exactly 6 players.

## Hard constraints

A result that breaks any of these is rejected as a whole.

1. Every `party_id` in the output exists in the snapshot.
2. A party is placed at most once across all matches, and all of its members play on the same team (you place parties, not players).
3. Each team has exactly 6 players in total.
4. The match `region` is in the `regions` list of every party in that match.
5. No player is placed twice. If two parties share a `player_id`, at most one of them can be matched.
6. Skill balance: `abs(sum_skill_team_a - sum_skill_team_b) / 6 <= max_skill_gap`.

## Objective

Among valid results, a higher score is better.

```
wait_s        = min(max(snapshot_time - enqueued_at, 0), 1200)
player_value  = 100 + wait_s / 10            # every matched player, by their party's wait
match_score   = sum(player_value of the 12 players) - 2 * abs(sum_a - sum_b) / 6
total_score   = sum(match_score over all matches)
```

So matching more players matters most, players who have waited longer are worth more (up to 2.2 times a fresh ticket), and lopsided matches cost a little.

`tools/check_matches.py` validates a result against a queue and prints its score.
