@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw LibraryApp.py
) else (
  python LibraryApp.py
  pause
)
