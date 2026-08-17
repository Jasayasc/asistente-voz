# tests/test_gemini.py
"""Pruebas de ClienteGemini con el SDK sustituido: sin red, sin clave.

El cliente real de `google-genai` se construye (no hace ninguna llamada de
red al construirse), y luego se sustituye `models.generate_content_stream`
por una versión falsa que devuelve fragmentos preparados a mano. Así se
comprueba la traducción de excepciones y el bucle de herramientas sin
depender de la API de Gemini.
"""
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from asistente.llm.base import ErrorDeRed
from asistente.llm.gemini import (
    MAX_VUELTAS_HERRAMIENTAS,
    TURNOS_DE_HISTORIAL,
    ClienteGemini,
    _construir_herramientas,
    _tipo_gemini,
)


def _parte(texto=None, llamada=None):
    """Construye una parte de fragmento falsa, del mismo modo en que
    `_partes` de ClienteGemini la consulta: por atributos, no por tipo."""
    return SimpleNamespace(text=texto, function_call=llamada)


def _fragmento(*partes):
    """Envuelve partes en la estructura candidates -> content -> parts que
    usa el SDK, con SimpleNamespace: a `_partes` le basta con eso."""
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(partes)))]
    )


class ClienteStreamFalso:
    """Sustituye a `cliente.models.generate_content_stream`.

    Cada llamada consume la siguiente entrada de `turnos`: una lista de
    fragmentos, o una excepción para lanzar en su lugar. Registra los
    argumentos de cada llamada para poder comprobar cuántas veces se llamó.
    """

    def __init__(self, turnos):
        self._turnos = list(turnos)
        self.llamadas = []

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        turno = self._turnos[len(self.llamadas) - 1]
        if isinstance(turno, BaseException):
            raise turno
        return iter(turno)


def _cliente_con_stream_falso(turnos) -> tuple[ClienteGemini, ClienteStreamFalso]:
    cliente = ClienteGemini(api_key="clave-falsa", modelo="gemini-2.5-flash")
    falso = ClienteStreamFalso(turnos)
    cliente._cliente.models.generate_content_stream = falso
    return cliente, falso


# --- Corrección 1: fallos de red reales se traducen a ErrorDeRed ---------


def test_error_de_conexion_se_traduce_a_error_de_red():
    """Una wifi caída da httpx.ConnectError, no genai_errors.APIError: es
    justo el caso que la excepción original del brief no cubría."""
    cliente, _ = _cliente_con_stream_falso(
        [httpx.ConnectError("no se pudo conectar")]
    )
    with pytest.raises(ErrorDeRed):
        list(cliente.conversar("¿qué tiempo hace?"))


def test_respuesta_no_parseable_se_traduce_a_error_de_red():
    """UnknownApiResponseError del SDK hereda de ValueError, no de APIError:
    una respuesta cortada a mitad de JSON debe traducirse igual."""
    cliente, _ = _cliente_con_stream_falso([ValueError("json inválido")])
    with pytest.raises(ErrorDeRed):
        list(cliente.conversar("¿qué tiempo hace?"))


def test_no_lanza_error_de_red_sin_fallo_de_verdad():
    """Control negativo: si no hay excepción, conversar no debe fallar."""
    cliente, _ = _cliente_con_stream_falso([[_fragmento(_parte(texto="Hola."))]])
    assert list(cliente.conversar("hola")) == ["Hola."]


# --- Frases completas, no fragmentos sueltos ------------------------------


def test_conversar_emite_frases_completas_no_fragmentos():
    turno = [
        _fragmento(_parte(texto="Hola")),
        _fragmento(_parte(texto=" mun")),
        _fragmento(_parte(texto="do.")),
        _fragmento(_parte(texto=" ¿Qué")),
        _fragmento(_parte(texto=" tal?")),
    ]
    cliente, _ = _cliente_con_stream_falso([turno])
    assert list(cliente.conversar("saluda")) == ["Hola mundo.", "¿Qué tal?"]


# --- Bucle de herramientas -------------------------------------------------


def test_bucle_de_herramientas_ejecuta_y_continua(monkeypatch):
    """Si el modelo pide una función, se ejecuta y la conversación sigue con
    el resultado; cuando ya no hay más llamadas, termina con el texto."""
    resultados_ejecutados = []

    def ejecutar_falso(nombre, argumentos):
        resultados_ejecutados.append((nombre, argumentos))
        return "Templado y despejado."

    monkeypatch.setattr("asistente.llm.gemini.ejecutar", ejecutar_falso)

    llamada = types.FunctionCall(
        name="consultar_clima", args={"latitud": 40.4, "longitud": -3.7}
    )
    turno_1 = [_fragmento(_parte(llamada=llamada))]
    turno_2 = [_fragmento(_parte(texto="Hace sol en Madrid."))]

    cliente, falso = _cliente_con_stream_falso([turno_1, turno_2])
    frases = list(cliente.conversar("¿qué tiempo hace en Madrid?"))

    assert frases == ["Hace sol en Madrid."]
    assert resultados_ejecutados == [
        ("consultar_clima", {"latitud": 40.4, "longitud": -3.7})
    ]
    assert len(falso.llamadas) == 2


def test_bucle_de_herramientas_no_supera_el_maximo_de_vueltas(monkeypatch):
    """Si el modelo insiste en llamar a la función sin parar, el bucle debe
    cortar en MAX_VUELTAS_HERRAMIENTAS y no colgarse."""
    monkeypatch.setattr(
        "asistente.llm.gemini.ejecutar", lambda nombre, argumentos: "resultado"
    )
    llamada = types.FunctionCall(
        name="consultar_clima", args={"latitud": 1.0, "longitud": 2.0}
    )
    turno_repetido = [_fragmento(_parte(llamada=llamada))]

    cliente, falso = _cliente_con_stream_falso(
        [turno_repetido] * MAX_VUELTAS_HERRAMIENTAS
    )
    frases = list(cliente.conversar("insiste"))

    assert frases == []
    assert len(falso.llamadas) == MAX_VUELTAS_HERRAMIENTAS


def test_construccion_de_llamada_invalida_se_traduce_a_error_de_red():
    """Corrección 2: la construcción de Content/Part tras el streaming debe
    quedar dentro de la misma guarda. Una function_call mal formada (aquí,
    una cadena en vez de un FunctionCall real) hace que la validación de
    pydantic del SDK falle con ValidationError, que hereda de ValueError."""
    turno = [_fragmento(_parte(llamada="no-es-una-function-call-valida"))]
    cliente, _ = _cliente_con_stream_falso([turno])
    with pytest.raises(ErrorDeRed):
        list(cliente.conversar("pregunta"))


# --- Recorte del historial --------------------------------------------------


def test_historial_se_recorta_a_turnos_de_historial():
    """El comentario del código llama a esto comportamiento deliberado:
    solo se guardan los últimos TURNOS_DE_HISTORIAL elementos."""
    cliente, falso = _cliente_con_stream_falso(
        [[_fragmento(_parte(texto=f"Respuesta {i}."))] for i in range(5)]
    )
    for i in range(5):
        list(cliente.conversar(f"Pregunta {i}"))

    assert len(cliente._historial) == TURNOS_DE_HISTORIAL
    # Las últimas 3 respuestas (3 intercambios) deben seguir presentes.
    textos_modelo = [
        parte.text
        for contenido in cliente._historial
        if contenido.role == "model"
        for parte in contenido.parts
    ]
    assert textos_modelo == ["Respuesta 2.", "Respuesta 3.", "Respuesta 4."]


def test_reiniciar_vacia_el_historial():
    cliente, _ = _cliente_con_stream_falso([[_fragmento(_parte(texto="Hola."))]])
    list(cliente.conversar("hola"))
    assert cliente._historial != []
    cliente.reiniciar()
    assert cliente._historial == []


# --- Corrección 3: el traductor de esquema respeta el tipo declarado ------


def test_tipo_gemini_traduce_number_y_string():
    assert _tipo_gemini("number") == types.Type.NUMBER
    assert _tipo_gemini("string") == types.Type.STRING


def test_tipo_gemini_falla_con_tipo_desconocido():
    """Debe fallar alto y claro, no elegir NUMBER por defecto en silencio:
    ese silencio es justo lo que hacía el brief original."""
    with pytest.raises(ValueError):
        _tipo_gemini("boolean")


def test_construir_herramientas_usa_number_para_esquema_clima():
    herramienta = _construir_herramientas()
    parametros = herramienta.function_declarations[0].parameters.properties
    assert parametros["latitud"].type == types.Type.NUMBER
    assert parametros["longitud"].type == types.Type.NUMBER


def test_construir_herramientas_respeta_un_parametro_de_texto(monkeypatch):
    """Prueba de integración: si el esquema neutro declarase un parámetro
    de texto, debe llegar a Gemini como STRING, no como NUMBER por defecto.
    Esto es justo lo que el brief original no comprobaba: como los dos
    parámetros de ESQUEMA_CLIMA son numéricos, forzar NUMBER para todos
    "funcionaba" sin que ningún test lo notase."""
    esquema_con_texto = {
        "nombre": "consultar_clima",
        "descripcion": "Consulta el clima.",
        "parametros": {
            "ciudad": {"tipo": "string", "descripcion": "Nombre de la ciudad"},
        },
    }
    monkeypatch.setattr("asistente.llm.gemini.ESQUEMA_CLIMA", esquema_con_texto)

    herramienta = _construir_herramientas()
    parametros = herramienta.function_declarations[0].parameters.properties
    assert parametros["ciudad"].type == types.Type.STRING
