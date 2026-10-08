#!/bin/bash
# runs the sealed verifier and writes the reward
mkdir -p /logs/verifier
if pytest /tests/test_outputs.py -rA -p no:cacheprovider; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
