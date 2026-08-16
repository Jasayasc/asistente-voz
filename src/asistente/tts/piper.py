# src/asistente/tts/piper.py
from collections.abc import Iterator

from piper import PiperVoice


class Piper:
    """Síntesis de voz local.

    Que el TTS sea local hace dos cosas: elimina un viaje de red del camino
    crítico de la respuesta, y permite que el asistente avise por voz
    cuando no hay internet. Con un TTS en la nube, un corte de red lo
    dejaría mudo justo cuando más falta hace avisar.
    """

    def __init__(self, ruta_modelo: str) -> None:
        self._voz = PiperVoice.load(ruta_modelo)
        self.tasa_muestreo = self._voz.config.sample_rate

    def sintetizar(self, texto: str) -> Iterator[bytes]:
        """Devuelve PCM int16 en trozos, a medida que se generan.

        `piper-tts` 1.x no tiene `synthesize_stream_raw`: `synthesize`
        devuelve un `AudioChunk` por frase, con el audio como floats en
        `[-1, 1]`. `audio_int16_bytes` hace esa conversión a PCM int16.
        """
        texto = texto.strip()
        if not texto:
            return
        for fragmento in self._voz.synthesize(texto):
            yield fragmento.audio_int16_bytes
