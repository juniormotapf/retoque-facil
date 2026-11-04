#!/bin/bash
# Retoque Fácil - instalador para Mac (chip Apple M1 ou mais novo)
cd "$(dirname "$0")" || exit 1
echo
echo "============================================"
echo "   Retoque Fácil - Instalador"
echo "============================================"
echo
if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "Instalando o uv, que baixa o Python para o programa..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi
if ! uv run --no-project --python 3.12 instalar/instalador.py; then
  echo
  echo "Algo deu errado. Tire um print desta janela e mande para quem te passou o programa."
fi
echo
read -n 1 -s -r -p "Pressione qualquer tecla para fechar"
echo
