import socket
import time

from cara.servidor import ServidorCara
from comun.estados import Estado
from comun.protocolo import Mensaje, codificar


def _esperar(condicion, timeout=2.0):
    limite = time.time() + timeout
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_arranca_en_reposo():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        assert servidor.estado_actual().estado is Estado.REPOSO
    finally:
        servidor.detener()


def test_recibe_un_cambio_de_estado():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(codificar(Mensaje(Estado.PENSANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.PENSANDO
            )
    finally:
        servidor.detener()


def test_recibe_varios_mensajes_en_un_solo_paquete():
    """El emisor puede mandar varias líneas juntas; el servidor debe
    procesarlas todas y quedarse con la última."""
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(
                codificar(Mensaje(Estado.ESCUCHANDO))
                + codificar(Mensaje(Estado.PENSANDO))
                + codificar(Mensaje(Estado.HABLANDO, rms=0.7))
            )
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.HABLANDO
            )
            assert servidor.estado_actual().rms == 0.7
    finally:
        servidor.detener()


def test_vuelve_a_reposo_si_el_cliente_se_desconecta():
    """Si el asistente muere, la cara no debe quedarse congelada
    'pensando' para siempre."""
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        sock = socket.create_connection(("127.0.0.1", servidor.puerto))
        sock.sendall(codificar(Mensaje(Estado.PENSANDO)))
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.PENSANDO)
        sock.close()
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.REPOSO)
    finally:
        servidor.detener()


def test_una_linea_invalida_no_tumba_el_servidor():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(b"basura sin sentido\n")
            sock.sendall(codificar(Mensaje(Estado.HABLANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.HABLANDO
            )
    finally:
        servidor.detener()


def test_acepta_una_reconexion():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as s1:
            s1.sendall(codificar(Mensaje(Estado.PENSANDO)))
            assert _esperar(lambda: servidor.estado_actual().estado is Estado.PENSANDO)
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.REPOSO)
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as s2:
            s2.sendall(codificar(Mensaje(Estado.ESCUCHANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.ESCUCHANDO
            )
    finally:
        servidor.detener()
