#!/usr/bin/env bash
# run.sh: see the Garden work on the synthetic feeds in examples/sources/, with no setup.
# It needs no network, no Herdr and no config of yours. The output must match
# examples/expected-output.txt (a test checks it).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 src/garden.py --demo
echo
echo "The prompt the d key (diff) sends for the first item:"
python3 src/garden.py --demo prompt diff acme/review-plugin
