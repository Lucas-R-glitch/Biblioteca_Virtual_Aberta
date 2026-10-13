@echo off
setlocal
echo Instalando pywebview...

py -m pip install pywebview >nul 2>&1
if %errorlevel%==0 goto done

python -m pip install pywebview >nul 2>&1
if %errorlevel%==0 goto done

py -m ensurepip >nul 2>&1
py -m pip install pywebview >nul 2>&1
if %errorlevel%==0 goto done

python -m ensurepip >nul 2>&1
python -m pip install pywebview >nul 2>&1
if %errorlevel%==0 goto done

echo Nao foi possivel instalar automaticamente o pywebview.
echo Verifique qual Python esta associado ao app e tente instalar manualmente.
pause
exit /b 1

:done
echo pywebview instalado com sucesso.
pause
