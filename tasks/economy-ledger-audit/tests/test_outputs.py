"""Sealed checks for the ledger audit task.

Every case here is fresh data the agent never saw. We write a log to a temp
folder, run /app/audit.py on it, and compare the output to the known answer.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger_gen import make_case  # noqa: E402

AUDIT = "/app/audit.py"

# a tiny hand made log that walks through most of the rules once
HAND_LINES = [
    '{"seq": 140, "type": "spend", "key": "k10", "player": "cc", "amount": 300.0, "attempt": 1}',
    '{"seq": 10, "type": "grant", "key": "k1", "player": "aa", "amount": 100, "attempt": 1}',
    '{"seq": 40, "type": "spend", "key": "k2", "player": "aa", "amount": 150, "attempt": 2}',
    '{"seq": 20, "type": "spend", "key": "k2", "player": "aa", "amount": 150, "attempt": 1}',
    '{"seq": 30, "type": "grant", "key": "k3", "player": "aa", "amount": 100, "attempt": 1}',
    '{"seq": 50, "type": "spend", "key": "k2", "player": "aa", "amount": 150, "attempt": 3}',
    '{"seq": 60, "type": "spend", "key": "k2", "player": "aa", "amount": 151, "attempt": 4}',
    '{"seq": 55, "type": "grant", "key": "k4a", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 56, "type": "grant", "key": "k4b", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 57, "type": "grant", "key": "k4c", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 58, "type": "grant", "key": "k4d", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 59, "type": "grant", "key": "k4e", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 61, "type": "grant", "key": "k4f", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 62, "type": "grant", "key": "k4g", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 63, "type": "grant", "key": "k4h", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 64, "type": "grant", "key": "k4i", "player": "bb", "amount": 1000000, "attempt": 1}',
    '{"seq": 65, "type": "grant", "key": "k4", "player": "bb", "amount": 999990, "attempt": 1}',
    '{"seq": 70, "type": "purchase", "key": "k5", "player": "bb", "amount": 30, "attempt": 1}',
    '{"seq": 75, "type": "grant", "key": "k6", "player": "bb", "amount": 40, "attempt": 1}',
    '{"seq": 85, "type": "refund", "key": "k8", "player": "bb", "ref": "k5", "attempt": 1}',
    '{"seq": 80, "type": "refund", "key": "k7", "player": "bb", "ref": "k5", "attempt": 1}',
    '{"seq": 90, "type": "grant", "key": "k9", "player": "bb", "amount": 1, "attempt": 1}',
    '{"seq": 105, "type": "trade", "trade_id": "T1", "player": "aa", "counterparty": "bb", "amount": 0, "attempt": 2}',
    '{"seq": 100, "type": "trade", "trade_id": "T1", "player": "aa", "counterparty": "bb", "amount": 50, "attempt": 1}',
    '{"seq": 110, "type": "trade", "trade_id": "T1", "player": "cc", "counterparty": "aa", "amount": 5, "attempt": 1}',
    '{"seq": 120, "type": "trade", "trade_id": "T1", "player": "bb", "counterparty": "aa", "amount": 0, "attempt": 1}',
    '{"seq": 130, "type": "trade", "trade_id": "T1", "player": "bb", "counterparty": "aa", "amount": 0, "attempt": 2}',
    '{"seq": 140, "type": "spend", "key": "k10", "player": "cc", "amount": 300.0, "attempt": 1}',
    '{"seq": 150, "type": "purchase", "key": "k11", "player": "cc", "amount": "5", "attempt": 1}',
    '{"seq": 160, "type": "spend", "key": "k12", "player": "dd", "amount": NaN, "attempt": 1}',
    '{"seq": 170, "type": "trade", "trade_id": "T2", "player": "ee", "counterparty": "ee", "amount": 0, "attempt": 1}',
    '{"seq": 175, "type": "grant", "key": "k13", "player": "ee", "amount": Infinity, "attempt": 1}',
    '{"seq": 190, "type": "trade", "trade_id": "T3", "player": "aa", "counterparty": "ee", "amount": 0, "attempt": 1}',
    '{"seq": 180, "type": "trade", "trade_id": "T3", "player": "ee", "counterparty": "aa", "amount": 0, "attempt": 1}',
    '{"seq": 200, "type": "refund", "key": "k14", "player": "aa", "ref": "k5", "attempt": 1}',
]
HAND_ANSWER = {
    "balances": {"aa": 50, "bb": 10000030, "cc": 0, "dd": 0, "ee": 0},
    "flagged": ["cc", "dd"],
}

# seed, steps, players. none of these seeds were used for the /app files
CASES = [
    (60117, 250, 8),
    (60118, 1200, 16),
    (60119, 4000, 24),
    (60120, 9000, 30),
    (60121, 25000, 40),
]


def run_audit(Tmp, Text):
    InPath = Tmp / "events.jsonl"
    OutPath = Tmp / "result.json"
    InPath.write_text(Text, encoding="utf-8")
    assert os.path.isfile(AUDIT), "missing /app/audit.py"
    Proc = subprocess.run(
        [sys.executable, AUDIT, str(InPath), str(OutPath)],
        capture_output=True, text=True, timeout=300, cwd=str(Tmp),
    )
    assert Proc.returncode == 0, "audit.py crashed:\n" + Proc.stderr[-3000:]
    assert OutPath.is_file(), "audit.py did not write the output file"
    return json.loads(OutPath.read_text(encoding="utf-8"))


def check(Got, Want):
    assert isinstance(Got, dict) and set(Got) == {"balances", "flagged"}, "bad top level shape"
    Bal = Got["balances"]
    assert isinstance(Bal, dict), "balances must be an object"
    for Name, Value in Bal.items():
        assert type(Value) is int, f"balance for {Name} is not an integer: {Value!r}"
    Missing = sorted(set(Want["balances"]) - set(Bal))
    Extra = sorted(set(Bal) - set(Want["balances"]))
    assert not Missing and not Extra, f"account set wrong, missing {Missing[:5]} extra {Extra[:5]}"
    Wrong = [N for N in Want["balances"] if Bal[N] != Want["balances"][N]]
    assert not Wrong, (
        f"{len(Wrong)} wrong balances, e.g. "
        + ", ".join(f"{N}: got {Bal[N]} want {Want['balances'][N]}" for N in Wrong[:3])
    )
    assert Got["flagged"] == Want["flagged"], (
        f"flagged list wrong, got {Got['flagged']} want {Want['flagged']}"
    )


def test_hand_written_log(tmp_path):
    Text = "\n".join(HAND_LINES) + "\n"
    check(run_audit(tmp_path, Text), HAND_ANSWER)


@pytest.mark.parametrize("Seed,Steps,Players", CASES)
def test_hidden_log(tmp_path, Seed, Steps, Players):
    Text, Want = make_case(Seed, Steps, Players)
    check(run_audit(tmp_path, Text), Want)
