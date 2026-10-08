# trade-dupe-race

An asyncio player trading service has an item duplication exploit. The agent
gets a small repo (`/app/tradesvc`) with a store contract and written trade
rules, and has to make the service hold those rules when many trades run at
once across several service instances that share one versioned store.

## What it tests

- Race conditions across awaits in async Python, where a read and a later
  write can interleave with other coroutines.
- Cross-process correctness: in-process locks aren't enough because several
  service instances share the store, so the fix has to lean on what the store
  contract offers.
- Idempotency that survives concurrent replays on different servers, plus
  detecting a reused request id with a different payload.
- Input validation that's easy to get wrong when an offer can list the same
  item more than once.
- Slot limit accounting that reflects what's given away as well as received.
- Failure handling: an outage applies nothing and leaves later retries of the
  same request free to succeed.

## Why it's hard

Several defects interact. Fixing the obvious race inside one process still
leaves cross-server dupes. The validation dupes survive a fix to the replay
path too. Rejecting on any write conflict looks safe but breaks
liveness, which the verifier checks with trades that are all valid at once.

## How it's graded

The sealed verifier plugs in its own store that follows the documented
contract, inserts seeded random awaits around every call, injects outages,
and checks each row as it's written. It runs targeted scenarios plus a seeded
soak with several servers, replays and failures, then compares the final
state to the starting state plus the completed trades. Grading is on
results and stored state only. Runs are deterministic.

## Failure modes it catches

- Duplicated or lost items and gold under concurrency
- Replays applied twice, or failures cached forever
- Negative quantities, self trades and repeated stack entries used as exploits
- Over or under rejecting on the slot limit
- Conflicts surfaced to players, or trades that hang
