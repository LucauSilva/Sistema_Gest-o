#!/usr/bin/env bash
# ============================================================
#  ENPCB - Criação do instalável para Linux / macOS
#  Requer Python 3.9+ (normalmente já vem instalado)
# ============================================================
set -e

echo ""
echo "=== ENPCB - A preparar o executável ==="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "ERRO: Não foi encontrado o Python 3 no seu computador."
    echo "Instale com: sudo apt install python3 python3-tk   (Linux/Debian/Ubuntu)"
    echo "ou descarregue em https://www.python.org/downloads/  (macOS)"
    exit 1
fi

echo "A instalar o PyInstaller (ferramenta que cria o executável)..."
python3 -m pip install --upgrade pyinstaller --break-system-packages 2>/dev/null || python3 -m pip install --upgrade pyinstaller

echo ""
echo "A construir o executável ENPCB..."
python3 -m PyInstaller --onefile --windowed --name ENPCB enpcb_sistema.py

echo ""
echo "============================================================"
echo " Concluído! O executável está em:  dist/ENPCB"
echo " Pode copiar esse ficheiro para qualquer pasta - funciona"
echo " sem instalação adicional e sem ligação à Internet."
echo "============================================================"
