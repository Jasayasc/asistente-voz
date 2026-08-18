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


def test_el_silencio_inicial_no_termina_antes_de_su_propio_tope():
    """Si el usuario aún no ha empezado a hablar, no cierra antes de
    `segundos_sin_voz` (el tope corto del falso positivo; ver el test de
    abajo para el caso en que sí se alcanza)."""
    vad = DetectorSilencio(segundos_silencio=0.5, segundos_sin_voz=5.0)
    for _ in range(50):  # 4.0 s: menos que los 5.0 s de segundos_sin_voz
        assert vad.procesar(bloque_silencio()) is False


def test_falso_positivo_corta_pronto_por_su_propio_tope_sin_voz():
    """Un falso positivo del wake word (nadie habla) debe volver a reposo
    tras `segundos_sin_voz`, mucho antes que `maximo_segundos`: si no, el
    detector de palabra clave queda sin ejecutarse —el asistente sordo a su
    propio nombre— durante toda la ventana larga."""
    vad = DetectorSilencio(segundos_sin_voz=0.5, maximo_segundos=12.0)
    terminado = False
    bloques_usados = 0
    for _ in range(50):
        bloques_usados += 1
        if vad.procesar(bloque_silencio()):
            terminado = True
            break
    assert terminado
    assert vad.hubo_voz is False
    # 0.5 s / 0.08 s por bloque ≈ 6 bloques; muy por debajo de los ~150
    # bloques que tomarían los 12 s de maximo_segundos.
    assert bloques_usados <= 8


def test_falso_positivo_usa_el_valor_por_defecto_de_unos_tres_segundos():
    """El tope corto por defecto ronda los ~3 s que pide el diseño, no los
    12 s de `maximo_segundos`."""
    vad = DetectorSilencio()
    terminado = False
    bloques_usados = 0
    for _ in range(60):
        bloques_usados += 1
        if vad.procesar(bloque_silencio()):
            terminado = True
            break
    assert terminado
    assert vad.hubo_voz is False
    assert bloques_usados <= 40  # ~3.0 s; el tope de 12 s son ~150 bloques


def test_intervencion_larga_con_voz_sigue_usando_el_tope_largo():
    """Una intervención genuina y larga (hay voz real) no debe cortarse por
    el tope corto de "nadie ha dicho nada todavía": sigue rigiéndose por
    `maximo_segundos`, no por `segundos_sin_voz`."""
    vad = DetectorSilencio(segundos_sin_voz=0.5, maximo_segundos=2.0)
    # `maximo_segundos` cuenta desde que hay voz, y la voz se da por
    # empezada al segundo bloque seguido con energia: el primero solo
    # arranca la cuenta. Por eso el tope llega un bloque mas tarde que los
    # 2.0 s de escucha.
    for _ in range(_en_bloques(2.0)):
        assert vad.procesar(bloque_voz()) is False
    assert vad.procesar(bloque_voz()) is True


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
    # bloques_para_voz=1 aisla lo que prueba este test —la comparacion
    # de energia contra el umbral— del numero de bloques seguidos que
    # exige el valor por defecto.
    vad = DetectorSilencio(umbral=0.02, bloques_para_voz=1)
    bloque_alto = bloque_amplitud(656)
    vad.procesar(bloque_alto)
    # Debe haber detectado voz
    assert vad.hubo_voz is True


def test_umbral_claramente_por_encima():
    """Energía claramente encima del umbral cuenta como voz."""
    # Amplitud 657 da RMS ≈ 0.02005 (más claramente encima)
    vad = DetectorSilencio(umbral=0.02, bloques_para_voz=1)
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

    # bloques_para_voz=1 aísla la comparación de energía, que es lo que
    # prueba este test, del número de bloques seguidos que exige el valor
    # por defecto.
    vad = DetectorSilencio(umbral=umbral_exacto, bloques_para_voz=1)
    bloque_frontera = bloque_amplitud(amplitud)

    # La energía será exactamente igual al umbral
    # Con >= cuenta como voz; con > no contaría
    vad.procesar(bloque_frontera)
    assert vad.hubo_voz is True


# --- Espera configurable por intervención (modo conversación) -------------


def _en_bloques(segundos):
    """Misma conversión que usa DetectorSilencio.

    `int(x + 0.5)` y `round(x)` NO son lo mismo: round() aplica redondeo
    bancario, y con 1,0 s (12,5 bloques exactos) devuelve 12 en vez de 13.
    Calcular aquí lo esperado con otra fórmula que la del código haría
    fallar el test por un bloque sin que hubiera nada roto.
    """
    return max(1, int(segundos / SEGUNDOS_POR_BLOQUE + 0.5))


def _bloques_hasta_cortar(vad, hacer_bloque):
    """Cuántos bloques hacen falta hasta que el VAD dice "se acabó"."""
    n = 0
    while True:
        n += 1
        if vad.procesar(hacer_bloque()):
            return n


def test_reiniciar_sin_argumentos_mantiene_la_espera_de_siempre():
    """Control negativo: quien llame como antes debe ver lo de antes."""
    vad = DetectorSilencio(segundos_sin_voz=1.0, maximo_segundos=30.0)
    vad.reiniciar()
    esperados = _en_bloques(1.0)
    assert _bloques_hasta_cortar(vad, bloque_silencio) == esperados


def test_reiniciar_puede_alargar_la_espera_de_esta_intervencion():
    """El modo conversación necesita esperar mucho más entre turnos que
    tras la palabra clave: allí el silencio es un falso positivo, aquí es
    alguien pensando qué preguntar."""
    vad = DetectorSilencio(segundos_sin_voz=1.0, maximo_segundos=30.0)
    vad.reiniciar(segundos_sin_voz=4.0)
    esperados = _en_bloques(4.0)
    assert _bloques_hasta_cortar(vad, bloque_silencio) == esperados


def test_la_espera_alargada_dura_solo_esa_intervencion():
    """No se queda pegada: el turno siguiente vuelve al valor de fábrica si
    nadie pide otra cosa."""
    vad = DetectorSilencio(segundos_sin_voz=1.0, maximo_segundos=30.0)
    vad.reiniciar(segundos_sin_voz=4.0)
    vad.reiniciar()
    esperados = _en_bloques(1.0)
    assert _bloques_hasta_cortar(vad, bloque_silencio) == esperados


def test_la_espera_alargada_no_afecta_al_corte_tras_hablar():
    """Solo alarga la paciencia con el silencio INICIAL. Una vez que el
    usuario ha hablado, sigue cortando con `segundos_silencio`, o el
    asistente tardaría cuatro segundos en contestar a todo."""
    vad = DetectorSilencio(
        segundos_silencio=1.0, segundos_sin_voz=1.0, maximo_segundos=30.0
    )
    vad.reiniciar(segundos_sin_voz=8.0)
    # Dos bloques: la voz se da por empezada al segundo seguido con
    # energía, no al primero.
    assert not vad.procesar(bloque_voz())
    assert not vad.procesar(bloque_voz())
    assert vad.hubo_voz
    esperados = _en_bloques(1.0)
    assert _bloques_hasta_cortar(vad, bloque_silencio) == esperados
