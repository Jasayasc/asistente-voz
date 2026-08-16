import socket
import threading

from comun.estados import Estado
from comun.protocolo import Mensaje, decodificar

REPOSO = Mensaje(Estado.REPOSO)


class ServidorCara:
    """Recibe estados del proceso `asistente` por TCP.

    Corre en un hilo aparte para que el bucle de render nunca se bloquee
    esperando en el socket. Acepta un cliente cada vez; al desconectarse,
    vuelve a REPOSO y espera al siguiente. Ninguna condición de error debe
    tumbar este servidor: la cara tiene que sobrevivir a que el asistente
    se caiga.
    """

    def __init__(self, host: str, puerto: int) -> None:
        self._host = host
        self._puerto_pedido = puerto
        self._mensaje = REPOSO
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self.puerto = puerto

    def iniciar(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._puerto_pedido))
        self._sock.listen(1)
        self._sock.settimeout(0.2)
        self.puerto = self._sock.getsockname()[1]
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def estado_actual(self) -> Mensaje:
        with self._lock:
            return self._mensaje

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
        if self._sock is not None:
            self._sock.close()

    def _fijar(self, mensaje: Mensaje) -> None:
        with self._lock:
            self._mensaje = mensaje

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                conexion, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conexion:
                self._atender(conexion)
            self._fijar(REPOSO)

    def _atender(self, conexion: socket.socket) -> None:
        conexion.settimeout(0.2)
        pendiente = b""
        while not self._parar.is_set():
            try:
                datos = conexion.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not datos:
                return
            pendiente += datos
            while b"\n" in pendiente:
                linea, pendiente = pendiente.split(b"\n", 1)
                if not linea.strip():
                    continue
                try:
                    self._fijar(decodificar(linea))
                except ValueError:
                    # Una línea corrupta se descarta. La cara sigue viva.
                    continue
