@echo off
@color 0A
@mode con:cols=120 lines=45

if "%~1" == "" (
    echo Usage: icf-decode [icf_file]
    pause
    exit /b 1
)

python icf_tool.py decode %1

echo.
echo DONE
echo 
echo 
echo.