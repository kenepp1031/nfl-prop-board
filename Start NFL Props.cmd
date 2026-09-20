@echo off
setlocal
cd /d "%~dp0"
title NFL Prop Board

rem If a board is already serving on this port, just open that one. Starting a
rem second copy fails with "port already in use", and on a double-click the
rem window closes too fast to read why.
powershell -NoProfile -Command "try { $null = Invoke-WebRequest 'http://localhost:8502' -UseBasicParsing -TimeoutSec 3; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo Board is already running. Opening it.
  start "" "http://localhost:8502"
  exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python is not on your PATH, so the board cannot start.
  echo Install Python 3, tick "Add python.exe to PATH", then run this again.
  echo.
  pause
  exit /b 1
)

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Streamlit is missing. Installing it now...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Install failed. Nothing has been changed.
    pause
    exit /b 1
  )
)

echo Starting the board on http://localhost:8502
echo Leave this window open while you use it. Close it to stop the board.
echo.
python -m streamlit run app.py --server.port 8502

rem A non-zero exit means it never came up. Hold the window open so the reason
rem is readable instead of flashing past.
if errorlevel 1 (
  echo.
  echo The board stopped with an error. The message above says why.
  pause
)
endlocal
