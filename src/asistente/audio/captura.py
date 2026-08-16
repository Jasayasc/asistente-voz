# src/asistente/audio/captura.py
import queue

import numpy as np
import sounddevice as sd

TASA_MUESTREO = 16000
TAMANO_BLOQUE = 1280  # 80 ms — es el tamaño que espera openWakeWord
CANALES = 1
TIPO = "int16"

MAX_BLOQUES_EN_COLA = 50  # ~4 segundos; más allá se descartan los viejos


class Captura:
    """Lee del micrófono en bloques de tamaño fijo.

    `sounddevice` entrega el audio desde un hilo propio de PortAudio. Ese
    callback no puede bloquearse ni hacer trabajo pesado, así que solo
    encola. Si el consumidor se retrasa, se descartan los bloques más
    antiguos: en un asistente de voz, el audio viejo no sirve de nada.
    """

    def __init__(self, dispositivo: str | None = None) -> None:
        self._dispositivo = dispositivo
        self._cola: queue.Queue = queue.Queue(maxsize=MAX_BLOQUES_EN_COLA)
        self._stream: sd.InputStream | None = None

    def _callback(self, datos, frames, tiempo, estado) -> None:
        try:
            self._cola.put_nowait(datos[:, 0].copy())
        except queue.Full:
            try:
                self._cola.get_nowait()
                self._cola.put_nowait(datos[:, 0].copy())
            except (queue.Empty, queue.Full):
                pass

    def iniciar(self) -> None:
        self._stream = sd.InputStream(
            samplerate=TASA_MUESTREO,
            blocksize=TAMANO_BLOQUE,
            device=self._dispositivo,
            channels=CANALES,
            dtype=TIPO,
            callback=self._callback,
        )
        self._stream.start()

    def leer_bloque(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._cola.get(timeout=timeout)
        except queue.Empty:
            return None

    def vaciar(self) -> None:
        """Descarta lo acumulado. Se llama al despertar, para no procesar
        audio anterior a la palabra clave."""
        while True:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                return

    def detener(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "Captura":
        self.iniciar()
        return self

    def __exit__(self, *exc) -> None:
        self.detener()
