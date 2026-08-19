# tests/test_tacto.py
"""Pruebas de la detección de gestos, sin pantalla ni pygame.

El tiempo entra por `actualizar(dt)` y nunca de un reloj de pared, así que
estos tests son deterministas: una caricia de dos segundos se simula en
microsegundos y siempre da el mismo resultado.

El fallo que más importa evitar aquí es confundir una caricia con un
golpe. Son la misma secuencia de eventos —apoyar, mover, levantar— y solo
las separan cuánto se recorrió y cuánto duró.
"""
import pytest

from cara.tacto import (
    DISTANCIA_CARICIA,
    DURACION_MOLESTIA,
    DURACION_SORPRESA,
    DURACION_TOQUE_MAX,
    TOQUES_PARA_MOLESTIA,
    VENTANA_GOLPES,
    Reaccion,
    Tacto,
)


def golpe(tacto: Tacto, x: float = 0.5, y: float = 0.5) -> None:
    """Un dedo que baja y sube en el sitio, deprisa."""
    tacto.pulsar(x, y)
    tacto.actualizar(DURACION_TOQUE_MAX / 2)
    tacto.soltar(x, y)


def caricia(tacto: Tacto, pasos: int = 12, largo: float = 0.6) -> None:
    """Un dedo que recorre la pantalla de izquierda a derecha, apoyado."""
    tacto.pulsar(0.2, 0.5)
    for i in range(1, pasos + 1):
        tacto.actualizar(0.05)
        tacto.mover(0.2 + largo * i / pasos, 0.5)
    tacto.soltar(0.2 + largo, 0.5)


# --- Caricias -------------------------------------------------------------


def test_una_caricia_da_cosquillas():
    tacto = Tacto()
    caricia(tacto)
    assert tacto.reaccion is Reaccion.COSQUILLAS


def test_un_roce_corto_no_llega_a_cosquillas():
    """Mover el dedo un poco no es acariciar; si lo fuera, cualquier
    temblor de la mano sobre la pantalla haría reír al asistente."""
    tacto = Tacto()
    tacto.pulsar(0.5, 0.5)
    tacto.actualizar(0.05)
    tacto.mover(0.5 + DISTANCIA_CARICIA / 3, 0.5)
    assert tacto.reaccion is Reaccion.ATENCION


def test_seguir_acariciando_renueva_las_cosquillas():
    """Mientras la mano siga recorriendo la cara, la risa no se apaga."""
    tacto = Tacto()
    caricia(tacto, pasos=40, largo=2.0)
    # Ha recorrido mucho más que un tramo: la reacción sigue recién puesta.
    assert tacto.reaccion is Reaccion.COSQUILLAS
    assert tacto.intensidad == pytest.approx(1.0)


def test_las_cosquillas_se_pasan_solas():
    tacto = Tacto()
    caricia(tacto)
    tacto.actualizar(5.0)
    assert tacto.reaccion is None


def test_soltar_al_final_de_una_caricia_no_la_borra():
    """Visto de cerca, el `soltar` que cierra una caricia es un toque
    cortito: el dedo apenas se movió en ese último instante. Sin
    prioridades, ese toque pisaría las cosquillas justo al empezar."""
    tacto = Tacto()
    tacto.pulsar(0.2, 0.5)
    for i in range(1, 13):
        tacto.actualizar(0.05)
        tacto.mover(0.2 + 0.05 * i, 0.5)
    tacto.soltar(0.8, 0.5)
    assert tacto.reaccion is Reaccion.COSQUILLAS


# --- Golpes ---------------------------------------------------------------


def test_un_toque_suelto_solo_sorprende():
    """Uno solo no es agresión: el asistente se sobresalta y mira."""
    tacto = Tacto()
    golpe(tacto)
    assert tacto.reaccion is Reaccion.SORPRESA


def test_dos_golpes_seguidos_molestan():
    tacto = Tacto()
    golpe(tacto)
    tacto.actualizar(0.3)
    golpe(tacto)
    assert tacto.reaccion is Reaccion.MOLESTIA


def test_dos_golpes_muy_separados_no_molestan():
    """Tocarle una vez ahora y otra dentro de un minuto no es insistir."""
    tacto = Tacto()
    golpe(tacto)
    tacto.actualizar(VENTANA_GOLPES + 1.0)
    golpe(tacto)
    assert tacto.reaccion is Reaccion.SORPRESA


def test_insistir_empeora_la_cara():
    """Cada golpe de más dentro de la misma ventana sube el enfado, en vez
    de repetir siempre exactamente el mismo gesto."""
    tacto = Tacto()
    for _ in range(TOQUES_PARA_MOLESTIA):
        golpe(tacto)
        tacto.actualizar(0.2)
    enfado_inicial = tacto.enfado
    for _ in range(3):
        golpe(tacto)
        tacto.actualizar(0.2)
    assert tacto.enfado > enfado_inicial


def test_la_molestia_dura_mas_que_la_sorpresa():
    """Sobresaltarse se pasa enseguida; el enfado, no tanto."""
    assert DURACION_MOLESTIA > DURACION_SORPRESA


def test_un_dedo_apoyado_mucho_rato_no_es_un_golpe():
    """Apoyar el dedo y dejarlo quieto no es golpear: es tocar."""
    tacto = Tacto()
    tacto.pulsar(0.5, 0.5)
    tacto.actualizar(DURACION_TOQUE_MAX * 4)
    tacto.soltar(0.5, 0.5)
    assert tacto.reaccion is None


# --- Atención -------------------------------------------------------------


def test_apoyar_el_dedo_llama_la_atencion():
    tacto = Tacto()
    tacto.pulsar(0.8, 0.9)
    assert tacto.reaccion is Reaccion.ATENCION
    assert tacto.punto == (0.8, 0.9)


def test_la_atencion_dura_lo_que_dure_el_dedo():
    """No caduca sola, al revés que las demás: mientras haya un dedo
    apoyado, la cara lo sigue mirando."""
    tacto = Tacto()
    tacto.pulsar(0.5, 0.5)
    tacto.actualizar(30.0)
    assert tacto.reaccion is Reaccion.ATENCION
    tacto.soltar(0.5, 0.5)
    tacto.actualizar(0.1)
    assert tacto.reaccion is None


def test_al_pasarse_una_reaccion_vuelve_a_mirar_el_dedo():
    """Si el dedo sigue apoyado cuando se apagan las cosquillas, la cara no
    se queda indiferente: vuelve a mirarlo."""
    tacto = Tacto()
    tacto.pulsar(0.2, 0.5)
    for i in range(1, 13):
        tacto.actualizar(0.05)
        tacto.mover(0.2 + 0.05 * i, 0.5)
    assert tacto.reaccion is Reaccion.COSQUILLAS
    tacto.actualizar(5.0)  # se pasan, pero el dedo sigue puesto
    assert tacto.reaccion is Reaccion.ATENCION


# --- Higiene del detector -------------------------------------------------


def test_mover_sin_tocar_no_hace_nada():
    """El ratón manda MOUSEMOTION también con el botón suelto. Pasar el
    puntero por encima de la cara no es tocarla."""
    tacto = Tacto()
    for i in range(50):
        tacto.mover(i / 50, 0.5)
    assert tacto.reaccion is None


def test_soltar_sin_haber_tocado_no_hace_nada():
    tacto = Tacto()
    tacto.soltar(0.5, 0.5)
    assert tacto.reaccion is None


def test_sin_tocar_nada_no_hay_reaccion():
    tacto = Tacto()
    tacto.actualizar(10.0)
    assert tacto.reaccion is None
    assert tacto.intensidad == 0.0


def test_la_intensidad_decae_hasta_cero():
    """Es lo que hace que la cara vuelva sola a su expresión de estado sin
    animar ninguna transición a mano."""
    tacto = Tacto()
    golpe(tacto)
    assert tacto.intensidad == pytest.approx(1.0)
    tacto.actualizar(DURACION_SORPRESA / 2)
    assert 0.0 < tacto.intensidad < 1.0
    tacto.actualizar(DURACION_SORPRESA)
    assert tacto.intensidad == 0.0


# --- Multitactil (solo pasa en la pantalla de la Raspberry Pi) ------------


def test_un_segundo_dedo_no_dispara_cosquillas():
    """Posar dos dedos separados haria saltar el punto de uno a otro. Ese
    salto se contaria como recorrido y bastaria para disparar unas
    cosquillas que nadie ha hecho."""
    tacto = Tacto()
    tacto.pulsar(0.1, 0.5, dedo=1)
    tacto.actualizar(0.05)
    tacto.pulsar(0.9, 0.5, dedo=2)  # segundo dedo, muy lejos
    tacto.mover(0.9, 0.5, dedo=2)
    assert tacto.reaccion is Reaccion.ATENCION
    assert tacto.punto == (0.1, 0.5)


def test_levantar_el_segundo_dedo_no_termina_el_gesto():
    tacto = Tacto()
    tacto.pulsar(0.2, 0.5, dedo=1)
    tacto.pulsar(0.8, 0.5, dedo=2)
    tacto.soltar(0.8, 0.5, dedo=2)
    for i in range(1, 13):
        tacto.actualizar(0.05)
        tacto.mover(0.2 + 0.05 * i, 0.5, dedo=1)
    assert tacto.reaccion is Reaccion.COSQUILLAS


def test_tras_levantar_el_dedo_manda_el_siguiente():
    tacto = Tacto()
    tacto.pulsar(0.1, 0.5, dedo=1)
    tacto.soltar(0.1, 0.5, dedo=1)
    tacto.actualizar(2.0)
    tacto.pulsar(0.9, 0.5, dedo=7)
    assert tacto.punto == (0.9, 0.5)


def test_el_raton_no_necesita_identificador():
    """El ordenador de desarrollo no manda ningun id, y todo debe seguir
    funcionando igual."""
    tacto = Tacto()
    tacto.pulsar(0.2, 0.5)
    for i in range(1, 13):
        tacto.actualizar(0.05)
        tacto.mover(0.2 + 0.05 * i, 0.5)
    assert tacto.reaccion is Reaccion.COSQUILLAS
