import pytest

from cara.parametros import Parametros, factor_por_dt, interpolar


def test_valores_predeterminados_son_cara_neutra():
    p = Parametros()
    assert p.ojo_izq == 1.0
    assert p.ojo_der == 1.0
    assert p.pupila_x == 0.0
    assert p.pupila_y == 0.0
    assert p.boca == 0.0
    assert p.sonrisa == 0.0


def test_interpolar_se_acerca_al_objetivo():
    actual = Parametros(ojo_izq=0.0)
    objetivo = Parametros(ojo_izq=1.0)
    resultado = interpolar(actual, objetivo, 0.5)
    assert resultado.ojo_izq == 0.5


def test_interpolar_con_factor_uno_alcanza_el_objetivo():
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=0.8)
    assert interpolar(actual, objetivo, 1.0).boca == 0.8


def test_interpolar_no_muta_los_originales():
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=1.0)
    interpolar(actual, objetivo, 0.5)
    assert actual.boca == 0.0
    assert objetivo.boca == 1.0


def test_interpolar_converge_por_repeticion():
    actual = Parametros(sonrisa=0.0)
    objetivo = Parametros(sonrisa=1.0)
    for _ in range(60):
        actual = interpolar(actual, objetivo, 0.15)
    assert actual.sonrisa > 0.99


def test_copia_es_independiente():
    p = Parametros(boca=0.5)
    c = p.copia()
    c.boca = 0.9
    assert p.boca == 0.5


# --- Suavizado independiente del framerate --------------------------------


def test_a_sesenta_fps_el_factor_no_cambia():
    """Referencia: en el portatil, donde todo se calibro, no debe moverse
    nada."""
    assert factor_por_dt(0.15, 1 / 60) == pytest.approx(0.15)


def test_a_menos_fps_cada_frame_avanza_mas():
    """En la Raspberry Pi hay menos frames por segundo, asi que cada uno
    tiene que recorrer mas camino para que la animacion dure lo mismo."""
    assert factor_por_dt(0.15, 1 / 20) > factor_por_dt(0.15, 1 / 60)


def test_la_transicion_dura_lo_mismo_a_cualquier_framerate():
    """El test que justifica todo esto: la misma transicion, medida en
    segundos, a 60 y a 20 fps. Con el factor por frame sin corregir, a 20
    fps duraba el triple."""

    def recorrido_en(fps, segundos):
        dt = 1.0 / fps
        restante = 1.0
        for _ in range(int(fps * segundos)):
            restante *= 1.0 - factor_por_dt(0.15, dt)
        return 1.0 - restante

    assert recorrido_en(60, 0.2) == pytest.approx(recorrido_en(20, 0.2), abs=0.01)


def test_un_frame_largo_no_sobrepasa_el_objetivo():
    """El primer frame tras arrancar, o un tiron del sistema, pueden traer
    un dt enorme. Lo que no puede pasar nunca es que el factor supere 1.0:
    eso haria que la cara se pasara del objetivo y oscilara. Llegar
    exactamente a 1.0 si, y es lo correcto: tras treinta segundos parado,
    ponerse en el objetivo de golpe es justo lo que se quiere."""
    for dt in (0.5, 2.0, 30.0):
        assert 0.0 < factor_por_dt(0.15, dt) <= 1.0


def test_un_dt_de_cero_no_avanza_nada():
    assert factor_por_dt(0.15, 0.0) == 0.0
    assert factor_por_dt(0.15, -1.0) == 0.0
