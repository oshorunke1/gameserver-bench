# lockstep-desync

A small lockstep RTS sim (spawning, an economy with a shared mine, movement, auto targeting, focus fire, crits, simultaneous damage) desyncs between peers. The agent has to make it bit for bit deterministic while keeping every documented gameplay rule.

## What it tests
- Spotting nondeterminism that hides in ordinary looking Python: iteration order, hashing, global state, timing, and float math.
- Reading a design doc and restoring the documented processing order instead of picking any order that happens to be stable.
- Fixing several independent bugs. Each one alone is enough to fail grading, so a partial fix scores 0.

## Why it's hard
Several of the problems only show up across processes, under scrambled input delivery, after earlier matches in the same process, or in rare multi hit fights. Running the demo twice in one shell can look fine. Some bugs make peers disagree, others leave peers agreeing with each other but drifting from the rules, so the agent needs both kinds of check.

## How it's graded
The sealed verifier generates unseen matches from fixed seeds. Each match runs on four separate peer processes with different `PYTHONHASHSEED` values, shuffled player lists, commands submitted out of order and early, and some peers playing a warm up match first. Every peer also replays the match a second time in the same process. All hashes (every 10 ticks) must match each other and must match a clean reference build of `RULES.md`, and the final snapshot must match exactly.

## Failure modes it catches
- Fixing only the cross process issues and missing in process state that leaks between matches.
- Sorting things in an order that is stable but not the documented one.
- "Fixing" desyncs by removing randomness, cooldowns or combat, or by weakening the hash.
- Swapping the hash for something cheaper that is not the documented sha256 format.
