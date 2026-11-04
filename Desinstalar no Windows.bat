@echo off
setlocal
chcp 65001 >nul
title Retoque Facil - Desinstalar
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 goto SEM_UV
uv run --no-project --python 3.12 "%~dp0instalar\instalador.py" --desinstalar
echo.
pause
exit /b 0

:SEM_UV
echo  O uv nao esta instalado, entao o Retoque Facil tambem nao deve estar.
pause
exit /b 1
