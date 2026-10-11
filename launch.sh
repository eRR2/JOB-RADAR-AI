#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --only-binary=:all: -r requirements.lock.txt
fi
exec .venv/bin/python -m job_radar_ai
