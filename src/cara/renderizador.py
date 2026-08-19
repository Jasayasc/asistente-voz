import pygame

from cara.parametros import Parametros

FONDO = (12, 14, 20)
COLOR_OJO = (120, 220, 255)
COLOR_PUPILA = (10, 12, 18)
COLOR_BOCA = (120, 220, 255)

# Todas las medidas son fracciones del lado del lienzo virtual, para que
# el dibujo sea idéntico a cualquier resolución.
SEPARACION_OJOS = 0.20   # distancia de cada ojo al centro horizontal
ALTURA_OJOS = 0.38       # posición vertical de los ojos
RADIO_OJO = 0.13
RADIO_PUPILA = 0.055
RECORRIDO_PUPILA = 0.05  # cuánto se desplaza la pupila dentro del ojo
ALTURA_BOCA = 0.68
ANCHO_BOCA = 0.26
ALTURA_MAX_BOCA = 0.18
GROSOR_BOCA = 0.022


class Renderizador:
    """Dibuja la cara sobre un lienzo virtual cuadrado y centrado.

    Al trabajar en coordenadas normalizadas y escalar al lado del cuadrado,
    la cara mantiene proporciones correctas en cualquier pantalla: el
    monitor 16:9 de desarrollo y la DSI 5:3 de producción.
    """

    def __init__(self, ancho: int, alto: int) -> None:
        self.ancho = ancho
        self.alto = alto
        self.lado = min(ancho, alto)
        self.origen_x = (ancho - self.lado) // 2
        self.origen_y = (alto - self.lado) // 2
        # Desplazamiento temporal de la cara entera, en fraccion del lado.
        # Lo usa el respingo al recibir un golpe. Se fija al principio de
        # cada `dibujar` y no sobrevive al frame.
        self._desplazamiento = 0

    def _punto(self, x: float, y: float) -> tuple[int, int]:
        """Convierte coordenadas normalizadas (0..1) a píxeles de pantalla."""
        return (
            self.origen_x + self._desplazamiento + int(x * self.lado),
            self.origen_y + int(y * self.lado),
        )

    def _escala(self, valor: float) -> int:
        return max(1, int(valor * self.lado))

    def dibujar(
        self,
        superficie: pygame.Surface,
        p: Parametros,
        desplazamiento_x: float = 0.0,
    ) -> None:
        """Pinta la cara. `desplazamiento_x` la corre en horizontal.

        Se expresa como fraccion del lado, igual que el resto de medidas de
        este modulo, para que el respingo se vea igual en la pantalla de la
        Raspberry Pi que en el monitor de desarrollo.
        """
        self._desplazamiento = int(desplazamiento_x * self.lado)
        superficie.fill(FONDO)
        self._dibujar_ojo(superficie, 0.5 - SEPARACION_OJOS, p.ojo_izq, p)
        self._dibujar_ojo(superficie, 0.5 + SEPARACION_OJOS, p.ojo_der, p)
        self._dibujar_boca(superficie, p)

    def _dibujar_ojo(
        self, superficie: pygame.Surface, cx: float, apertura: float, p: Parametros
    ) -> None:
        radio = self._escala(RADIO_OJO)
        alto_ojo = max(2, int(radio * 2 * max(0.04, apertura)))
        centro = self._punto(cx, ALTURA_OJOS)

        rect = pygame.Rect(0, 0, radio * 2, alto_ojo)
        rect.center = centro
        pygame.draw.ellipse(superficie, COLOR_OJO, rect)

        # La pupila solo se dibuja si el ojo está lo bastante abierto para
        # contenerla; si no, asoma fuera del párpado y se ve mal.
        if apertura > 0.35:
            pupila = self._punto(
                cx + p.pupila_x * RECORRIDO_PUPILA,
                ALTURA_OJOS + p.pupila_y * RECORRIDO_PUPILA,
            )
            pygame.draw.circle(
                superficie, COLOR_PUPILA, pupila, self._escala(RADIO_PUPILA)
            )

    def _dibujar_boca(self, superficie: pygame.Surface, p: Parametros) -> None:
        medio_ancho = self._escala(ANCHO_BOCA / 2)
        izq = self._punto(0.5 - ANCHO_BOCA / 2, ALTURA_BOCA)
        der = self._punto(0.5 + ANCHO_BOCA / 2, ALTURA_BOCA)
        grosor = self._escala(GROSOR_BOCA)

        alto_abertura = int(p.boca * self._escala(ALTURA_MAX_BOCA))

        if alto_abertura > grosor:
            # Boca abierta: elipse. La curva de sonrisa la desplaza vertical.
            desplazamiento = int(p.sonrisa * self._escala(0.02))
            rect = pygame.Rect(0, 0, medio_ancho * 2, alto_abertura)
            rect.center = (izq[0] + medio_ancho, izq[1] + desplazamiento)
            pygame.draw.ellipse(superficie, COLOR_BOCA, rect)
        else:
            # Boca cerrada: arco aproximado por una polilínea de 3 puntos,
            # cuya altura central marca la sonrisa.
            curva = int(-p.sonrisa * self._escala(0.05))
            centro = (izq[0] + medio_ancho, izq[1] + curva)
            pygame.draw.lines(
                superficie, COLOR_BOCA, False, [izq, centro, der], grosor
            )
