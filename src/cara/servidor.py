import logging
import socket
import threading

from comun.estados import Estado
from comun.protocolo import Mensaje, decodificar

logger = logging.getLogger(__name__)

REPOSO = Mensaje(Estado.REPOSO)

# Margen amplio sobre un mensaje legítimo (decenas de bytes). Si un par nunca
# manda un salto de línea, no dejamos que el búfer de la conexión crezca sin
# límite: en la Raspberry Pi eso agota la RAM y mata el proceso entero.
TAM_MAXIMO_BUFFER = 8192


class ServidorCara:
    """Recibe estados del proceso `asistente` por TCP.

    Corre en un hilo aparte para que el bucle de render nunca se bloquee
    esperando en el socket. Acepta un cliente cada vez; al desconectarse,
    vuelve a REPOSO y espera al siguiente. Ninguna condición de error debe
    tumbar este servidor: la cara tiene que sobrevivir a que el asistente
    se caiga. Los errores recuperables se registran con `logging` (nunca se
    imprimen: este proceso comparte terminal con el bucle de render) y el
    hilo siempre continúa.
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
                if self._parar.is_set():
                    # detener() cerró el socket a propósito: salida limpia.
                    return
                # Error recuperable (p. ej. ECONNABORTED, EMFILE/ENFILE en
                # la Pi). El servidor sigue escuchando en vez de morir.
                logger.warning(
                    "accept() falló con un error recuperable; se sigue escuchando",
                    exc_info=True,
                )
                continue
            try:
                with conexion:
                    self._atender(conexion)
            except Exception:
                # Red de seguridad: nada de lo que pase atendiendo una
                # conexión puede tumbar el hilo del servidor.
                logger.exception(
                    "Excepción inesperada atendiendo una conexión; se descarta"
                )
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
            if len(pendiente) > TAM_MAXIMO_BUFFER:
                # Un par que nunca manda '\n' no debe poder agotar la RAM
                # ni forzar un reescaneo cuadrático del búfer: se descarta.
                logger.warning(
                    "búfer de conexión superó %d bytes sin salto de línea; "
                    "se descarta la conexión",
                    TAM_MAXIMO_BUFFER,
                )
                return
            while b"\n" in pendiente:
                linea, pendiente = pendiente.split(b"\n", 1)
                if not linea.strip():
                    continue
                try:
                    self._fijar(decodificar(linea))
                except Exception:
                    # Cualquier excepción al decodificar (ValueError por
                    # formato inválido, pero también cosas como
                    # RecursionError de un JSON demasiado anidado) se
                    # registra y se descarta. La cara sigue viva.
                    logger.warning(
                        "línea inválida descartada: %r", linea, exc_info=True
                    )
                    continue
