import numpy as np
import pytest

from asistente.audio import reproductor as reproductor_mod
from asistente.audio.captura import TASA_MUESTREO
from asistente.audio.reproductor import Reproductor, calcular_rms


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


def test_amplitud_media_escala_da_valor_exacto():
    """Verifica el valor exacto de RMS para detectar errores de escala.

    Con amplitud de 16384 (media escala de int16 ±32768), el RMS normalizado
    debe ser exactamente 0.5. Un error de factor 2 en MAXIMO_INT16 (ej. 16384.0)
    lo haría 1.0 tras clamping. Este test lo detecta.
    """
    bloque = np.full(1000, 16384, dtype=np.int16)
    assert calcular_rms(bloque) == pytest.approx(0.5, abs=0.001)


class _StreamFalso:
    """Doble de `sd.OutputStream` que no toca hardware. Registra los
    parámetros de construcción para poder comprobar qué tasa llegó."""

    instancias: list["_StreamFalso"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        _StreamFalso.instancias.append(self)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass

    def write(self, trozo) -> None:
        pass


def test_tasa_predeterminada_es_la_de_captura(monkeypatch):
    """Sin pasar `tasa`, el reproductor sigue usando `TASA_MUESTREO` (16000)
    — así ningún llamador existente (Task 12) cambia de comportamiento."""
    _StreamFalso.instancias.clear()
    monkeypatch.setattr(reproductor_mod.sd, "OutputStream", _StreamFalso)
    rep = Reproductor()
    rep.reproducir([], al_rms=lambda r: None)
    assert _StreamFalso.instancias[0].kwargs["samplerate"] == TASA_MUESTREO


def test_la_tasa_pasada_al_constructor_llega_al_stream(monkeypatch):
    """La tasa del modelo de voz (p.ej. 22050 de Piper) debe llegar tal
    cual al stream de salida, o la voz suena lenta y grave."""
    _StreamFalso.instancias.clear()
    monkeypatch.setattr(reproductor_mod.sd, "OutputStream", _StreamFalso)
    rep = Reproductor(tasa=22050)
    rep.reproducir([], al_rms=lambda r: None)
    assert _StreamFalso.instancias[0].kwargs["samplerate"] == 22050
