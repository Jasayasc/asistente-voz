import httpx
import numpy as np
import pytest

from asistente.llm.base import ErrorDeRed
from asistente.stt.deepgram import ClienteDeepgram

RESPUESTA_OK = {
    "results": {
        "channels": [
            {"alternatives": [{"transcript": "  hola qué tal  "}]},
        ]
    }
}


def _audio() -> np.ndarray:
    return np.zeros(160, dtype=np.int16)


def _cliente(manejador):
    return httpx.Client(transport=httpx.MockTransport(manejador))


def test_una_respuesta_200_con_cuerpo_no_json_lanza_error_de_red():
    cliente = _cliente(lambda req: httpx.Response(200, content=b"<html>portal cautivo</html>"))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    with pytest.raises(ErrorDeRed):
        stt.transcribir(_audio())


def test_un_fallo_de_transporte_lanza_error_de_red():
    def falla(req):
        raise httpx.ConnectError("sin red")

    stt = ClienteDeepgram("clave", cliente_http=_cliente(falla))
    with pytest.raises(ErrorDeRed):
        stt.transcribir(_audio())


def test_un_error_http_lanza_error_de_red():
    cliente = _cliente(lambda req: httpx.Response(500))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    with pytest.raises(ErrorDeRed):
        stt.transcribir(_audio())


def test_una_respuesta_bien_formada_devuelve_la_transcripcion_recortada():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    assert stt.transcribir(_audio()) == "hola qué tal"


def test_faltan_las_claves_esperadas_devuelve_cadena_vacia():
    cliente = _cliente(lambda req: httpx.Response(200, json={}))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    assert stt.transcribir(_audio()) == ""


def test_alternatives_como_cadena_devuelve_cadena_vacia():
    respuesta = {"results": {"channels": [{"alternatives": "no soy una lista"}]}}
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    assert stt.transcribir(_audio()) == ""


def test_alternatives_vacia_devuelve_cadena_vacia():
    respuesta = {"results": {"channels": [{"alternatives": []}]}}
    cliente = _cliente(lambda req: httpx.Response(200, json=respuesta))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    assert stt.transcribir(_audio()) == ""


def test_audio_vacio_devuelve_cadena_vacia_sin_hacer_peticion():
    llamadas = []

    def manejador(req):
        llamadas.append(req)
        return httpx.Response(200, json=RESPUESTA_OK)

    stt = ClienteDeepgram("clave", cliente_http=_cliente(manejador))
    assert stt.transcribir(np.zeros(0, dtype=np.int16)) == ""
    assert llamadas == []


def test_no_cierra_un_cliente_provisto_por_quien_llama():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    stt = ClienteDeepgram("clave", cliente_http=cliente)
    stt.transcribir(_audio())
    assert not cliente.is_closed
    cliente.close()


def test_la_construccion_con_dos_argumentos_posicionales_sigue_funcionando():
    stt = ClienteDeepgram("clave", "es")
    assert stt._idioma == "es"
