@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Raio-X de Reputacao

where python >nul 2>nul
if errorlevel 1 goto sem_python

where ollama >nul 2>nul
if errorlevel 1 goto sem_ollama

if exist ".venv\instalado.txt" goto venv_ok

echo.
echo === Primeira execucao: preparando o ambiente. Pode levar alguns minutos. ===
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto erro_instalar
echo ok> .venv\instalado.txt
goto depois_venv

:venv_ok
call .venv\Scripts\activate.bat

:depois_venv
ollama list | findstr /C:"gemma3:4b" >nul
if errorlevel 1 (
    echo.
    echo === Baixando o modelo de IA. So na primeira vez. ===
    ollama pull gemma3:4b
)

if not exist "edge_profile_maps" (
    echo.
    echo === Login no Google ===
    echo Vai abrir o Edge. Entre na sua conta Google e depois FECHE a janela.
    python login_maps.py
)

echo.
echo === Abrindo o app. Para encerrar, feche esta janela. ===
streamlit run app.py
pause
exit /b

:sem_python
echo Python nao encontrado.
echo Instale em https://www.python.org/downloads/ e marque a opcao "Add Python to PATH".
start https://www.python.org/downloads/
pause
exit /b

:sem_ollama
echo Ollama nao encontrado.
echo Instale em https://ollama.com/download e rode este arquivo de novo.
start https://ollama.com/download
pause
exit /b

:erro_instalar
echo Falha ao instalar as dependencias. Verifique sua internet e tente de novo.
pause
exit /b