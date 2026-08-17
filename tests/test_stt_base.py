import numpy as np
import pytest

from asistente.stt.base import ClienteSTT, STTFalso


def test_el_doble_devuelve_lo_configurado():
    stt = STTFalso("hola qué tal")
    assert stt.transcribir(np.zeros(100, dtype=np.int16)) == "hola qué tal"


def test_el_doble_registra_las_llamadas():
    stt = STTFalso("x")
    stt.transcribir(np.zeros(10, dtype=np.int16))
    stt.transcribir(np.zeros(20, dtype=np.int16))
    assert len(stt.llamadas) == 2


def test_el_doble_puede_simular_un_fallo():
    from asistente.llm.base import ErrorDeRed

    stt = STTFalso("x", fallar=True)
    with pytest.raises(ErrorDeRed):
        stt.transcribir(np.zeros(10, dtype=np.int16))


def test_la_interfaz_es_abstracta():
    with pytest.raises(TypeError):
        ClienteSTT()
