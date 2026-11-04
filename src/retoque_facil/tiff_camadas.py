"""TIFF com camadas no padrão do Photoshop.

O arquivo tem duas partes:
1) a imagem "achatada" (como a foto aparece), lida por qualquer programa;
2) os dados de camadas do Photoshop (tag 37724, ImageSourceData), com a camada
   "Original" embaixo e a "Retocada" por cima. Photoshop, Affinity Photo, GIMP 3,
   Krita e PhotoCraft abrem as camadas separadas.

A estrutura das camadas segue a especificação pública do formato PSD (seção
"Layer and Mask Information"), gravada com compressão RLE (PackBits).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

ASSINATURA_TIFF = b"Adobe Photoshop Document Data Block\x00"
TAG_IMAGE_SOURCE_DATA = 37724
TAG_ICC = 34675


def _packbits(linha: bytes) -> bytes:
    try:
        import imagecodecs

        return imagecodecs.packbits_encode(linha)
    except ImportError:  # pragma: no cover - reserva, bem mais lenta
        return _packbits_python(linha)


def _packbits_python(dados: bytes) -> bytes:
    saida = bytearray()
    i, n = 0, len(dados)
    while i < n:
        j = i
        while j + 1 < n and dados[j] == dados[j + 1] and j - i < 127:
            j += 1
        if j > i:  # repetição
            saida.append((257 - (j - i + 1)) & 0xFF)
            saida.append(dados[i])
            i = j + 1
            continue
        j = i
        while j < n and j - i < 128 and not (j + 2 < n and dados[j] == dados[j + 1] == dados[j + 2]):
            j += 1
        saida.append(j - i - 1)
        saida.extend(dados[i:j])
        i = j
    return bytes(saida)


def _canal_rle(plano: np.ndarray) -> bytes:
    """Um canal (2D) comprimido em RLE: tabela de tamanhos por linha + linhas."""
    plano = np.ascontiguousarray(plano.astype(plano.dtype.newbyteorder(">"), copy=False))
    linhas = [_packbits(plano[i].tobytes()) for i in range(plano.shape[0])]
    tamanhos = np.array([len(x) for x in linhas], dtype=">u2")
    if tamanhos.size and tamanhos.max() >= 65535:  # linha enorme: grava sem compressão
        return struct.pack(">H", 0) + plano.tobytes()
    return struct.pack(">H", 1) + tamanhos.tobytes() + b"".join(linhas)


def _nome_pascal(nome: str) -> bytes:
    bruto = nome.encode("latin-1", "replace")[:255]
    dados = bytes([len(bruto)]) + bruto
    return dados + b"\x00" * ((-len(dados)) % 4)


def _bloco_unicode(nome: str) -> bytes:
    utf16 = nome.encode("utf-16-be")
    corpo = struct.pack(">I", len(nome)) + utf16
    corpo += b"\x00" * (len(corpo) % 2)
    return b"8BIM" + b"luni" + struct.pack(">I", len(corpo)) + corpo


def informacao_de_camadas(camadas: list[tuple[str, np.ndarray]]) -> bytes:
    """Monta a "layer info" do PSD. A primeira camada da lista fica EMBAIXO.

    camadas: [(nome, imagem HxWx3 uint8 ou uint16), ...], todas do mesmo tamanho.
    """
    registros = bytearray()
    dados_canais = bytearray()
    for nome, img in camadas:
        h, w = img.shape[:2]
        maximo = np.iinfo(img.dtype).max
        alfa = np.full((h, w), maximo, dtype=img.dtype)
        canais = [(-1, alfa), (0, img[..., 0]), (1, img[..., 1]), (2, img[..., 2])]
        comprimidos = [(cid, _canal_rle(plano)) for cid, plano in canais]

        registros += struct.pack(">iiii", 0, 0, h, w)
        registros += struct.pack(">H", len(comprimidos))
        for cid, dado in comprimidos:
            registros += struct.pack(">hI", cid, len(dado))
        registros += b"8BIM" + b"norm"
        registros += struct.pack(">BBBB", 255, 0, 0, 0)  # opacidade, recorte, visível, enchimento
        extra = struct.pack(">I", 0)  # sem máscara de camada
        extra += struct.pack(">I", 0)  # sem faixas de mesclagem
        extra += _nome_pascal(nome)
        extra += _bloco_unicode(nome)
        registros += struct.pack(">I", len(extra)) + extra
        for _, dado in comprimidos:
            dados_canais += dado

    corpo = struct.pack(">h", len(camadas)) + bytes(registros) + bytes(dados_canais)
    return corpo


def dados_photoshop(camadas: list[tuple[str, np.ndarray]]) -> bytes:
    corpo = informacao_de_camadas(camadas)
    corpo += b"\x00" * ((-len(corpo)) % 4)
    chave = b"Lr16" if camadas[0][1].dtype == np.uint16 else b"Layr"
    return ASSINATURA_TIFF + b"8BIM" + chave + struct.pack(">I", len(corpo)) + corpo


def salvar(
    caminho: str | Path,
    original: np.ndarray,
    retocada: np.ndarray,
    icc: bytes | None = None,
    dpi: float | None = None,
    nomes: tuple[str, str] = ("Original", "Retocada"),
) -> Path:
    """Grava o TIFF: imagem visível = retocada; camadas = original (baixo) + retocada (cima)."""
    import tifffile

    if original.shape != retocada.shape or original.dtype != retocada.dtype:
        raise ValueError("as duas camadas precisam ter o mesmo tamanho e profundidade")
    if original.dtype not in (np.uint8, np.uint16):
        raise ValueError("use imagens de 8 ou 16 bits")
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    extras = [(TAG_IMAGE_SOURCE_DATA, 7, None, dados_photoshop([(nomes[0], original), (nomes[1], retocada)]), True)]
    if icc:
        extras.append((TAG_ICC, 7, None, icc, True))
    for i, (codigo, tipo, _, valor, unico) in enumerate(extras):
        extras[i] = (codigo, tipo, len(valor), valor, unico)

    opcoes = {}
    if dpi:
        opcoes["resolution"] = (float(dpi), float(dpi))
        opcoes["resolutionunit"] = "INCH"

    temporario = caminho.with_name(caminho.name + ".gravando")
    tifffile.imwrite(
        temporario,
        retocada,
        byteorder=">",
        photometric="rgb",
        planarconfig="contig",
        compression="zlib",
        predictor=True,
        software="Retoque Facil",
        extratags=extras,
        metadata=None,
        **opcoes,
    )
    temporario.replace(caminho)
    return caminho


def ler_camadas(caminho: str | Path) -> list[tuple[str, np.ndarray]]:
    """Lê de volta as camadas gravadas por `salvar` (usado nos testes e na conferência)."""
    import tifffile

    with tifffile.TiffFile(caminho) as tif:
        pagina = tif.pages[0]
        bruto = bytes(pagina.tags[TAG_IMAGE_SOURCE_DATA].value)
    if not bruto.startswith(ASSINATURA_TIFF):
        raise ValueError("TIFF sem dados de camadas do Photoshop")
    pos = len(ASSINATURA_TIFF)
    while pos + 12 <= len(bruto):
        assinatura, chave = bruto[pos : pos + 4], bruto[pos + 4 : pos + 8]
        (tamanho,) = struct.unpack(">I", bruto[pos + 8 : pos + 12])
        if assinatura == b"8BIM" and chave in (b"Layr", b"Lr16"):
            return _ler_info(bruto[pos + 12 : pos + 12 + tamanho], 2 if chave == b"Lr16" else 1)
        pos += 12 + tamanho + ((-tamanho) % 4)
    raise ValueError("bloco de camadas não encontrado")


def _ler_info(dados: bytes, bytes_por_amostra: int) -> list[tuple[str, np.ndarray]]:
    import imagecodecs

    (n,) = struct.unpack(">h", dados[:2])
    n = abs(n)
    pos = 2
    registros = []
    for _ in range(n):
        top, left, bottom, right = struct.unpack(">iiii", dados[pos : pos + 16])
        pos += 16
        (nc,) = struct.unpack(">H", dados[pos : pos + 2])
        pos += 2
        canais = []
        for _ in range(nc):
            cid, tam = struct.unpack(">hI", dados[pos : pos + 6])
            canais.append((cid, tam))
            pos += 6
        pos += 12  # assinatura, modo, opacidade etc.
        (tam_extra,) = struct.unpack(">I", dados[pos : pos + 4])
        extra = dados[pos + 4 : pos + 4 + tam_extra]
        pos += 4 + tam_extra
        (lm,) = struct.unpack(">I", extra[:4])
        q = 4 + lm
        (lb,) = struct.unpack(">I", extra[q : q + 4])
        q += 4 + lb
        nome = extra[q + 1 : q + 1 + extra[q]].decode("latin-1")
        registros.append((nome, bottom - top, right - left, canais))
    tipo = ">u2" if bytes_por_amostra == 2 else "u1"
    camadas = []
    for nome, h, w, canais in registros:
        planos = {}
        for cid, tam in canais:
            bloco = dados[pos : pos + tam]
            pos += tam
            (comp,) = struct.unpack(">H", bloco[:2])
            if comp == 0:
                plano = np.frombuffer(bloco[2:], dtype=tipo).reshape(h, w)
            elif comp == 1:
                tamanhos = np.frombuffer(bloco[2 : 2 + 2 * h], dtype=">u2")
                q = 2 + 2 * h
                linhas = []
                for t in tamanhos:
                    linhas.append(np.frombuffer(imagecodecs.packbits_decode(bloco[q : q + int(t)]), dtype=tipo))
                    q += int(t)
                plano = np.stack(linhas).reshape(h, w)
            else:
                raise ValueError(f"compressão {comp} não suportada na leitura")
            planos[cid] = plano
        img = np.stack([planos[0], planos[1], planos[2]], -1).astype(np.uint16 if bytes_por_amostra == 2 else np.uint8)
        camadas.append((nome, img))
    return camadas
