# Queue snapshot format

The matchmaking service dumps the waiting queue as one JSON object.

```json
{
  "snapshot_time": 1760042445,
  "max_skill_gap": 50,
  "parties": [
    {
      "party_id": "P5928",
      "regions": ["na-east", "eu-west"],
      "enqueued_at": 1760042108,
      "members": [
        {"player_id": "U00117", "skill": 1737}
      ]
    }
  ]
}
```

- `snapshot_time` is the unix time (seconds) the snapshot was taken.
- `max_skill_gap` is the largest allowed difference between the two teams' average skill in one match.
- `parties` lists every ticket in the queue, in no particular order.
  - `party_id` is unique per ticket.
  - `regions` are the server regions this party will accept. At least one.
  - `enqueued_at` is the unix time the party joined the queue. Wait time is `snapshot_time - enqueued_at`.
  - `members` holds 1 to 6 players, each with an integer `skill`.

The queue service is eventually consistent, so a `player_id` can show up in more than one party (for example a stale solo ticket left behind after the player joined a group). Each entry describes the same player with the same skill.

# Match output format

```json
{
  "matches": [
    {"region": "na-east", "team_a": ["P5928", "P7461"], "team_b": ["P8916"]}
  ]
}
```

Teams are lists of `party_id`s. Parties not listed in any match stay in the queue for the next tick. An empty `matches` list is valid output.
