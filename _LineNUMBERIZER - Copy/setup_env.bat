@echo off
echo Setting up LineNumberizer Environment...
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
echo Setup Complete.
echo ----------------------------------------------------------------------
echo  Starting LineNumberizer GUI...
echo ----------------------------------------------------------------------
python -m src.app
pause