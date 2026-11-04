"""Onde ficam as pastas de trabalho do usuário."""

from __future__ import annotations

import os
import sys
from pathlib import Path

NOME_PASTA = "Retoque Facil"
PASTA_ENTRADA = "1 - Fotos para retocar"
PASTA_SAIDA = "2 - Fotos prontas"


def pasta_documentos() -> Path:
    """Pasta Documentos de verdade (no Windows ela pode estar dentro do OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            guid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                        (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            caminho = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(caminho)) == 0:
                resultado = Path(caminho.value)
                ctypes.windll.ole32.CoTaskMemFree(caminho)
                return resultado
        except Exception:
            pass
    for nome in ("Documents", "Documentos"):
        p = Path.home() / nome
        if p.is_dir():
            return p
    return Path.home()


def pasta_base() -> Path:
    escolhida = os.environ.get("RETOQUE_PASTA", "").strip()
    if escolhida and "${" not in escolhida:
        return Path(escolhida).expanduser()
    return pasta_documentos() / NOME_PASTA


def pastas(criar: bool = True) -> tuple[Path, Path]:
    base = pasta_base()
    entrada, saida = base / PASTA_ENTRADA, base / PASTA_SAIDA
    if criar:
        entrada.mkdir(parents=True, exist_ok=True)
        saida.mkdir(parents=True, exist_ok=True)
    return entrada, saida
