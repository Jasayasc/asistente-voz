import random

from cara.expresiones import EXPRESIONES, Comportamiento
from comun.estados import Estado


def test_todos_los_estados_tienen_expresion():
    for estado in Estado:
        assert estado in EXPRESIONES


def test_escuchando_abre_mas_los_ojos_que_pensando():
    assert EXPRESIONES[Estado.ESCUCHANDO].ojo_izq > EXPRESIONES[Estado.PENSANDO].ojo_izq


def test_pensando_mira_hacia_arriba():
    assert EXPRESIONES[Estado.PENSANDO].pupila_y < 0


def test_error_tiene_sonrisa_negativa():
    assert EXPRESIONES[Estado.ERROR].sonrisa < 0


def test_el_parpadeo_cierra_los_ojos_en_algun_momento():
    c = Comportamiento(aleatorio=random.Random(1))
    aperturas = [c.actualizar(Estado.REPOSO, 1 / 60).ojo_izq for _ in range(60 * 20)]
    assert min(aperturas) < 0.1, "en 20 segundos debería haber parpadeado"


def test_el_parpadeo_cierra_ambos_ojos_a_la_vez():
    c = Comportamiento(aleatorio=random.Random(1))
    for _ in range(60 * 20):
        p = c.actualizar(Estado.REPOSO, 1 / 60)
        assert abs(p.ojo_izq - p.ojo_der) < 1e-9


def test_las_pupilas_derivan_en_reposo():
    c = Comportamiento(aleatorio=random.Random(2))
    posiciones = {
        (round(p.pupila_x, 3), round(p.pupila_y, 3))
        for p in (c.actualizar(Estado.REPOSO, 1 / 60) for _ in range(60 * 20))
    }
    assert len(posiciones) > 1, "las pupilas deberían moverse en reposo"


def test_las_pupilas_no_derivan_al_escuchar():
    c = Comportamiento(aleatorio=random.Random(2))
    for _ in range(60 * 20):
        p = c.actualizar(Estado.ESCUCHANDO, 1 / 60)
        assert p.pupila_x == EXPRESIONES[Estado.ESCUCHANDO].pupila_x


def test_hablando_no_fija_la_boca():
    """La boca en HABLANDO la controla el lipsync, no la expresión."""
    c = Comportamiento(aleatorio=random.Random(3))
    assert c.actualizar(Estado.HABLANDO, 1 / 60).boca == 0.0
