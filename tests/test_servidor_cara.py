import errno
import socket
import time

from cara.servidor import ServidorCara
from comun.estados import Estado
from comun.protocolo import Mensaje, codificar, decodificar


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


def test_sobrevive_a_un_error_recuperable_en_accept(monkeypatch):
    """accept() puede lanzar OSError por causas recuperables (ECONNABORTED,
    EMFILE/ENFILE en la Pi) sin que sea la señal de que detener() cerró el
    socket. El servidor debe registrar el error y seguir escuchando."""
    accept_original = socket.socket.accept
    llamadas = {"n": 0}

    def accept_con_un_fallo(self):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise OSError(errno.ECONNABORTED, "conexión abortada (simulado)")
        return accept_original(self)

    monkeypatch.setattr(socket.socket, "accept", accept_con_un_fallo)

    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        assert _esperar(lambda: llamadas["n"] >= 1)
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(codificar(Mensaje(Estado.ESCUCHANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.ESCUCHANDO
            )
    finally:
        servidor.detener()


def test_una_excepcion_no_esperada_al_decodificar_no_tumba_el_servidor(monkeypatch):
    """decodificar() se documenta lanzando ValueError, pero cosas como un
    JSON demasiado anidado producen RecursionError. Cualquier excepción al
    procesar una línea debe descartarse sin matar el hilo del servidor."""

    def decodificar_que_a_veces_explota(linea):
        if linea == b"explota":
            raise RecursionError("simulación de json.loads muy anidado")
        return decodificar(linea)

    monkeypatch.setattr(
        "cara.servidor.decodificar", decodificar_que_a_veces_explota
    )

    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(b"explota\n")
            sock.sendall(codificar(Mensaje(Estado.HABLANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.HABLANDO
            )
    finally:
        servidor.detener()


def test_flujo_sin_salto_de_linea_se_descarta_al_superar_el_limite():
    """Un par que nunca manda un salto de línea (un `asistente` roto, o
    cualquier proceso que se conecte al puerto por error) no debe poder
    agotar la RAM de la Pi. Al superar el tope se descarta la conexión y
    el servidor sigue vivo para aceptar la siguiente."""
    from cara.servidor import TAM_MAXIMO_BUFFER

    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.settimeout(0.5)
            sock.sendall(b"x" * (TAM_MAXIMO_BUFFER + 4096 * 3))

            def _conexion_cerrada():
                try:
                    return sock.recv(1) == b""
                except socket.timeout:
                    return False
                except OSError:
                    return True

            assert _esperar(_conexion_cerrada)

        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock2:
            sock2.sendall(codificar(Mensaje(Estado.ESCUCHANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.ESCUCHANDO
            )
    finally:
        servidor.detener()
