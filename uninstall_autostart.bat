@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\WorkLog.lnk" 2>nul
echo The Work log will no longer start by itself. (If it is running now, it keeps running until you shut it down.)
pause
