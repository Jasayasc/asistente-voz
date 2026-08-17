# tests/test_cara_main.py
"""Pruebas de la composición por frame del bucle de render de `cara`.

`src/cara/__main__.py` no tenía tests: es una de las dos raíces de
composición de la rama (la otra es `asistente/__main__.py`), y es donde
vivía el defecto del doble suavizado de la boca (ver revisión final del
Hito 1, M2). Se extrajo `_componer_frame` para poder probarlo sin abrir
pantalla ni socket.
"""
from cara.__main__ import _componer_frame
from cara.parametros import Parametros


def test_la_boca_llega_sin_suavizar():
    """El valor de lipsync ya trae su propio ataque/liberación
    (`Lipsync.procesar`): pasarlo otra vez por `interpolar` lo suaviza dos
    veces y anula el ataque rápido. El valor que llega al renderizador debe
    ser exactamente el que puso el lipsync, no uno acercado a él."""
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=0.8)  # ya viene de lipsync.procesar()

    resultado = _componer_frame(actual, objetivo, factor=0.15)

    assert resultado.boca == 0.8


def test_el_resto_de_parametros_si_se_suaviza():
    """La boca es la única excepción: los demás campos deben seguir
    pasando por el factor de suavizado genérico, como antes del arreglo."""
    actual = Parametros(ojo_izq=0.0, pupila_x=0.0, sonrisa=0.0, boca=0.0)
    objetivo = Parametros(ojo_izq=1.0, pupila_x=1.0, sonrisa=1.0, boca=1.0)

    resultado = _componer_frame(actual, objetivo, factor=0.5)

    assert resultado.ojo_izq == 0.5
    assert resultado.pupila_x == 0.5
    assert resultado.sonrisa == 0.5
    assert resultado.boca == 1.0  # la boca sí llega directa al objetivo


def test_no_muta_los_parametros_originales():
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=0.8)
    _componer_frame(actual, objetivo, factor=0.15)
    assert actual.boca == 0.0
    assert objetivo.boca == 0.8
