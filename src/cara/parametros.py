from dataclasses import dataclass, fields, replace

CAMPOS = ("ojo_izq", "ojo_der", "pupila_x", "pupila_y", "boca", "sonrisa")


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
    """
    valores = {}
    for campo in fields(actual):
        a = getattr(actual, campo.name)
        b = getattr(objetivo, campo.name)
        valores[campo.name] = a + (b - a) * factor
    return Parametros(**valores)
