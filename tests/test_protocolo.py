import pytest

from comun.estados import Estado
from comun.protocolo import Mensaje, codificar, decodificar


def test_ida_y_vuelta():
    original = Mensaje(estado=Estado.HABLANDO, rms=0.42)
    assert decodificar(codificar(original)) == original


def test_codificar_termina_en_salto_de_linea():
    datos = codificar(Mensaje(estado=Estado.REPOSO))
    assert datos.endswith(b"\n")
    assert b"\n" not in datos[:-1]


def test_rms_predeterminado_es_cero():
    assert Mensaje(estado=Estado.REPOSO).rms == 0.0


def test_decodificar_rechaza_json_invalido():
    with pytest.raises(ValueError):
        decodificar(b"esto no es json\n")


def test_decodificar_rechaza_estado_desconocido():
    with pytest.raises(ValueError):
        decodificar(b'{"estado": "bailando", "rms": 0.0}\n')


def test_decodificar_rechaza_mensaje_sin_estado():
    with pytest.raises(ValueError):
        decodificar(b'{"rms": 0.5}\n')


def test_decodificar_rechaza_rms_nulo():
    with pytest.raises(ValueError):
        decodificar(b'{"estado": "reposo", "rms": null}\n')


def test_decodificar_rechaza_rms_no_numerico():
    with pytest.raises(ValueError):
        decodificar(b'{"estado": "reposo", "rms": "no_es_numero"}\n')


def test_decodificar_rechaza_rms_lista():
    with pytest.raises(ValueError):
        decodificar(b'{"estado": "reposo", "rms": [1, 2, 3]}\n')
