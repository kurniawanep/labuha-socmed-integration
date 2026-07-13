@echo off
:: One Gate Dissemination Bot - Auto-start script
:: Auto-restarts if the bot crashes. Prevents duplicate instances.

cd /d "c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi"

:: Check if another instance is already running via lock file
if exist bot.lock (
    echo [%date% %time%] Another instance already running. Exiting.
    exit /b
)

:: Wait 15 seconds for network to be ready after boot
timeout /t 15 /nobreak >nul

:loop
echo %~dp0 > bot.lock
echo [%date% %time%] Starting bot...
"c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi\.venv\Scripts\python.exe" main.py
del bot.lock 2>nul
echo [%date% %time%] Bot exited. Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto loop
