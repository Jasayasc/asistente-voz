from abc import ABC, abstractmethod

import numpy as np

from asistente.llm.base import ErrorDeRed


class ClienteSTT(ABC):
    """Interfaz de transcripción de voz a texto."""

    @abstractmethod
    def transcribir(self, audio: np.ndarray) -> str:
        """Devuelve el texto transcrito, o cadena vacía si no se entendió
        nada. Debe lanzar ErrorDeRed si no hay conectividad."""


class STTFalso(ClienteSTT):
    """Doble para tests y para probar el orquestador sin gastar cuota."""

    def __init__(self, texto: str = "", fallar: bool = False) -> None:
        self.texto = texto
        self.fallar = fallar
        self.llamadas: list[int] = []

    def transcribir(self, audio: np.ndarray) -> str:
        self.llamadas.append(len(audio))
        if self.fallar:
            raise ErrorDeRed("fallo simulado")
        return self.texto
