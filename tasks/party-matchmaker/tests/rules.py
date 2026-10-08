"""Hard constraint checks and scoring for match output.

This is the sealed copy the verifier trusts. It mirrors the rules written
in /app/docs/match_rules.md.
"""

TEAM_SIZE = 6
WAIT_CAP_SECONDS = 1200
BASE_PLAYER_VALUE = 100.0
GAP_PENALTY = 2.0


def player_value(wait_seconds):
    wait = min(max(wait_seconds, 0), WAIT_CAP_SECONDS)
    return BASE_PLAYER_VALUE + wait / 10.0


def evaluate(queue, result):
    """Returns (errors, score, matched_players). Score is None when invalid."""
    errors = []
    now = queue["snapshot_time"]
    max_gap = queue["max_skill_gap"]
    parties = {p["party_id"]: p for p in queue["parties"]}

    if not isinstance(result, dict) or not isinstance(result.get("matches"), list):
        return ["output must be an object with a 'matches' list"], None, 0

    used_parties = set()
    used_players = set()
    score = 0.0
    matched = 0

    for n, match in enumerate(result["matches"]):
        tag = f"match {n}"
        if not isinstance(match, dict):
            errors.append(f"{tag}: not an object")
            continue
        region = match.get("region")
        teams = [match.get("team_a"), match.get("team_b")]
        if not isinstance(region, str):
            errors.append(f"{tag}: region missing")
            continue
        if not all(isinstance(t, list) for t in teams):
            errors.append(f"{tag}: team_a and team_b must be lists")
            continue

        sums = []
        value = 0.0
        bad = False
        for team in teams:
            size = 0
            skill_sum = 0
            for pid in team:
                if not isinstance(pid, str) or pid not in parties:
                    errors.append(f"{tag}: unknown party {pid!r}")
                    bad = True
                    continue
                if pid in used_parties:
                    errors.append(f"{tag}: party {pid} used twice")
                    bad = True
                    continue
                used_parties.add(pid)
                party = parties[pid]
                if region not in party["regions"]:
                    errors.append(f"{tag}: party {pid} does not accept {region}")
                    bad = True
                pv = player_value(now - party["enqueued_at"])
                for member in party["members"]:
                    if member["player_id"] in used_players:
                        errors.append(f"{tag}: player {member['player_id']} placed twice")
                        bad = True
                    used_players.add(member["player_id"])
                    size += 1
                    skill_sum += member["skill"]
                    value += pv
            if size != TEAM_SIZE:
                errors.append(f"{tag}: team has {size} players, needs {TEAM_SIZE}")
                bad = True
            sums.append(skill_sum)
        if bad:
            continue
        gap = abs(sums[0] - sums[1]) / TEAM_SIZE
        if gap > max_gap + 1e-9:
            errors.append(f"{tag}: skill gap {gap:.2f} over limit {max_gap}")
            continue
        score += value - GAP_PENALTY * gap
        matched += 2 * TEAM_SIZE

    if errors:
        return errors, None, matched
    return [], score, matched
