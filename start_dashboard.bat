@echo off
setlocal
cd /d "%~dp0"
call "%~dp0start_dashboard.cmd"
exit /b %ERRORLEVEL%
