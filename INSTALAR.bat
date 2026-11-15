@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo No encuentro Python en este PC.
  echo Instalalo con:  winget install Python.Python.3.12
  echo y vuelve a abrir este archivo.
  pause
  exit /b 1
)

rem Traduce tu Nolvus al español. Se puede cortar y volver a ejecutar: sigue donde lo dejó.
%PY% -m nolvus_es.instalador instalar %*
echo.
pause
