import random

from cara.parametros import Parametros
from comun.estados import Estado

EXPRESIONES: dict[Estado, Parametros] = {
    Estado.REPOSO: Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.15),
    Estado.ESCUCHANDO: Parametros(ojo_izq=1.0, ojo_der=1.0, sonrisa=0.30),
    Estado.PENSANDO: Parametros(
        ojo_izq=0.6, ojo_der=0.6, pupila_x=-0.5, pupila_y=-0.6, sonrisa=0.0
    ),
    Estado.HABLANDO: Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.20),
    Estado.ERROR: Parametros(ojo_izq=0.5, ojo_der=0.5, sonrisa=-0.30),
}

# Estados en los que la cara se comporta de forma "ociosa": parpadeo normal
# y pupilas que se mueven solas. Sin esto la cara parece congelada.
ESTADOS_OCIOSOS = {Estado.REPOSO}

DURACION_PARPADEO = 0.12       # segundos que tarda el ciclo completo
INTERVALO_PARPADEO = (3.0, 6.0)
INTERVALO_PARPADEO_LENTO = (7.0, 12.0)  # en PENSANDO: se lee como concentración
INTERVALO_DERIVA = (2.0, 5.0)
RADIO_DERIVA = 0.25


class Comportamiento:
    """Añade vida a la expresión base: parpadeo y deriva de pupilas.

    Mantiene estado entre frames, así que hay una única instancia viva
    durante toda la ejecución del proceso `cara`.
    """

    def __init__(self, aleatorio: random.Random | None = None) -> None:
        self._az = aleatorio or random.Random()
        self._t_parpadeo = self._az.uniform(*INTERVALO_PARPADEO)
        self._parpadeando = 0.0
        self._t_deriva = self._az.uniform(*INTERVALO_DERIVA)
        self._deriva = (0.0, 0.0)

    def actualizar(self, estado: Estado, dt: float) -> Parametros:
        base = EXPRESIONES[estado].copia()
        self._avanzar_parpadeo(estado, dt)
        self._avanzar_deriva(estado, dt)

        if self._parpadeando > 0.0:
            factor = self._factor_parpadeo()
            base.ojo_izq *= factor
            base.ojo_der *= factor

        if estado in ESTADOS_OCIOSOS:
            base.pupila_x += self._deriva[0]
            base.pupila_y += self._deriva[1]

        return base

    def _avanzar_parpadeo(self, estado: Estado, dt: float) -> None:
        if self._parpadeando > 0.0:
            self._parpadeando = max(0.0, self._parpadeando - dt)
            return

        self._t_parpadeo -= dt
        if self._t_parpadeo <= 0.0:
            self._parpadeando = DURACION_PARPADEO
            intervalo = (
                INTERVALO_PARPADEO_LENTO
                if estado is Estado.PENSANDO
                else INTERVALO_PARPADEO
            )
            self._t_parpadeo = self._az.uniform(*intervalo)

    def _factor_parpadeo(self) -> float:
        """0.0 en mitad del parpadeo, 1.0 en los extremos. Triangular."""
        mitad = DURACION_PARPADEO / 2
        distancia = abs(self._parpadeando - mitad)
        return distancia / mitad

    def _avanzar_deriva(self, estado: Estado, dt: float) -> None:
        if estado not in ESTADOS_OCIOSOS:
            self._deriva = (0.0, 0.0)
            return
        self._t_deriva -= dt
        if self._t_deriva <= 0.0:
            self._deriva = (
                self._az.uniform(-RADIO_DERIVA, RADIO_DERIVA),
                self._az.uniform(-RADIO_DERIVA, RADIO_DERIVA),
            )
            self._t_deriva = self._az.uniform(*INTERVALO_DERIVA)
