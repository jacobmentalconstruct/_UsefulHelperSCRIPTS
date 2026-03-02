@echo off
echo Setting up System Thinker Environment...
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
echo Setup Complete. Run via: python -m src.app
pause