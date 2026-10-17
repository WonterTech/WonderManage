@echo off
rem Choose who can connect and how well protected the connection is, then restart the Work log. Safe to run any time.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Run start.bat once first so the setup can finish, then run this file again.
  pause
  exit /b 1
)
if not exist data mkdir data

:menu
cls
echo ==============================================================
echo   Work log - network and security
echo ==============================================================
venv\Scripts\python.exe serve.py --show --port 80
echo.
echo   WHO CAN CONNECT
echo   1  This computer only
echo   2  Client's local network      (Wi-Fi / cable in the same building)
echo   3  Tailscale + local network   (reach it from anywhere with Tailscale)
echo   4  Tailscale ONLY              (everyone on the Wi-Fi is blocked - safest)
echo.
echo   PROTECTION
echo   5  Encrypted connection (HTTPS)  - switch ON / OFF
echo   6  Certificate to install on devices
echo.
echo   7  Refresh        0  Exit
echo.
choice /c 12345670 /n /m "Choose 1-7 or 0: "
if errorlevel 8 exit /b 0
if errorlevel 7 goto menu
if errorlevel 6 goto certs
if errorlevel 5 goto https
if errorlevel 4 set MODE=tailscale-only& goto apply
if errorlevel 3 set MODE=tailscale& goto apply
if errorlevel 2 set MODE=lan& goto apply
set MODE=local

:apply
> "data\network_mode.txt" echo %MODE%
goto restart

:https
set CUR=off
if exist data\https.txt set /p CUR=<data\https.txt
if /i "%CUR%"=="on" (set NEWH=off) else (set NEWH=on)
if /i "%NEWH%"=="on" echo Installing the encryption packages if they are missing...
if /i "%NEWH%"=="on" venv\Scripts\python.exe -m pip install -q -r requirements.txt
rem Write the word with "echo." - plain "echo on" / "echo off" would only switch command echoing and write nothing.
> "data\https.txt" echo.%NEWH%
if /i "%NEWH%"=="on" (
  echo.
  echo IMPORTANT: a device only trusts the https address after the certificate is installed on it, once.
  echo Choose option 6 in the menu to get the file, and see the README for each phone or computer.
  echo.
  pause
)
goto restart

:certs
cls
venv\Scripts\python.exe serve.py --certs
echo.
start "" explorer "%~dp0data\certs"
pause
goto menu

:restart
echo.
echo Saving a backup, then restarting...
venv\Scripts\python.exe backup.py >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%' AND CommandLine like '%%serve.py%%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 3 >nul
wscript "%~dp0worklog_hidden.vbs"
echo Starting... (about 10 seconds)
timeout /t 10 >nul
goto menu
