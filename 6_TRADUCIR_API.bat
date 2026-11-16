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

rem Traduce lo que queda con la API por lotes de Anthropic u OpenAI (alternativa a Ollama).
if not exist API.txt (
  copy /y API.ejemplo.txt API.txt >nul
  echo Pega tu clave de API en el archivo que se va a abrir, guarda y vuelve a ejecutar este .bat.
  notepad API.txt
  exit /b 0
)
%PY% -m nolvus_es.lotes auto --data data --reintentar-fallidos %*
echo.
pause
