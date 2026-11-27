@echo off
rem Double-click me to play Last Light. Checks for updates first.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 play.py %*
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python play.py %*
  goto done
)
echo Last Light needs Python, and this computer doesn't have it yet.
echo Opening the Python download page. Install it - and TICK "Add python.exe to PATH" - then double-click this file again.
start "" "https://www.python.org/downloads/windows/"
pause
:done
if errorlevel 1 pause
