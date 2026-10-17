@echo off
cd /d "%~dp0"
if not exist venv\Scripts\pythonw.exe (
  echo Run start.bat once first so the setup can finish, then run this file again.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\WorkLog.lnk'); $s.TargetPath='%~dp0worklog_hidden.vbs'; $s.WorkingDirectory='%~dp0'; $s.Save()"
if errorlevel 1 (
  echo Could not create the startup entry.
  pause
  exit /b 1
)
echo.
echo Done. The Work log will now start by itself, in the background, every time you sign in to Windows.
echo Starting it now as well...
wscript "%~dp0worklog_hidden.vbs"
echo.
echo To undo this, run uninstall_autostart.bat
pause
