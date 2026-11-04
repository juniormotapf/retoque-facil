"""Fotos de teste: retratos de exemplo do próprio MediaPipe (Apache-2.0), baixados uma vez.

Nenhuma foto de pessoa fica guardada no repositório.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import numpy as np
import pytest

CACHE = Path(os.environ.get("RETOQUE_TESTE_CACHE", Path(__file__).parent / ".cache"))
FOTOS = {
    "estudio": "https://storage.googleapis.com/mediapipe-assets/business-person.png",
    "escritorio": "https://storage.googleapis.com/mediapipe-assets/portrait.jpg",
}


def _baixar(nome: str) -> Path:
    url = FOTOS[nome]
    destino = CACHE / Path(url).name
    if not destino.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(url, destino)
        except Exception as e:  # sem internet: pula os testes que precisam de rosto real
            pytest.skip(f"não consegui baixar a foto de teste: {e}")
    return destino


@pytest.fixture(scope="session")
def foto_estudio() -> Path:
    return _baixar("estudio")


@pytest.fixture(scope="session")
def foto_escritorio() -> Path:
    return _baixar("escritorio")


@pytest.fixture(scope="session")
def estudio_analisado(foto_estudio):
    from retoque_facil import analise, imagem_io

    foto = imagem_io.carregar(foto_estudio)
    return foto, analise.analisar(foto.rgb)


@pytest.fixture()
def rng():
    return np.random.default_rng(1234)
