import logging

import numpy as np
import pytest

import asistente.orquestador as orquestador_mod
from asistente.audio.captura import TAMANO_BLOQUE
from asistente.llm.base import ErrorDeRed
from asistente.orquestador import MENSAJE_NO_ENTENDIDO, MENSAJE_SIN_RED, Orquestador
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
