# src/asistente/llm/gemini.py
from collections.abc import Iterator

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from asistente.llm.base import ClienteLLM, ErrorDeRed, acumular_frases
from asistente.llm.herramientas import ESQUEMA_CLIMA, ejecutar

INSTRUCCIONES = (
    "Eres un asistente de voz doméstico. Tus respuestas se convierten en voz "
    "y se escuchan en voz alta, así que:\n"
    "- Responde en dos o tres frases como mucho. Sé directo.\n"
    "- Escribe como se habla: sin listas, sin viñetas, sin markdown, sin "
    "emojis, sin paréntesis.\n"
    "- Escribe los números y las unidades como se pronuncian.\n"
    "- Si no sabes algo, dilo en una frase y no te disculpes de más.\n"
    "- Responde siempre en español."
)

MAX_TOKENS = 400
MAX_VUELTAS_HERRAMIENTAS = 3
TURNOS_DE_HISTORIAL = 6  # 3 intercambios; suficiente para dar contexto

# HttpOptions.timeout está en MILISEGUNDOS (a diferencia de httpx, que usa
# segundos): así lo espera el SDK internamente antes de pasarlo a httpx.
# Sin esto, genai.Client deja timeout=None y httpx espera para siempre ante
# una conexión medio abierta (router vivo, internet muerto): el asistente
# se queda colgado en PENSANDO sin posibilidad de recuperación, porque
# nunca se lanza nada que la red de seguridad del orquestador pueda atrapar.
TIMEOUT_MS = 15_000

# Traduce el campo "tipo" del esquema neutro de herramientas.py al enum de
# tipos de Gemini. Un tipo no soportado debe fallar alto y claro al
# construir las herramientas, no elegir un tipo por defecto en silencio:
# eso escondería el día en que alguien añada un parámetro de un tipo nuevo.
_TIPOS_GEMINI = {
    "number": types.Type.NUMBER,
    "string": types.Type.STRING,
}


def _tipo_gemini(tipo: str) -> types.Type:
    """Traduce un "tipo" del esquema neutro al enum de tipos de Gemini."""
    try:
        return _TIPOS_GEMINI[tipo]
    except KeyError:
        raise ValueError(f"Tipo de parámetro no soportado: '{tipo}'") from None


def _construir_herramientas() -> types.Tool:
    """Traduce el esquema neutro de `herramientas.py` al formato de Gemini.

    Esta traducción vive aquí, en el cliente del proveedor, y no en el
    módulo de herramientas: así cambiar de proveedor no obliga a tocar la
    definición de las herramientas.
    """
    propiedades = {
        nombre: types.Schema(
            type=_tipo_gemini(definicion["tipo"]),
            description=definicion["descripcion"],
        )
        for nombre, definicion in ESQUEMA_CLIMA["parametros"].items()
    }
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=ESQUEMA_CLIMA["nombre"],
                description=ESQUEMA_CLIMA["descripcion"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=propiedades,
                    required=list(ESQUEMA_CLIMA["parametros"]),
                ),
            )
        ]
    )


class ClienteGemini(ClienteLLM):
    """Implementación del cerebro contra la API de Gemini.

    Se desactiva la llamada automática a funciones del SDK y se maneja el
    ciclo a mano: con streaming es la única forma de emitir el texto según
    llega, que es lo que permite empezar a hablar antes de que termine la
    respuesta.
    """

    def __init__(self, api_key: str, modelo: str) -> None:
        self._cliente = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
        self._modelo = modelo
        self._config = types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES,
            tools=[_construir_herramientas()],
            max_output_tokens=MAX_TOKENS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        self._historial: list[types.Content] = []

    def reiniciar(self) -> None:
        self._historial = []

    def conversar(self, texto_usuario: str) -> Iterator[str]:
        yield from acumular_frases(self._tokens(texto_usuario))

    def _tokens(self, texto_usuario: str) -> Iterator[str]:
        turno_usuario = types.Content(
            role="user", parts=[types.Part(text=texto_usuario)]
        )
        contenidos = self._historial + [turno_usuario]
        texto_final = ""

        for _ in range(MAX_VUELTAS_HERRAMIENTAS):
            # Todo lo que puede lanzar en esta vuelta —el streaming en sí y
            # la construcción de los Content/Part de respuesta a partir de
            # lo que devolvió el modelo— vive dentro de esta guarda. La
            # validación de pydantic del SDK puede fallar igual que una
            # llamada de red (p. ej. una function_call sin forma válida), y
            # ninguna de las dos debe escapar sin traducir.
            try:
                llamadas: list[types.FunctionCall] = []
                for fragmento in self._cliente.models.generate_content_stream(
                    model=self._modelo, contents=contenidos, config=self._config
                ):
                    for parte in self._partes(fragmento):
                        if parte.text:
                            texto_final += parte.text
                            yield parte.text
                        if parte.function_call is not None:
                            llamadas.append(parte.function_call)

                if not llamadas:
                    self._recordar(turno_usuario, texto_final)
                    return

                contenidos = contenidos + [
                    types.Content(
                        role="model",
                        parts=[types.Part(function_call=ll) for ll in llamadas],
                    ),
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=ll.name,
                                response={
                                    "resultado": ejecutar(
                                        ll.name, dict(ll.args or {})
                                    )
                                },
                            )
                            for ll in llamadas
                        ],
                    ),
                ]
            except (genai_errors.APIError, httpx.HTTPError, ValueError) as exc:
                # httpx.HTTPError cubre los fallos de red reales (wifi
                # caída, DNS muerto, timeout): el wrapper de reintentos del
                # SDK usa tenacity con reraise=True, así que una vez
                # agotados los reintentos deja pasar la excepción de httpx
                # tal cual, sin envolverla en APIError. ValueError cubre
                # tanto UnknownApiResponseError (JSON no parseable a mitad
                # de stream) como ValidationError de pydantic (respuesta
                # con forma inválida al construir el siguiente turno).
                raise ErrorDeRed(str(exc)) from exc

        self._recordar(turno_usuario, texto_final)

    @staticmethod
    def _partes(fragmento) -> list:
        """Extrae las partes de un fragmento del stream.

        Los fragmentos pueden llegar sin candidatos o sin contenido; hay que
        comprobarlo en cada nivel o el generador revienta a mitad de una
        respuesta perfectamente válida.
        """
        candidatos = getattr(fragmento, "candidates", None) or []
        if not candidatos:
            return []
        contenido = getattr(candidatos[0], "content", None)
        if contenido is None:
            return []
        return list(getattr(contenido, "parts", None) or [])

    def _recordar(self, turno_usuario: types.Content, respuesta: str) -> None:
        """Guarda solo el texto del intercambio, no las llamadas a
        herramientas: mantiene el historial corto y evita arrastrar
        estructuras que el proveedor podría dejar de aceptar."""
        if not respuesta.strip():
            return
        self._historial.append(turno_usuario)
        self._historial.append(
            types.Content(role="model", parts=[types.Part(text=respuesta)])
        )
        self._historial = self._historial[-TURNOS_DE_HISTORIAL:]
