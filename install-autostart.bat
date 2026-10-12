@echo off
rem Register Toss to auto-start at logon (current user, no admin needed)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Toss /t REG_SZ /d "%~dp0Toss.exe" /f
echo.
echo [OK] Toss auto-start registered. It will run hidden at next logon.
echo To verify: Task Manager - Startup apps, or check registry Run key.
pause
