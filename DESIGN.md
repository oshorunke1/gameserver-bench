# gameserver-bench: design notes

A small public benchmark of agentic coding tasks set in multiplayer game backend engineering, the domain the author shipped in for years (two live titles at 15k to 20k concurrent players). Every task is original and built for this repo. Tasks run in Harbor (https://github.com/laude-institute/harbor), version 0.18.

## Task layout (Harbor public template)
tasks/<slug>/
  task.toml            name = "oshorunke1/<slug>", author Olushola Shorunke, difficulty + keywords in [metadata]
  instruction.md       what the agent sees. States the goal, the inputs, and the output contract. Never hints at the method.
  environment/Dockerfile   pinned base image (python:3.12-slim with a digest-free pinned tag is fine), pinned pip versions, copies the starting codebase or data into /app
  solution/solve.sh    reference (oracle) solution, may call a Python file under solution/
  tests/test.sh        runs pytest on /tests/test_outputs.py, writes 1 or 0 to /logs/verifier/reward.txt. pytest is pre-installed in the image, so the verifier needs no network.
  tests/test_outputs.py  the sealed verifier
  README.md            for humans: what the task tests, why it is hard, what failure modes it catches. No answers.

## Rules every task must follow
1. Graded on results. Tests check behaviour and output files only.
2. Oracle passes (reward 1.0) and a do-nothing agent fails (reward 0.0). Verified with `harbor run -p tasks/<slug> --agent oracle` and `--agent nop`.
3. Hard to shortcut. Hidden test inputs differ from anything in /app, so hardcoding visible examples fails. Data generators use fixed seeds so results are deterministic.
4. Deterministic. No wall-clock or network dependence in grading. Concurrency tasks use deterministic schedulers or enough repetitions to make flakiness impossible, and must pass the oracle 3 times in a row.
5. Python 3.12 for task code and verifiers.
6. Instructions are short and precise, around 150 to 400 words.
7. Realistic: each task should read like a ticket a game backend team would pick up.

## Tasks
| slug | summary |
|---|---|
| trade-dupe-race | Fix an item duplication exploit in an async player trading service: concurrent and replayed trade requests must be atomic and idempotent. |
| session-locked-saves | Implement session locking for player save data across simulated game servers (leases, expiry, version checks) so server hops and crashes never lose or roll back progress. |
| economy-ledger-audit | Rebuild final currency balances from a messy event log (retries, duplicates, out of order, NaN and overflow values) per a written policy and flag exploit accounts. |
| party-matchmaker | Form 6v6 matches from a queue snapshot: parties stay together, regions respected, skill balanced, longest waiters first. Graded on constraint validity plus quality versus a reference. |
| remote-event-gate | Harden a server-side validator for client remote events against hostile payloads (wrong types, NaN and inf, huge or deeply nested tables, spoofed ids, flooding). Graded by a fuzzer. |
| lockstep-desync | A deterministic lockstep simulation desyncs between peers. Find and remove every source of nondeterminism so state hashes match across runs and orderings. |
