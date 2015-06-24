@echo off

cd %1
%2

if not errorlevel 1 goto quit
echo.
echo.
pause
:quit