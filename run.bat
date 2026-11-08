@echo off
rem Run from source in a native window (no .exe build needed).
cd /d %~dp0
if not exist .env ( copy .env.example .env >nul & notepad .env )
if not exist .venv ( py -3.12 -m venv .venv || py -3 -m venv .venv )
call .venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt
python app.py
pause
