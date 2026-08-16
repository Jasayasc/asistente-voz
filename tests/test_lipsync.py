# tests/test_lipsync.py
from cara.lipsync import Lipsync


def test_silencio_mantiene_la_boca_cerrada():
    ls = Lipsync()
    for _ in range(50):
        assert ls.procesar(0.0) == 0.0


def test_la_boca_se_abre_con_audio():
    ls = Lipsync()
    for _ in range(10):
        apertura = ls.procesar(0.5)
    assert apertura > 0.3


def test_la_apertura_nunca_sale_del_rango():
    ls = Lipsync()
    for valor in (0.0, 0.1, 5.0, 100.0, 0.3):
        for _ in range(20):
            apertura = ls.procesar(valor)
            assert 0.0 <= apertura <= 1.0


def test_normaliza_voz_suave_y_voz_fuerte_por_igual():
    """Una voz suave sostenida debe acabar abriendo la boca tanto como una
    fuerte: el máximo móvil se adapta al nivel de la señal."""
    suave = Lipsync()
    fuerte = Lipsync()
    for _ in range(60):
        a_suave = suave.procesar(0.05)
        a_fuerte = fuerte.procesar(0.9)
    assert abs(a_suave - a_fuerte) < 0.2


def test_abre_mas_rapido_de_lo_que_cierra():
    """Ataque rápido, liberación lenta. Es lo que separa 'parece que habla'
    de 'parece que tiembla'."""
    ls = Lipsync()
    for _ in range(30):
        ls.procesar(0.8)
    pico = ls.procesar(0.8)

    apertura = pico
    pasos_para_cerrar = 0
    while apertura > pico / 2 and pasos_para_cerrar < 500:
        apertura = ls.procesar(0.0)
        pasos_para_cerrar += 1

    subida = Lipsync()
    pasos_para_abrir = 0
    apertura = 0.0
    while apertura < pico / 2 and pasos_para_abrir < 500:
        apertura = subida.procesar(0.8)
        pasos_para_abrir += 1

    assert pasos_para_abrir < pasos_para_cerrar


def test_reposar_cierra_la_boca():
    ls = Lipsync()
    for _ in range(30):
        ls.procesar(0.8)
    for _ in range(200):
        apertura = ls.reposar()
    assert apertura < 0.05
