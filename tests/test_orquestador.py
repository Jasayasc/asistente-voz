import logging

import numpy as np
import pytest

from asistente.audio.captura import TAMANO_BLOQUE
from asistente.llm.base import ErrorDeRed
from asistente.orquestador import MENSAJE_NO_ENTENDIDO, MENSAJE_SIN_RED, Orquestador
from asistente.stt.base import STTFalso
from comun.estados import Estado


class CapturaFalsa:
    def __init__(self, bloques):
        self._bloques = list(bloques)

    def leer_bloque(self, timeout=1.0):
        if not self._bloques:
            return None
        return self._bloques.pop(0)

    def vaciar(self):
        pass


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
    def __init__(self, bloques_hasta_fin=2, hubo_voz=True):
        self._restantes = bloques_hasta_fin
        self.hubo_voz = hubo_voz

    def procesar(self, bloque):
        self._restantes -= 1
        return self._restantes <= 0

    def reiniciar(self):
        pass


class LlmFalso:
    def __init__(self, frases=("Hola.",), fallar=False):
        self.frases = list(frases)
        self.fallar = fallar
        self.preguntas = []

    def conversar(self, texto):
        self.preguntas.append(texto)
        if self.fallar:
            raise ErrorDeRed("sin red")
        yield from self.frases

    def reiniciar(self):
        pass


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
    }
    piezas.update(cambios)
    return Orquestador(**piezas), piezas


def test_un_ciclo_completo_recorre_todos_los_estados():
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["cara"].estados == [
        Estado.ESCUCHANDO,
        Estado.PENSANDO,
        Estado.HABLANDO,
        Estado.REPOSO,
    ]


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


def test_el_detector_se_reinicia_tras_despertar():
    """Sin esto, la misma palabra dispararía varias veces seguidas."""
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["detector"].reinicios >= 1


def test_el_llm_sin_frases_avisa_y_no_falla():
    """Si el LLM no produce ninguna frase (pero tampoco lanza), el usuario
    debe recibir el mismo aviso que si no se le hubiera entendido nada."""
    orq, piezas = construir(llm=LlmFalso(frases=()))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tiempo hace"]
    assert piezas["tts"].textos == [MENSAJE_NO_ENTENDIDO]
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_una_excepcion_inesperada_no_mata_el_bucle(caplog):
    """Tasks 15 y 16 traducen sus errores a ErrorDeRed, pero envuelven SDKs
    de terceros que este proyecto no controla. Un bug ahí no debe tumbar el
    proceso completo: se registra con logging (nunca se imprime) y el bucle
    sigue en el siguiente ciclo."""
    _, piezas = construir()

    class OrquestadorFragil(Orquestador):
        def __init__(self, **piezas):
            super().__init__(**piezas)
            self.llamadas = 0

        def un_ciclo(self):
            self.llamadas += 1
            if self.llamadas == 1:
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
