# src/asistente/llm/base.py
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

# Cierre de frase: signo de puntuación seguido de espacio o final de texto.
# El lookbehind negativo evita cortar en decimales como "18.4".
CORTE_FRASE = re.compile(r"(?<!\d)([.!?…])(?=\s|$)")


class ErrorDeRed(Exception):
    """Cualquier fallo de conectividad, sea del proveedor que sea.

    Las implementaciones traducen sus excepciones propias a esta, para que
    el orquestador no tenga que conocer ningún SDK."""


class ClienteLLM(ABC):
    """Interfaz del cerebro del asistente.

    Cambiar de proveedor es escribir otra subclase. Ningún otro módulo del
    sistema importa un SDK de LLM.
    """

    @abstractmethod
    def conversar(self, texto_usuario: str) -> Iterator[str]:
        """Emite la respuesta como frases completas, en orden.

        Debe lanzar ErrorDeRed si no hay conectividad."""

    @abstractmethod
    def reiniciar(self) -> None:
        """Olvida el historial de la conversación."""


def acumular_frases(tokens: Iterable[str]) -> Iterator[str]:
    """Agrupa tokens sueltos en frases pronunciables.

    El TTS necesita unidades con sentido: sintetizar token a token suena
    entrecortado, y esperar la respuesta entera arruina la latencia. La
    frase es el punto medio.
    """
    buffer = ""
    for token in tokens:
        buffer += token
        while True:
            coincidencia = CORTE_FRASE.search(buffer)
            if coincidencia is None:
                break
            corte = coincidencia.end()
            frase = buffer[:corte].strip()
            buffer = buffer[corte:]
            if frase:
                yield frase
    resto = buffer.strip()
    if resto:
        yield resto
