import logging

import numpy as np

from asistente.llm.base import ErrorDeRed
from comun.estados import Estado

logger = logging.getLogger(__name__)

MENSAJE_SIN_RED = "No puedo ayudarte con esto hasta que estés conectado a una red."
MENSAJE_NO_ENTENDIDO = "No te he entendido."


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

    def ejecutar(self) -> None:
        """Bucle principal: un ciclo tras otro, para siempre.

        `un_ciclo()` ya traduce `ErrorDeRed` en un aviso hablado, así que lo
        que llega hasta aquí es siempre un fallo inesperado (un bug en algún
        cliente de la Tarea 15/16, por ejemplo). Ese fallo se registra con
        logging (nunca se imprime: este proceso comparte terminal con la
        cara) y el bucle sigue en el siguiente ciclo en vez de morir: un
        asistente de palabra clave que se calla de noche por una excepción
        no capturada es peor que uno que se recupera solo.

        `KeyboardInterrupt` y `SystemExit` no son `Exception` y por tanto no
        se capturan aquí: deben propagar para poder parar el proceso.
        """
        self._cara.set_estado(Estado.REPOSO)
        while True:
            try:
                self.un_ciclo()
            except Exception:
                logger.exception(
                    "Excepción inesperada en un_ciclo(); se descarta y se sigue"
                )
                self._cara.set_estado(Estado.REPOSO)

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
