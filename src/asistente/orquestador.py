import logging
import time

import numpy as np

from asistente.llm.base import ErrorDeRed
from comun.estados import Estado

logger = logging.getLogger(__name__)

MENSAJE_SIN_RED = "No puedo ayudarte con esto hasta que estés conectado a una red."
MENSAJE_NO_ENTENDIDO = "No te he entendido."

# Pacing de la red de seguridad de ejecutar(). Sin él, un colaborador que
# falle en cada bloque de audio entregado (p. ej. Detector.procesar contra
# un ONNX o un numpy mal compilados en ARM) reintentaría a la velocidad de
# llegada del audio, ~30 bloques/s, escribiendo una traza completa por
# fallo: en una Raspberry Pi desatendida que registra a fichero, eso llena
# la tarjeta SD en minutos. La espera crece con cada fallo consecutivo y se
# limita a un tope razonable.
ESPERA_BASE_TRAS_FALLO = 0.1  # segundos
ESPERA_TOPE_TRAS_FALLO = 30.0  # segundos


class Orquestador:
    """La máquina de estados del asistente.

    Recibe todas sus dependencias ya construidas y solo las usa a través de
    sus interfaces: no importa sounddevice, httpx, google-genai ni pygame. Eso
    es lo que permite ejercitar el ciclo completo, incluidos los caminos de
    error, sin micrófono ni conexión.
    """

    def __init__(self, captura, detector, vad, stt, llm, tts, reproductor, cara) -> None:
        self._captura = captura
        self._detector = detector
        self._vad = vad
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._reproductor = reproductor
        self._cara = cara
        # Estado de la red de seguridad de ejecutar(): cuántos fallos
        # inesperados van seguidos (para el backoff) y cuál fue el último
        # (para no repetir su traza completa).
        self._fallos_consecutivos = 0
        self._firma_ultimo_fallo = None
        self._repeticiones_mismo_fallo = 0

    def ejecutar(self) -> None:
        """Bucle principal: un ciclo tras otro, para siempre.

        `un_ciclo()` ya traduce `ErrorDeRed` en un aviso hablado, así que lo
        que llega hasta aquí es siempre un fallo inesperado (un bug en algún
        cliente de la Tarea 15/16, por ejemplo). Ese fallo se registra con
        logging (nunca se imprime: este proceso comparte terminal con la
        cara), se vacía la cola de captura (para no arrastrar al siguiente
        ciclo audio grabado a medio ciclo, que puede ser la propia voz
        sintetizada del asistente saliendo por el altavoz), la cara vuelve a
        REPOSO, y el bucle sigue en el siguiente ciclo en vez de morir: un
        asistente de palabra clave que se calla de noche por una excepción
        no capturada es peor que uno que se recupera solo.

        Un fallo que se repite en cada ciclo (p. ej. un colaborador roto que
        lanza en cada bloque de audio) se frena con una espera creciente y
        no vuelve a escribir su traza completa cada vez: solo la primera, y
        luego un aviso corto de cuántas veces se ha suprimido. El contador
        de fallos consecutivos se reinicia en cuanto un ciclo completa bien.

        `KeyboardInterrupt` y `SystemExit` no son `Exception` y por tanto no
        se capturan aquí: deben propagar para poder parar el proceso.
        """
        self._cara.set_estado(Estado.REPOSO)
        while True:
            try:
                self.un_ciclo()
            except Exception as excepcion:
                self._registrar_fallo_inesperado(excepcion)
                self._captura.vaciar()
                self._cara.set_estado(Estado.REPOSO)
                time.sleep(self._espera_tras_fallo())
            else:
                self._fallos_consecutivos = 0
                self._firma_ultimo_fallo = None
                self._repeticiones_mismo_fallo = 0

    def _registrar_fallo_inesperado(self, excepcion: Exception) -> None:
        self._fallos_consecutivos += 1
        firma = (type(excepcion), str(excepcion))
        if firma == self._firma_ultimo_fallo:
            self._repeticiones_mismo_fallo += 1
            logger.warning(
                "Mismo error que el ciclo anterior, %d veces suprimido: %s: %s",
                self._repeticiones_mismo_fallo,
                firma[0].__name__,
                firma[1],
            )
        else:
            self._firma_ultimo_fallo = firma
            self._repeticiones_mismo_fallo = 0
            logger.exception(
                "Excepción inesperada en un_ciclo(); se descarta y se sigue"
            )

    def _espera_tras_fallo(self) -> float:
        return min(
            ESPERA_BASE_TRAS_FALLO * (2 ** (self._fallos_consecutivos - 1)),
            ESPERA_TOPE_TRAS_FALLO,
        )

    def un_ciclo(self) -> None:
        """Espera la palabra clave, atiende una petición, y vuelve a reposo."""
        if not self._esperar_palabra_clave():
            return

        self._detector.reiniciar()
        self._captura.vaciar()
        self._cara.set_estado(Estado.ESCUCHANDO)

        audio = self._grabar_intervencion()

        if not self._vad.hubo_voz:
            # Falso positivo del wake word: nadie dijo nada. Volver a reposo
            # en silencio; hablar aquí sería peor que no despertar.
            self._cara.set_estado(Estado.REPOSO)
            return

        self._cara.set_estado(Estado.PENSANDO)
        try:
            texto = self._stt.transcribir(audio)
        except ErrorDeRed:
            self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
            return

        if not texto.strip():
            self._avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)
            return

        try:
            self._responder(texto)
        except ErrorDeRed:
            self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
            return

        self._cara.set_estado(Estado.REPOSO)

    def _esperar_palabra_clave(self) -> bool:
        bloque = self._captura.leer_bloque()
        if bloque is None:
            return False
        return self._detector.procesar(bloque)

    def _grabar_intervencion(self) -> np.ndarray:
        self._vad.reiniciar()
        bloques = []
        while True:
            bloque = self._captura.leer_bloque()
            if bloque is None:
                break
            bloques.append(bloque)
            if self._vad.procesar(bloque):
                break
        if not bloques:
            return np.array([], dtype=np.int16)
        return np.concatenate(bloques)

    def _responder(self, texto: str) -> None:
        """Sintetiza y reproduce frase a frase, según van llegando.

        No espera a tener la respuesta completa: en cuanto el LLM cierra la
        primera frase, esa frase ya se está oyendo mientras el modelo sigue
        generando el resto."""
        hablando = False
        for frase in self._llm.conversar(texto):
            if not hablando:
                self._cara.set_estado(Estado.HABLANDO)
                hablando = True
            self._decir(frase)
        if not hablando:
            self._avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)

    def _decir(self, texto: str) -> None:
        self._reproductor.reproducir(
            self._tts.sintetizar(texto),
            al_rms=lambda rms: self._cara.set_estado(Estado.HABLANDO, rms=rms),
        )

    def _avisar(self, texto: str, estado: Estado) -> None:
        """Dice un mensaje del sistema y vuelve a reposo.

        Funciona sin internet porque el TTS es local: por eso el asistente
        puede avisar de que no hay red en vez de quedarse mudo."""
        self._cara.set_estado(estado)
        self._decir(texto)
        self._cara.set_estado(Estado.REPOSO)
