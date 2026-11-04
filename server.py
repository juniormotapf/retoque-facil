"""Ponto de entrada usado pelo Claude Desktop (extensão .mcpb e instalador)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from retoque_facil.server import main  # noqa: E402

if __name__ == "__main__":
    main()
