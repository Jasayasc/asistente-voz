# src/asistente/wake/detector.py
import numpy as np
from openwakeword.model import Model


class Detector:
    """Detecta la palabra de activación en el flujo de audio.

    openWakeWord mantiene estado interno entre bloques (usa una ventana
    deslizante), así que hay una única instancia viva y se le pasan los
    bloques en orden. Tras una detección hay que llamar a `reiniciar` para
    que no dispare varias veces con la misma palabra.
    """

    def __init__(self, modelo: str = "hey_jarvis", umbral: float = 0.5) -> None:
        self._umbral = umbral
        self._modelo = Model(wakeword_models=[modelo], inference_framework="onnx")
        self._clave = list(self._modelo.models.keys())[0]

    def procesar(self, bloque: np.ndarray) -> bool:
        puntuaciones = self._modelo.predict(bloque)
        return puntuaciones[self._clave] >= self._umbral

    def puntuacion(self, bloque: np.ndarray) -> float:
        """Para calibrar el umbral durante las pruebas."""
        return float(self._modelo.predict(bloque)[self._clave])

    def reiniciar(self) -> None:
        self._modelo.reset()
