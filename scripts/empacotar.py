"""Gera os arquivos de distribuição em dist/.

  RetoqueFacil.zip      -> pasta completa com os instaladores (Windows/Mac)
  retoque-facil.mcpb    -> extensão de um clique para o Claude Desktop
  retoque-de-pele.zip   -> skill para enviar em Personalizar > Skills

Uso: uv run --no-project python scripts/empacotar.py
"""

from __future__ import annotations

import json
import re
import stat
import sys
import tomllib
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist"

APP = ["server.py", "pyproject.toml", "uv.lock", ".python-version", "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"]
INSTALADOR = APP + ["Instalar no Windows.bat", "Desinstalar no Windows.bat", "Instalar no Mac.command"]
PASTAS_APP = ["src"]
PASTAS_INSTALADOR = ["src", "instalar", "skill"]


def _arquivos(pasta: Path):
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            yield p


def _gravar(z: zipfile.ZipFile, origem: Path, nome: str) -> None:
    info = zipfile.ZipInfo.from_file(origem, nome)
    info.compress_type = zipfile.ZIP_DEFLATED
    modo = 0o755 if origem.suffix in (".command", ".sh") else 0o644
    info.external_attr = (stat.S_IFREG | modo) << 16
    with open(origem, "rb") as f:
        z.writestr(info, f.read())


def conferir_versoes() -> str:
    pyproj = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifesto = json.loads((RAIZ / "manifest.json").read_text(encoding="utf-8"))["version"]
    init = re.search(r'__version__ = "([^"]+)"', (RAIZ / "src/retoque_facil/__init__.py").read_text()).group(1)
    if len({pyproj, manifesto, init}) != 1:
        sys.exit(f"versões diferentes: pyproject={pyproj} manifest={manifesto} __init__={init}")
    return pyproj


def main() -> None:
    versao = conferir_versoes()
    DIST.mkdir(exist_ok=True)

    with zipfile.ZipFile(DIST / "RetoqueFacil.zip", "w") as z:
        for nome in INSTALADOR:
            _gravar(z, RAIZ / nome, f"RetoqueFacil/{nome}")
        for pasta in PASTAS_INSTALADOR:
            for arq in _arquivos(RAIZ / pasta):
                _gravar(z, arq, f"RetoqueFacil/{arq.relative_to(RAIZ).as_posix()}")

    with zipfile.ZipFile(DIST / "retoque-facil.mcpb", "w") as z:
        _gravar(z, RAIZ / "manifest.json", "manifest.json")
        for nome in APP:
            _gravar(z, RAIZ / nome, nome)
        for pasta in PASTAS_APP:
            for arq in _arquivos(RAIZ / pasta):
                _gravar(z, arq, arq.relative_to(RAIZ).as_posix())

    with zipfile.ZipFile(DIST / "retoque-de-pele.zip", "w") as z:
        for arq in _arquivos(RAIZ / "skill" / "retoque-de-pele"):
            _gravar(z, arq, f"retoque-de-pele/{arq.relative_to(RAIZ / 'skill' / 'retoque-de-pele').as_posix()}")

    for p in sorted(DIST.iterdir()):
        print(f"{p.name:24s} {p.stat().st_size / 1e6:6.1f} MB")
    print(f"versão {versao}")


if __name__ == "__main__":
    main()
