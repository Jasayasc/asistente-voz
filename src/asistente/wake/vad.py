import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE, TASA_MUESTREO

SEGUNDOS_POR_BLOQUE = TAMANO_BLOQUE / TASA_MUESTREO
MAXIMO_INT16 = 32768.0


class DetectorSilencio:
    """Decide cuándo el usuario ha terminado de hablar.

    Es un detector por energía, no un VAD entrenado: para un asistente que
    escucha a un metro de distancia en una habitación tranquila es
    suficiente, y no cuesta CPU ni añade dependencias.

    Distingue dos situaciones que parecen la misma pero no lo son: el
    usuario ha terminado de hablar (`procesar` devuelve True y `hubo_voz`
    es True), y el asistente despertó por error y nadie dijo nada
    (`hubo_voz` es False). La segunda no debe producir respuesta.
    """

    def __init__(
        self,
        umbral: float = 0.02,
        segundos_silencio: float = 1.0,
        segundos_sin_voz: float = 3.0,
        maximo_segundos: float = 12.0,
    ) -> None:
        self._umbral = umbral
        self._bloques_silencio_necesarios = max(
            1, int(segundos_silencio / SEGUNDOS_POR_BLOQUE + 0.5)
        )
        # Tope corto para el caso "el wake word disparó y nadie habló": sin
        # esto, un falso positivo solo corta en `maximo_segundos` (pensado
        # para intervenciones largas de verdad), y durante esa espera el
        # detector de palabra clave no se ejecuta —el asistente queda sordo
        # a su propio nombre— y cualquier conversación ambiental que ocurra
        # dentro de la ventana se transcribe y se contesta sin que nadie lo
        # haya pedido.
        self._bloques_sin_voz = max(
            1, int(segundos_sin_voz / SEGUNDOS_POR_BLOQUE + 0.5)
        )
        self._bloques_maximos = max(1, int(maximo_segundos / SEGUNDOS_POR_BLOQUE + 0.5))
        self.reiniciar()

    def reiniciar(self) -> None:
        self._silencios = 0
        self._bloques = 0
        self.hubo_voz = False

    def procesar(self, bloque: np.ndarray) -> bool:
        self._bloques += 1
        if self._energia(bloque) >= self._umbral:
            self.hubo_voz = True
            self._silencios = 0
        else:
            self._silencios += 1

        if self._bloques >= self._bloques_maximos:
            return True
        if not self.hubo_voz:
            # Todavía no ha empezado a hablar: si el silencio se alarga,
            # es un falso positivo del wake word, no una pausa dentro de
            # una intervención real. Corta con su propio tope, más corto
            # que `maximo_segundos`.
            return self._silencios >= self._bloques_sin_voz
        return self._silencios >= self._bloques_silencio_necesarios

    @staticmethod
    def _energia(bloque: np.ndarray) -> float:
        muestras = bloque.astype(np.float32) / MAXIMO_INT16
        return float(np.sqrt(np.mean(muestras**2)))
