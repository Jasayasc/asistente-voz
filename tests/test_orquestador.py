import logging

import numpy as np
import pytest

import asistente.orquestador as orquestador_mod
from asistente.audio.captura import TAMANO_BLOQUE
from asistente.llm.base import ErrorDeRed
from asistente.orquestador import (
    MAX_TURNOS_POR_CONVERSACION,
    MENSAJE_CONVERSACION_LARGA,
    MENSAJE_DESPEDIDA,
    MENSAJE_ME_RINDO,
    MENSAJE_NO_ENTENDIDO,
    MENSAJE_SIN_RED,
    MENSAJE_SIN_RED_DEFINITIVO,
    MENSAJE_SIN_RESPUESTA,
    MENSAJE_SIN_RESPUESTA_DEFINITIVO,
    Orquestador,
)
from asistente.stt.base import STTFalso
from comun.estados import Estado


class CapturaFalsa:
    def __init__(self, bloques):
        self._bloques = list(bloques)
        self.vaciados = 0

    def leer_bloque(self, timeout=1.0):
        if not self._bloques:
            return None
        return self._bloques.pop(0)

    def vaciar(self):
        self.vaciados += 1


class DetectorFalso:
    def __init__(self, despertar_en=0):
        self._n = 0
        self._despertar_en = despertar_en
        self.reinicios = 0

    def procesar(self, bloque):
        self._n += 1
        return self._n > self._despertar_en

    def reiniciar(self):
        self.reinicios += 1


class VadFalso:
    """Doble del detector de silencio.

    `hubo_voz` ya no es fijo: el orquestador llama a `reiniciar` una vez
    por turno, y en modo conversación un turno sin voz es justamente lo que
    cierra la conversación. Por defecto se oye voz en el primer turno y
    silencio después, que es como termina una conversación de verdad: la
    gente se va, no dice "adiós". Sin ese valor por defecto, cualquier test
    que solo quiera comprobar un turno se quedaría dando vueltas.
    """

    def __init__(self, bloques_hasta_fin=2, hubo_voz=True, turnos_con_voz=None):
        self._bloques_hasta_fin = bloques_hasta_fin
        self._restantes = bloques_hasta_fin
        if turnos_con_voz is None:
            turnos_con_voz = 1 if hubo_voz else 0
        self._turnos_con_voz = turnos_con_voz
        self._turnos = 0
        self.hubo_voz = turnos_con_voz > 0
        # Cada entrada es el `segundos_sin_voz` con el que se reinició ese
        # turno: None tras la palabra clave, y la espera larga entre turnos.
        self.esperas_pedidas = []

    def procesar(self, bloque):
        self._restantes -= 1
        return self._restantes <= 0

    def reiniciar(self, segundos_sin_voz=None):
        self.esperas_pedidas.append(segundos_sin_voz)
        self._restantes = self._bloques_hasta_fin
        self.hubo_voz = self._turnos < self._turnos_con_voz
        self._turnos += 1


class LlmFalso:
    def __init__(self, frases=("Hola.",), fallar=False, respuestas=None):
        self.frases = list(frases)
        self.fallar = fallar
        # `respuestas` permite dar una lista distinta por turno, para
        # comprobar conversaciones de varios turnos.
        self._respuestas = None if respuestas is None else list(respuestas)
        self.preguntas = []
        self.reinicios = 0

    def conversar(self, texto):
        self.preguntas.append(texto)
        if self.fallar:
            raise ErrorDeRed("sin red")
        if self._respuestas is not None:
            indice = min(len(self.preguntas) - 1, len(self._respuestas) - 1)
            yield from self._respuestas[indice]
            return
        yield from self.frases

    def reiniciar(self):
        self.reinicios += 1


class TtsFalso:
    def __init__(self):
        self.textos = []
        self.tasa_muestreo = 16000

    def sintetizar(self, texto):
        self.textos.append(texto)
        yield np.zeros(320, dtype=np.int16).tobytes()


class ReproductorFalso:
    def __init__(self):
        self.reproducciones = 0

    def reproducir(self, chunks, al_rms):
        self.reproducciones += 1
        for _ in chunks:
            al_rms(0.5)
        al_rms(0.0)

    def detener(self):
        pass


class CaraFalsa:
    def __init__(self):
        self.estados = []

    def set_estado(self, estado, rms=0.0):
        if not self.estados or self.estados[-1] != estado:
            self.estados.append(estado)

    def cerrar(self):
        pass


def bloque():
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def construir(**cambios):
    piezas = {
        "captura": CapturaFalsa([bloque() for _ in range(20)]),
        "detector": DetectorFalso(),
        "vad": VadFalso(),
        "stt": STTFalso("qué tiempo hace"),
        "llm": LlmFalso(["Hace sol.", "Veinte grados."]),
        "tts": TtsFalso(),
        "reproductor": ReproductorFalso(),
        "cara": CaraFalsa(),
        # Sin espera de guarda: en producción son 350 ms reales después de
        # cada frase, y aquí solo harían lenta la suite. Que la guarda
        # exista y caiga en el sitio correcto lo comprueban
        # `test_espera_la_guarda_de_eco_antes_de_vaciar` y
        # `test_nunca_se_escucha_sin_haber_vaciado_despues_de_hablar`.
        "guarda_eco": 0.0,
    }
    piezas.update(cambios)
    orquestador = Orquestador(**piezas)
    piezas.pop("guarda_eco", None)
    return orquestador, piezas


def test_un_ciclo_completo_recorre_todos_los_estados():
    """Tras responder vuelve a ESCUCHANDO, no a REPOSO: eso es el modo
    conversación visto desde la cara. Solo cae a REPOSO cuando el turno
    siguiente no oye a nadie."""
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["cara"].estados == [
        Estado.ESCUCHANDO,
        Estado.PENSANDO,
        Estado.HABLANDO,
        Estado.ESCUCHANDO,
        Estado.REPOSO,
    ]


def test_sin_modo_conversacion_vuelve_a_reposo_tras_una_pregunta():
    """El comportamiento de antes sigue disponible con un interruptor."""
    orq, piezas = construir(modo_conversacion=False)
    orq.un_ciclo()
    assert piezas["cara"].estados == [
        Estado.ESCUCHANDO,
        Estado.PENSANDO,
        Estado.HABLANDO,
        Estado.REPOSO,
    ]
    assert len(piezas["llm"].preguntas) == 1


def test_la_transcripcion_llega_al_llm():
    orq, piezas = construir(stt=STTFalso("qué tiempo hace"))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tiempo hace"]


def test_cada_frase_se_sintetiza_por_separado():
    """Sintetizar frase a frase es lo que permite empezar a hablar antes de
    tener la respuesta completa."""
    orq, piezas = construir(llm=LlmFalso(["Uno.", "Dos.", "Tres."]))
    orq.un_ciclo()
    assert piezas["tts"].textos == ["Uno.", "Dos.", "Tres."]


def test_un_falso_positivo_no_produce_respuesta():
    orq, piezas = construir(vad=VadFalso(hubo_voz=False))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == []
    assert Estado.HABLANDO not in piezas["cara"].estados


def test_un_falso_positivo_vuelve_a_reposo():
    orq, piezas = construir(vad=VadFalso(hubo_voz=False))
    orq.un_ciclo()
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_transcripcion_vacia_avisa_y_no_llama_al_llm():
    orq, piezas = construir(stt=STTFalso(""))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == [MENSAJE_NO_ENTENDIDO]


def test_sin_red_en_el_stt_avisa_por_voz():
    orq, piezas = construir(stt=STTFalso("x", fallar=True))
    orq.un_ciclo()
    assert piezas["tts"].textos == [MENSAJE_SIN_RED]
    assert Estado.ERROR in piezas["cara"].estados


def test_sin_red_en_el_llm_avisa_por_voz():
    orq, piezas = construir(llm=LlmFalso(fallar=True))
    orq.un_ciclo()
    assert piezas["tts"].textos == [MENSAJE_SIN_RED]
    assert Estado.ERROR in piezas["cara"].estados


def test_siempre_vuelve_a_reposo_tras_un_error():
    orq, piezas = construir(llm=LlmFalso(fallar=True))
    orq.un_ciclo()
    assert piezas["cara"].estados[-1] is Estado.REPOSO


# --- Modo conversación ----------------------------------------------------


class STTSecuencia:
    """STT que devuelve un texto distinto en cada llamada."""

    def __init__(self, *textos):
        self._textos = list(textos)
        self.llamadas = 0

    def transcribir(self, audio):
        indice = min(self.llamadas, len(self._textos) - 1)
        self.llamadas += 1
        return self._textos[indice]


def test_encadena_varios_turnos_sin_repetir_la_palabra_clave():
    """El objetivo del modo: una palabra clave, varias preguntas."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=3),
        stt=STTSecuencia("qué tiempo hace", "y mañana", "y el fin de semana"),
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == [
        "qué tiempo hace",
        "y mañana",
        "y el fin de semana",
    ]
    assert piezas["detector"].reinicios == 1  # una sola palabra clave


def test_el_historial_del_llm_se_conserva_entre_turnos():
    """La memoria dentro de una conversación la mantiene el cliente del
    LLM: el orquestador no debe reiniciarlo en cada turno, solo al abrir
    una conversación nueva."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=3),
        stt=STTSecuencia("una", "dos", "tres"),
    )
    orq.un_ciclo()
    assert piezas["llm"].reinicios == 1


def test_cada_palabra_clave_empieza_una_conversacion_limpia():
    """Lo contrario del test anterior: entre conversaciones no se arrastra
    contexto. Preguntar por Madrid esta mañana no debe colarse en la
    conversación de esta noche."""
    orq, piezas = construir()
    orq.un_ciclo()
    orq.un_ciclo()
    assert piezas["llm"].reinicios == 2


@pytest.mark.parametrize(
    "despedida",
    ["desactívate", "Inactívate.", "vale, gracias, adiós", "hasta luego"],
)
def test_una_despedida_cierra_la_conversacion(despedida):
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=3),
        stt=STTSecuencia("qué tiempo hace", despedida, "esto ya no se pregunta"),
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tiempo hace"]
    assert piezas["tts"].textos[-1] == MENSAJE_DESPEDIDA
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_una_pregunta_que_menciona_una_despedida_no_la_cierra():
    """"¿Cómo se dice adiós en francés?" es una pregunta, no una
    despedida. Confundirlas apagaría el asistente justo cuando le
    preguntan algo."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=2),
        stt=STTSecuencia("cómo se dice adiós en francés", "y en alemán"),
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == [
        "cómo se dice adiós en francés",
        "y en alemán",
    ]
    assert MENSAJE_DESPEDIDA not in piezas["tts"].textos


def test_el_silencio_cierra_la_conversacion_sin_hablar():
    """Irse sin decir nada es como termina la mayoría de conversaciones.
    Despedirse en voz alta de una habitación vacía no ayuda a nadie."""
    orq, piezas = construir(vad=VadFalso(turnos_con_voz=1))
    orq.un_ciclo()
    assert MENSAJE_DESPEDIDA not in piezas["tts"].textos
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_entre_turnos_se_espera_mas_que_tras_la_palabra_clave():
    """Tres segundos de silencio tras el wake word son un falso positivo;
    los mismos tres segundos en mitad de una conversación son alguien
    pensando qué preguntar."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=2), segundos_para_cerrar=8.0
    )
    orq.un_ciclo()
    esperas = piezas["vad"].esperas_pedidas
    assert esperas[0] is None  # primer turno: el tope corto de siempre
    assert all(espera == 8.0 for espera in esperas[1:])


def test_la_cola_se_vacia_tras_cada_respuesta():
    """Lo grabado mientras hablaba es su propia voz. Si llega al turno
    siguiente, el asistente se transcribe y se contesta a sí mismo."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=2), stt=STTSecuencia("una", "dos")
    )
    orq.un_ciclo()
    # Uno al despertar, uno tras cada una de las dos respuestas, y el del
    # `finally` al cerrar.
    assert piezas["captura"].vaciados == 4


def test_dos_transcripciones_vacias_seguidas_cierran_la_conversacion():
    """Una tele de fondo mantendría el bucle vivo indefinidamente."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=5), stt=STTSecuencia("", "", "", "")
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == [MENSAJE_NO_ENTENDIDO, MENSAJE_ME_RINDO]
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_una_transcripcion_vacia_suelta_no_cierra_la_conversacion():
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=3), stt=STTSecuencia("", "qué tal", "")
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tal"]
    assert MENSAJE_ME_RINDO not in piezas["tts"].textos


def test_un_fallo_suelto_no_cierra_la_conversacion():
    """Un 503 de "modelo saturado" es habitual y pasajero. Cerrar por él
    obliga a repetir la palabra clave y a recontar el contexto, que es lo
    que este modo viene a quitar."""

    class LlmQueFallaUnaVez(LlmFalso):
        def conversar(self, texto):
            self.preguntas.append(texto)
            if len(self.preguntas) == 1:
                raise ErrorDeRed("503 saturado")
            yield from self.frases

    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=3),
        llm=LlmQueFallaUnaVez(),
        stt=STTSecuencia("una", "dos", "tres"),
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["una", "dos", "tres"]
    assert piezas["tts"].textos[0] == MENSAJE_SIN_RED


def test_dos_fallos_seguidos_cierran_la_conversacion():
    """Dos seguidos ya no es un bache: insistir con el usuario delante solo
    gasta cuota y repite el mismo aviso.

    El segundo aviso NO puede ser igual que el primero: si lo fuera, el
    usuario oiría dos veces lo mismo y seguiría hablándole a un asistente
    que ya ha dejado de escuchar, sin nada que se lo indique."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=5), llm=LlmFalso(fallar=True)
    )
    orq.un_ciclo()
    assert len(piezas["llm"].preguntas) == 2
    assert piezas["tts"].textos == [MENSAJE_SIN_RED, MENSAJE_SIN_RED_DEFINITIVO]
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_sin_modo_conversacion_una_transcripcion_vacia_cierra_igual_que_antes():
    orq, piezas = construir(stt=STTFalso(""), modo_conversacion=False)
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == [MENSAJE_NO_ENTENDIDO]
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_sin_modo_conversacion_un_fallo_cierra_igual_que_antes():
    orq, piezas = construir(llm=LlmFalso(fallar=True), modo_conversacion=False)
    orq.un_ciclo()
    assert len(piezas["llm"].preguntas) == 1
    assert piezas["tts"].textos == [MENSAJE_SIN_RED]


def test_un_turno_bueno_perdona_el_fallo_anterior():
    """El contador es de fallos SEGUIDOS: si entre medias contesta bien, la
    conversación no debe morir por un bache de hace cinco minutos."""

    class LlmQueFallaAlterno(LlmFalso):
        def conversar(self, texto):
            self.preguntas.append(texto)
            if len(self.preguntas) % 2 == 1:
                raise ErrorDeRed("503 saturado")
            yield from self.frases

    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=4),
        llm=LlmQueFallaAlterno(),
        stt=STTSecuencia("una", "dos", "tres", "cuatro"),
    )
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["una", "dos", "tres", "cuatro"]


def test_un_falso_positivo_no_abre_conversacion():
    orq, piezas = construir(vad=VadFalso(hubo_voz=False))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == []
    assert piezas["cara"].estados[-1] is Estado.REPOSO


# --- Que no se oiga a sí mismo -------------------------------------------


class PiezasConEventos:
    """Dobles que anotan en una lista común el orden de lo que les pasa.

    Sin esto, un test solo puede contar cuántas veces se vació la cola, y un
    refactor que mueva el vaciado a ANTES de hablar deja la suite en verde
    mientras el asistente se contesta a sí mismo en producción. Lo que hay
    que fijar es el orden, no el número.
    """

    def __init__(self, bloques):
        self.eventos = []
        self._bloques = list(bloques)

    class _Captura:
        def __init__(self, padre):
            self._padre = padre
            self.vaciados = 0

        def leer_bloque(self, timeout=1.0):
            self._padre.eventos.append("escuchar")
            if not self._padre._bloques:
                return None
            return self._padre._bloques.pop(0)

        def vaciar(self):
            self.vaciados += 1
            self._padre.eventos.append("vaciar")

    class _Reproductor:
        def __init__(self, padre):
            self._padre = padre

        def reproducir(self, chunks, al_rms):
            self._padre.eventos.append("hablar")
            for _ in chunks:
                al_rms(0.5)
            al_rms(0.0)

        def detener(self):
            pass


def test_nunca_se_escucha_sin_haber_vaciado_despues_de_hablar():
    """El invariante que impide la realimentación acústica: entre cada vez
    que suena el altavoz y la siguiente vez que se lee del micrófono tiene
    que haber un vaciado de la cola. Se comprueba sobre TODOS los caminos
    que producen voz, no solo el de una respuesta normal."""
    piezas_eventos = PiezasConEventos([bloque() for _ in range(40)])
    orq, piezas = construir(
        captura=piezas_eventos._Captura(piezas_eventos),
        reproductor=piezas_eventos._Reproductor(piezas_eventos),
        vad=VadFalso(turnos_con_voz=4),
        # Un turno normal, uno sin entender, una despedida.
        stt=STTSecuencia("qué tiempo hace", "", "adiós"),
    )
    orq.un_ciclo()

    eventos = piezas_eventos.eventos
    assert "hablar" in eventos and "escuchar" in eventos
    pendiente = False
    for evento in eventos:
        if evento == "hablar":
            pendiente = True
        elif evento == "vaciar":
            pendiente = False
        elif evento == "escuchar":
            assert not pendiente, (
                "se escuchó el micrófono después de hablar sin vaciar la "
                f"cola; orden observado: {eventos}"
            )


def test_espera_la_guarda_de_eco_antes_de_vaciar(monkeypatch):
    """`reproducir()` vuelve cuando ha sonado el último byte, pero el bloque
    de ENTRADA que lo contiene todavía va de camino. Vaciar sin esperar lo
    deja en la cola y el asistente se transcribe a sí mismo."""
    orden = []
    monkeypatch.setattr(
        orquestador_mod.time, "sleep", lambda s: orden.append(("dormir", s))
    )

    class CapturaQueAnota(CapturaFalsa):
        def vaciar(self):
            orden.append(("vaciar", None))
            super().vaciar()

    orq, _ = construir(
        captura=CapturaQueAnota([bloque() for _ in range(20)]),
        guarda_eco=0.35,
    )
    orq.un_ciclo()

    # Tras hablar: primero se espera, después se vacía. Nunca al revés.
    assert ("dormir", 0.35) in orden
    primera_espera = orden.index(("dormir", 0.35))
    assert orden[primera_espera + 1] == ("vaciar", None)


# --- Topes duros de la conversación ---------------------------------------


def test_un_tope_de_turnos_cierra_la_conversacion():
    """Los contadores de "sin entender" y "fallos" se reinician con cada
    turno que sale bien, así que por sí solos no garantizan que esto
    termine. Una televisión encendida produce habla real que el STT
    transcribe: ni vacía, ni una despedida, ni un fallo. Sin tope duro, el
    asistente le contesta a la tele hasta que alguien la apague."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=500),
        stt=STTSecuencia("diálogo de la televisión"),
    )
    orq.un_ciclo()
    assert len(piezas["llm"].preguntas) == MAX_TURNOS_POR_CONVERSACION
    assert piezas["tts"].textos[-1] == MENSAJE_CONVERSACION_LARGA
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_un_tope_de_tiempo_cierra_la_conversacion(monkeypatch):
    """El otro tope: aunque los turnos sean pocos, una conversación no
    puede tener el micrófono abierto indefinidamente."""
    reloj = [0.0]
    monkeypatch.setattr(orquestador_mod.time, "monotonic", lambda: reloj[0])

    llm = LlmFalso()
    conversar_original = llm.conversar

    def conversar_y_avanzar(texto):
        reloj[0] += 120.0  # cada turno consume dos minutos
        yield from conversar_original(texto)

    llm.conversar = conversar_y_avanzar

    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=500),
        stt=STTSecuencia("sigue hablando"),
        llm=llm,
        max_turnos=1000,  # que corte el reloj, no el contador de turnos
        max_segundos=300.0,
    )
    orq.un_ciclo()
    assert len(piezas["llm"].preguntas) == 3  # 3 x 120 s = 360 s > 300 s
    assert piezas["tts"].textos[-1] == MENSAJE_CONVERSACION_LARGA


def test_el_aviso_del_tope_se_dice_en_voz_alta():
    """Al revés que el cierre por silencio: aquí puede haber alguien
    delante en mitad de una conversación legítima, y necesita saber que a
    partir de ahora hay que repetir la palabra clave."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=500),
        stt=STTSecuencia("una cosa más"),
        max_turnos=2,
    )
    orq.un_ciclo()
    assert MENSAJE_CONVERSACION_LARGA in piezas["tts"].textos


def test_el_detector_se_reinicia_tras_despertar():
    """Sin esto, la misma palabra dispararía varias veces seguidas."""
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["detector"].reinicios >= 1


def test_el_llm_sin_frases_avisa_y_no_falla():
    """Si el LLM no produce ninguna frase (pero tampoco lanza), el aviso no
    debe culpar a quien pregunta.

    Antes decía "no te he entendido", que invita a repetir la pregunta más
    despacio; pero la pregunta se entendió perfectamente y quien se quedó
    en blanco fue el modelo. Repetirla no arregla nada, así que además
    cuenta como fallo del turno y no como una pregunta más."""
    orq, piezas = construir(llm=LlmFalso(frases=()))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tiempo hace"]
    assert piezas["tts"].textos == [MENSAJE_SIN_RESPUESTA]
    assert MENSAJE_NO_ENTENDIDO not in piezas["tts"].textos


def test_un_llm_mudo_no_deja_al_usuario_repitiendo_para_siempre():
    """Sin contarlo como fallo, el usuario repetía la pregunta y el modelo
    seguía en blanco, indefinidamente."""
    orq, piezas = construir(
        vad=VadFalso(turnos_con_voz=6), llm=LlmFalso(frases=())
    )
    orq.un_ciclo()
    assert len(piezas["llm"].preguntas) == 2
    assert piezas["tts"].textos == [
        MENSAJE_SIN_RESPUESTA,
        MENSAJE_SIN_RESPUESTA_DEFINITIVO,
    ]
    assert piezas["cara"].estados[-1] is Estado.REPOSO
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_una_excepcion_inesperada_no_mata_el_bucle(monkeypatch, caplog):
    """Tasks 15 y 16 traducen sus errores a ErrorDeRed, pero envuelven SDKs
    de terceros que este proyecto no controla. Un bug ahí no debe tumbar el
    proceso completo: se registra con logging (nunca se imprime) y el bucle
    sigue en el siguiente ciclo."""
    monkeypatch.setattr(orquestador_mod.time, "sleep", lambda segundos: None)
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas == 1:
                # Un estado intermedio antes de fallar: si no, la aserción
                # de más abajo sería trivial, porque ejecutar() ya pone
                # REPOSO como primerísima acción y CaraFalsa colapsa
                # estados consecutivos iguales.
                self._cara.set_estado(Estado.ESCUCHANDO)
                raise ValueError("bug simulado")
            # Sale del bucle infinito de ejecutar() sin que se confunda con
            # la excepción inesperada que se está probando.
            raise SystemExit

    orq = OrquestadorFragil(**piezas)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit):
            orq.ejecutar()

    assert orq.llamadas == 2
    assert "bug simulado" in caplog.text
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_un_fallo_inesperado_vacia_la_cola_de_audio(monkeypatch):
    """Si un ciclo muere a mitad de hablar, la cola de captura conserva
    bloques con la propia voz sintetizada del asistente. Sin vaciarla, el
    siguiente ciclo se la entrega bloque a bloque al detector de palabra
    clave: el asistente podría despertarse con su propia voz."""
    monkeypatch.setattr(orquestador_mod.time, "sleep", lambda segundos: None)
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas == 1:
                raise ValueError("bug simulado")
            raise SystemExit

    orq = OrquestadorFragil(**piezas)
    with pytest.raises(SystemExit):
        orq.ejecutar()

    assert piezas["captura"].vaciados >= 1


def test_fallos_consecutivos_esperan_con_backoff_creciente(monkeypatch):
    """Sin este freno, un colaborador que falle en cada bloque entregado
    (Detector.procesar contra un ONNX roto, por ejemplo) reintentaría a la
    velocidad de llegada de audio, ~30 Hz, en vez de a la de un fallo real."""
    esperas = []
    monkeypatch.setattr(orquestador_mod.time, "sleep", esperas.append)
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas <= 3:
                raise ValueError(f"bug distinto {self.llamadas}")
            raise SystemExit

    orq = OrquestadorFragil(**piezas)
    with pytest.raises(SystemExit):
        orq.ejecutar()

    base = orquestador_mod.ESPERA_BASE_TRAS_FALLO
    assert esperas == [base, base * 2, base * 4]


def test_el_backoff_se_reinicia_tras_un_ciclo_correcto(monkeypatch):
    """El contador de fallos consecutivos no debe arrastrarse entre
    incidentes separados por un ciclo que funcionó bien."""
    esperas = []
    monkeypatch.setattr(orquestador_mod.time, "sleep", esperas.append)
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas == 1:
                raise ValueError("bug")
            if self.llamadas == 2:
                return  # ciclo correcto: no lanza nada
            if self.llamadas == 3:
                raise ValueError("bug de nuevo")
            raise SystemExit

    orq = OrquestadorFragil(**piezas)
    with pytest.raises(SystemExit):
        orq.ejecutar()

    base = orquestador_mod.ESPERA_BASE_TRAS_FALLO
    assert esperas == [base, base]


def test_fallo_repetido_no_repite_traza_completa(monkeypatch, caplog):
    """Un mismo error disparado en cada ciclo no debe escribir su traza
    completa una y otra vez: en una Pi desatendida que registra a fichero,
    eso llena la tarjeta SD. Se registra una vez y luego se cuenta."""
    monkeypatch.setattr(orquestador_mod.time, "sleep", lambda segundos: None)
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas <= 3:
                raise ValueError("siempre el mismo bug")
            raise SystemExit

    orq = OrquestadorFragil(**piezas)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit):
            orq.ejecutar()

    con_traza = [r for r in caplog.records if r.exc_info]
    assert len(con_traza) == 1
    assert caplog.text.count("veces suprimido") == 2
