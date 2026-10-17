#!/usr/bin/env bash
# First run creates the virtual environment and installs everything. Pass --lan to share on your network.
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
python serve.py "$@"
