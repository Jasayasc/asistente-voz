import socket
import threading
import time

from asistente.cara_cliente import CaraCliente
from comun.estados import Estado
from comun.protocolo import decodificar


class ServidorFalso:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        self.recibidos = []
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def _bucle(self):
        try:
            conexion, _ = self.sock.accept()
        except OSError:
            return
        pendiente = b""
        with conexion:
            while True:
                try:
                    datos = conexion.recv(4096)
                except OSError:
                    return
                if not datos:
                    return
                pendiente += datos
                while b"\n" in pendiente:
                    linea, pendiente = pendiente.split(b"\n", 1)
                    if linea.strip():
                        self.recibidos.append(decodificar(linea))

    def cerrar(self):
        self.sock.close()


def _esperar(condicion, timeout=2.0):
    limite = time.time() + timeout
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_envia_el_estado():
    servidor = ServidorFalso()
    cliente = CaraCliente("127.0.0.1", servidor.puerto)
    try:
        cliente.set_estado(Estado.PENSANDO)
        assert _esperar(lambda: len(servidor.recibidos) >= 1)
        assert servidor.recibidos[0].estado is Estado.PENSANDO
    finally:
        cliente.cerrar()
        servidor.cerrar()


def test_envia_el_rms():
    servidor = ServidorFalso()
    cliente = CaraCliente("127.0.0.1", servidor.puerto)
    try:
        cliente.set_estado(Estado.HABLANDO, rms=0.65)
        assert _esperar(lambda: len(servidor.recibidos) >= 1)
        assert servidor.recibidos[0].rms == 0.65
    finally:
        cliente.cerrar()
        servidor.cerrar()


def test_no_lanza_si_no_hay_nadie_escuchando():
    """El asistente debe funcionar aunque la cara no esté arrancada."""
    cliente = CaraCliente("127.0.0.1", 1)  # puerto donde nadie escucha
    cliente.set_estado(Estado.PENSANDO)
    cliente.set_estado(Estado.HABLANDO, rms=0.5)
    cliente.cerrar()


def test_se_reconecta_cuando_la_cara_vuelve():
    cliente = CaraCliente("127.0.0.1", 1)
    cliente.set_estado(Estado.PENSANDO)  # falla en silencio

    servidor = ServidorFalso()
    cliente._puerto = servidor.puerto  # simula que la cara arrancó ahí
    try:
        assert _esperar(
            lambda: (cliente.set_estado(Estado.HABLANDO), servidor.recibidos)[1],
            timeout=3.0,
        )
    finally:
        cliente.cerrar()
        servidor.cerrar()
