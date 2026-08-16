# src/cara/lipsync.py
ATAQUE = 0.5          # la boca abre rápido
LIBERACION = 0.15     # y cierra despacio, por inercia
DECAIMIENTO_MAXIMO = 0.999  # el máximo móvil baja lentamente
MAXIMO_MINIMO = 1e-4  # suelo para no dividir por cero en silencio
UMBRAL_SILENCIO = 1e-5


class Lipsync:
    """Convierte el volumen del audio que suena en apertura de boca.

    Mapear RMS directamente a apertura produce un movimiento nervioso.
    Los tres pasos que lo arreglan son: normalizar contra un máximo móvil
    (para que funcione igual con voz suave o fuerte), y usar constantes
    distintas para abrir y cerrar (la boca humana abre de golpe y cierra
    con inercia).
    """

    def __init__(self) -> None:
        self._maximo = MAXIMO_MINIMO
        self._apertura = 0.0

    def procesar(self, rms: float) -> float:
        if rms <= UMBRAL_SILENCIO:
            return self.reposar()

        self._maximo = max(rms, self._maximo * DECAIMIENTO_MAXIMO, MAXIMO_MINIMO)
        objetivo = min(1.0, rms / self._maximo)
        factor = ATAQUE if objetivo > self._apertura else LIBERACION
        self._apertura += (objetivo - self._apertura) * factor
        return self._limitar(self._apertura)

    def reposar(self) -> float:
        """Cierra la boca progresivamente. Se llama cuando no hay audio
        sonando, para que la boca no se quede congelada a medio abrir."""
        self._apertura += (0.0 - self._apertura) * LIBERACION
        if self._apertura < 1e-4:
            self._apertura = 0.0
        return self._limitar(self._apertura)

    def _limitar(self, valor: float) -> float:
        return max(0.0, min(1.0, valor))
