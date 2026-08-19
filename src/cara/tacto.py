# src/cara/tacto.py
"""Qué le está haciendo la mano a la cara.

En la Raspberry Pi la pantalla es táctil y en el ordenador de desarrollo
hay un ratón, pero los dos producen lo mismo: un punto que se apoya, se
mueve y se levanta. Este módulo no sabe nada de pygame ni de SDL —recibe
esos tres verbos ya normalizados— y a cambio se puede probar entero sin
abrir una ventana.

Todo el tiempo entra por `actualizar(dt)`, nunca de un reloj de pared. Eso
hace que los gestos sean deterministas en los tests y, de paso, que la
detección no dependa del framerate: una caricia se reconoce igual a los
60 fps del portátil que a los 20 de la Raspberry Pi.

La distinción que importa es entre acariciar y golpear, y sale de dos
medidas que no se parecen en nada:

- Una **caricia** recorre distancia con el dedo apoyado. Es larga en
  espacio, y da igual cuánto dure.
- Un **golpe** es corto en tiempo y no recorre nada: el dedo baja y sube
  casi en el mismo sitio. Uno suelto es solo un toque —sorprende—; varios
  seguidos ya son alguien insistiendo, y ahí es donde la cara se molesta.
"""
from enum import Enum
from math import hypot

# Todas las distancias son fracciones del lado de la pantalla, igual que en
# el renderizador: así los gestos se sienten iguales en la pantalla de cinco
# pulgadas de la Pi y en el monitor de desarrollo.
DISTANCIA_CARICIA = 0.22      # recorrido necesario para dar cosquillas
DURACION_TOQUE_MAX = 0.25     # segundos; más que esto ya no es un golpe seco
DISTANCIA_TOQUE_MAX = 0.04    # si se mueve más que esto, no es un golpe
VENTANA_GOLPES = 1.5          # segundos dentro de los que los toques cuentan
TOQUES_PARA_MOLESTIA = 2      # el primero sorprende; el segundo ya molesta

DURACION_COSQUILLAS = 1.4
DURACION_MOLESTIA = 2.5
DURACION_SORPRESA = 0.9


class Reaccion(str, Enum):
    """Lo que la cara está sintiendo ahora mismo."""

    ATENCION = "atencion"      # hay un dedo apoyado: lo sigue con la mirada
    SORPRESA = "sorpresa"      # un toque suelto
    COSQUILLAS = "cosquillas"  # el dedo recorre la cara
    MOLESTIA = "molestia"      # varios golpes seguidos


# Una reacción solo puede pisar a otra igual o menos importante. Sin esto,
# el `soltar()` del final de una caricia —que visto de cerca es un toque
# cortito, porque el dedo apenas se movió en ese último instante— borraría
# las cosquillas justo cuando empiezan.
PRIORIDAD = {
    Reaccion.ATENCION: 0,
    Reaccion.SORPRESA: 1,
    Reaccion.COSQUILLAS: 2,
    Reaccion.MOLESTIA: 3,
}

DURACIONES = {
    Reaccion.ATENCION: 0.0,  # dura lo que dure el dedo apoyado
    Reaccion.SORPRESA: DURACION_SORPRESA,
    Reaccion.COSQUILLAS: DURACION_COSQUILLAS,
    Reaccion.MOLESTIA: DURACION_MOLESTIA,
}


class Tacto:
    """Traduce apoyar, mover y levantar el dedo en reacciones de la cara."""

    def __init__(self) -> None:
        self.tiempo = 0.0
        self._pulsado = False
        self._punto = (0.5, 0.5)
        self._ultimo = (0.5, 0.5)
        self._inicio_pulsacion = 0.0
        self._recorrido = 0.0
        self._recorrido_total = 0.0
        self._dedo: object | None = None
        self._golpes: list[float] = []
        self._reaccion: Reaccion | None = None
        self._restante = 0.0
        self._duracion = 0.0

    # --- Lo que llega de la pantalla --------------------------------------

    def pulsar(self, x: float, y: float, dedo: object | None = None) -> None:
        """Un dedo (o el botón del ratón) se apoya en la pantalla.

        `dedo` identifica cuál, y solo lo usa la pantalla táctil. La de la
        Raspberry Pi es multitáctil: apoyar un segundo dedo manda otro
        evento, y sin distinguirlos el punto saltaría de golpe de uno a
        otro. Ese salto se contabilizaría como recorrido y bastaría con
        posar dos dedos separados para disparar unas cosquillas que nadie
        ha hecho. Manda el primero que llega hasta que se levanta.
        """
        if self._pulsado and dedo != self._dedo:
            return
        self._dedo = dedo
        self._pulsado = True
        self._punto = (x, y)
        self._ultimo = (x, y)
        self._inicio_pulsacion = self.tiempo
        self._recorrido = 0.0
        self._recorrido_total = 0.0
        self._emitir(Reaccion.ATENCION)

    def mover(self, x: float, y: float, dedo: object | None = None) -> None:
        # Un ratón manda MOUSEMOTION también con el botón suelto. Pasar el
        # puntero por encima no es tocar a nadie.
        if not self._pulsado or dedo != self._dedo:
            return
        avance = hypot(x - self._ultimo[0], y - self._ultimo[1])
        self._ultimo = (x, y)
        self._punto = (x, y)
        self._recorrido += avance
        self._recorrido_total += avance

        # Cada tramo completo de caricia renueva las cosquillas: mientras la
        # mano siga recorriendo la cara, la risa no se apaga. Se descuenta el
        # tramo en vez de poner el contador a cero para no perder el sobrante
        # y que acariciar despacio tarde de más en volver a contar.
        while self._recorrido >= DISTANCIA_CARICIA:
            self._recorrido -= DISTANCIA_CARICIA
            self._emitir(Reaccion.COSQUILLAS)

    def soltar(self, x: float, y: float, dedo: object | None = None) -> None:
        if not self._pulsado or dedo != self._dedo:
            return
        self._pulsado = False
        self._dedo = None
        self._punto = (x, y)
        duracion = self.tiempo - self._inicio_pulsacion

        if (
            duracion <= DURACION_TOQUE_MAX
            and self._recorrido_total <= DISTANCIA_TOQUE_MAX
        ):
            self._contar_golpe()
        elif self._reaccion is Reaccion.ATENCION:
            # Estuvo el dedo apoyado un rato sin llegar a acariciar: al
            # levantarlo ya no queda nada que mirar.
            self._reaccion = None
            self._restante = 0.0

    def _contar_golpe(self) -> None:
        self._golpes = [
            momento
            for momento in self._golpes
            if self.tiempo - momento <= VENTANA_GOLPES
        ]
        self._golpes.append(self.tiempo)
        if len(self._golpes) >= TOQUES_PARA_MOLESTIA:
            self._emitir(Reaccion.MOLESTIA)
        else:
            self._emitir(Reaccion.SORPRESA)

    # --- Lo que consulta el bucle de render -------------------------------

    def actualizar(self, dt: float) -> None:
        self.tiempo += dt
        if self._reaccion is None:
            return
        if self._reaccion is Reaccion.ATENCION:
            # No caduca sola: dura lo que dure el dedo encima.
            if not self._pulsado:
                self._reaccion = None
            return
        self._restante -= dt
        if self._restante > 0.0:
            return
        # Al apagarse una reacción, si el dedo sigue apoyado la cara vuelve a
        # mirarlo en vez de quedarse indiferente.
        self._reaccion = Reaccion.ATENCION if self._pulsado else None
        self._restante = 0.0

    @property
    def reaccion(self) -> Reaccion | None:
        return self._reaccion

    @property
    def punto(self) -> tuple[float, float]:
        """Dónde está (o estuvo) el dedo, en coordenadas de pantalla 0..1."""
        return self._punto

    @property
    def intensidad(self) -> float:
        """1.0 recién sentida, 0.0 cuando se apaga.

        Sirve para que la reacción se desvanezca sola en vez de cortarse de
        golpe. ATENCION no decae: mientras el dedo esté ahí, está ahí.
        """
        if self._reaccion is None:
            return 0.0
        if self._reaccion is Reaccion.ATENCION:
            return 1.0
        if self._duracion <= 0.0:
            return 0.0
        return max(0.0, min(1.0, self._restante / self._duracion))

    @property
    def enfado(self) -> float:
        """Cuánto se ha insistido, de 0.0 a 1.0.

        Dos golpes molestan; a partir de ahí, cada uno más dentro de la
        misma ventana pone la cara un poco peor.
        """
        de_mas = max(0, len(self._golpes) - TOQUES_PARA_MOLESTIA)
        return min(1.0, 0.5 + 0.25 * de_mas)

    def _emitir(self, reaccion: Reaccion) -> None:
        if (
            self._reaccion is not None
            and self._restante > 0.0
            and PRIORIDAD[reaccion] < PRIORIDAD[self._reaccion]
        ):
            return
        self._reaccion = reaccion
        self._duracion = DURACIONES[reaccion]
        self._restante = self._duracion
