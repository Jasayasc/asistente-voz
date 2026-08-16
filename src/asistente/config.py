# src/asistente/config.py
import os
from dataclasses import dataclass

from dotenv import load_dotenv


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
    dispositivo_entrada: str | None
    dispositivo_salida: str | None
    pantalla_completa: bool
    ancho: int
    alto: int

    @classmethod
    def cargar(cls) -> "Config":
        load_dotenv()
        return cls(
            puerto_cara=int(os.getenv("PUERTO_CARA", "8765")),
            host_cara=os.getenv("HOST_CARA", "127.0.0.1"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            modelo_llm=os.getenv("MODELO_LLM", "gemini-2.5-flash"),
            dispositivo_entrada=_texto_o_none(os.getenv("DISPOSITIVO_ENTRADA")),
            dispositivo_salida=_texto_o_none(os.getenv("DISPOSITIVO_SALIDA")),
            pantalla_completa=os.getenv("PANTALLA_COMPLETA", "false").lower() == "true",
            ancho=int(os.getenv("ANCHO", "800")),
            alto=int(os.getenv("ALTO", "480")),
        )
