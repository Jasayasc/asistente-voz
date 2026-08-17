import httpx

from asistente.llm.herramientas import ESQUEMA_CLIMA, consultar_clima, ejecutar

RESPUESTA_OK = {
    "current": {
        "temperature_2m": 18.4,
        "apparent_temperature": 17.1,
        "relative_humidity_2m": 62,
        "wind_speed_10m": 11.2,
        "weather_code": 3,
    }
}


def _cliente(manejador):
    return httpx.Client(transport=httpx.MockTransport(manejador))


def test_el_esquema_tiene_los_campos_obligatorios():
    assert ESQUEMA_CLIMA["nombre"] == "consultar_clima"
    assert ESQUEMA_CLIMA["descripcion"]
    props = ESQUEMA_CLIMA["parametros"]
    assert set(props) == {"latitud", "longitud"}
    for definicion in props.values():
        assert definicion["tipo"] == "number"
        assert definicion["descripcion"]


def test_devuelve_la_temperatura():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "18.4" in texto


def test_describe_el_estado_del_cielo():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "nublado" in texto.lower()


def test_un_error_http_devuelve_texto_no_excepcion():
    cliente = _cliente(lambda req: httpx.Response(500))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "no" in texto.lower()


def test_un_fallo_de_red_devuelve_texto_no_excepcion():
    def falla(req):
        raise httpx.ConnectError("sin red")

    texto = consultar_clima(40.4, -3.7, cliente_http=_cliente(falla))
    assert "no" in texto.lower()


def test_ejecutar_despacha_a_la_herramienta():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = ejecutar(
        "consultar_clima", {"latitud": 40.4, "longitud": -3.7}, cliente_http=cliente
    )
    assert "18.4" in texto


def test_ejecutar_con_herramienta_desconocida_no_lanza():
    texto = ejecutar("volar", {})
    assert "volar" in texto


def test_ejecutar_con_argumentos_invalidos_no_lanza():
    texto = ejecutar("consultar_clima", {"latitud": "no soy un número"})
    assert isinstance(texto, str)


def test_respuesta_200_con_current_faltando_un_campo_no_lanza():
    """Respuesta 200 pero current sin temperature_2m."""
    respuesta_incompleta = {
        "current": {
            "apparent_temperature": 17.1,
            "relative_humidity_2m": 62,
            "wind_speed_10m": 11.2,
            "weather_code": 3,
        }
    }
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta_incompleta))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert isinstance(texto, str)
    assert "no" in texto.lower()


def test_respuesta_200_con_current_no_diccionario_no_lanza():
    """Respuesta 200 pero current es una cadena, no diccionario."""
    respuesta_mala = {"current": "esto no es un diccionario"}
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta_mala))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert isinstance(texto, str)
    assert "no" in texto.lower()


def test_respuesta_200_con_weather_code_nulo_no_lanza():
    """Respuesta 200 pero weather_code es null."""
    respuesta_weather_nulo = {
        "current": {
            "temperature_2m": 18.4,
            "apparent_temperature": 17.1,
            "relative_humidity_2m": 62,
            "wind_speed_10m": 11.2,
            "weather_code": None,
        }
    }
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta_weather_nulo))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert isinstance(texto, str)
    assert "no" in texto.lower() or "datos" in texto.lower()


def test_respuesta_200_con_weather_code_no_numerico_no_lanza():
    """Respuesta 200 pero weather_code es una cadena."""
    respuesta_code_texto = {
        "current": {
            "temperature_2m": 18.4,
            "apparent_temperature": 17.1,
            "relative_humidity_2m": 62,
            "wind_speed_10m": 11.2,
            "weather_code": "no soy un número",
        }
    }
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta_code_texto))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert isinstance(texto, str)
    assert "no" in texto.lower()


def test_respuesta_200_json_no_diccionario_no_lanza():
    """Respuesta 200 pero el JSON es una lista, no diccionario."""
    cliente = _cliente(lambda req: httpx.Response(200, json=[1, 2, 3]))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert isinstance(texto, str)
    assert "no" in texto.lower()
