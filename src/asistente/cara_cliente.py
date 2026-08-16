import socket
import time

from comun.estados import Estado
from comun.protocolo import Mensaje, codificar

ESPERA_RECONEXION = 1.0  # segundos entre intentos, para no martillear


class CaraCliente:
    """Envía estados al proceso `cara`.

    La cara es opcional: si no está corriendo, el asistente sigue
    funcionando sin ella. Por eso ningún método lanza excepción — un fallo
    de conexión se traga y se reintenta más tarde.
    """

    def __init__(
        self, host: str, puerto: int, espera_reconexion: float = ESPERA_RECONEXION
    ) -> None:
        self._host = host
        self._puerto = puerto
        self._espera_reconexion = espera_reconexion
        self._sock: socket.socket | None = None
        self._proximo_intento = 0.0

    def set_estado(self, estado: Estado, rms: float = 0.0) -> None:
        if not self._asegurar_conexion():
            return
        try:
            self._sock.sendall(codificar(Mensaje(estado, rms=rms)))
        except OSError:
            self._descartar()

    def cerrar(self) -> None:
        self._descartar()

    def _asegurar_conexion(self) -> bool:
        if self._sock is not None:
            return True
        if time.monotonic() < self._proximo_intento:
            return False
        try:
            self._sock = socket.create_connection(
                (self._host, self._puerto), timeout=1.0
            )
            return True
        except OSError:
            self._sock = None
            self._proximo_intento = time.monotonic() + self._espera_reconexion
            return False

    def _descartar(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._proximo_intento = time.monotonic() + self._espera_reconexion
