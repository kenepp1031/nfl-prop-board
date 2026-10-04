@echo off
setlocal
cd /d "%~dp0"
title NFL Props - refresh

rem The same pull the scheduled task does each morning, with the output left
rem on screen. Run this when you want today's numbers now rather than at the
rem next scheduled time -- after a night the machine spent switched off, or
rem when the books have just moved a line you care about.
rem
rem Safe to run while the board is open. Every file is written to a temp name
rem and renamed into place, so a reader never sees a half-written one.

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python is not on your PATH, so the refresh cannot run.
  echo Install Python 3, tick "Add python.exe to PATH", then run this again.
  echo.
  pause
  exit /b 1
)

python refresh.py
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo One or more feeds did not answer. The board will fall back to the last
  echo good copy of each, so it still opens -- the lines may just be older
  echo than today. cache\refresh.log has the detail.
) else (
  echo Everything is current. The board will open from disk.
)
echo.
pause
endlocal
exit /b %RC%
