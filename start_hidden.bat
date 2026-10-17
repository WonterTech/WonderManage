@echo off
rem Starts the Work log in the background (no window). Use this after shutting it down from the website.
wscript "%~dp0worklog_hidden.vbs"
echo Work log is starting in the background. Give it about 10 seconds, then open the address in your browser.
timeout /t 5 >nul
