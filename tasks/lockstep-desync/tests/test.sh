#!/bin/bash
mkdir -p /logs/verifier
cd /tests
if pytest /tests/test_outputs.py -rA -p no:cacheprovider; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
