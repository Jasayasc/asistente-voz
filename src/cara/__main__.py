import sys
import time

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

        actual = interpolar(actual, objetivo, SUAVIZADO)
        renderizador.dibujar(pantalla, actual)
        pygame.display.flip()

    servidor.detener()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
