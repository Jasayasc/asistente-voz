import sys

import pygame

from asistente.config import Config
from cara.expresiones import Comportamiento
from cara.lipsync import Lipsync
from cara.parametros import Parametros, factor_por_dt, interpolar
from cara.reacciones import aplicar as aplicar_reaccion
from cara.reacciones import temblor
from cara.renderizador import Renderizador
from cara.servidor import ServidorCara
from cara.tacto import Tacto
from comun.estados import Estado

FPS = 60
SUAVIZADO = 0.15


def _componer_frame(
    actual: Parametros, objetivo: Parametros, factor: float
) -> Parametros:
    """Un frame de la animación: suaviza todo salvo la boca.

    `objetivo.boca` ya viene de `Lipsync.procesar`/`reposar`, que aplica su
    propio ataque rápido / liberación lenta (ver `cara/lipsync.py`). Pasarla
    otra vez por `interpolar` encadena un segundo filtro de primer orden
    sobre el primero: el ataque de 0.5 queda gobernado por el 0.15 genérico,
    y una sílaba corta abre la boca a una fracción de la amplitud que debía.
    Por eso la boca se asigna después de interpolar, sin pasar por el
    factor genérico, mientras el resto de parámetros sí lo hace.
    """
    resultado = interpolar(actual, objetivo, factor)
    resultado.boca = objetivo.boca
    return resultado


def _normalizar(pos: tuple[int, int], tamano: tuple[int, int]) -> tuple[float, float]:
    """Pasa una posicion en pixeles a coordenadas 0..1 de la ventana.

    Los eventos tactiles de SDL ya llegan normalizados; los del raton, en
    pixeles. Se unifican aqui para que `Tacto` no tenga que saber de cual
    de los dos viene cada gesto.
    """
    ancho, alto = tamano
    return (
        pos[0] / ancho if ancho else 0.0,
        pos[1] / alto if alto else 0.0,
    )


def _atender_evento(evento, tacto: Tacto, tamano: tuple[int, int]) -> bool:
    """Traduce un evento de pygame a un gesto. Devuelve si hay que seguir.

    En una pantalla tactil, SDL entrega el gesto DOS veces: como evento de
    dedo y, ademas, como un evento de raton sintetico para que las
    aplicaciones que solo saben de raton funcionen. Contar los dos haria
    que cada caricia recorriese el doble de distancia y que cada golpe
    valiera por dos. Por eso se descartan los eventos de raton que pygame
    marca con `touch=True`: en la Raspberry Pi mandan los eventos de dedo,
    y en el ordenador de desarrollo, los del raton.
    """
    if evento.type == pygame.QUIT:
        return False
    if evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
        return False

    if evento.type == pygame.FINGERDOWN:
        tacto.pulsar(evento.x, evento.y, evento.finger_id)
    elif evento.type == pygame.FINGERMOTION:
        tacto.mover(evento.x, evento.y, evento.finger_id)
    elif evento.type == pygame.FINGERUP:
        tacto.soltar(evento.x, evento.y, evento.finger_id)
    elif not getattr(evento, "touch", False):
        if evento.type == pygame.MOUSEBUTTONDOWN:
            tacto.pulsar(*_normalizar(evento.pos, tamano))
        elif evento.type == pygame.MOUSEMOTION:
            tacto.mover(*_normalizar(evento.pos, tamano))
        elif evento.type == pygame.MOUSEBUTTONUP:
            tacto.soltar(*_normalizar(evento.pos, tamano))
    return True


def main() -> int:
    cfg = Config.cargar()

    servidor = ServidorCara(cfg.host_cara, cfg.puerto_cara)
    servidor.iniciar()
    print(f"cara escuchando en {cfg.host_cara}:{servidor.puerto}")

    pygame.init()
    pygame.display.set_caption("asistente")
    banderas = pygame.FULLSCREEN if cfg.pantalla_completa else 0
    pantalla = pygame.display.set_mode((cfg.ancho, cfg.alto), banderas)
    reloj = pygame.time.Clock()

    renderizador = Renderizador(*pantalla.get_size())
    comportamiento = Comportamiento()
    lipsync = Lipsync()
    tacto = Tacto()
    actual = Parametros()

    corriendo = True
    while corriendo:
        dt = reloj.tick(FPS) / 1000.0

        tamano = pantalla.get_size()
        for evento in pygame.event.get():
            if not _atender_evento(evento, tacto, tamano):
                corriendo = False

        tacto.actualizar(dt)
        mensaje = servidor.estado_actual()
        objetivo = comportamiento.actualizar(mensaje.estado, dt)

        hablando = mensaje.estado is Estado.HABLANDO
        if hablando:
            objetivo.boca = lipsync.procesar(mensaje.rms)
        else:
            objetivo.boca = lipsync.reposar()

        # La reaccion tactil se pinta ENCIMA de la expresion del estado, no
        # en lugar de ella: se puede estar pensando y tener cosquillas a la
        # vez. Mientras habla, la boca la sigue gobernando el lipsync.
        objetivo = aplicar_reaccion(objetivo, tacto, mueve_la_boca=not hablando)

        actual = _componer_frame(actual, objetivo, factor_por_dt(SUAVIZADO, dt))
        renderizador.dibujar(pantalla, actual, temblor(tacto))
        pygame.display.flip()

    servidor.detener()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
