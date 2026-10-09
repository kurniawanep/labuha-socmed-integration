@echo off
:: One Gate Dissemination Bot - Auto-start script
:: Auto-restarts if the bot crashes. Prevents duplicate instances.

cd /d "c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi"

:: Wait 15 seconds for network to be ready after boot
C:\Windows\System32\timeout.exe /t 15 /nobreak >nul

:loop
echo [%date% %time%] Starting bot...
"c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi\.venv\Scripts\python.exe" main.py

:: If main.py exited with errorlevel 99, another instance is already running.
if %ERRORLEVEL% equ 99 (
    echo [%date% %time%] Another instance is already running. Exiting.
    exit /b
)

echo [%date% %time%] Bot exited. Restarting in 10 seconds...
C:\Windows\System32\timeout.exe /t 10 /nobreak >nul
goto loop
