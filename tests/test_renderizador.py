import pygame
import pytest

from cara.parametros import Parametros
from cara.renderizador import Renderizador


@pytest.fixture(scope="module", autouse=True)
def pygame_headless():
    import os

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    yield
    pygame.quit()


def _superficie(ancho, alto):
    return pygame.Surface((ancho, alto))


@pytest.mark.parametrize("ancho,alto", [(800, 480), (1920, 1080), (480, 800)])
def test_dibuja_sin_error_en_cualquier_resolucion(ancho, alto):
    r = Renderizador(ancho, alto)
    r.dibujar(_superficie(ancho, alto), Parametros())


def test_el_lienzo_virtual_es_cuadrado_y_cabe():
    r = Renderizador(1920, 1080)
    assert r.lado == 1080
    r2 = Renderizador(480, 800)
    assert r2.lado == 480


def test_el_lienzo_esta_centrado():
    r = Renderizador(1920, 1080)
    assert r.origen_x == (1920 - 1080) // 2
    assert r.origen_y == 0


def test_los_ojos_cerrados_pintan_menos_que_los_abiertos():
    """Comprobación indirecta pero real: con los ojos cerrados hay menos
    píxeles no-fondo que con los ojos abiertos."""
    r = Renderizador(400, 400)

    abierta = _superficie(400, 400)
    r.dibujar(abierta, Parametros(ojo_izq=1.0, ojo_der=1.0))

    cerrada = _superficie(400, 400)
    r.dibujar(cerrada, Parametros(ojo_izq=0.0, ojo_der=0.0))

    def no_fondo(sup):
        fondo = sup.get_at((0, 0))
        return sum(
            1
            for x in range(0, 400, 4)
            for y in range(0, 400, 4)
            if sup.get_at((x, y)) != fondo
        )

    assert no_fondo(abierta) > no_fondo(cerrada)


def test_la_boca_abierta_pinta_mas_que_la_cerrada():
    r = Renderizador(400, 400)

    abierta = _superficie(400, 400)
    r.dibujar(abierta, Parametros(ojo_izq=0.0, ojo_der=0.0, boca=1.0))

    cerrada = _superficie(400, 400)
    r.dibujar(cerrada, Parametros(ojo_izq=0.0, ojo_der=0.0, boca=0.0))

    def no_fondo(sup):
        fondo = sup.get_at((0, 0))
        return sum(
            1
            for x in range(0, 400, 4)
            for y in range(0, 400, 4)
            if sup.get_at((x, y)) != fondo
        )

    assert no_fondo(abierta) > no_fondo(cerrada)
