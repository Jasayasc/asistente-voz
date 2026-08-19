# tests/test_reacciones.py
"""Pruebas de cómo se le pone la cara cuando la tocan.

Se trabaja sobre `Parametros`, no sobre píxeles: lo que se comprueba es
que cada reacción mueve los valores en la dirección correcta y que la
expresión del estado se respeta en lo que no toca.
"""
import pytest

from cara.parametros import Parametros
from cara.reacciones import aplicar, temblor
from cara.tacto import DURACION_TOQUE_MAX, Reaccion, Tacto


def _con_reaccion(reaccion: Reaccion) -> Tacto:
    """Un Tacto puesto directamente en la reacción que se quiere probar.

    Llegar a cada reacción con gestos completos ya lo cubre
    `test_tacto.py`; aquí interesa la traducción a expresión, así que se
    fija el estado a mano."""
    tacto = Tacto()
    tacto._emitir(reaccion)
    return tacto


NEUTRA = Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.15)


def test_sin_reaccion_la_cara_no_se_toca():
    """Control negativo: si nadie ha tocado nada, la expresión del estado
    tiene que llegar intacta."""
    resultado = aplicar(NEUTRA, Tacto())
    assert resultado == NEUTRA


def test_las_cosquillas_sonrien_y_entrecierran_los_ojos():
    resultado = aplicar(NEUTRA, _con_reaccion(Reaccion.COSQUILLAS))
    assert resultado.sonrisa > NEUTRA.sonrisa
    assert resultado.ojo_izq < NEUTRA.ojo_izq
    assert resultado.ojo_der < NEUTRA.ojo_der


def test_las_cosquillas_mueven_la_boca():
    """La risa es lo que se ve; sin boca, unas cosquillas son solo una
    sonrisa fija."""
    tacto = _con_reaccion(Reaccion.COSQUILLAS)
    aperturas = set()
    for _ in range(20):
        tacto.actualizar(0.02)
        aperturas.add(round(aplicar(NEUTRA, tacto).boca, 3))
    assert len(aperturas) > 3


def test_la_molestia_pone_mala_cara():
    tacto = _con_reaccion(Reaccion.MOLESTIA)
    resultado = aplicar(NEUTRA, tacto)
    assert resultado.sonrisa < 0
    assert resultado.ojo_izq < NEUTRA.ojo_izq


def test_la_molestia_mira_a_quien_le_ha_dado():
    """La mirada de reojo: si el golpe viene de la derecha, mira a la
    derecha."""
    tacto = Tacto()
    tacto.pulsar(0.95, 0.5)
    tacto.actualizar(DURACION_TOQUE_MAX / 2)
    tacto.soltar(0.95, 0.5)
    tacto.actualizar(0.1)
    tacto.pulsar(0.95, 0.5)
    tacto.actualizar(DURACION_TOQUE_MAX / 2)
    tacto.soltar(0.95, 0.5)
    assert tacto.reaccion is Reaccion.MOLESTIA
    assert aplicar(NEUTRA, tacto).pupila_x > 0.5


def test_insistir_pone_peor_cara():
    """Cada golpe de más dentro de la misma ventana empeora el gesto."""
    tacto = Tacto()

    def dar_un_golpe():
        tacto.pulsar(0.5, 0.5)
        tacto.actualizar(DURACION_TOQUE_MAX / 2)
        tacto.soltar(0.5, 0.5)
        tacto.actualizar(0.05)

    dar_un_golpe()
    dar_un_golpe()
    sonrisa_con_dos = aplicar(NEUTRA, tacto).sonrisa
    for _ in range(4):
        dar_un_golpe()
    assert aplicar(NEUTRA, tacto).sonrisa < sonrisa_con_dos


def test_la_sorpresa_abre_los_ojos():
    resultado = aplicar(NEUTRA, _con_reaccion(Reaccion.SORPRESA))
    assert resultado.ojo_izq > NEUTRA.ojo_izq
    assert resultado.ojo_der > NEUTRA.ojo_der


def test_apoyar_el_dedo_solo_mueve_la_mirada():
    """ATENCION es la reacción más discreta: mira, y nada más. Si tocara
    también los ojos o la boca, apoyar el dedo taparía la expresión del
    estado en el que esté el asistente."""
    tacto = Tacto()
    tacto.pulsar(0.9, 0.9)
    resultado = aplicar(NEUTRA, tacto)
    assert resultado.pupila_x > 0
    assert resultado.pupila_y > 0
    assert resultado.ojo_izq == NEUTRA.ojo_izq
    assert resultado.sonrisa == NEUTRA.sonrisa
    assert resultado.boca == NEUTRA.boca


def test_mira_hacia_donde_le_tocan():
    izquierda = Tacto()
    izquierda.pulsar(0.05, 0.5)
    derecha = Tacto()
    derecha.pulsar(0.95, 0.5)
    assert aplicar(NEUTRA, izquierda).pupila_x < 0
    assert aplicar(NEUTRA, derecha).pupila_x > 0


def test_mientras_habla_la_boca_es_del_lipsync():
    """La boca la gobierna el lipsync mientras el asistente contesta:
    pisarla con una risa desincronizaría la voz de la cara. El resto de la
    reacción sí se ve, que es lo que permite contestar y tener cosquillas a
    la vez."""
    hablando = Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.2, boca=0.7)
    tacto = _con_reaccion(Reaccion.COSQUILLAS)
    resultado = aplicar(hablando, tacto, mueve_la_boca=False)
    assert resultado.boca == 0.7
    assert resultado.sonrisa > hablando.sonrisa


def test_la_reaccion_se_desvanece_sola():
    """La intensidad decae, así que la cara vuelve a su expresión de estado
    sin necesidad de animar ninguna transición a mano."""
    tacto = _con_reaccion(Reaccion.MOLESTIA)
    recien = aplicar(NEUTRA, tacto).sonrisa
    tacto.actualizar(2.0)
    casi_pasada = aplicar(NEUTRA, tacto).sonrisa
    assert recien < casi_pasada <= NEUTRA.sonrisa


def test_no_muta_la_expresion_de_entrada():
    base = Parametros(ojo_izq=0.85, sonrisa=0.15)
    aplicar(base, _con_reaccion(Reaccion.COSQUILLAS))
    assert base.ojo_izq == 0.85
    assert base.sonrisa == 0.15


# --- Respingo -------------------------------------------------------------


def test_solo_un_golpe_hace_temblar_la_cara():
    assert temblor(Tacto()) == 0.0
    assert temblor(_con_reaccion(Reaccion.COSQUILLAS)) == 0.0


def test_el_respingo_se_amortigua():
    """Un respingo seco al recibir el golpe que se disuelve en medio
    segundo, no un temblor permanente."""
    tacto = _con_reaccion(Reaccion.MOLESTIA)
    maximos = []
    for tramo in range(3):
        pico = 0.0
        for _ in range(20):
            tacto.actualizar(0.01)
            pico = max(pico, abs(temblor(tacto)))
        maximos.append(pico)
    assert maximos[0] > maximos[-1]


def test_el_respingo_es_pequeno():
    """Es un respingo, no un terremoto: mover la cara media pantalla
    marearía a cualquiera."""
    tacto = _con_reaccion(Reaccion.MOLESTIA)
    for _ in range(200):
        tacto.actualizar(0.005)
        assert abs(temblor(tacto)) < 0.02
