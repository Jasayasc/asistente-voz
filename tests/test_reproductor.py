import numpy as np

from asistente.audio.reproductor import calcular_rms


def test_silencio_da_cero():
    assert calcular_rms(np.zeros(1000, dtype=np.int16)) == 0.0


def test_amplitud_maxima_da_uno():
    bloque = np.full(1000, 32767, dtype=np.int16)
    assert calcular_rms(bloque) > 0.99


def test_mas_amplitud_da_mas_rms():
    suave = np.full(1000, 3000, dtype=np.int16)
    fuerte = np.full(1000, 20000, dtype=np.int16)
    assert calcular_rms(fuerte) > calcular_rms(suave)


def test_resultado_siempre_en_rango():
    rng = np.random.default_rng(0)
    for amplitud in (100, 5000, 32767):
        bloque = rng.integers(-amplitud, amplitud, 1000, dtype=np.int16)
        assert 0.0 <= calcular_rms(bloque) <= 1.0


def test_bloque_vacio_da_cero():
    assert calcular_rms(np.array([], dtype=np.int16)) == 0.0
