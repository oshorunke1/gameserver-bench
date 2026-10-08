# Coins ledger policy (v3)

This is the rulebook the economy team uses to rebuild player coin balances from
the raw event log. The log is JSON Lines. Every line is one JSON object (one
"record"). Lines are written by many game servers, so the file is messy.

## Constants

- `MAX_TX = 1000000` largest amount a single record may carry
- `CAP = 10000000` largest balance a wallet may reach through grants or trades

Every account starts at balance 0.

## Record shapes

Every record has `seq` (integer), `type`, `player` (string) and `attempt` (integer).

| type | other fields |
|---|---|
| `grant` | `key`, `amount` |
| `spend` | `key`, `amount` |
| `purchase` | `key`, `amount` |
| `refund` | `key`, `ref` (the `key` of a purchase) |
| `trade` | `trade_id`, `counterparty` (string), `amount` |

`grant` comes from the server. `spend`, `purchase`, `refund` and `trade` are
player originated. The `amount` field may be missing or hold any JSON value,
including `NaN`, `Infinity` and `-Infinity` tokens.

## Ordering and duplicate lines

1. Records are processed in ascending `seq`, never in file order.
2. Two lines with the same `seq` are copies of one record. Process it once.

## Amount validity

A number means a JSON integer or float (booleans are not numbers).

- **Valid** amount: a JSON integer (not a float, so `50.0` is not valid) with
  `1 <= amount <= MAX_TX`. For `trade` only, `0` is also valid.
- **Severe** amount: a number that is NaN, `Infinity`, `-Infinity`, less than 0,
  or greater than `MAX_TX`.
- **Minor** amount: anything else that is not valid (missing, null, string,
  boolean, a float inside range, `0` outside trades, and so on).

## Strikes

Strikes are only ever given to the `player` of a player originated record.
A severe amount gives a severe strike. Every other strike is minor.

## Processing a `grant`, `spend`, `purchase` or `refund` record

Run these steps in order and stop at the first one that ends the record.

1. If the amount (not for refunds) is not valid, drop the record. Give a strike
   if player originated.
2. Idempotency. A key is *consumed* once a record carrying it is applied. If
   this key is already consumed, drop the record. If its payload (every field
   except `seq` and `attempt`) differs from the record that consumed the key,
   give a minor strike if player originated. Identical retries are silent.
3. Apply the type rule below. If the rule rejects the record, nothing changes
   and the key stays unconsumed, so a later retry can still succeed.
   - `grant`: rejected if the new balance would exceed `CAP`.
   - `spend`, `purchase`: rejected if the balance is below `amount`.
   - `refund`: valid only if `ref` is a key consumed by an applied `purchase`
     of the same player, and that purchase has not been refunded before. A
     valid refund credits the purchase amount and ignores `CAP`. An invalid
     refund is rejected and gives a minor strike.
4. Otherwise apply it and consume the key.

## Processing a `trade` record (a "leg")

A trade has two legs that share a `trade_id`. Legs have no key.

1. If the amount is not valid, or `counterparty` equals `player`, drop the leg
   with a strike.
2. If the trade is closed, drop the leg silently.
3. If the trade has no pending leg, this leg becomes the pending leg.
4. If this leg's `player` is the pending leg's `player`, it is a retry. Drop it
   silently.
5. If this leg's `player` is the pending leg's `counterparty` and its
   `counterparty` is the pending leg's `player`, settle the trade. Otherwise
   drop the leg with a minor strike.

Settling: pending player A gives `a`, this player B gives `b`. The trade
succeeds only if A's balance is at least `a`, B's balance is at least `b`,
and neither post trade balance (A: `bal - a + b`, B: `bal - b + a`) exceeds
`CAP`. On success both transfers happen at once. Either way the trade closes.

## Exploit accounts

An account is flagged if it has at least one severe strike, or 3 or more strikes
in total (severe and minor together).

## Output

Report every account named in any `player` or `counterparty` field anywhere in
the log, including records that were dropped.
