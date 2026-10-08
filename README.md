# gameserver-bench

Agentic coding tasks from multiplayer game backend engineering, packaged for [Harbor](https://github.com/laude-institute/harbor).

Each task reads like a ticket on a live game's backend team: an item dupe exploit, lost player saves, a broken economy log, a matchmaker, a hostile client, a desyncing simulation. These are the bugs that cost live games their players, and they're hard for coding agents for the same reasons they're hard for people. The invariants are subtle and the failures only show up under concurrency or hostile input. The obvious fix passes the visible tests and leaves the hole open.

## Tasks

| Task | What the agent has to do | What makes it hard |
|---|---|---|
| [trade-dupe-race](tasks/trade-dupe-race) | Fix an item duplication exploit in an async player trading service | Blind writes across servers, replay tracking per process, receipts committed separately, duplicate keys inside one offer, bad quantities. Partial fixes fail 10 to 20 of 45 tests. |
| [session-locked-saves](tasks/session-locked-saves) | Add lease based session locking to player save data across game servers | Exact lease boundaries, takeovers, stale writes from a server that lost the player, crashes mid save, restarted servers reusing ids, retry limits. 24 scenarios plus 200 seeded random histories checked against a model. |
| [economy-ledger-audit](tasks/economy-ledger-audit) | Rebuild currency balances from a messy event log and flag exploit accounts | Several interacting policy rules: sequence ordering, duplicate collapse, retries after rejection, changed payload replays, strict amount types, refunds, two sided trades. |
| [party-matchmaker](tasks/party-matchmaker) | Form 6v6 matches from a queue snapshot | Hard constraints (parties together, regions, skill gap, no double booking) plus a quality bar of 97% of a branch and bound reference. A greedy matcher scores 36 to 58%. |
| [remote-event-gate](tasks/remote-event-gate) | Harden a server side validator against hostile client payloads | Bool as int, NaN and infinity, surrogates, deep and cyclic tables, unowned items, rate limits. Graded by a seeded fuzzer that also checks zero false rejections and exact world state. |
| [lockstep-desync](tasks/lockstep-desync) | Remove every source of nondeterminism from a lockstep RTS simulation | Eight independent sources (id() ordering, float summation order, unseeded RNG, shared counters, hash seed dependence, wall clock, hash()) and the gameplay must still match a reference sim. Leaving any one in fails. |

## Design rules

- Graded on results. Verifiers check behaviour and outputs only.
- Hidden inputs. Verifiers use fresh seeded data, worlds and schedules that differ from anything in `/app`, so hardcoding examples fails.
- Deterministic. Simulated clocks and seeded generators. No wall clock or network in grading.
- Checked references. Each reference solution was cross-checked against an independent model or generator, and deliberately broken variants were confirmed to fail.

More detail is in [DESIGN.md](DESIGN.md) and each task's README.

## Validation

Every task passes its reference solution (`--agent oracle`, reward 1.0) and fails a do-nothing agent (`--agent nop`, reward 0.0). Oracles were run at least three times in a row, including all six tasks at once.

## Running

Needs Docker and Harbor 0.18 or later.

```bash
harbor run -p tasks/trade-dupe-race --agent oracle   # expect 1.0
harbor run -p tasks/trade-dupe-race --agent nop      # expect 0.0
```

Point `--agent` at any Harbor supported coding agent to benchmark it.

Note: tasks use `network_mode = "public"` because Harbor's `no-network` mode needs kernel netfilter support that Docker Desktop on Windows lacks. On a Linux host you can switch to `no-network`.

## Author

Olushola Shorunke. Built from years of shipping live multiplayer games at 15,000 to 20,000 concurrent players.

MIT licensed.
