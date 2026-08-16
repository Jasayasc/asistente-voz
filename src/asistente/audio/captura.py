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
        bloque = datos[:, 0].copy()
        try:
            self._cola.put_nowait(bloque)
            return
        except queue.Full:
            pass

        # La cola está llena: descartamos el más viejo para hacer sitio al
        # que acaba de llegar. Si otro hilo ya la vació por su cuenta,
        # get_nowait lanza Empty — lo ignoramos, porque igual seguimos
        # queriendo intentar el put_nowait de abajo, no rendirnos.
        try:
            self._cola.get_nowait()
        except queue.Empty:
            pass

        try:
            self._cola.put_nowait(bloque)
        except queue.Full:
            # Otro productor ganó la carrera y volvió a llenar la cola
            # entre nuestro get_nowait y este put_nowait. No hay más que
            # intentar sin arriesgarnos a bloquear: se pierde este bloque.
            pass

    def iniciar(self) -> None:
        if self._stream is not None:
            self.detener()

        stream = sd.InputStream(
            samplerate=TASA_MUESTREO,
            blocksize=TAMANO_BLOQUE,
            device=self._dispositivo,
            channels=CANALES,
            dtype=TIPO,
            callback=self._callback,
        )
        try:
            stream.start()
        except Exception:
            # Si el dispositivo rechaza el arranque (ocupado, sin permiso,
            # frecuencia no soportada) el stream ya está abierto en
            # PortAudio. Hay que cerrarlo aquí porque, si esto se llamó
            # desde __enter__, Python no invocará __exit__ y nadie más
            # tendrá ocasión de limpiarlo.
            stream.close()
            raise
        self._stream = stream

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
