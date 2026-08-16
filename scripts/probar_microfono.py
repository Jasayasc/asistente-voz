# scripts/probar_microfono.py
"""Graba 5 segundos y guarda prueba.wav. Verifica que el micrófono funciona."""
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from asistente.audio.captura import (  # noqa: E402
    TAMANO_BLOQUE,
    TASA_MUESTREO,
    Captura,
)
from asistente.config import Config  # noqa: E402

SEGUNDOS = 5


def main() -> int:
    cfg = Config.cargar()
    bloques_necesarios = int(SEGUNDOS * TASA_MUESTREO / TAMANO_BLOQUE)
    bloques = []

    print(f"grabando {SEGUNDOS} segundos, habla ahora...")
    with Captura(cfg.dispositivo_entrada) as captura:
        while len(bloques) < bloques_necesarios:
            bloque = captura.leer_bloque()
            if bloque is not None:
                bloques.append(bloque)

    audio = np.concatenate(bloques)
    pico = int(np.abs(audio).max())
    print(f"pico de amplitud: {pico} (de 32767)")
    if pico < 500:
        print("AVISO: señal muy débil. ¿Micrófono correcto? ¿Silenciado?")

    with wave.open("prueba.wav", "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TASA_MUESTREO)
        wav.writeframes(audio.tobytes())
    print("escrito prueba.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
