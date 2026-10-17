@echo off
rem One-time: lets other devices reach the Work log through Windows Firewall (ports 80 and 443).
rem Right-click this file and choose "Run as administrator".
net session >nul 2>&1
if errorlevel 1 (
  echo This needs administrator rights: right-click the file and choose "Run as administrator".
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="WorkLog LAN" >nul 2>&1
netsh advfirewall firewall delete rule name="WorkLog Tailscale" >nul 2>&1
rem Local network: only devices in the SAME subnet as this computer, on any network profile (Public, Private, Domain).
netsh advfirewall firewall add rule name="WorkLog LAN" dir=in action=allow protocol=TCP localport=80,443 remoteip=localsubnet profile=any
rem Tailscale: only Tailscale addresses.
netsh advfirewall firewall add rule name="WorkLog Tailscale" dir=in action=allow protocol=TCP localport=80,443 remoteip=100.64.0.0/10 profile=any
echo.
echo Done.
pause
