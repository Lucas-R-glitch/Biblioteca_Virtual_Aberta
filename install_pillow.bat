@echo off
where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install pillow
    pause
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m pip install pillow
    pause
    exit /b
)

echo Python nao foi encontrado no PATH.
echo Instale o Python e tente novamente.
pause
