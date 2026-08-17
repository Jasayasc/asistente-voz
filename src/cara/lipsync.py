# src/cara/lipsync.py
# ATAQUE y LIBERACION son factores POR FRAME, no por segundo — no reciben
# `dt` (ver `procesar`/`reposar` más abajo). RIESGO CONOCIDO, diferido al
# Hito 2 (ver revisión final del Hito 1): a 60 fps (Windows, desarrollo)
# el ataque tarda ~4 frames (~67 ms) en llegar al 90 % del objetivo; a
# ~20 fps (Raspberry Pi 3B) la misma transición tardará ~3x más. Y no es
# solo el retraso: el bucle de la cara solo lee el último RMS recibido por
# frame (`cara/servidor.py`, `_fijar`), y el asistente emite RMS a ~69
# mensajes/s, así que a 20 fps se pierden dos de cada tres picos de la
# envolvente, no solo se leen tarde. Escalar estos factores por `dt` (con
# un tope, para no sobrepasar el objetivo en un frame largo) corrige el
# retraso pero no la pérdida de picos; para eso el servidor debería
# acumular el máximo de RMS recibido desde el último frame en vez de
# quedarse con el último. Medir con el framerate y el buffer de audio
# reales de la Pi antes de tocar esto: ver también `reproductor.py`, donde
# `al_rms` se emite antes de escribir el audio y la boca va ligeramente
# adelantada a lo que suena, lo que hoy compensa en parte este retraso.
ATAQUE = 0.5          # la boca abre rápido
LIBERACION = 0.15     # y cierra despacio, por inercia
DECAIMIENTO_MAXIMO = 0.999  # el máximo móvil baja lentamente
MAXIMO_MINIMO = 1e-4  # suelo para no dividir por cero en silencio
UMBRAL_SILENCIO = 1e-5


class Lipsync:
    """Convierte el volumen del audio que suena en apertura de boca.

    Mapear RMS directamente a apertura produce un movimiento nervioso.
    Los tres pasos que lo arreglan son: tomar el RMS por bloque de ~20 ms
    del audio que está sonando (lo hace quien llama, no esta clase),
    normalizar contra un máximo móvil (para que funcione igual con voz
    suave o fuerte), y usar constantes distintas para abrir y cerrar (la
    boca humana abre de golpe y cierra con inercia).
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
