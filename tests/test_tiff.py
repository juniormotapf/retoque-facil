import io
import struct

import numpy as np
import pytest
import tifffile

from retoque_facil import tiff_camadas as T


def _par(dtype, rng):
    h, w = 123, 217
    mx = np.iinfo(dtype).max
    yy, xx = np.mgrid[0:h, 0:w]
    original = np.stack([xx / w * mx, yy / h * mx, np.full((h, w), mx * 0.3)], -1).astype(dtype)
    retocada = original.copy()
    retocada[30:80, 60:150] = np.array([mx, 0, mx // 2], dtype)
    retocada = (retocada.astype(np.int64) + rng.integers(0, 3, retocada.shape)).clip(0, mx).astype(dtype)
    return original, retocada


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_camadas_voltam_identicas(tmp_path, dtype, rng):
    original, retocada = _par(dtype, rng)
    icc = b"perfil-de-teste" * 10
    p = T.salvar(tmp_path / "a.tif", original, retocada, icc=icc, dpi=300)
    camadas = T.ler_camadas(p)
    assert [c[0] for c in camadas] == ["Original", "Retocada"]  # de baixo para cima
    assert np.array_equal(camadas[0][1], original)
    assert np.array_equal(camadas[1][1], retocada)
    with tifffile.TiffFile(p) as tif:
        pagina = tif.pages[0]
        assert np.array_equal(pagina.asarray(), retocada)  # imagem visível = retocada
        assert bytes(pagina.tags[34675].value) == icc
        assert pagina.tags[282].value[0] / pagina.tags[282].value[1] == 300


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_psd_tools_le_a_mesma_estrutura(dtype, rng):
    psd_tools = pytest.importorskip("psd_tools")
    original, retocada = _par(dtype, rng)
    h, w = original.shape[:2]
    bits = 16 if dtype == np.uint16 else 8
    info = T.informacao_de_camadas([("Original", original), ("Retocada", retocada)])
    info += b"\0" * (len(info) % 2)
    secao = struct.pack(">I", len(info)) + info + struct.pack(">I", 0)
    plano = b"".join(retocada[..., c].astype(retocada.dtype.newbyteorder(">")).tobytes() for c in range(3))
    psd = (b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 3, h, w, bits, 3)
           + struct.pack(">I", 0) + struct.pack(">I", 0) + struct.pack(">I", len(secao)) + secao
           + struct.pack(">H", 0) + plano)
    im = psd_tools.PSDImage.open(io.BytesIO(psd))
    assert [c.name for c in im] == ["Original", "Retocada"]
    mx = np.iinfo(dtype).max
    assert np.allclose(im[0].numpy()[..., :3], original / mx, atol=1 / mx)
    assert np.allclose(im[1].numpy()[..., :3], retocada / mx, atol=1 / mx)


def test_packbits_reserva_igual_ao_imagecodecs(rng):
    imagecodecs = pytest.importorskip("imagecodecs")
    for dados in (bytes(rng.integers(0, 4, 500, dtype=np.uint8)), b"\x07" * 300, bytes(range(256)) * 2):
        assert imagecodecs.packbits_decode(T._packbits_python(dados)) == dados


def test_recusa_tamanhos_diferentes(tmp_path):
    with pytest.raises(ValueError):
        T.salvar(tmp_path / "x.tif", np.zeros((5, 5, 3), np.uint8), np.zeros((5, 6, 3), np.uint8))
