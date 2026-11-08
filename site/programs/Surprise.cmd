@echo off
cd /d "%~dp0"
python surprise.py
if errorlevel 1 pause
