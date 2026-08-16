import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE
from asistente.wake.vad import DetectorSilencio


def bloque_silencio():
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def bloque_voz(amplitud=8000):
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitud, TAMANO_BLOQUE)).astype(np.int16)


def test_el_silencio_inicial_no_termina_la_intervencion():
    """Si el usuario aún no ha empezado a hablar, no hay nada que cerrar."""
    vad = DetectorSilencio(segundos_silencio=0.5)
    for _ in range(50):
        assert vad.procesar(bloque_silencio()) is False


def test_termina_tras_hablar_y_callar():
    vad = DetectorSilencio(segundos_silencio=0.5)
    for _ in range(10):
        assert vad.procesar(bloque_voz()) is False
    terminado = False
    for _ in range(30):
        if vad.procesar(bloque_silencio()):
            terminado = True
            break
    assert terminado


def test_una_pausa_corta_no_termina_la_intervencion():
    vad = DetectorSilencio(segundos_silencio=1.0)
    for _ in range(10):
        vad.procesar(bloque_voz())
    for _ in range(5):  # 400 ms de pausa: menos que el umbral
        assert vad.procesar(bloque_silencio()) is False
    for _ in range(5):
        assert vad.procesar(bloque_voz()) is False


def test_hubo_voz_es_falso_si_solo_hubo_silencio():
    """Distingue un falso positivo del wake word de una pregunta real."""
    vad = DetectorSilencio()
    for _ in range(20):
        vad.procesar(bloque_silencio())
    assert vad.hubo_voz is False


def test_hubo_voz_es_verdadero_tras_hablar():
    vad = DetectorSilencio()
    for _ in range(10):
        vad.procesar(bloque_voz())
    assert vad.hubo_voz is True


def test_corta_al_llegar_al_maximo():
    """Si alguien habla sin parar, hay que cortar en algún momento."""
    vad = DetectorSilencio(maximo_segundos=1.0)
    terminado = False
    for _ in range(100):
        if vad.procesar(bloque_voz()):
            terminado = True
            break
    assert terminado


def test_reiniciar_limpia_el_estado():
    vad = DetectorSilencio()
    for _ in range(10):
        vad.procesar(bloque_voz())
    vad.reiniciar()
    assert vad.hubo_voz is False
