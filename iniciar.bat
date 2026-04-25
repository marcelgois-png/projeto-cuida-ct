@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_BIN="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

echo ============================================
echo   CT -^> SINFRA ^| Inicializacao Local
echo ============================================
echo.
echo Projeto: %CD%
echo Python : %PYTHON_BIN%
echo.

if not exist ".venv\Scripts\python.exe" (
    where "%PYTHON_BIN%" >nul 2>nul
)
if errorlevel 1 (
    echo Nao foi possivel localizar o Python para iniciar o projeto.
    echo Se voce usa ambiente virtual, crie uma pasta .venv ou ajuste o PATH.
    echo.
    pause
    exit /b 1
)

echo Aplicando migracoes...
"%PYTHON_BIN%" manage.py migrate
if errorlevel 1 (
    echo.
    echo Falha ao aplicar as migracoes.
    pause
    exit /b 1
)

if defined DJANGO_SKIP_RUNSERVER (
    echo.
    echo Script validado com DJANGO_SKIP_RUNSERVER. Servidor nao iniciado.
    exit /b 0
)

echo.
echo Iniciando servidor em http://127.0.0.1:8000/
echo Para encerrar, pressione Ctrl+C nesta janela.
echo.
"%PYTHON_BIN%" manage.py runserver

endlocal
