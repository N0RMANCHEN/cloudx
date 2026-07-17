#!/usr/bin/env bash
set -euo pipefail

python3 scripts/check_architecture.py
python3 scripts/check_phi_cloudx_legacy_health_bridge.py
python3 scripts/check_phi_cloudx_privileged_boundary.py
python3 scripts/check_phi_cloudx_release_ordering.py
python3 scripts/check_phi_cloudx_failure_semantics.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/build.py --check
