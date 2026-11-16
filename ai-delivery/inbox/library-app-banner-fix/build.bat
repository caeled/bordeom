@echo off
rem Build dist\LibraryApp\LibraryApp.exe with the banner and icon baked in.
rem Builds straight from LibraryApp.py (never from an old LibraryApp.spec),
rem keeps your LibraryData across the rebuild, and checks that banner.png
rem really landed in the bundle.
setlocal
cd /d "%~dp0"

if not exist banner.png (
  echo banner.png is missing from %CD% - run this from the repo folder.
  exit /b 1
)

python -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

rem PyInstaller deletes dist\LibraryApp on every build, LibraryData included.
set "SAVED=%TEMP%\LibraryData-%RANDOM%%RANDOM%"
if exist "dist\LibraryApp\LibraryData" (
  echo Saving your library to %SAVED%
  move "dist\LibraryApp\LibraryData" "%SAVED%" >nul
  if errorlevel 1 (
    echo Could not move LibraryData aside; stopping so it is not deleted.
    exit /b 1
  )
)

if exist LibraryApp.spec del LibraryApp.spec
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm --clean --windowed --icon LibraryApp.ico --name LibraryApp --add-data "banner.png;." --add-data "LibraryApp.ico;." LibraryApp.py
set "BUILD_RESULT=%errorlevel%"

if exist "%SAVED%" (
  if not exist "dist\LibraryApp" mkdir "dist\LibraryApp"
  move "%SAVED%" "dist\LibraryApp\LibraryData" >nul
  echo Library restored to dist\LibraryApp\LibraryData
)

if not "%BUILD_RESULT%"=="0" (
  echo PyInstaller failed - see the messages above. The old exe was NOT replaced.
  exit /b 1
)

if exist "dist\LibraryApp\_internal\banner.png" (
  echo OK: banner.png is in dist\LibraryApp\_internal
) else if exist "dist\LibraryApp\banner.png" (
  echo OK: banner.png is in dist\LibraryApp
) else (
  echo WARNING: banner.png is not in the build output.
  exit /b 1
)
echo Done: dist\LibraryApp\LibraryApp.exe
