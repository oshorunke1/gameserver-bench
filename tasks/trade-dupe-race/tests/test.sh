#!/bin/bash
# runs the sealed tests and turns the exit code into a reward
mkdir -p /logs/verifier
cd /tmp
if pytest /tests/test_outputs.py -rA -p no:cacheprovider; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
