from dataclasses import dataclass, fields, replace

# Framerate para el que están calibrados los factores de suavizado del
# proyecto. No es el framerate real: es la referencia contra la que
# `factor_por_dt` corrige.
FPS_REFERENCIA = 60.0


@dataclass
class Parametros:
    """Los seis valores que definen la cara completa.

    ojo_izq / ojo_der : 0.0 cerrado, 1.0 muy abierto
    pupila_x / pupila_y : -1.0 a 1.0, desplazamiento desde el centro
    boca : 0.0 cerrada, 1.0 muy abierta
    sonrisa : -1.0 triste, 0.0 neutra, 1.0 contenta
    """

    ojo_izq: float = 1.0
    ojo_der: float = 1.0
    pupila_x: float = 0.0
    pupila_y: float = 0.0
    boca: float = 0.0
    sonrisa: float = 0.0

    def copia(self) -> "Parametros":
        return replace(self)


def interpolar(actual: Parametros, objetivo: Parametros, factor: float) -> Parametros:
    """Acerca `actual` a `objetivo` en la proporción `factor`.

    Aplicado cada frame produce transiciones suaves sin escribir animaciones
    a mano: con factor 0.15 a 60 fps, una transición completa dura ~200 ms.

    `factor` es por frame, no por segundo. Quien llame desde un bucle de
    render debe pasarlo por `factor_por_dt` para que la animación dure lo
    mismo a cualquier framerate; ver el porqué allí.
    """
    valores = {}
    for campo in fields(actual):
        a = getattr(actual, campo.name)
        b = getattr(objetivo, campo.name)
        valores[campo.name] = a + (b - a) * factor
    return Parametros(**valores)


def factor_por_dt(
    factor_base: float, dt: float, fps_referencia: float = FPS_REFERENCIA
) -> float:
    """Corrige un factor por frame para que la animación dure lo mismo
    a cualquier framerate.

    Este era un riesgo conocido y anotado del Hito 1, aplazado hasta tener
    la Raspberry Pi delante. `interpolar` acerca la cara al objetivo un
    porcentaje FIJO en cada frame, así que la velocidad real depende de
    cuántos frames haya por segundo: los ~200 ms medidos en el portátil a
    60 fps se convierten en ~600 ms a los 20 fps de la Pi. Con la cara
    reaccionando al tacto eso ya no es un detalle estético — una caricia
    que tarda más de medio segundo en verse no se siente como respuesta al
    gesto, sino como un fallo.

    La corrección es exacta, no aproximada: aplicar `factor_base` n veces
    deja sin recorrer `(1 - factor_base) ** n` del camino, así que basta
    con resolver para el número de frames de referencia que caben en `dt`.
    De paso queda acotada por debajo de 1.0 por construcción, y un frame
    muy largo aislado —el primero tras arrancar, o un tirón del sistema— no
    puede producir un factor mayor que 1 que haga sobrepasar el objetivo y
    oscilar.
    """
    if dt <= 0.0 or factor_base <= 0.0:
        return 0.0
    if factor_base >= 1.0:
        return 1.0
    return 1.0 - (1.0 - factor_base) ** (dt * fps_referencia)
