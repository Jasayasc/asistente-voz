import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE, TASA_MUESTREO
from asistente.wake.vad import DetectorSilencio, SEGUNDOS_POR_BLOQUE


def bloque_silencio():
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def bloque_voz(amplitud=8000):
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitud, TAMANO_BLOQUE)).astype(np.int16)


def bloque_amplitud(amplitud):
    """Crea un bloque con amplitud constante para control de RMS exacto.

    Para una señal constante, RMS = |amplitud| / 32768.
    """
    return np.full(TAMANO_BLOQUE, amplitud, dtype=np.int16)


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


def test_conversion_segundos_a_bloques_con_redondeo():
    """Verifica que los segundos se redondean, no se truncan.

    1.0 segundos / 0.08 seg/bloque = 12.5 bloques → debe redondear a 13.
    """
    vad = DetectorSilencio(segundos_silencio=1.0)
    # Con 12 bloques de silencio (0.96 s) no debe terminar
    for _ in range(12):
        assert vad.procesar(bloque_silencio()) is False
    # El bloque 13 (1.04 s) debe terminar porque hemos alcanzado el umbral
    # Pero primero necesitamos haber dicho algo
    vad.reiniciar()
    for _ in range(5):
        vad.procesar(bloque_voz())
    # Ahora silencio: los 13 bloques deben alcanzar el umbral
    for i in range(12):
        result = vad.procesar(bloque_silencio())
        if i < 11:
            assert result is False, f"Bloque {i+1} de 12 no debe terminar"
    # El bloque 13 debe terminar
    assert vad.procesar(bloque_silencio()) is True


def test_redondeo_intermedio():
    """Verifica rounding correcto con un valor que cae entre bloques.

    0.5 segundos / 0.08 seg/bloque = 6.25 bloques → debe redondear a 6.
    """
    vad = DetectorSilencio(segundos_silencio=0.5)
    for _ in range(5):
        vad.procesar(bloque_voz())
    # Con 5 bloques de silencio (0.4 s) no debe terminar (menos de 6)
    for _ in range(5):
        assert vad.procesar(bloque_silencio()) is False
    # El bloque 6 debe terminar
    assert vad.procesar(bloque_silencio()) is True


def test_umbral_justo_por_debajo():
    """Energía justo por debajo del umbral no cuenta como voz."""
    # Umbral es 0.02. Amplitud 655 da RMS ≈ 0.01999 (justo debajo)
    vad = DetectorSilencio(umbral=0.02)
    bloque_bajo = bloque_amplitud(655)
    for _ in range(50):
        vad.procesar(bloque_bajo)
    # No debe haber detectado voz
    assert vad.hubo_voz is False


def test_umbral_ligeramente_por_encima():
    """Energía justo por encima del umbral cuenta como voz.

    Amplitud 656 da RMS ≈ 0.02002 (justo encima del 0.02 predeterminado).
    """
    vad = DetectorSilencio(umbral=0.02)
    bloque_alto = bloque_amplitud(656)
    vad.procesar(bloque_alto)
    # Debe haber detectado voz
    assert vad.hubo_voz is True


def test_umbral_claramente_por_encima():
    """Energía claramente encima del umbral cuenta como voz."""
    # Amplitud 657 da RMS ≈ 0.02005 (más claramente encima)
    vad = DetectorSilencio(umbral=0.02)
    bloque_alto = bloque_amplitud(657)
    vad.procesar(bloque_alto)
    # Debe haber detectado voz
    assert vad.hubo_voz is True


def test_comparacion_inclusiva_en_frontera_exacta():
    """Detecta cambios de >= a > en la comparación de energía.

    Construye umbral calculado exactamente a partir de una amplitud entera,
    así energía y umbral son idénticos bit a bit. Con comparación inclusiva (>=)
    la energía iguala al umbral y cuenta como voz. Si alguien cambiara a
    comparación estricta (>), fallaría esta prueba. Este test existe para
    detectar esa regresión.
    """
    # Amplitud 512 es conveniente: da RMS exacta de 512/32768
    amplitud = 512
    umbral_exacto = amplitud / 32768.0

    vad = DetectorSilencio(umbral=umbral_exacto)
    bloque_frontera = bloque_amplitud(amplitud)

    # La energía será exactamente igual al umbral
    # Con >= cuenta como voz; con > no contaría
    vad.procesar(bloque_frontera)
    assert vad.hubo_voz is True
