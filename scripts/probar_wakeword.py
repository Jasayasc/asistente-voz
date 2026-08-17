# scripts/probar_wakeword.py
"""Escucha el micrófono e imprime la puntuación de la palabra clave.

Sirve para calibrar `UMBRAL_WAKEWORD`: di la palabra varias veces, deja
unos segundos de silencio entre cada una, y al salir con Ctrl+C se resume
qué puntuaciones alcanzaron los intentos y qué dio el ruido de fondo. El
umbral debe quedar cómodamente entre ambos.

Usa el modelo y el umbral que hay en `.env`, no unos fijos: lo que se ve
aquí es exactamente lo que hará el asistente.

Vigila también el nivel de entrada. openWakeWord no normaliza la ganancia:
fue entrenado con voz a nivel normal, así que un micrófono con la ganancia
demasiado alta satura la señal, llena el espectro de distorsión y hunde las
puntuaciones a cero justo cuando más alto hablas. Si aparece el aviso de
saturación, baja el nivel del micrófono en Windows (Configuración > Sonido >
Entrada) o desactiva el "refuerzo de micrófono" antes de tocar el umbral.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from asistente.audio.captura import Captura  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.wake.detector import Detector  # noqa: E402

MUESTRA_SATURADA = 32700  # a partir de aquí la muestra está recortada
RMS_ALTO = 0.15  # por encima de esto la voz entra demasiado fuerte
RMS_VOZ = 0.01  # a partir de aquí consideramos que hay voz, no silencio


def _rms(bloque: np.ndarray) -> float:
    muestras = bloque.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(muestras**2)))


def _resumen(picos: list[float], fondo: list[float], saturados: int) -> None:
    print("\n--- resumen ---")
    if saturados:
        print(
            f"AVISO: {saturados} bloques saturados. El micrófono entra "
            "demasiado fuerte y eso hunde las puntuaciones: baja su nivel "
            "en Windows antes de tocar el umbral."
        )
    if not picos:
        print("no se detectó ningún intento (ninguna puntuación pasó de 0.1).")
        return

    picos.sort(reverse=True)
    print(f"intentos detectados: {len(picos)}")
    print("  picos: " + ", ".join(f"{p:.3f}" for p in picos))
    techo_fondo = max(fondo) if fondo else 0.0
    print(f"  ruido de fondo, máximo: {techo_fondo:.3f}")

    # Un umbral útil deja pasar los intentos flojos y sigue por encima del
    # ruido. La media geométrica entre el intento más flojo y el techo del
    # ruido reparte el margen entre los dos errores posibles.
    flojo = picos[-1]
    if flojo > techo_fondo:
        sugerido = (flojo * max(techo_fondo, 0.02)) ** 0.5
        print(f"  umbral sugerido: {sugerido:.2f}  (UMBRAL_WAKEWORD en .env)")
    else:
        print(
            "  el ruido puntúa tan alto como los intentos: no hay umbral "
            "que separe. Acércate al micrófono o baja el ruido ambiente."
        )


def main() -> int:
    cfg = Config.cargar()
    detector = Detector(cfg.modelo_wakeword, cfg.umbral_wakeword)
    nombre = cfg.modelo_wakeword.replace("_", " ")
    print(f"escuchando. di '{nombre}' varias veces, con pausas entre ellas.")
    print(f"umbral actual: {cfg.umbral_wakeword}. Ctrl+C para el resumen.")

    picos: list[float] = []
    fondo: list[float] = []
    saturados = 0
    pico_actual = 0.0  # máximo del intento que se está viendo ahora mismo

    with Captura(cfg.dispositivo_entrada) as captura:
        try:
            while True:
                bloque = captura.leer_bloque()
                if bloque is None:
                    continue

                if int(np.abs(bloque).max()) >= MUESTRA_SATURADA:
                    saturados += 1

                p = detector.puntuacion(bloque)
                nivel = _rms(bloque)

                if p > 0.1:
                    # Dentro de un intento: quedarse con su máximo. Las
                    # puntuaciones suben y bajan a lo largo de ~1 segundo,
                    # y contarlas todas inflaría la cuenta de intentos.
                    pico_actual = max(pico_actual, p)
                else:
                    if pico_actual:
                        picos.append(pico_actual)
                        pico_actual = 0.0
                    if nivel < RMS_VOZ:
                        fondo.append(p)

                # Se imprime también cuando solo hay nivel y ninguna
                # puntuación. Sin esto, un micrófono que capta la voz
                # deformada —efectos de Windows, ganancia mal puesta— no
                # muestra absolutamente nada en pantalla, y no hay forma de
                # distinguir "no me oye" de "me oye y no me reconoce".
                if p > 0.1 or nivel >= RMS_VOZ:
                    barra = "#" * min(30, int(nivel * 200))
                    marca = "  <<< DETECTADO" if p >= cfg.umbral_wakeword else ""
                    if nivel > RMS_ALTO:
                        marca += "  [SATURADO: baja el nivel del micrófono]"
                    print(f"nivel {nivel:.3f} |{barra:<30}| score {p:.3f}{marca}")
        except KeyboardInterrupt:
            if pico_actual:
                picos.append(pico_actual)
            _resumen(picos, fondo, saturados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
