@echo off
rem Builds dist\WhatsPlaying.exe - ONE self-contained file (Python and all libraries inside).
rem Run "build-onefile.bat debug" to keep a console window open, which shows startup errors.
rem The .exe creates .env, recognitions.csv and whatsplaying.log next to itself.
cd /d %~dp0
if not exist .venv-build ( py -3.12 -m venv .venv-build || py -3 -m venv .venv-build )
call .venv-build\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt pyinstaller || goto :fail
set CONS=--noconsole
if /i "%1"=="debug" set CONS=--console
python tools\build_legal_files.py || goto :fail
pyinstaller --noconfirm --clean --onefile --name WhatsPlaying %CONS% ^
  --workpath build-onefile --specpath build-onefile ^
  --add-data "%~dp0.env.example;." ^
  --add-data "%~dp0THIRD_PARTY_NOTICES.txt;." ^
  --collect-all shazamio --collect-all shazamio_core --collect-all soundcard --collect-all webview ^
  app.py || goto :fail
echo.
echo Built: dist\WhatsPlaying.exe
echo Put it in its own folder (it saves .env, recognitions.csv and logs beside itself).
pause
exit /b 0
:fail
echo Build failed - see messages above.
pause
exit /b 1
