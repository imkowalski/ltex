@echo off
set "LTEX=%USERPROFILE%\.local\bin\ltex.exe"
echo ltex inverse-search debug wrapper
echo file: %~1
echo line: %~2
echo column: %~3
echo.
"%LTEX%" --debug inverse-search "%~1" %~2 %~3
echo.
pause
