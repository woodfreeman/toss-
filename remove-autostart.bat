@echo off
rem Remove Toss auto-start registration
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Toss /f 2>nul
echo [OK] Toss auto-start removed (if it was registered).
pause
