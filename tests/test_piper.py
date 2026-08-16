# tests/test_piper.py
from asistente.tts import piper as piper_mod
from asistente.tts.piper import Piper


class _FragmentoFalso:
    """Doble de `piper.voice.AudioChunk`: solo expone los bytes PCM que
    consume `Piper.sintetizar`."""

    def __init__(self, datos: bytes) -> None:
        self.audio_int16_bytes = datos


class _VozFalsa:
    """Doble de `PiperVoice` que no carga ningún ONNX.

    Registra los textos recibidos por `synthesize` y devuelve fragmentos
    fijados de antemano, para poder probar `Piper.sintetizar` sin tocar
    el modelo real (63 MB, lento de cargar).
    """

    class _Config:
        sample_rate = 22050

    def __init__(self, ruta_modelo: str) -> None:
        self.ruta_modelo = ruta_modelo
        self.textos_recibidos: list[str] = []
        self.fragmentos = [_FragmentoFalso(b"abc"), _FragmentoFalso(b"def")]
        self.config = self._Config()

    def synthesize(self, texto: str):
        self.textos_recibidos.append(texto)
        return iter(self.fragmentos)

    @classmethod
    def load(cls, ruta_modelo: str) -> "_VozFalsa":
        return cls(ruta_modelo)


def _piper_falso(monkeypatch) -> Piper:
    monkeypatch.setattr(piper_mod, "PiperVoice", _VozFalsa)
    return Piper("modelos/falso.onnx")


def test_texto_vacio_no_produce_audio_ni_toca_el_modelo(monkeypatch):
    p = _piper_falso(monkeypatch)
    resultado = list(p.sintetizar(""))
    assert resultado == []
    assert p._voz.textos_recibidos == []


def test_texto_solo_espacios_no_produce_audio_ni_toca_el_modelo(monkeypatch):
    p = _piper_falso(monkeypatch)
    resultado = list(p.sintetizar("   \n\t  "))
    assert resultado == []
    assert p._voz.textos_recibidos == []


def test_texto_no_vacio_delega_en_la_voz_y_devuelve_los_fragmentos_en_orden(
    monkeypatch,
):
    p = _piper_falso(monkeypatch)
    resultado = list(p.sintetizar("Hola, ¿cómo estás?"))
    assert resultado == [b"abc", b"def"]
    assert p._voz.textos_recibidos == ["Hola, ¿cómo estás?"]


def test_tasa_de_muestreo_se_toma_de_la_configuracion_del_modelo(monkeypatch):
    p = _piper_falso(monkeypatch)
    assert p.tasa_muestreo == 22050
