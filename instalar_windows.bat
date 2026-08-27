@echo off
REM ============================================================
REM  ENPCB - Criacao do instalavel (.exe) para Windows
REM  Basta ter Python 3.9+ instalado (com a opcao "Add to PATH")
REM  Descarregue em: https://www.python.org/downloads/
REM ============================================================

echo.
echo === ENPCB - A preparar o executavel para Windows ===
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Nao foi encontrado o Python no seu computador.
    echo Instale o Python em https://www.python.org/downloads/
    echo e volte a correr este ficheiro.
    pause
    exit /b 1
)

echo A instalar o PyInstaller ^(ferramenta que cria o .exe^)...
python -m pip install --upgrade pyinstaller

echo.
echo A construir o ENPCB.exe ...
python -m PyInstaller --onefile --windowed --name ENPCB enpcb_sistema.py

echo.
echo ============================================================
echo  Concluido! O executavel esta em:  dist\ENPCB.exe
echo  Pode copiar esse ficheiro para o Ambiente de Trabalho
echo  ou para qualquer pasta - funciona sem instalacao adicional
echo  e sem ligacao a Internet.
echo ============================================================
pause
