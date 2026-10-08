# Rebuild coin balances from the economy event log

Our live game had a bad night: servers retried requests, the log shipper duplicated and reordered lines, and some clients sent garbage amounts. We need a tool that rebuilds every player's final coin balance from a raw event log and flags exploit accounts.

The rules live in `/app/POLICY.md`. Follow them exactly, they are the source of truth. Last night's log is `/app/events.jsonl`. A small sample log with its correct result is in `/app/example/` (`events.jsonl` and `expected.json`).

## What to build

Write `/app/audit.py`, run with Python 3.12 using only the standard library:

```
python3 /app/audit.py <input.jsonl> <output.json>
```

- `<input.jsonl>` is any log in the same format as `/app/events.jsonl`. Every line is one JSON object and may contain the bare tokens `NaN`, `Infinity` and `-Infinity`.
- `<output.json>` must be written as a JSON object with exactly two keys:

```json
{
  "balances": {"<player>": <integer balance>, "...": 0},
  "flagged": ["<player>", "..."]
}
```

- `balances` has one entry for every account the policy says to report, and each value is a JSON integer.
- `flagged` lists the exploit accounts, sorted ascending by plain string comparison, with no duplicates.

The program is run on other logs you have not seen, some tens of thousands of lines long, and its output is compared exactly against the correct result. It must exit with status 0 and finish each log in well under a minute. Do not rely on anything specific to the provided files.

You may also write the result for last night's log to `/app/report.json`, but only `/app/audit.py` is graded.
