# src/asistente/config.py
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from asistente.conversacion import frases_desde_configuracion

logger = logging.getLogger(__name__)

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


CIERTOS = frozenset({"true", "1", "si", "sí", "yes", "on"})
FALSOS = frozenset({"false", "0", "no", "off"})


def _texto_o_none(valor: str | None) -> str | None:
    """Convierte cadenas vacías en None. Una variable de entorno sin valor
    y una variable ausente significan lo mismo aquí."""
    if valor is None or valor.strip() == "":
        return None
    return valor.strip()


def _flotante(nombre: str, defecto: float, minimo: float | None = None) -> float:
    """Lee un número del entorno sin poder tumbar el arranque.

    Un `float()` a pelo sobre una variable del `.env` convierte cualquier
    dedazo en un traceback al arrancar, sin decir qué línea lo causó. Y hay
    dos dedazos que este proyecto se va a comer seguro: dejar la variable
    puesta pero vacía, y escribir los decimales con coma, que es como se
    escriben en español.

    Un valor imposible no aborta: se avisa por el log y se usa el
    predeterminado, que es lo que deja al asistente funcionando.
    """
    crudo = _texto_o_none(os.getenv(nombre))
    if crudo is None:
        return defecto
    try:
        valor = float(crudo.replace(",", "."))
    except ValueError:
        logger.warning("%s=%r no es un número; se usa %s", nombre, crudo, defecto)
        return defecto
    if not math.isfinite(valor):
        # "inf" y "nan" pasan el float() y estallan mucho más tarde, ya
        # dentro del bucle de conversación, donde el origen es irrastreable.
        logger.warning("%s=%r no es un número finito; se usa %s", nombre, crudo, defecto)
        return defecto
    if minimo is not None and valor < minimo:
        logger.warning(
            "%s=%s está por debajo del mínimo (%s); se usa %s",
            nombre,
            valor,
            minimo,
            defecto,
        )
        return defecto
    return valor


def _entero(nombre: str, defecto: int, minimo: int | None = None) -> int:
    return int(_flotante(nombre, float(defecto), None if minimo is None else float(minimo)))


def _booleano(nombre: str, defecto: bool) -> bool:
    """Lee un sí/no del entorno aceptando cómo lo escribe la gente.

    Antes solo valía exactamente "true": quien escribía `MODO_CONVERSACION=1`
    —o dejaba el `=` vacío, como en las demás variables opcionales del
    `.env.example`— se encontraba el modo apagado sin ningún aviso, y
    parecía que la función estaba rota.
    """
    crudo = _texto_o_none(os.getenv(nombre))
    if crudo is None:
        return defecto
    normalizado = crudo.lower()
    if normalizado in CIERTOS:
        return True
    if normalizado in FALSOS:
        return False
    logger.warning(
        "%s=%r no se entiende como sí/no; se usa %s", nombre, crudo, defecto
    )
    return defecto


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
    modo_conversacion: bool
    segundos_para_cerrar_conversacion: float
    frases_de_despedida: tuple[str, ...]
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
            puerto_cara=_entero("PUERTO_CARA", 8765, minimo=1),
            host_cara=os.getenv("HOST_CARA", "127.0.0.1"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            modelo_llm=os.getenv("MODELO_LLM", "gemini-2.5-flash"),
            ruta_voz=os.getenv("RUTA_VOZ", "modelos/es_ES-davefx-medium.onnx"),
            modelo_wakeword=os.getenv("MODELO_WAKEWORD", "hey_jarvis"),
            # 0.3, no el 0.5 que openWakeWord trae de fábrica: ese valor está
            # pensado para voces inglesas, y `hey_jarvis` pronunciado en
            # castellano puntúa bastante por debajo. Ver .env.example.
            umbral_wakeword=_flotante("UMBRAL_WAKEWORD", 0.3, minimo=0.0),
            dispositivo_entrada=_texto_o_none(os.getenv("DISPOSITIVO_ENTRADA")),
            dispositivo_salida=_texto_o_none(os.getenv("DISPOSITIVO_SALIDA")),
            # Con esto en false el asistente vuelve al comportamiento de
            # antes: una pregunta por cada palabra clave.
            modo_conversacion=_booleano("MODO_CONVERSACION", True),
            # Mínimo 1 s: un 0 no significa "sin límite" sino "cierra la
            # conversación en cuanto termines de contestar", que es lo
            # contrario de lo que busca quien lo pone.
            segundos_para_cerrar_conversacion=_flotante(
                "SEGUNDOS_PARA_CERRAR_CONVERSACION", 8.0, minimo=1.0
            ),
            frases_de_despedida=frases_desde_configuracion(
                os.getenv("FRASES_DE_DESPEDIDA")
            ),
            pantalla_completa=_booleano("PANTALLA_COMPLETA", False),
            ancho=_entero("ANCHO", 800, minimo=1),
            alto=_entero("ALTO", 480, minimo=1),
        )
