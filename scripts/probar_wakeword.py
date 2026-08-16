# scripts/probar_wakeword.py
"""Escucha el micrófono e imprime la puntuación de la palabra clave.

Sirve para calibrar el umbral: di la palabra varias veces y mira qué
puntuaciones alcanza, luego habla normal y mira qué puntuaciones da el
ruido de fondo. El umbral debe quedar cómodamente entre ambos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.audio.captura import Captura  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.wake.detector import Detector  # noqa: E402


def main() -> int:
    cfg = Config.cargar()
    detector = Detector()
    print("escuchando. di 'hey jarvis'. Ctrl+C para salir.")

    with Captura(cfg.dispositivo_entrada) as captura:
        try:
            while True:
                bloque = captura.leer_bloque()
                if bloque is None:
                    continue
                p = detector.puntuacion(bloque)
                if p > 0.1:
                    marca = "  <<< DETECTADO" if p >= 0.5 else ""
                    print(f"{p:.3f}{marca}")
        except KeyboardInterrupt:
            print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
