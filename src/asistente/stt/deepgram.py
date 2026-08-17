import httpx
import numpy as np

from asistente.audio.captura import TASA_MUESTREO
from asistente.llm.base import ErrorDeRed
from asistente.stt.base import ClienteSTT

URL = "https://api.deepgram.com/v1/listen"
TIMEOUT = 15.0


class ClienteDeepgram(ClienteSTT):
    """Transcripción con Deepgram.

    Se envía el audio completo tras detectar el fin de la intervención,
    no en streaming. Para frases cortas de asistente doméstico la
    diferencia es de décimas, y a cambio el código es mucho más simple:
    una petición HTTP en vez de un WebSocket con su propio ciclo de vida.
    Si más adelante la latencia molesta, esta clase es lo único que hay
    que cambiar.
    """

    def __init__(
        self,
        api_key: str,
        idioma: str = "es",
        cliente_http: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._idioma = idioma
        self._cliente_http = cliente_http

    def transcribir(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""

        propio = self._cliente_http is None
        cliente = self._cliente_http or httpx.Client(timeout=TIMEOUT)
        try:
            respuesta = cliente.post(
                URL,
                params={
                    "model": "nova-2",
                    "language": self._idioma,
                    "punctuate": "true",
                    "encoding": "linear16",
                    "sample_rate": str(TASA_MUESTREO),
                    "channels": "1",
                },
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Content-Type": "audio/raw",
                },
                content=audio.tobytes(),
                timeout=TIMEOUT,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ErrorDeRed(str(exc)) from exc
        finally:
            if propio:
                cliente.close()

        try:
            alternativas = datos["results"]["channels"][0]["alternatives"]
            if not alternativas:
                return ""
            return alternativas[0].get("transcript", "").strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""
