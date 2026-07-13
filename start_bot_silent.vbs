' OneGate Dissemination Bot - Silent launcher
' Run by Windows Task Scheduler at logon. Hides the CMD window.
Set oShell = CreateObject("WScript.Shell")
oShell.Run "cmd.exe /c ""c:\Users\BMKG\Downloads\LATSAR IRSYAD\aktualisasi\start_bot.bat""", 0, False
