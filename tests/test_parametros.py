from cara.parametros import Parametros, interpolar


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
