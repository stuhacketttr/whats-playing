@echo off
rem Builds dist\WhatsPlaying\WhatsPlaying.exe (portable folder).
rem Run "build.bat debug" to keep a console window open, which shows startup errors.
cd /d %~dp0
if not exist .venv-build ( py -3.12 -m venv .venv-build || py -3 -m venv .venv-build )
call .venv-build\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt pyinstaller || goto :fail
set CONS=--noconsole
if /i "%1"=="debug" set CONS=--console
python tools\build_legal_files.py || goto :fail
pyinstaller --noconfirm --clean --name WhatsPlaying %CONS% ^
  --collect-all shazamio --collect-all shazamio_core --collect-all soundcard --collect-all webview ^
  app.py || goto :fail
copy /y .env.example dist\WhatsPlaying\.env.example >nul
copy /y LICENSE dist\WhatsPlaying\LICENSE >nul
copy /y TERMS.txt dist\WhatsPlaying\TERMS.txt >nul
copy /y THIRD_PARTY_NOTICES.txt dist\WhatsPlaying\THIRD_PARTY_NOTICES.txt >nul
echo.
echo Built: dist\WhatsPlaying\WhatsPlaying.exe
echo Put your .env (and an existing recognitions.csv, if any) in that folder.
pause
exit /b 0
:fail
echo Build failed - see messages above.
pause
exit /b 1
