@echo off
cd /d "%~dp0"
type nul > data\PARAR
echo Aviso enviado: la traduccion se parara al terminar los lotes en curso (unos segundos).
timeout /t 5
