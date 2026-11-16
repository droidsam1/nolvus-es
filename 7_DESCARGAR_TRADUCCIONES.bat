@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY call :python_portatil
if not defined PY (
  echo No he podido preparar Python. Instalalo con:  winget install Python.Python.3.12
  pause
  exit /b 1
)

rem Solo descarga de Nexus las traducciones al español del catálogo (con NEXUS.txt y cuenta Premium,
rem automáticamente). No crea ni activa nada en Mod Organizer.
%PY% -m nolvus_es.instalador instalar --solo-descargar --si %*
echo.
pause
exit /b 0

:python_portatil
if not defined PY (
  echo No he podido preparar Python. Instalalo con:  winget install Python.Python.3.12
  pause
  exit /b 1
)

rem Traduce tu Nolvus al español. Se puede cortar y volver a ejecutar.
%PY% -m nolvus_es.instalador instalar %*
echo.
pause
exit /b 0

:python_portatil
rem Python portatil oficial (python.org), solo para este instalador: no toca tu sistema.
set PYDIR=%~dp0instalacion\python
if not exist "%PYDIR%\python.exe" (
  echo Preparando Python portatil ^(una sola vez, unos 11 MB^)...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $z=Join-Path $env:TEMP 'nolvus-es-python.zip'; Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip' -OutFile $z; Expand-Archive -Force $z '%PYDIR%'; Add-Content -Path (Get-ChildItem '%PYDIR%\python*._pth').FullName -Value '..\..'"
)
if exist "%PYDIR%\python.exe" set PY="%PYDIR%\python.exe"
exit /b 0
