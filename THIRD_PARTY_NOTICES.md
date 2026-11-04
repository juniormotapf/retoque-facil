# Componentes de terceiros

O código do Retoque Fácil é MIT (veja `LICENSE`). Ele usa e redistribui os componentes abaixo.

## Modelos incluídos em `src/retoque_facil/modelos/`

Os dois modelos são do Google (projeto MediaPipe), licenciados sob **Apache License 2.0**,
redistribuídos sem modificação. Cópia da licença: https://www.apache.org/licenses/LICENSE-2.0

| Arquivo | Origem | SHA-256 |
|---|---|---|
| `face_landmarker.task` | https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` |
| `selfie_multiclass_256x256.tflite` | https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite | `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0` |

Copyright Google LLC. Os cartões dos modelos (uso previsto e limitações) estão em
https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker e
https://ai.google.dev/edge/mediapipe/solutions/vision/image_segmenter.

## Bibliotecas Python (baixadas na instalação)

| Pacote | Licença |
|---|---|
| mcp (SDK do Model Context Protocol) | MIT |
| mediapipe | Apache-2.0 |
| opencv-contrib-python | Apache-2.0 |
| numpy | BSD-3-Clause (e outras permissivas) |
| pillow | MIT-CMU |
| tifffile | BSD-3-Clause |
| imagecodecs | BSD-3-Clause |
| anyio | MIT |
| matplotlib (dependência do mediapipe) | licença PSF/matplotlib |

## Referências de método

- Formato de camadas: especificação pública "Adobe Photoshop File Formats Specification"
  (seção Layer and Mask Information) e Adobe TIFF Technical Note (ImageSourceData, tag 37724).
- Filtro guiado: K. He, J. Sun, X. Tang, "Guided Image Filtering", ECCV 2010.
