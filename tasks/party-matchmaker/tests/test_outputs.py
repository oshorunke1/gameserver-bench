"""Sealed verifier for party-matchmaker.

Runs /app/matcher.py on hidden seeded queues, checks every hard rule, and
compares the score to what the reference matcher got on the same queue.
"""

import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from queue_gen import generate  # noqa: E402
from rules import evaluate  # noqa: E402

MATCHER = "/app/matcher.py"
TIME_LIMIT_SECONDS = 30
TOLERANCE = 0.97

# each hidden queue plus the score the reference matcher reached on it
CASES = [
    (dict(seed=101, n_parties=60, max_gap=50), 12361.1667),
    (dict(seed=202, n_parties=140, max_gap=45, spread=1.4), 34023.6333),
    (dict(seed=303, n_parties=220, max_gap=40), 60602.9333),
    (dict(seed=404, n_parties=320, max_gap=50, neighbor_prob=0.6), 85844.6667),
    (dict(seed=505, n_parties=180, max_gap=30), 47827.0667),
    (dict(seed=606, n_parties=260, max_gap=55, dup_rate=0.12), 63304.4333),
    (dict(seed=707, n_parties=100, max_gap=45, region_weights=[1, 1, 3, 1, 1, 4, 4]), 23327.5667),
    (dict(seed=808, n_parties=400, max_gap=45), 102372.8667),
    (dict(seed=909, n_parties=7, max_gap=40), 0.0),
]


def run_matcher(queue):
    with tempfile.TemporaryDirectory() as tmp:
        qpath = os.path.join(tmp, "queue.json")
        opath = os.path.join(tmp, "matches.json")
        with open(qpath, "w") as f:
            json.dump(queue, f)
        proc = subprocess.run(
            [sys.executable, MATCHER, qpath, opath],
            cwd=tmp, capture_output=True, text=True, timeout=TIME_LIMIT_SECONDS,
        )
        assert proc.returncode == 0, f"matcher exited {proc.returncode}: {proc.stderr[-2000:]}"
        assert os.path.exists(opath), "matcher did not write the output file"
        with open(opath) as f:
            return json.load(f)


def test_matcher_exists():
    assert os.path.isfile(MATCHER), f"{MATCHER} is missing"


@pytest.mark.parametrize("params,ref_score", CASES, ids=[f"seed{c[0]['seed']}" for c in CASES])
def test_hidden_queue(params, ref_score):
    queue = generate(**params)
    try:
        result = run_matcher(queue)
    except subprocess.TimeoutExpired:
        pytest.fail(f"matcher took longer than {TIME_LIMIT_SECONDS}s")
    errors, score, matched = evaluate(queue, result)
    assert not errors, "hard rule violations: " + "; ".join(errors[:10])
    need = TOLERANCE * ref_score
    assert score >= need - 1e-6, (
        f"score {score:.1f} with {matched} players matched is below the bar "
        f"{need:.1f} (reference {ref_score:.1f})"
    )
