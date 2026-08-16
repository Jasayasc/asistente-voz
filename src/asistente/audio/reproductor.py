from collections.abc import Callable, Iterable

import numpy as np
import sounddevice as sd

from asistente.audio.captura import TASA_MUESTREO

MAXIMO_INT16 = 32768.0
MUESTRAS_POR_TROZO = 320  # 20 ms — resolución del movimiento de boca


def calcular_rms(bloque: np.ndarray) -> float:
    """Energía del bloque, normalizada a 0.0–1.0."""
    if bloque.size == 0:
        return 0.0
    muestras = bloque.astype(np.float32) / MAXIMO_INT16
    return float(min(1.0, np.sqrt(np.mean(muestras**2))))


class Reproductor:
    """Reproduce PCM y va informando del volumen de cada trozo.

    Ese segundo trabajo es lo que sincroniza la boca de la cara con la voz:
    el mismo audio que sale por el altavoz alimenta el movimiento labial,
    así que van acompasados por construcción, sin analizar fonemas.

    Consume `chunks` perezosamente: el TTS puede ir generando mientras esto
    reproduce, que es lo que permite empezar a hablar antes de tener la
    respuesta completa.
    """

    def __init__(self, dispositivo: str | None = None) -> None:
        self._dispositivo = dispositivo
        self._cancelado = False

    def detener(self) -> None:
        self._cancelado = True

    def reproducir(
        self, chunks: Iterable[bytes], al_rms: Callable[[float], None]
    ) -> None:
        self._cancelado = False
        stream = sd.OutputStream(
            samplerate=TASA_MUESTREO,
            channels=1,
            dtype="int16",
            device=self._dispositivo,
        )
        stream.start()
        try:
            for chunk in chunks:
                if self._cancelado:
                    break
                muestras = np.frombuffer(chunk, dtype=np.int16)
                for inicio in range(0, len(muestras), MUESTRAS_POR_TROZO):
                    if self._cancelado:
                        break
                    trozo = muestras[inicio : inicio + MUESTRAS_POR_TROZO]
                    al_rms(calcular_rms(trozo))
                    stream.write(trozo)
        finally:
            al_rms(0.0)
            stream.stop()
            stream.close()
