# tests/test_captura.py
import queue

import numpy as np
import pytest

from asistente.audio import captura as captura_mod
from asistente.audio.captura import MAX_BLOQUES_EN_COLA, TAMANO_BLOQUE, Captura


def _bloque(valor: int) -> np.ndarray:
    """Bloque sintético del tamaño esperado, relleno con un valor constante
    para poder identificarlo luego."""
    return np.full((TAMANO_BLOQUE, 1), valor, dtype=np.int16)


class _StreamFalso:
    """Doble de `sd.InputStream` que no toca hardware. Registra si se llamó
    a `start()` y a `close()` para poder comprobarlo desde el test."""

    def __init__(self, **kwargs) -> None:
        self.iniciado = False
        self.cerrado = False

    def start(self) -> None:
        self.iniciado = True

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.cerrado = True


class _StreamQueFallaAlIniciar(_StreamFalso):
    """Simula un dispositivo que rechaza `start()`: ocupado, sin permiso o
    con una frecuencia no soportada."""

    def start(self) -> None:
        raise RuntimeError("dispositivo ocupado")


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


def test_iniciar_cierra_el_stream_si_start_falla(monkeypatch):
    creado: dict[str, _StreamFalso] = {}

    def fabrica(**kwargs):
        stream = _StreamQueFallaAlIniciar(**kwargs)
        creado["stream"] = stream
        return stream

    monkeypatch.setattr(captura_mod.sd, "InputStream", fabrica)

    captura = Captura()
    with pytest.raises(RuntimeError):
        captura.iniciar()

    # El objeto queda como si iniciar() nunca se hubiera llamado: sin
    # stream referenciado, y el que se llegó a abrir, cerrado.
    assert captura._stream is None
    assert creado["stream"].cerrado is True


def test_iniciar_dos_veces_cierra_el_stream_anterior(monkeypatch):
    creados: list[_StreamFalso] = []

    def fabrica(**kwargs):
        stream = _StreamFalso(**kwargs)
        creados.append(stream)
        return stream

    monkeypatch.setattr(captura_mod.sd, "InputStream", fabrica)

    captura = Captura()
    captura.iniciar()
    primero = captura._stream

    captura.iniciar()
    segundo = captura._stream

    assert primero is not segundo
    assert primero.cerrado is True
    assert segundo.cerrado is False
    assert captura._stream is segundo


def test_callback_no_pierde_el_bloque_nuevo_si_el_descarte_encuentra_la_cola_vacia(
    monkeypatch,
):
    """Reproduce la carrera: la cola está llena, put_nowait falla con Full,
    y justo antes de que _callback intente descartar el más viejo, un
    consumidor externo ya vació la cola por su cuenta. El get_nowait de
    _callback entonces encuentra la cola vacía y lanza Empty — pero eso no
    debe impedir que el bloque nuevo se intente encolar: ya hay sitio."""
    captura = Captura()
    for i in range(MAX_BLOQUES_EN_COLA):
        captura._callback(_bloque(i), TAMANO_BLOQUE, None, None)
    assert captura._cola.full()

    get_nowait_real = captura._cola.get_nowait

    def get_nowait_que_encuentra_la_cola_vaciada_por_otro():
        # Simula que, entre el Full de arriba y esta llamada, un
        # consumidor externo ya se llevó todo lo que había.
        while True:
            try:
                get_nowait_real()
            except queue.Empty:
                break
        raise queue.Empty

    monkeypatch.setattr(
        captura._cola, "get_nowait", get_nowait_que_encuentra_la_cola_vaciada_por_otro
    )

    captura._callback(_bloque(999), TAMANO_BLOQUE, None, None)

    monkeypatch.setattr(captura._cola, "get_nowait", get_nowait_real)

    assert captura._cola.qsize() == 1
    assert captura.leer_bloque()[0] == 999
