# session-locked-saves

A ticket every live multiplayer game ends up with: players hop servers and
lose progress. The agent gets a small save service (an in-memory key-value
store with versioned conditional writes, a simulated clock, a server loop
and a naive `SessionStore` with no locking) and has to add lease-based
session locking that holds up under server hops, crashes, restarts, lease
expiry and flaky store writes.

## What it tests

- Using conditional writes correctly so two servers can never both win a race for the same player.
- Telling "my lease ran out but nobody took it" apart from "someone took my player", and refusing stale writes in the second case only.
- Restarted processes reusing a `server_id` taking over their own players while the old process is shut out.
- Resolving ambiguous write timeouts by reading back, so a write that landed counts as a success and its own version bump doesn't trip the retry.
- A precise retry budget that leaves the store and the lock untouched when it gives up.

## How it's graded

The verifier swaps in pristine copies of the shared modules and drives the
agent's `SessionStore` through hidden scenarios on the simulated clock:
exact lease boundaries, takeovers, zombie writes, races injected inside a
`put` through a store hook, and every fault type. It then replays 200 seeded
random multi-server histories (loads, saves, renews, releases, clock jumps,
restarts, zombie calls and fault bursts) and compares every outcome and the
final stored data with a small model of the written contract. Only
observable behaviour counts. The record format is free.

## Why it's hard

The happy path is easy and the visible examples barely touch the failure
modes. The traps are the interactions: a timeout that landed bumps the
version, so a naive retry reports a lost lease; checking ownership by
server id lets a crashed predecessor keep writing; checking expiry locally
rejects legal saves; and an off by one on the lease boundary shows up in
almost every random history.
