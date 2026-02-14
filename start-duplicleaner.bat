@echo off
setlocal

echo 1) Normal
echo 2) Profiler
echo.
choice /C 12 /T 4 /D 1 /M "Select mode (auto-starts Normal in 4 seconds)"

if errorlevel 2 (
  echo Starting in Profiler mode...
  python -m duplicleaner --profile --profile-min-ms 5
) else (
  echo Starting in Normal mode...
  python -m duplicleaner
)

pause
