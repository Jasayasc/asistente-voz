# scripts/probar_stt.py
"""Graba 5 segundos del micrófono y los transcribe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from asistente.audio.captura import (  # noqa: E402
    TAMANO_BLOQUE,
    TASA_MUESTREO,
    Captura,
)
from asistente.config import Config  # noqa: E402
from asistente.stt.deepgram import ClienteDeepgram  # noqa: E402

SEGUNDOS = 5


def main() -> int:
    cfg = Config.cargar()
    bloques = []
    necesarios = int(SEGUNDOS * TASA_MUESTREO / TAMANO_BLOQUE)

    print(f"habla durante {SEGUNDOS} segundos...")
    with Captura(cfg.dispositivo_entrada) as captura:
        while len(bloques) < necesarios:
            bloque = captura.leer_bloque()
            if bloque is not None:
                bloques.append(bloque)

    print("transcribiendo...")
    stt = ClienteDeepgram(cfg.deepgram_api_key)
    print(f"-> {stt.transcribir(np.concatenate(bloques))!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
