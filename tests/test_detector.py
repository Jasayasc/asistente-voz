# tests/test_detector.py
import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE
from asistente.wake import detector as detector_mod
from asistente.wake.detector import Detector


class _ModeloFalso:
    """Doble de `openwakeword.model.Model` que no carga ningún ONNX.

    Devuelve la puntuación fijada en `puntuacion_fija` sin mirar el bloque
    de audio, y registra si `reset()` se llamó. Así se puede probar la
    lógica del envoltorio sin descargar modelos ni tocar el micrófono.
    """

    def __init__(self, wakeword_models, inference_framework=None) -> None:
        self.clave = wakeword_models[0]
        self.models = {self.clave: object()}
        self.puntuacion_fija = 0.0
        self.reiniciado = False

    def predict(self, bloque):
        return {self.clave: self.puntuacion_fija}

    def reset(self) -> None:
        self.reiniciado = True


def _detector_falso(monkeypatch, umbral: float = 0.5, modelo: str = "hey_jarvis") -> Detector:
    monkeypatch.setattr(detector_mod, "Model", _ModeloFalso)
    return Detector(modelo=modelo, umbral=umbral)


def _bloque() -> np.ndarray:
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def test_por_debajo_del_umbral_no_detecta(monkeypatch):
    det = _detector_falso(monkeypatch, umbral=0.5)
    det._modelo.puntuacion_fija = 0.3
    assert det.procesar(_bloque()) is False


def test_en_el_umbral_exacto_detecta(monkeypatch):
    """Umbral inclusivo: puntuación == umbral cuenta como detección.

    0.5 es representable exactamente en binario, así que en la frontera
    no hay ambigüedad de redondeo. Si la comparación cambiara de `>=` a
    `>`, esta prueba fallaría — para eso existe.
    """
    det = _detector_falso(monkeypatch, umbral=0.5)
    det._modelo.puntuacion_fija = 0.5
    assert det.procesar(_bloque()) is True


def test_por_encima_del_umbral_detecta(monkeypatch):
    det = _detector_falso(monkeypatch, umbral=0.5)
    det._modelo.puntuacion_fija = 0.75
    assert det.procesar(_bloque()) is True


def test_puntuacion_devuelve_float(monkeypatch):
    """`puntuacion` debe convertir el resultado a `float` de Python.

    openWakeWord puede devolver tipos numpy (p.ej. `np.float32`); el
    envoltorio debe normalizarlos. 0.5 es exacta también en float32, así
    que la comparación de igualdad no depende de redondeo.
    """
    det = _detector_falso(monkeypatch)
    det._modelo.puntuacion_fija = np.float32(0.5)
    resultado = det.puntuacion(_bloque())
    assert isinstance(resultado, float)
    assert resultado == 0.5


def test_reiniciar_delega_en_el_modelo(monkeypatch):
    det = _detector_falso(monkeypatch)
    det.reiniciar()
    assert det._modelo.reiniciado is True


def test_usa_el_modelo_indicado(monkeypatch):
    """El nombre de modelo pasado al constructor llega a openWakeWord.

    Importa porque una palabra clave personalizada (tarea futura) solo
    cambiará este valor, sin tocar el resto del envoltorio.
    """
    det = _detector_falso(monkeypatch, modelo="palabra_personalizada")
    assert det._clave == "palabra_personalizada"
