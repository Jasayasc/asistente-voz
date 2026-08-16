# tests/test_captura.py
import numpy as np

from asistente.audio.captura import MAX_BLOQUES_EN_COLA, TAMANO_BLOQUE, Captura


def _bloque(valor: int) -> np.ndarray:
    """Bloque sintético del tamaño esperado, relleno con un valor constante
    para poder identificarlo luego."""
    return np.full((TAMANO_BLOQUE, 1), valor, dtype=np.int16)


def test_leer_bloque_devuelve_en_orden_de_llegada():
    captura = Captura()
    captura._callback(_bloque(1), TAMANO_BLOQUE, None, None)
    captura._callback(_bloque(2), TAMANO_BLOQUE, None, None)
    captura._callback(_bloque(3), TAMANO_BLOQUE, None, None)

    assert captura.leer_bloque()[0] == 1
    assert captura.leer_bloque()[0] == 2
    assert captura.leer_bloque()[0] == 3


def test_cola_llena_descarta_el_bloque_mas_antiguo():
    captura = Captura()
    total = MAX_BLOQUES_EN_COLA + 5
    for i in range(total):
        captura._callback(_bloque(i), TAMANO_BLOQUE, None, None)

    # Los primeros 5 (los más antiguos) deben haberse descartado; deben
    # sobrevivir los últimos MAX_BLOQUES_EN_COLA, en orden.
    supervivientes = [captura.leer_bloque()[0] for _ in range(MAX_BLOQUES_EN_COLA)]
    assert supervivientes == list(range(5, total))
    assert captura.leer_bloque() is None


def test_vaciar_deja_la_cola_vacia():
    captura = Captura()
    captura._callback(_bloque(1), TAMANO_BLOQUE, None, None)
    captura._callback(_bloque(2), TAMANO_BLOQUE, None, None)

    captura.vaciar()

    assert captura.leer_bloque(timeout=0.05) is None


def test_leer_bloque_devuelve_none_si_no_hay_datos():
    captura = Captura()
    assert captura.leer_bloque(timeout=0.05) is None
