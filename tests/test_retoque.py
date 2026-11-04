import cv2
import numpy as np

from retoque_facil import cura, espinhas, fundo, imagem_io, pele

from .sinteticas import adicionar_espinhas, sujar_fundo


def _vermelhidao(rgb, x, y, r):
    R = int(r * 1.5) + 1
    pedaco = cv2.cvtColor(rgb[int(y) - R : int(y) + R + 1, int(x) - R : int(x) + R + 1].astype(np.float32), cv2.COLOR_RGB2Lab)
    return float(pedaco[..., 1].mean())


def test_acha_rosto(estudio_analisado):
    _, an = estudio_analisado
    assert len(an.rostos) == 1
    assert an.rostos[0].largura > 150


def test_rosto_limpo_quase_sem_marcas(estudio_analisado):
    foto, an = estudio_analisado
    marcas = espinhas.detectar(foto.rgb, an, "media")
    assert sum(m.remover for m in marcas) <= 3


def test_encontra_e_remove_espinhas(estudio_analisado):
    foto, an = estudio_analisado
    com_espinhas, verdade = adicionar_espinhas(foto.rgb, an, n=12, semente=3)
    marcas = espinhas.detectar(com_espinhas, an, "media")
    achadas = sum(
        any((m.x - x) ** 2 + (m.y - y) ** 2 < (max(r, m.raio) * 1.5) ** 2 for m in marcas if m.remover)
        for x, y, r in verdade
    )
    assert achadas >= 0.7 * len(verdade)

    curada, feitas = cura.remover_marcas(com_espinhas, an, marcas)
    assert feitas == sum(m.remover for m in marcas)
    reducoes = []
    for x, y, r in verdade:
        antes = _vermelhidao(com_espinhas, x, y, r) - _vermelhidao(foto.rgb, x, y, r)
        depois = _vermelhidao(curada, x, y, r) - _vermelhidao(foto.rgb, x, y, r)
        reducoes.append(1 - depois / max(antes, 1e-6))
    assert np.median(reducoes) > 0.6


def test_desmarcar_preserva(estudio_analisado):
    foto, an = estudio_analisado
    com_espinhas, _ = adicionar_espinhas(foto.rgb, an, n=6, semente=8)
    marcas = espinhas.detectar(com_espinhas, an, "media")
    alvo = next(m for m in marcas if m.remover)
    alvo.remover = False
    curada, _ = cura.remover_marcas(com_espinhas, an, marcas)
    R = int(alvo.raio)
    sl = (slice(int(alvo.y) - R, int(alvo.y) + R + 1), slice(int(alvo.x) - R, int(alvo.x) + R + 1))
    assert np.abs(curada[sl] - com_espinhas[sl]).max() < 0.02


def test_suavizar_nao_mexe_fora_do_rosto(estudio_analisado):
    foto, an = estudio_analisado
    suave = pele.suavizar(foto.rgb, an, "media")
    x0, y0, x1, y1 = an.rostos[0].caixa(0.12, (an.altura, an.largura))
    fora = np.ones(foto.rgb.shape[:2], bool)
    fora[y0:y1, x0:x1] = False
    assert np.abs(suave[fora] - foto.rgb[fora]).max() == 0


def test_diagnostico_de_fundo(estudio_analisado, foto_escritorio):
    from retoque_facil import analise

    foto, an = estudio_analisado
    assert fundo.diagnosticar(foto.rgb, an).estudio
    outra = imagem_io.carregar(foto_escritorio)
    assert not fundo.diagnosticar(outra.rgb, analise.analisar(outra.rgb)).estudio


def test_limpa_sujeira_do_fundo(estudio_analisado):
    foto, an = estudio_analisado
    suja, sujeira = sujar_fundo(foto.rgb, an, semente=2)
    limpa = fundo.limpar(suja, an, "media")
    manchas = sujeira > 0.04
    erro_antes = np.abs(suja - foto.rgb).mean(-1)[manchas].mean()
    erro_depois = np.abs(limpa - foto.rgb).mean(-1)[manchas].mean()
    assert erro_depois < 0.35 * erro_antes
