#!/bin/bash
# runs the sealed verifier and writes 1 for a full pass, 0 otherwise
mkdir -p /logs/verifier
if pytest /tests/test_outputs.py -rA; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
