"""Envía estados a la cara manualmente, para verla sin el resto del sistema.

Uso:
    python -m cara            (en una terminal)
    python scripts/probar_cara.py   (en otra)
"""
import math
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.config import Config  # noqa: E402
from comun.estados import Estado  # noqa: E402
from comun.protocolo import Mensaje, codificar  # noqa: E402

GUION = [
    (Estado.REPOSO, 4.0),
    (Estado.ESCUCHANDO, 3.0),
    (Estado.PENSANDO, 3.0),
    (Estado.HABLANDO, 5.0),
    (Estado.ERROR, 2.0),
]


def main() -> int:
    cfg = Config.cargar()
    with socket.create_connection((cfg.host_cara, cfg.puerto_cara)) as sock:
        for estado, duracion in GUION:
            print(f"-> {estado.value} ({duracion}s)")
            fin = time.time() + duracion
            while time.time() < fin:
                if estado is Estado.HABLANDO:
                    # Onda que imita el ritmo del habla, para ver la boca.
                    t = time.time() * 6
                    rms = abs(math.sin(t)) * (0.5 + 0.5 * abs(math.sin(t / 3)))
                else:
                    rms = 0.0
                sock.sendall(codificar(Mensaje(estado, rms=rms)))
                time.sleep(0.03)
    return 0


if __name__ == "__main__":
    sys.exit(main())
