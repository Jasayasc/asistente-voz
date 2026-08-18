import logging
import time

import numpy as np

from asistente.conversacion import FRASES_DE_DESPEDIDA, es_despedida
from asistente.llm.base import ErrorDeRed
from comun.estados import Estado

logger = logging.getLogger(__name__)

MENSAJE_SIN_RED = "No puedo ayudarte con esto hasta que estés conectado a una red."
MENSAJE_NO_ENTENDIDO = "No te he entendido."
MENSAJE_DESPEDIDA = "Hasta luego."
# Cuando se cierra por no entender, hay que decir algo más que "no te he
# entendido": el usuario tiene que saber que el asistente ha dejado de
# escuchar, o se quedará hablándole a un aparato que ya no le oye.
MENSAJE_ME_RINDO = "Sigo sin entenderte. Di la palabra clave cuando quieras."

# Cuántas transcripciones vacías seguidas se toleran antes de cerrar la
# conversación. Sin tope, una tele de fondo o un micrófono con ruido
# mantienen al asistente en bucle: graba, no entiende, avisa, y vuelve a
# grabar su propio aviso.
MAX_SIN_ENTENDER = 2

# Lo mismo para los fallos del STT o del LLM. Un 503 de "el modelo está
# saturado" es habitual y pasajero —medido, uno de cada cinco turnos en una
# conversación real—, y cerrar la conversación por eso obliga a decir la
# palabra clave otra vez y a repetir el contexto: justo lo que el modo
# conversación viene a quitar. Se avisa, se sigue escuchando, y solo se
# cierra si vuelve a fallar seguido, que ya sí parece una avería de verdad.
MAX_FALLOS_SEGUIDOS = 2
MENSAJE_SIN_RED_DEFINITIVO = (
    "Sigo sin poder conectarme. Di la palabra clave cuando quieras."
)
# Cuando el modelo termina sin escribir una palabra. Antes esto decía "no
# te he entendido", que culpa a quien pregunta de una avería que no es
# suya: la pregunta se entendió perfectamente y fue el modelo el que se
# quedó en blanco. Repetirla más despacio no arregla nada.
MENSAJE_SIN_RESPUESTA = "No he podido preparar la respuesta."
MENSAJE_SIN_RESPUESTA_DEFINITIVO = (
    "Sigo sin poder responderte. Di la palabra clave cuando quieras."
)

# Topes duros de una conversación. Los contadores de arriba se reinician en
# cuanto un turno sale bien, así que por sí solos no garantizan que esto
# termine: una televisión encendida produce turno tras turno de habla que
# el STT transcribe perfectamente, ninguno vacío y ninguno una despedida.
# Sin estos topes, el asistente se quedaría contestándole a la tele hasta
# que alguien la apagase, gastando una llamada de transcripción y otra al
# modelo por vuelta.
MAX_TURNOS_POR_CONVERSACION = 15
MAX_SEGUNDOS_POR_CONVERSACION = 300.0
MENSAJE_CONVERSACION_LARGA = "Me callo un rato. Di la palabra clave cuando quieras."

# Cuánto se sigue descartando audio después de hablar.
#
# `reproducir()` vuelve cuando ha sonado el último byte, pero el bloque de
# ENTRADA que contiene ese último byte todavía va de camino: PortAudio lo
# entrega al callback hasta un bloque (80 ms) más la latencia del
# dispositivo después. Vaciar sin esperar deja ese bloque en la cola, el
# VAD lo toma por voz —le basta con superar el umbral de energía— y el
# asistente acaba transcribiéndose a sí mismo: en el mejor caso oye "no te
# he entendido" en cada turno, y en el peor se contesta solo en bucle.
#
# Es el precio de no tener cancelación de eco. Trescientos cincuenta
# milisegundos cubren el bloque en vuelo y la latencia típica de un
# dispositivo de Windows con margen, y no se notan porque caen justo
# después de hablar, cuando nadie ha empezado todavía a responder.
GUARDA_ECO = 0.35

# Cuánto silencio cierra la conversación entre turnos. Es mucho más que los
# 3 s con los que se descarta un falso positivo del wake word, porque aquí
# el silencio es una persona pensando qué preguntar, no un aparato que se
# despertó solo.
SEGUNDOS_PARA_CERRAR = 8.0

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

    def __init__(
        self,
        captura,
        detector,
        vad,
        stt,
        llm,
        tts,
        reproductor,
        cara,
        modo_conversacion: bool = True,
        segundos_para_cerrar: float = SEGUNDOS_PARA_CERRAR,
        frases_de_despedida: tuple[str, ...] = FRASES_DE_DESPEDIDA,
        guarda_eco: float = GUARDA_ECO,
        max_turnos: int = MAX_TURNOS_POR_CONVERSACION,
        max_segundos: float = MAX_SEGUNDOS_POR_CONVERSACION,
    ) -> None:
        self._captura = captura
        self._detector = detector
        self._vad = vad
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._reproductor = reproductor
        self._cara = cara
        self._modo_conversacion = modo_conversacion
        self._segundos_para_cerrar = segundos_para_cerrar
        self._frases_de_despedida = frases_de_despedida
        self._guarda_eco = guarda_eco
        self._max_turnos = max_turnos
        self._max_segundos = max_segundos
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
        """Espera la palabra clave y atiende una conversación entera.

        La palabra clave abre la conversación; a partir de ahí se encadenan
        turnos sin volver a decirla. Se cierra de tres formas: una frase de
        despedida, un silencio largo, o un fallo. Con
        `modo_conversacion=False` se comporta como antes: una pregunta por
        cada "hey jarvis".
        """
        if not self._esperar_palabra_clave():
            return

        self._detector.reiniciar()
        self._captura.vaciar()
        # Cada palabra clave abre una conversación nueva. Sin esto el
        # modelo arrastraría de qué se habló hace tres horas y contestaría
        # a un "¿y el de ayer?" que nadie ha preguntado hoy. El historial
        # que importa —el de esta conversación— lo mantiene el propio
        # cliente del LLM entre turnos.
        self._llm.reiniciar()

        try:
            self._conversar()
        finally:
            # Lo último que se grabó es la propia voz del asistente saliendo
            # por el altavoz. Si pasa al siguiente ciclo, el detector puede
            # oír la palabra clave en ella y despertarse solo: aquí no hay
            # cancelación de eco. En `finally` para que valga también cuando
            # se sale por un aviso de error.
            self._captura.vaciar()
            self._cara.set_estado(Estado.REPOSO)

    def _conversar(self) -> None:
        """Encadena turnos hasta que la conversación se cierre."""
        turnos = 0
        sin_entender = 0
        fallos = 0
        inicio = time.monotonic()

        while True:
            if self._se_ha_alargado(turnos, inicio):
                # Aquí sí se avisa en voz alta, al revés que en el cierre
                # por silencio: puede haber alguien delante en mitad de una
                # conversación legítima, y necesita saber que a partir de
                # ahora hay que volver a decir la palabra clave.
                self._avisar(MENSAJE_CONVERSACION_LARGA, Estado.HABLANDO)
                return

            self._cara.set_estado(Estado.ESCUCHANDO)
            audio = self._grabar_intervencion(primer_turno=turnos == 0)

            if not self._vad.hubo_voz:
                if turnos == 0:
                    # Falso positivo del wake word: nadie dijo nada. Volver
                    # a reposo en silencio; hablar aquí sería peor que no
                    # despertar.
                    logger.info("Falso positivo del wake word")
                else:
                    # Irse sin decir nada es como termina de verdad la
                    # mayoría de las conversaciones. No se despide en voz
                    # alta: si el usuario ya no está, hablarle a la
                    # habitación vacía no ayuda a nadie.
                    logger.info("Silencio: se cierra la conversación")
                return

            turnos += 1
            self._cara.set_estado(Estado.PENSANDO)
            try:
                texto = self._stt.transcribir(audio)
            except ErrorDeRed:
                fallos += 1
                if self._cerrar_por_fallo(fallos):
                    return
                continue

            if not texto.strip():
                sin_entender += 1
                se_acaba = (
                    sin_entender >= MAX_SIN_ENTENDER or not self._modo_conversacion
                )
                # "Sigo sin entenderte" solo tiene sentido cuando además se
                # deja de escuchar por ello: si se cierra porque el modo
                # conversación está apagado, el aviso correcto es el de
                # siempre.
                self._avisar(
                    MENSAJE_ME_RINDO
                    if se_acaba and self._modo_conversacion
                    else MENSAJE_NO_ENTENDIDO,
                    Estado.PENSANDO,
                )
                if se_acaba:
                    return
                continue
            sin_entender = 0

            logger.info("Turno %d: %r", turnos, texto)

            if es_despedida(texto, self._frases_de_despedida):
                logger.info("Despedida reconocida")
                self._avisar(MENSAJE_DESPEDIDA, Estado.HABLANDO)
                return

            try:
                hablo = self._responder(texto)
            except ErrorDeRed:
                fallos += 1
                if self._cerrar_por_fallo(fallos):
                    return
                continue

            if not hablo:
                # El modelo no escribió nada: agotó su presupuesto de
                # tokens razonando, o se quedó dando vueltas llamando a
                # herramientas. No es culpa de quien pregunta, y sobre todo
                # no se arregla repitiendo la pregunta más despacio: sin
                # contarlo como fallo, el usuario y el asistente podían
                # quedarse en ese bucle indefinidamente.
                fallos += 1
                if self._cerrar_por_fallo(
                    fallos,
                    MENSAJE_SIN_RESPUESTA,
                    MENSAJE_SIN_RESPUESTA_DEFINITIVO,
                ):
                    return
                continue
            fallos = 0

            if not self._modo_conversacion:
                return

    def _se_ha_alargado(self, turnos: int, inicio: float) -> bool:
        """¿La conversación ha pasado de los topes duros?"""
        transcurrido = time.monotonic() - inicio
        if turnos >= self._max_turnos or transcurrido >= self._max_segundos:
            logger.warning(
                "Tope de conversación alcanzado (%d turnos, %.0f s); se cierra",
                turnos,
                transcurrido,
            )
            return True
        return False

    def _cerrar_por_fallo(
        self,
        fallos: int,
        mensaje: str = MENSAJE_SIN_RED,
        mensaje_final: str = MENSAJE_SIN_RED_DEFINITIVO,
    ) -> bool:
        """Avisa del fallo y dice si hay que cerrar la conversación.

        Devuelve True cuando ya van demasiados seguidos. El aviso de cierre
        es distinto del de "lo intento otra vez": repetir dos veces la
        misma frase deja al usuario hablándole a un asistente que ya no le
        escucha, sin nada que se lo indique.
        """
        se_acaba = fallos >= MAX_FALLOS_SEGUIDOS or not self._modo_conversacion
        self._avisar(
            mensaje_final if se_acaba and self._modo_conversacion else mensaje,
            Estado.ERROR,
        )
        if se_acaba:
            logger.warning("Se cierra la conversación tras %d fallo(s)", fallos)
        else:
            logger.warning("Fallo %d; se sigue escuchando", fallos)
        return se_acaba

    def _esperar_palabra_clave(self) -> bool:
        bloque = self._captura.leer_bloque()
        if bloque is None:
            return False
        return self._detector.procesar(bloque)

    def _grabar_intervencion(self, primer_turno: bool = True) -> np.ndarray:
        # Tras la palabra clave se corta pronto ante el silencio, porque un
        # silencio ahí significa que el wake word se disparó solo. Entre
        # turnos se espera mucho más: ahí el silencio es alguien pensando.
        self._vad.reiniciar(
            None if primer_turno else self._segundos_para_cerrar
        )
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

    def _responder(self, texto: str) -> bool:
        """Sintetiza y reproduce frase a frase, según van llegando.

        No espera a tener la respuesta completa: en cuanto el LLM cierra la
        primera frase, esa frase ya se está oyendo mientras el modelo sigue
        generando el resto.

        Devuelve si llegó a decir algo. Quien llama necesita saberlo: un
        modelo que termina sin escribir una palabra es una avería, no una
        pregunta mal hecha, y el bucle de conversación tiene que contarlo
        como tal en vez de invitar a repetir la pregunta para siempre.
        """
        hablando = False
        for frase in self._llm.conversar(texto):
            if not hablando:
                self._cara.set_estado(Estado.HABLANDO)
                hablando = True
            self._decir(frase)
        if hablando:
            self._tras_hablar()
        return hablando

    def _decir(self, texto: str) -> None:
        self._reproductor.reproducir(
            self._tts.sintetizar(texto),
            al_rms=lambda rms: self._cara.set_estado(Estado.HABLANDO, rms=rms),
        )

    def _tras_hablar(self) -> None:
        """Descarta el audio que el micrófono grabó mientras el asistente
        hablaba, incluido el que todavía venía de camino.

        Este es el único sitio donde se limpia la realimentación acústica, y
        por eso cada camino que produce voz tiene que pasar por aquí. La
        espera no es opcional: `reproducir()` vuelve cuando ha sonado el
        último byte, pero el bloque de entrada que lo contiene tarda todavía
        un bloque más la latencia del dispositivo en llegar a la cola. Ver
        `GUARDA_ECO`.
        """
        if self._guarda_eco > 0:
            time.sleep(self._guarda_eco)
        self._captura.vaciar()

    def _avisar(self, texto: str, estado: Estado) -> None:
        """Dice un mensaje del sistema y vuelve a reposo.

        Funciona sin internet porque el TTS es local: por eso el asistente
        puede avisar de que no hay red en vez de quedarse mudo."""
        self._cara.set_estado(estado)
        self._decir(texto)
        self._tras_hablar()
        self._cara.set_estado(Estado.REPOSO)
