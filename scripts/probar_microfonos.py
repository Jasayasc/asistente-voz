# scripts/probar_microfonos.py
"""Compara todos los micrófonos del equipo con la palabra de activación.

El asistente usa el micrófono predeterminado de Windows, y ese no siempre
es el que oye bien. Una entrada de la placa sin micrófono conectado, o un
micrófono tapado o mal orientado, entrega sonido apagado: nivel aparente
normal pero sin la banda de 1 a 3 kHz, que es donde viven las consonantes.
El detector no reconoce nada, aunque el medidor de nivel se mueva.

Este script graba unos segundos por cada entrada y compara tres cosas: el
nivel, cuánta energía llega en la banda de consonantes, y qué puntúa la
palabra de activación. El micrófono bueno destaca en las tres.

Uso:  .venv\\Scripts\\python.exe scripts\\probar_microfonos.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from asistente.audio.captura import TAMANO_BLOQUE, TASA_MUESTREO  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.wake.detector import Detector  # noqa: E402

SEGUNDOS = 8


def _entradas() -> list[tuple[int, dict]]:
    """Una entrada por dispositivo físico, evitando duplicados.

    Windows expone el mismo micrófono en varias APIs (MME, DirectSound,
    WASAPI, WDM-KS). Probarlas todas alargaría la sesión sin aportar: basta
    con una por nombre, y se prefiere MME porque es la que usa el asistente
    por omisión.
    """
    vistos: dict[str, tuple[int, dict]] = {}
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        api = sd.query_hostapis(d["hostapi"])["name"]
        if api not in ("MME", "Windows WASAPI"):
            continue
        nombre = d["name"].strip()
        if nombre.lower().startswith(("asignador", "controlador primario")):
            continue  # no son dispositivos, son enrutadores del sistema
        if nombre not in vistos or api == "MME":
            vistos.setdefault(nombre, (i, d))
    return list(vistos.values())


def _grabar(indice: int, info: dict) -> np.ndarray:
    """Graba a 16 kHz; si el dispositivo no lo acepta, a su tasa y remuestrea."""
    for tasa in (TASA_MUESTREO, int(info["default_samplerate"])):
        for canales in (1, min(2, int(info["max_input_channels"]))):
            trozos: list[np.ndarray] = []
            try:
                with sd.InputStream(
                    samplerate=tasa,
                    device=indice,
                    channels=canales,
                    dtype="int16",
                    blocksize=int(tasa * 0.08),
                    callback=lambda datos, *_: trozos.append(datos[:, 0].copy()),
                ):
                    time.sleep(SEGUNDOS)
            except Exception:
                continue
            if not trozos:
                continue
            audio = np.concatenate(trozos)
            if tasa != TASA_MUESTREO:
                audio = resample_poly(audio.astype(np.float32), TASA_MUESTREO, tasa)
                audio = np.clip(audio, -32768, 32767).astype(np.int16)
            return audio
    return np.array([], dtype=np.int16)


def _medir(audio: np.ndarray, modelo: str, umbral: float) -> dict:
    bloques = [
        audio[i : i + TAMANO_BLOQUE]
        for i in range(0, len(audio) - TAMANO_BLOQUE + 1, TAMANO_BLOQUE)
    ]
    if not bloques:
        return {}
    niveles = np.array(
        [float(np.sqrt(np.mean((b.astype(np.float32) / 32768.0) ** 2))) for b in bloques]
    )
    detector = Detector(modelo, umbral)
    puntuaciones = np.array([detector.puntuacion(b) for b in bloques])

    fuertes = [b for b, n in zip(bloques, niveles) if n >= 0.02]
    consonantes = float("nan")
    if fuertes:
        seg = np.concatenate(fuertes).astype(np.float32) / 32768.0
        pot = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        frec = np.fft.rfftfreq(len(seg), 1 / TASA_MUESTREO)
        banda = (frec >= 1000) & (frec < 3000)
        consonantes = 100 * float(pot[banda].sum() / pot.sum())
    return {
        "p95": float(np.percentile(niveles, 95)),
        "score": float(puntuaciones.max()),
        "consonantes": consonantes,
    }


def main() -> int:
    cfg = Config.cargar()
    entradas = _entradas()
    if not entradas:
        print("No se encontró ningún micrófono.")
        return 1

    palabra = cfg.modelo_wakeword.replace("_", " ")
    print(f"Se probarán {len(entradas)} micrófonos, {SEGUNDOS} s cada uno.")
    print(f"En cada uno, di '{palabra}' 3 veces. No toques el teclado.\n")

    resultados = []
    for indice, info in entradas:
        api = sd.query_hostapis(info["hostapi"])["name"]
        print(f"--- {info['name'].strip()}  [{api}] ---")
        input(f"    pulsa Enter y di '{palabra}' 3 veces: ")
        audio = _grabar(indice, info)
        if audio.size == 0:
            print("    no se pudo grabar de este dispositivo.\n")
            continue
        medida = _medir(audio, cfg.modelo_wakeword, cfg.umbral_wakeword)
        if not medida:
            print("    grabación demasiado corta.\n")
            continue
        print(
            f"    nivel p95={medida['p95']:.4f}   "
            f"consonantes(1-3kHz)={medida['consonantes']:.1f}%   "
            f"{palabra}={medida['score']:.3f}\n"
        )
        resultados.append((info["name"].strip(), indice, medida))

    if not resultados:
        return 1

    print("=== resumen, de mejor a peor ===")
    resultados.sort(key=lambda r: r[2]["score"], reverse=True)
    for nombre, indice, m in resultados:
        print(
            f"  {m['score']:.3f}  {nombre}  "
            f"(consonantes {m['consonantes']:.1f}%, nivel {m['p95']:.4f})"
        )

    nombre, indice, mejor = resultados[0]
    if mejor["score"] >= cfg.umbral_wakeword:
        print(f"\nUsa este: pon en .env  DISPOSITIVO_ENTRADA={nombre}")
    else:
        print(
            "\nNinguno reconoce la palabra. Como referencia, un micrófono "
            "sano da más del 10% de energía en 1-3 kHz; muy por debajo "
            "significa que la voz llega apagada (micrófono tapado, mal "
            "orientado, lejos, o una entrada sin micrófono conectado)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
