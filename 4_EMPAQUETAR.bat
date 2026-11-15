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

rem Genera el mod "Nolvus ES - Traduccion" con todo lo traducido hasta ahora.
set DESTINO=C:\Nolvus\Instances\Nolvus Awakening\MODS\mods\Nolvus ES - Traduccion
%PY% -m nolvus_es.pack --data data --out "%DESTINO%" --official "build\Nolvus ES"
echo.
echo Listo. En Mod Organizer pulsa F5 (o reinicia MO2) y lanza el juego.
pause
