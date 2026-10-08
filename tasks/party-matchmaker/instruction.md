# Party matchmaker for 6v6

Our 6v6 mode has outgrown its matchmaker. Every tick the queue service dumps a snapshot of who is waiting, and we need a program that turns that snapshot into matches.

Write `/app/matcher.py`. It is run as:

```
python3 /app/matcher.py <queue.json> <matches.json>
```

It reads a queue snapshot and writes the matches it forms to the second path.

Everything you need is in `/app`:

- `/app/docs/queue_format.md` describes the input and output JSON.
- `/app/docs/match_rules.md` lists the hard constraints and the scoring objective. In short: parties of 1 to 6 always stay on one team, every party in a match must accept the match region, the two teams' average skills must be within the snapshot's `max_skill_gap`, and nobody can be placed twice (the same player can appear in more than one queue ticket). The score rewards matching more players, favours players who have waited longest, and lightly penalises skill imbalance.
- `/app/examples/queue_example.json` is a sample snapshot.
- `/app/tools/check_matches.py` validates a result and prints its score.

How it is graded:

- Your matcher runs on several hidden queue snapshots of different sizes (up to roughly 400 parties and 900 queued players) and settings. They are not the example file.
- Each run gets 30 seconds of wall-clock time on a single CPU core and must exit with status 0.
- On every snapshot the output must satisfy every hard constraint in `match_rules.md`. One violation fails that snapshot.
- On every snapshot your score must be at least 97% of the score a strong reference matcher reaches on the same snapshot. Beating the reference is fine.
- The grader only looks at the output file. Stick to the Python 3.12 standard library.
