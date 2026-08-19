# src/cara/reacciones.py
"""Cómo se le pone la cara al asistente cuando lo tocan.

Vive aparte de `expresiones.py` porque son dos cosas distintas: allí está
lo que la cara expresa por su cuenta (en qué estado está el asistente),
y aquí lo que le pasa por fuera. La reacción se pinta *encima* de la
expresión del estado, no en lugar de ella: si el asistente está pensando y
alguien lo acaricia, sigue pensando, pero riéndose.
"""
from math import cos, pi, sin

from cara.parametros import Parametros
from cara.renderizador import ALTURA_OJOS
from cara.tacto import Reaccion, Tacto

# Cuántas veces por segundo se abre y cierra la boca al reírse. Cinco es lo
# que suena a carcajada corta; menos parece masticar y más, un tic.
FRECUENCIA_RISA = 5.0
APERTURA_RISA = 0.55

# Cuánto giran las pupilas hacia el dedo. No es 1.0 porque una pupila
# clavada en el borde del ojo se lee como bizquera, no como mirada.
SEGUIMIENTO_PUPILA = 0.85


def _mirar_a(punto: tuple[float, float]) -> tuple[float, float]:
    """Convierte un punto de la pantalla en desplazamiento de pupila.

    Los ojos no están en el centro del lienzo sino a la altura de
    `ALTURA_OJOS`, así que el eje vertical se mide desde ahí: un dedo en la
    parte baja de la pantalla tiene que hacer que mire hacia abajo, y con
    el centro geométrico como referencia miraría casi de frente.
    """
    x, y = punto
    pupila_x = max(-1.0, min(1.0, (x - 0.5) * 2.0)) * SEGUIMIENTO_PUPILA
    pupila_y = max(-1.0, min(1.0, (y - ALTURA_OJOS) * 2.0)) * SEGUIMIENTO_PUPILA
    return pupila_x, pupila_y


def _mezclar(base: float, objetivo: float, cantidad: float) -> float:
    return base + (objetivo - base) * cantidad


def aplicar(
    base: Parametros,
    tacto: Tacto,
    mueve_la_boca: bool = True,
) -> Parametros:
    """Devuelve la expresión del estado con la reacción táctil encima.

    `mueve_la_boca` es False mientras el asistente habla: ahí la boca la
    gobierna el lipsync, y pisarla con una risa desincronizaría la voz de
    la cara. El resto de la reacción sí se ve: se puede estar contestando
    y poner cara de cosquillas a la vez.
    """
    reaccion = tacto.reaccion
    if reaccion is None:
        return base

    # `intensidad` va de 1.0 a 0.0 según se apaga la reacción, así que la
    # cara vuelve sola a su expresión de estado sin necesidad de animar
    # ninguna transición a mano.
    fuerza = tacto.intensidad
    resultado = base.copia()

    if reaccion is Reaccion.ATENCION:
        # Solo mira. Es lo mínimo para que apoyar el dedo se note.
        pupila_x, pupila_y = _mirar_a(tacto.punto)
        resultado.pupila_x = _mezclar(base.pupila_x, pupila_x, fuerza)
        resultado.pupila_y = _mezclar(base.pupila_y, pupila_y, fuerza)
        return resultado

    if reaccion is Reaccion.SORPRESA:
        # Ojos de par en par y mirada al sitio donde le han tocado.
        pupila_x, pupila_y = _mirar_a(tacto.punto)
        resultado.ojo_izq = _mezclar(base.ojo_izq, 1.0, fuerza)
        resultado.ojo_der = _mezclar(base.ojo_der, 1.0, fuerza)
        resultado.pupila_x = _mezclar(base.pupila_x, pupila_x, fuerza)
        resultado.pupila_y = _mezclar(base.pupila_y, pupila_y, fuerza)
        if mueve_la_boca:
            resultado.boca = max(base.boca, 0.35 * fuerza)
        return resultado

    if reaccion is Reaccion.COSQUILLAS:
        # Ojos apretados de risa, sonrisa al máximo y la boca abriéndose y
        # cerrándose. Los ojos se cierran a la vez que la boca se abre, que
        # es lo que hace que se lea como carcajada y no como bostezo.
        oscilacion = (1.0 - cos(2.0 * pi * FRECUENCIA_RISA * tacto.tiempo)) / 2.0
        entrecerrado = 0.30 + 0.15 * (1.0 - oscilacion)
        resultado.ojo_izq = _mezclar(base.ojo_izq, entrecerrado, fuerza)
        resultado.ojo_der = _mezclar(base.ojo_der, entrecerrado, fuerza)
        resultado.sonrisa = _mezclar(base.sonrisa, 1.0, fuerza)
        # Se ríe mirando al frente: perseguir el dedo con la pupila mientras
        # se ríe queda como recelo, no como cosquillas.
        resultado.pupila_x = _mezclar(base.pupila_x, 0.0, fuerza)
        resultado.pupila_y = _mezclar(base.pupila_y, 0.0, fuerza)
        if mueve_la_boca:
            resultado.boca = max(base.boca, APERTURA_RISA * oscilacion * fuerza)
        return resultado

    # MOLESTIA: mirada de reojo hacia quien le ha dado, ojos entornados y
    # boca hacia abajo. `enfado` sube con cada golpe de más dentro de la
    # misma ventana, así que insistir empeora la cara en vez de repetir
    # siempre el mismo gesto.
    enfado = tacto.enfado
    pupila_x, pupila_y = _mirar_a(tacto.punto)
    entornado = 0.45 - 0.15 * enfado
    resultado.ojo_izq = _mezclar(base.ojo_izq, entornado, fuerza)
    resultado.ojo_der = _mezclar(base.ojo_der, entornado, fuerza)
    resultado.sonrisa = _mezclar(base.sonrisa, -0.4 - 0.6 * enfado, fuerza)
    resultado.pupila_x = _mezclar(base.pupila_x, pupila_x, fuerza)
    resultado.pupila_y = _mezclar(base.pupila_y, pupila_y, fuerza)
    if mueve_la_boca:
        # Boca cerrada y apretada: la curva de la sonrisa negativa ya la
        # dibuja el renderizador como un arco hacia abajo.
        resultado.boca = base.boca * (1.0 - fuerza)
    return resultado


def temblor(tacto: Tacto) -> float:
    """Desplazamiento horizontal de la cara entera, para el respingo.

    Un golpe no solo cambia la expresión: mueve el aparato. Devuelve una
    fracción del lado de la pantalla, positiva o negativa, que el bucle de
    render suma a la posición de todo el dibujo. Se amortigua con la propia
    intensidad de la reacción, así que se apaga solo.
    """
    if tacto.reaccion is not Reaccion.MOLESTIA:
        return 0.0
    fuerza = tacto.intensidad
    if fuerza <= 0.0:
        return 0.0
    # Oscilación rápida (18 Hz) por la intensidad al cuadrado: da un
    # respingo seco al recibir el golpe que se disuelve en medio segundo.
    return 0.012 * fuerza * fuerza * sin(2.0 * pi * 18.0 * tacto.tiempo)
