@echo off
setlocal
chcp 65001 >nul
title Retoque Facil - Instalador
cd /d "%~dp0"
echo.
echo  ============================================
echo     Retoque Facil - Instalador
echo  ============================================
echo.
echo  Deixe esta janela aberta ate aparecer PRONTO.
echo.

where uv >nul 2>nul
if not errorlevel 1 goto TEM_UV
if exist "%USERPROFILE%\.local\bin\uv.exe" goto UV_LOCAL

echo  Instalando o uv, que baixa o Python para o programa...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if not exist "%USERPROFILE%\.local\bin\uv.exe" goto SEM_UV

:UV_LOCAL
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:TEM_UV
uv run --no-project --python 3.12 "%~dp0instalar\instalador.py"
if errorlevel 1 goto FALHOU
echo.
pause
exit /b 0

:SEM_UV
echo.
echo  Nao consegui instalar o uv. Confira a internet e tente de novo.
echo.
pause
exit /b 1

:FALHOU
echo.
echo  Algo deu errado. Tire um print desta janela e mande para quem te passou o programa.
echo.
pause
exit /b 1
