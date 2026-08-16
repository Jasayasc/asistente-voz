# scripts/probar_voz.py
"""Sintetiza una frase y la reproduce, mostrando el RMS por consola."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.audio.reproductor import Reproductor  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.tts.piper import Piper  # noqa: E402

FRASE = "Hola. Soy tu asistente. Si me oyes con claridad, la voz funciona."


def main() -> int:
    cfg = Config.cargar()
    piper = Piper(cfg.ruta_voz)
    print(f"tasa de muestreo del modelo: {piper.tasa_muestreo} Hz")

    reproductor = Reproductor(cfg.dispositivo_salida, piper.tasa_muestreo)
    reproductor.reproducir(
        piper.sintetizar(FRASE),
        al_rms=lambda r: print(f"\rrms {r:.2f} {'#' * int(r * 40):<40}", end=""),
    )
    print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
