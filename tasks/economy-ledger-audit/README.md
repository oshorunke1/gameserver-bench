# economy-ledger-audit

A ticket you would see on a live game's economy team after an incident. The agent gets a written ledger policy, a messy JSONL event log and one small worked example, and has to ship `/app/audit.py`, a tool that rebuilds final coin balances and flags exploit accounts for any log in that format.

## What it tests

- Reading a dense spec carefully and implementing every rule, including the boring ones.
- Event sourcing basics: ordering by server sequence instead of arrival, collapsing copied lines, idempotency keys.
- Treating hostile numeric input correctly in Python (NaN, infinities, floats that look like integers, huge integers, booleans, strings).
- Getting interacting rules right. A rejected request leaves its key open for a later retry. A replay with a changed payload is a strike while an identical one is silent. Refunds skip the wallet cap while grants and trades respect it. Trades check each side's gross outgoing amount, and a failed trade closes for good.

## How it is graded

The verifier generates fresh logs from fixed seeds that do not match anything in `/app`, runs the agent's program on each, and compares balances and flagged accounts exactly. One small hand written log also walks through the rules one by one. The generator keeps its own books while it writes the log, and the reference solution was written separately and checked against it on many seeds.

## Common failure modes it catches

- Processing in file order, or counting a copied line twice.
- Burning an idempotency key on a rejected request, or ignoring payload changes on replays.
- Accepting `300.0` or `"100"` as a valid amount, or crashing on `NaN`.
- Capping refunds, rejecting zero amount trade legs, or checking only the net change of a trade.
- Letting a failed trade settle later, or giving strikes for server grants.
