@echo off
rem Builds the app folder with PyInstaller, then wraps it in a Windows installer:
rem   installer\WhatsPlaying-Setup-<version>.exe
rem Usage: build-installer.bat [version]     e.g. build-installer.bat 1.1.0
rem Needs Inno Setup 6.3+  (winget install JRSoftware.InnoSetup  or  https://jrsoftware.org/isdl.php)
cd /d %~dp0

set VERSION=1.1.0
if not "%~1"=="" set VERSION=%~1

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto :noinno

if not exist .venv-build ( py -3.12 -m venv .venv-build || py -3 -m venv .venv-build )
call .venv-build\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt pyinstaller || goto :fail

python tools\build_legal_files.py || goto :fail
pyinstaller --noconfirm --clean --name WhatsPlaying --noconsole ^
  --collect-all shazamio --collect-all shazamio_core --collect-all soundcard --collect-all webview ^
  app.py || goto :fail
copy /y .env.example dist\WhatsPlaying\.env.example >nul
copy /y LICENSE dist\WhatsPlaying\LICENSE >nul
copy /y TERMS.txt dist\WhatsPlaying\TERMS.txt >nul
copy /y THIRD_PARTY_NOTICES.txt dist\WhatsPlaying\THIRD_PARTY_NOTICES.txt >nul

"%ISCC%" /DMyAppVersion=%VERSION% installer.iss || goto :fail

echo.
echo Built: installer\WhatsPlaying-Setup-%VERSION%.exe
pause
exit /b 0

:noinno
echo Inno Setup 6.3 or later was not found.
echo Install it with:  winget install JRSoftware.InnoSetup
echo or download it from https://jrsoftware.org/isdl.php  then run this again.
pause
exit /b 1

:fail
echo Build failed - see messages above.
echo If the app itself fails to start, run build.bat debug to see its startup errors.
pause
exit /b 1
