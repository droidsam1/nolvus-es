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

rem ===== Ajustes =====
rem Modelo de Ollama (alternativa mas ligera: gemma3:12b)
set MODELO=gemma4:26b-a4b-it-qat
rem Peticiones en paralelo (2-4). Mas no siempre es mas rapido.
set PARALELO=2
rem ====================
title Nolvus ES - Traduciendo (puedes cerrar esta ventana cuando quieras)
%PY% -c "import urllib.request;urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5)" 2>nul
if errorlevel 1 (
  echo Ollama no esta en marcha. Abriendolo...
  start "" ollama serve
  timeout /t 8 >nul
)
echo.
echo  Traduciendo Nolvus al espanol con %MODELO%.
echo  - Puedes cerrar esta ventana o apagar el PC cuando quieras: no se pierde el progreso.
echo  - Para parar limpiamente: doble clic en 3_PARAR.bat
echo  - No juegues mientras traduce: la tarjeta grafica esta ocupada.
echo.
%PY% -m nolvus_es.translate run --data data --model %MODELO% --workers %PARALELO%
echo.
pause
