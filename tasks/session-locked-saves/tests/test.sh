#!/bin/bash
# put back the shared modules in case they got edited, then run the sealed checks
mkdir -p /logs/verifier
cp /tests/pristine/datastore.py /tests/pristine/clock.py /tests/pristine/errors.py /tests/pristine/defaults.py /app/savesys/
cd /tests
pytest /tests/test_outputs.py -rA
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
