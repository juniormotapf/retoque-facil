"""Leitura de fotos (JPEG, PNG, TIFF, WebP e RAW de câmera) em qualquer caminho, inclusive com acentos.

Tudo vira float32 RGB entre 0 e 1. A profundidade original (8 ou 16 bits), o perfil
de cor (ICC) e a resolução (DPI) são guardados para o TIFF final sair fiel à foto.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

EXTENSOES_RAW = {".nef", ".nrw", ".cr2", ".cr3", ".arw", ".srf", ".raf", ".dng", ".orf", ".rw2", ".pef", ".srw"}
EXTENSOES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"} | EXTENSOES_RAW
EXTENSOES_NAO_SUPORTADAS = {
    ".heic": "HEIC (foto de iPhone)",
    ".heif": "HEIF (foto de iPhone)",
    ".psd": "Photoshop (PSD)",
}


class FormatoNaoSuportado(ValueError):
    pass


@dataclass
class Foto:
    rgb: np.ndarray  # float32, HxWx3, 0..1
    bits: int  # 8 ou 16
    icc: bytes | None
    dpi: float | None
    caminho: Path

    @property
    def altura(self) -> int:
        return self.rgb.shape[0]

    @property
    def largura(self) -> int:
        return self.rgb.shape[1]


def _normalizar(arr: np.ndarray) -> tuple[np.ndarray, int]:
    """Converte qualquer array de imagem para float32 RGB 0..1 e diz se era 8 ou 16 bits."""
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    if arr.shape[-1] == 2:  # cinza + alfa
        arr = np.stack([arr[..., 0]] * 3, axis=-1)
    if arr.dtype == np.uint8:
        return arr.astype(np.float32) / 255.0, 8
    if arr.dtype == np.uint16:
        return arr.astype(np.float32) / 65535.0, 16
    if arr.dtype in (np.float32, np.float64):
        return np.clip(arr.astype(np.float32), 0.0, 1.0), 16
    if arr.dtype == bool:
        return arr.astype(np.float32), 8
    raise FormatoNaoSuportado(f"tipo de pixel não suportado: {arr.dtype}")


def _ler_tiff(caminho: Path) -> tuple[np.ndarray, bytes | None, float | None]:
    import tifffile

    with tifffile.TiffFile(caminho) as tif:
        pagina = tif.pages[0]
        arr = pagina.asarray()
        icc = None
        tag_icc = pagina.tags.get(34675)
        if tag_icc is not None:
            icc = bytes(tag_icc.value)
        dpi = None
        tag_res = pagina.tags.get(282)
        if tag_res is not None:
            num, den = tag_res.value
            if den:
                dpi = num / den
        fotometria = pagina.photometric
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
        arr = np.moveaxis(arr, 0, -1)  # planar -> intercalado
    if int(fotometria) == 5:  # CMYK
        raise FormatoNaoSuportado("TIFF em CMYK. Salve a foto em RGB antes.")
    return arr, icc, dpi


def _revelar_raw(caminho: Path) -> tuple[np.ndarray, bytes]:
    """Revela o RAW da câmera em 16 bits sRGB, com o balanço de branco da própria câmera.

    É uma revelação neutra, parecida com o JPEG da câmera. Quem quiser ajustar exposição e
    cor deve revelar antes no Lightroom/Darktable e mandar o TIFF.
    """
    try:
        import rawpy
    except ImportError as e:
        raise FormatoNaoSuportado("para abrir RAW é preciso o componente rawpy; rode o instalador de novo") from e
    from PIL import ImageCms

    with open(caminho, "rb") as f, rawpy.imread(f) as raw:  # arquivo aberto pelo Python: aceita acentos
        arr = raw.postprocess(use_camera_wb=True, output_bps=16, output_color=rawpy.ColorSpace.sRGB)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return arr, icc


def carregar(caminho: str | Path) -> Foto:
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"não encontrei o arquivo {caminho}")
    ext = caminho.suffix.lower()
    if ext in EXTENSOES_NAO_SUPORTADAS:
        raise FormatoNaoSuportado(
            f"o formato {EXTENSOES_NAO_SUPORTADAS[ext]} ainda não é aceito. "
            "Exporte a foto como JPEG ou TIFF e tente de novo."
        )
    if ext not in EXTENSOES:
        raise FormatoNaoSuportado(f"o formato '{ext}' não é de imagem aceita")

    icc: bytes | None = None
    dpi: float | None = None

    if ext in EXTENSOES_RAW:
        arr, icc = _revelar_raw(caminho)
    elif ext in (".tif", ".tiff"):
        arr, icc, dpi = _ler_tiff(caminho)
    elif ext == ".png":
        # cv2 preserva 16 bits; np.fromfile evita o problema de acentos no Windows.
        dados = np.fromfile(str(caminho), dtype=np.uint8)
        arr = cv2.imdecode(dados, cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise FormatoNaoSuportado("não consegui abrir este PNG")
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA if arr.shape[-1] == 4 else cv2.COLOR_BGR2RGB)
        with Image.open(caminho) as im:
            icc = im.info.get("icc_profile")
            d = im.info.get("dpi")
            dpi = float(d[0]) if d else None
    else:
        with Image.open(caminho) as im:
            im = ImageOps.exif_transpose(im)  # foto de celular "deitada"
            icc = im.info.get("icc_profile")
            d = im.info.get("dpi")
            dpi = float(d[0]) if d else None
            if im.mode == "CMYK":
                im = im.convert("RGB")
                icc = None  # o perfil CMYK não vale mais depois da conversão
            elif im.mode not in ("RGB", "RGBA", "L", "LA", "I;16"):
                im = im.convert("RGB")
            arr = np.asarray(im)

    rgb, bits = _normalizar(arr)
    if dpi is not None and not (1 <= dpi <= 10000):
        dpi = None
    return Foto(rgb=np.ascontiguousarray(rgb), bits=bits, icc=icc, dpi=dpi, caminho=caminho)


def para_inteiro(rgb: np.ndarray, bits: int) -> np.ndarray:
    """float 0..1 -> uint8/uint16, com arredondamento."""
    if bits == 16:
        return np.clip(rgb * 65535.0 + 0.5, 0, 65535).astype(np.uint16)
    return np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)


def para_uint8(rgb: np.ndarray) -> np.ndarray:
    return para_inteiro(rgb, 8)


def salvar_jpeg(rgb: np.ndarray, caminho: str | Path, qualidade: int = 88) -> None:
    Image.fromarray(para_uint8(rgb)).save(caminho, quality=qualidade)


def jpeg_bytes(rgb_u8: np.ndarray, qualidade: int = 85) -> bytes:
    import io

    buf = io.BytesIO()
    Image.fromarray(rgb_u8).save(buf, format="JPEG", quality=qualidade)
    return buf.getvalue()
