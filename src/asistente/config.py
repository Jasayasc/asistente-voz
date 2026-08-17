# src/asistente/config.py
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# `load_dotenv()` sin argumentos busca el `.env` a partir del directorio de
# trabajo. Eso vale mientras se arranque con `python -m asistente` desde la
# raíz del proyecto, pero un asistente doméstico acaba lanzándose desde un
# acceso directo, una tarea programada o un servicio, y entonces el
# directorio de trabajo es otro cualquiera: la configuración se cargaría
# vacía, y en silencio. Las claves ausentes las detecta `__main__`, pero un
# `UMBRAL_WAKEWORD` que vuelve a su valor por defecto sin avisar es
# justamente la clase de fallo que deja el asistente sordo sin explicación.
# Por eso se ancla al `.env` de la raíz del proyecto, junto a este código.
RUTA_ENV = Path(__file__).resolve().parents[2] / ".env"


def _texto_o_none(valor: str | None) -> str | None:
    """Convierte cadenas vacías en None. Una variable de entorno sin valor
    y una variable ausente significan lo mismo aquí."""
    if valor is None or valor.strip() == "":
        return None
    return valor.strip()


@dataclass(frozen=True)
class Config:
    puerto_cara: int
    host_cara: str
    deepgram_api_key: str
    gemini_api_key: str
    modelo_llm: str
    ruta_voz: str
    modelo_wakeword: str
    umbral_wakeword: float
    dispositivo_entrada: str | None
    dispositivo_salida: str | None
    pantalla_completa: bool
    ancho: int
    alto: int

    @classmethod
    def cargar(cls) -> "Config":
        # Si el `.env` de la raíz no existe (una instalación que configure
        # todo por variables de entorno, por ejemplo) se recurre a la
        # búsqueda normal, que no encontrará nada y no hará daño.
        if RUTA_ENV.is_file():
            load_dotenv(RUTA_ENV)
        else:
            load_dotenv()
        return cls(
            puerto_cara=int(os.getenv("PUERTO_CARA", "8765")),
            host_cara=os.getenv("HOST_CARA", "127.0.0.1"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            modelo_llm=os.getenv("MODELO_LLM", "gemini-2.5-flash"),
            ruta_voz=os.getenv("RUTA_VOZ", "modelos/es_ES-davefx-medium.onnx"),
            modelo_wakeword=os.getenv("MODELO_WAKEWORD", "hey_jarvis"),
            # 0.3, no el 0.5 que openWakeWord trae de fábrica: ese valor está
            # pensado para voces inglesas, y `hey_jarvis` pronunciado en
            # castellano puntúa bastante por debajo. Ver .env.example.
            umbral_wakeword=float(os.getenv("UMBRAL_WAKEWORD", "0.3")),
            dispositivo_entrada=_texto_o_none(os.getenv("DISPOSITIVO_ENTRADA")),
            dispositivo_salida=_texto_o_none(os.getenv("DISPOSITIVO_SALIDA")),
            pantalla_completa=os.getenv("PANTALLA_COMPLETA", "false").lower() == "true",
            ancho=int(os.getenv("ANCHO", "800")),
            alto=int(os.getenv("ALTO", "480")),
        )
