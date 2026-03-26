@echo off
@color 0A
@mode con:cols=120 lines=45
setlocal

if "%~2" == "" (
    echo Usage: icf-encode [channels_file] [output_file]
    pause
    exit /b 1
)

set CHANNELS=%~1
set OUTPUT=%~2
rem set TEMPLATE=template.icf

:: String substitution: replace "-channels.csv" with "-settings.csv"
set SETTINGS=%CHANNELS:-channels.csv=-settings.csv%

python icf_tool.py encode "%CHANNELS%" "%SETTINGS%" "%OUTPUT%"

endlocal
echo.
echo DONE
echo 
echo 
echo.