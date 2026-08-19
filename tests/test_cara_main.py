# tests/test_cara_main.py
"""Pruebas de la composición por frame del bucle de render de `cara`.

`src/cara/__main__.py` no tenía tests: es una de las dos raíces de
composición de la rama (la otra es `asistente/__main__.py`), y es donde
vivía el defecto del doble suavizado de la boca (ver revisión final del
Hito 1, M2). Se extrajo `_componer_frame` para poder probarlo sin abrir
pantalla ni socket.
"""
from types import SimpleNamespace

import pygame

from cara.__main__ import _atender_evento, _componer_frame, _normalizar
from cara.parametros import Parametros
from cara.tacto import DURACION_TOQUE_MAX, Reaccion, Tacto


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


# --- Enrutado de los eventos de pantalla ----------------------------------
#
# Aqui vive el unico problema de la interaccion tactil que no se puede
# reproducir en el ordenador de desarrollo: en una pantalla tactil, SDL
# entrega cada gesto DOS veces, como evento de dedo y ademas como evento de
# raton sintetico. Sin filtrarlo, en la Raspberry Pi cada caricia recorreria
# el doble de distancia y cada golpe valdria por dos.

TAMANO = (800, 480)


def _evento(tipo, **campos):
    return SimpleNamespace(type=tipo, **campos)


def test_el_raton_mueve_la_cara():
    tacto = Tacto()
    assert _atender_evento(_evento(pygame.MOUSEBUTTONDOWN, pos=(720, 240)), tacto, TAMANO)
    assert tacto.reaccion is Reaccion.ATENCION
    assert tacto.punto[0] == 0.9


def test_el_dedo_mueve_la_cara():
    tacto = Tacto()
    _atender_evento(_evento(pygame.FINGERDOWN, x=0.9, y=0.5, finger_id=1), tacto, TAMANO)
    assert tacto.reaccion is Reaccion.ATENCION
    assert tacto.punto == (0.9, 0.5)


def test_el_raton_sintetico_del_tactil_se_ignora():
    """El mismo gesto contado dos veces: la caricia recorreria el doble."""
    tacto = Tacto()
    _atender_evento(
        _evento(pygame.MOUSEBUTTONDOWN, pos=(400, 240), touch=True), tacto, TAMANO
    )
    assert tacto.reaccion is None


def test_un_golpe_tactil_no_cuenta_por_dos():
    """Con el evento sintetico sin filtrar, un solo golpe en la pantalla de
    la Pi habria bastado para que el asistente se molestase."""
    tacto = Tacto()
    for evento in (
        _evento(pygame.FINGERDOWN, x=0.5, y=0.5, finger_id=1),
        _evento(pygame.MOUSEBUTTONDOWN, pos=(400, 240), touch=True),
        _evento(pygame.FINGERUP, x=0.5, y=0.5, finger_id=1),
        _evento(pygame.MOUSEBUTTONUP, pos=(400, 240), touch=True),
    ):
        _atender_evento(evento, tacto, TAMANO)
    assert tacto.reaccion is Reaccion.SORPRESA


def test_una_caricia_tactil_no_recorre_el_doble():
    tacto = Tacto()
    _atender_evento(_evento(pygame.FINGERDOWN, x=0.4, y=0.5, finger_id=1), tacto, TAMANO)
    for i in range(1, 4):
        _atender_evento(
            _evento(pygame.FINGERMOTION, x=0.4 + 0.02 * i, y=0.5, finger_id=1), tacto, TAMANO
        )
        _atender_evento(
            _evento(
                pygame.MOUSEMOTION,
                pos=(int((0.4 + 0.02 * i) * 800), 240),
                touch=True,
            ),
            tacto,
            TAMANO,
        )
    # 0.06 de recorrido real: muy por debajo del umbral de caricia. Contado
    # doble tampoco llegaria, pero el punto es que no se duplica.
    assert tacto.reaccion is Reaccion.ATENCION


def test_salir_con_escape_y_con_la_x():
    tacto = Tacto()
    assert not _atender_evento(_evento(pygame.QUIT), tacto, TAMANO)
    assert not _atender_evento(
        _evento(pygame.KEYDOWN, key=pygame.K_ESCAPE), tacto, TAMANO
    )
    assert _atender_evento(_evento(pygame.KEYDOWN, key=pygame.K_a), tacto, TAMANO)


def test_normalizar_pasa_pixeles_a_fraccion():
    assert _normalizar((400, 240), (800, 480)) == (0.5, 0.5)
    assert _normalizar((0, 0), (800, 480)) == (0.0, 0.0)


def test_normalizar_no_divide_entre_cero():
    """Una ventana minimizada puede reportar tamano cero durante un frame."""
    assert _normalizar((10, 10), (0, 0)) == (0.0, 0.0)


def test_un_gesto_completo_con_raton_da_cosquillas():
    """De extremo a extremo por el mismo camino que en el ordenador de
    desarrollo: eventos de pygame dentro, reaccion fuera."""
    tacto = Tacto()
    _atender_evento(_evento(pygame.MOUSEBUTTONDOWN, pos=(160, 240)), tacto, TAMANO)
    for i in range(1, 13):
        tacto.actualizar(0.05)
        _atender_evento(
            _evento(pygame.MOUSEMOTION, pos=(160 + 40 * i, 240)), tacto, TAMANO
        )
    assert tacto.reaccion is Reaccion.COSQUILLAS


def test_un_golpe_con_raton_sorprende():
    tacto = Tacto()
    _atender_evento(_evento(pygame.MOUSEBUTTONDOWN, pos=(400, 240)), tacto, TAMANO)
    tacto.actualizar(DURACION_TOQUE_MAX / 2)
    _atender_evento(_evento(pygame.MOUSEBUTTONUP, pos=(400, 240)), tacto, TAMANO)
    assert tacto.reaccion is Reaccion.SORPRESA
