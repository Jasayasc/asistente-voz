# scripts/probar_sin_efectos.py
"""Compara el micrófono con y sin los efectos de audio de Windows.

Windows 11 carga sobre el micrófono un procesador propio ("Voice Clarity")
que suprime ruido antes de que la señal llegue a la aplicación. Con voz
lejana o floja llega a tratarla como ruido y vaciarla, y entonces ni el
wake word ni la transcripción reconocen nada aunque el nivel parezca
correcto.

El modo compartido de WASAPI, MME y DirectSound pasan por ese procesador.
El modo exclusivo no: habla con el dispositivo directamente. Este script
graba por los dos caminos, puntúa el wake word en cada uno y enseña el
reparto de energía por frecuencia, que es donde se ve el destrozo: la voz
inteligible necesita energía entre 1 y 3 kHz, y un supresor agresivo se la
come.

Uso:  .venv\\Scripts\\python.exe scripts\\probar_sin_efectos.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from asistente.audio.captura import TAMANO_BLOQUE, TASA_MUESTREO, Captura  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.wake.detector import Detector  # noqa: E402

SEGUNDOS = 12
SR_NATIVO = 48000  # lo que el Realtek acepta en exclusivo; se remuestrea a 16k


def _dispositivo_wasapi() -> int | None:
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        if "WASAPI" in sd.query_hostapis(d["hostapi"])["name"]:
            return i
    return None


def _grabar_como_el_asistente(dispositivo) -> np.ndarray:
    """Por el mismo camino que usa el asistente: MME/predeterminado a 16 kHz,
    con los efectos de Windows aplicados."""
    bloques = []
    inicio = time.time()
    with Captura(dispositivo) as captura:
        while time.time() - inicio < SEGUNDOS:
            bloque = captura.leer_bloque(timeout=1.0)
            if bloque is not None:
                bloques.append(bloque)
    return np.concatenate(bloques) if bloques else np.array([], dtype=np.int16)


def _grabar_exclusivo(dispositivo) -> np.ndarray:
    """Por WASAPI en modo exclusivo, que no pasa por los efectos.

    El formato exacto que acepta el modo exclusivo depende del driver, así
    que se prueban varias combinaciones en vez de dar una por supuesta: es
    lo que falla en modo compartido cuando el formato de mezcla es estéreo.
    """
    ultimo_error = None
    for canales in (1, 2):
        for bloque_dev in (int(SR_NATIVO * 0.08), 0):
            trozos = []
            try:
                with sd.InputStream(
                    samplerate=SR_NATIVO,
                    device=dispositivo,
                    channels=canales,
                    dtype="int16",
                    blocksize=bloque_dev,
                    extra_settings=sd.WasapiSettings(exclusive=True),
                    callback=lambda datos, *_: trozos.append(datos[:, 0].copy()),
                ):
                    print(f"    (abierto en exclusivo: {canales} canal(es), bloque {bloque_dev})")
                    time.sleep(SEGUNDOS)
            except Exception as excepcion:
                ultimo_error = excepcion
                continue
            if not trozos:
                continue
            audio = np.concatenate(trozos).astype(np.float32)
            audio = resample_poly(audio, TASA_MUESTREO, SR_NATIVO)
            return np.clip(audio, -32768, 32767).astype(np.int16)

    print(f"    no se pudo abrir en exclusivo: {ultimo_error}")
    return np.array([], dtype=np.int16)


def _informar(etiqueta: str, audio: np.ndarray, umbral: float, modelo: str) -> None:
    print(f"\n===== {etiqueta} =====")
    if audio.size == 0:
        print("  no se grabó nada.")
        return

    bloques = [
        audio[i : i + TAMANO_BLOQUE]
        for i in range(0, len(audio) - TAMANO_BLOQUE + 1, TAMANO_BLOQUE)
    ]
    niveles = np.array(
        [float(np.sqrt(np.mean((b.astype(np.float32) / 32768.0) ** 2))) for b in bloques]
    )

    detector = Detector(modelo, umbral)
    puntuaciones = np.array([detector.puntuacion(b) for b in bloques])

    print(f"  nivel: mediana={np.median(niveles):.4f}  p95={np.percentile(niveles, 95):.4f}")
    print(f"  wake word: máximo={puntuaciones.max():.3f}  (umbral {umbral})")
    print(f"  bloques que dispararían: {int((puntuaciones >= umbral).sum())}")

    # El reparto por frecuencia solo tiene sentido donde hay voz.
    fuertes = [b for b, n in zip(bloques, niveles) if n >= 0.02]
    if fuertes:
        seg = np.concatenate(fuertes).astype(np.float32) / 32768.0
        pot = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        frec = np.fft.rfftfreq(len(seg), 1 / TASA_MUESTREO)
        total = pot.sum()
        banda_voz = ((frec >= 1000) & (frec < 3000))
        print(f"  energía en 1-3 kHz (consonantes): {100 * pot[banda_voz].sum() / total:.1f}%")
        print(f"  90% de la energía por debajo de: {frec[np.searchsorted(np.cumsum(pot) / total, 0.9)]:.0f} Hz")


def main() -> int:
    cfg = Config.cargar()
    dispositivo = _dispositivo_wasapi()
    if dispositivo is None:
        print("No hay ningún dispositivo de entrada WASAPI en esta máquina.")
        return 1
    print(f"dispositivo WASAPI: {sd.query_devices(dispositivo)['name']}")

    print(f"\n1/2 CON los efectos de Windows. Di 'hey jarvis' 3 veces ({SEGUNDOS} s)...")
    input("    pulsa Enter y empieza a hablar: ")
    con = _grabar_como_el_asistente(cfg.dispositivo_entrada)
    print("    hecho.")

    print(f"\n2/2 SIN los efectos de Windows. Lo mismo otra vez ({SEGUNDOS} s)...")
    input("    pulsa Enter y empieza a hablar: ")
    sin = _grabar_exclusivo(dispositivo)
    print("    hecho.")

    _informar("CON efectos (lo que usa el asistente hoy)", con, cfg.umbral_wakeword, cfg.modelo_wakeword)
    _informar("SIN efectos (WASAPI exclusivo)", sin, cfg.umbral_wakeword, cfg.modelo_wakeword)

    print(
        "\nSi la segunda tiene bastante más energía en 1-3 kHz y puntúa más "
        "alto, el culpable es el procesador de voz de Windows, y merece la "
        "pena que el asistente abra el micrófono en exclusivo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
