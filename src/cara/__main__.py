import sys

import pygame

from asistente.config import Config
from cara.expresiones import Comportamiento
from cara.lipsync import Lipsync
from cara.parametros import Parametros, interpolar
from cara.renderizador import Renderizador
from cara.servidor import ServidorCara
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
    actual = Parametros()

    corriendo = True
    while corriendo:
        dt = reloj.tick(FPS) / 1000.0

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False
            elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                corriendo = False

        mensaje = servidor.estado_actual()
        objetivo = comportamiento.actualizar(mensaje.estado, dt)

        if mensaje.estado is Estado.HABLANDO:
            objetivo.boca = lipsync.procesar(mensaje.rms)
        else:
            objetivo.boca = lipsync.reposar()

        actual = _componer_frame(actual, objetivo, SUAVIZADO)
        renderizador.dibujar(pantalla, actual)
        pygame.display.flip()

    servidor.detener()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
