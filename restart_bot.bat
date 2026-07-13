@echo off
:: One Gate Dissemination Bot - RESTART helper
:: Kills all existing instances, then starts a fresh single instance.

echo Stopping existing bot instances...
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq*start_bot*" /T 2>nul
del "c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi\bot.lock" 2>nul

timeout /t 3 /nobreak >nul

echo Starting bot...
start "" wscript.exe "c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi\start_bot_silent.vbs"
echo Done. Bot started silently.
