@echo off
rem First run creates the virtual environment and installs everything. Pass --lan to share on your network.
cd /d "%~dp0"
if not exist venv python -m venv venv
call venv\Scripts\activate
pip install -q -r requirements.txt
python serve.py %*
