# remote-event-gate

A game server takes client remote events (shop purchase, equip, chat, move,
trade offer) as decoded payloads and hands them to handlers that trust their
input. The validator in front of them is an alpha era stub. The agent has to
turn it into a real trust boundary that follows a written protocol.

## What it tests

- Exact type discipline in a dynamic language: `bool` is an `int` in Python,
  `3.0` is not an int here, NaN slips through naive range checks, and huge
  ints blow up float math.
- String hygiene: length limits, control characters, surrogates left behind by
  undecodable bytes, and id patterns where a trailing newline or a lookalike
  letter must not pass.
- Structural safety: deeply nested and self referencing payloads, non string
  dict keys, extra or missing keys, payloads that aren't dicts at all, and
  unhashable values where a name or id is expected.
- Business rules that need world state: ownership, slot matching, stack caps,
  affordability, movement step limits, and not trading away an equipped copy.
- A sliding window rate limiter on an injected clock, where only accepted
  events count.

## Why it is hard

Nothing in the visible code fails on legit traffic, so the agent has to read
the protocol carefully and think adversarially. Being too strict is punished
as hard as being too loose: the legit generator uses emoji, combining marks,
zero width joiners, non breaking spaces, line separators, boundary values and
exact maximum step moves.

## How it is graded

`tests/test_outputs.py` builds hidden worlds and catalogs from fixed seeds and
replays legit streams, bursty streams that hit the rate limits, one stream per
hostile category, and fully mixed fuzz streams. A reference model written from
the protocol predicts every decision and the resulting world. After each event
the verifier checks for exceptions, the ok flag, and an exact world match.

## Failure modes it catches

Crashes on recursion or cycles, `bool` accepted as a quantity, NaN or infinite
coordinates, negative quantities that mint coins, duplicate trade entries that
push inventory negative, `re.match` with `$` accepting `"sword\n"`, fixed
window rate limiters, counting rejected events against the limit, side effects
from rejected events, and over strict text filters that drop real chat.
