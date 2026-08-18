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
        bloques_para_voz: int = 2,
    ) -> None:
        self._umbral = umbral
        # Cuántos bloques seguidos por encima del umbral hacen falta para
        # dar la voz por empezada. Con uno solo bastaba un chasquido —o,
        # peor, la cola de la propia voz del asistente colándose desde el
        # altavoz— para abrir una intervención: `hubo_voz` se ponía a True,
        # el resto eran silencio, y se mandaba a transcribir un segundo de
        # ruido propio. Dos bloques son 160 ms: menos que cualquier sílaba
        # real, más que cualquier golpe seco.
        self._bloques_para_voz = max(1, bloques_para_voz)
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

    def _en_bloques(self, segundos: float) -> int:
        return max(1, int(segundos / SEGUNDOS_POR_BLOQUE + 0.5))

    def reiniciar(self, segundos_sin_voz: float | None = None) -> None:
        """Prepara la escucha de una intervención.

        `segundos_sin_voz` permite alargar, solo para esta intervención, la
        paciencia con el silencio inicial. Existe por el modo conversación:
        tras la palabra clave, tres segundos sin oír nada significan que el
        wake word se disparó solo y hay que volver a reposo cuanto antes;
        pero en mitad de una conversación ese mismo silencio es la persona
        pensando qué preguntar a continuación, y cortarle a los tres
        segundos obliga a decir "hey jarvis" otra vez, que es justo lo que
        el modo conversación viene a quitar.
        """
        self._silencios = 0
        self._bloques_de_voz = 0
        self._con_energia = 0
        self.hubo_voz = False
        self._bloques_sin_voz_actual = (
            self._bloques_sin_voz
            if segundos_sin_voz is None
            else self._en_bloques(segundos_sin_voz)
        )

    def procesar(self, bloque: np.ndarray) -> bool:
        if self._energia(bloque) >= self._umbral:
            self._con_energia += 1
            self._silencios = 0
            if self._con_energia >= self._bloques_para_voz:
                self.hubo_voz = True
        else:
            self._con_energia = 0
            self._silencios += 1

        if not self.hubo_voz:
            # Todavía no ha empezado a hablar: si el silencio se alarga,
            # es un falso positivo del wake word, no una pausa dentro de
            # una intervención real. Corta con su propio tope, que en modo
            # conversación es mucho más largo. `maximo_segundos` no pinta
            # nada aquí: es el tope de lo que se GRABA, no de lo que se
            # espera.
            return self._silencios >= self._bloques_sin_voz_actual

        # A partir de que hay voz, `maximo_segundos` acota la grabación.
        # Se cuenta desde que empezó a hablar y no desde que se empezó a
        # escuchar: con la espera de 8 s del modo conversación metida en la
        # misma cuenta, a quien se quedaba pensando siete segundos se le
        # cortaba la pregunta a la mitad.
        self._bloques_de_voz += 1
        if self._bloques_de_voz >= self._bloques_maximos:
            return True
        return self._silencios >= self._bloques_silencio_necesarios

    @staticmethod
    def _energia(bloque: np.ndarray) -> float:
        muestras = bloque.astype(np.float32) / MAXIMO_INT16
        return float(np.sqrt(np.mean(muestras**2)))
