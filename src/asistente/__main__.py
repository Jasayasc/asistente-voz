# src/asistente/__main__.py
import logging
import os
import sys

import openwakeword

from asistente.audio.captura import Captura
from asistente.audio.reproductor import Reproductor
from asistente.cara_cliente import CaraCliente
from asistente.config import Config
from asistente.llm.gemini import ClienteGemini
from asistente.orquestador import Orquestador
from asistente.stt.deepgram import ClienteDeepgram
from asistente.tts.piper import Piper
from asistente.wake.detector import Detector
from asistente.wake.vad import DetectorSilencio


def _wakeword_disponible(nombre: str) -> bool:
    """Comprueba que el modelo de wake word está instalado.

    Si `nombre` ya es una ruta a un archivo (un modelo propio, entrenado a
    medida) basta con que exista. Si es el nombre corto de un modelo
    preentrenado (p. ej. "hey_jarvis"), hay que buscarlo donde
    `openwakeword.utils.download_models()` lo deja: dentro del propio
    paquete instalado, en `openwakeword/resources/models/`. Es la misma
    búsqueda por coincidencia de nombre que hace `openwakeword.Model`
    internamente al recibir un nombre en vez de una ruta.
    """
    if os.path.exists(nombre):
        return True
    clave = nombre.replace(" ", "_")
    candidatos = openwakeword.get_pretrained_model_paths(inference_framework="onnx")
    return any(clave in os.path.basename(c) and os.path.exists(c) for c in candidatos)


def _configurar_logging() -> None:
    """Deja a la vista lo que pasa dentro de una conversación.

    En modo conversación el asistente encadena turnos solo, y desde fuera
    no se distingue "se ha cerrado porque he dicho adiós" de "se ha cerrado
    porque no me ha oído". Con el log en INFO cada turno deja su línea: qué
    se transcribió y por qué se cerró.
    """
    logging.basicConfig(
        level=os.getenv("NIVEL_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    _configurar_logging()
    cfg = Config.cargar()

    if not cfg.gemini_api_key or not cfg.deepgram_api_key:
        print("Faltan claves de API. Copia .env.example a .env y rellénalo.")
        return 1

    if not os.path.exists(cfg.ruta_voz):
        print(
            f"No se encuentra el modelo de voz en '{cfg.ruta_voz}'. "
            "Descárgalo siguiendo el README (sección Instalación)."
        )
        return 1

    if not _wakeword_disponible(cfg.modelo_wakeword):
        print(
            f"No se encuentra el modelo de wake word '{cfg.modelo_wakeword}'. "
            'Descárgalo con: python -c "import openwakeword.utils; '
            'openwakeword.utils.download_models()" (ver README, sección '
            "Instalación)."
        )
        return 1

    print("cargando modelos...")
    # Todo lo que puede fallar en la construcción vive aquí, antes de abrir
    # el micrófono: si algo de esto lanza (una API key rechazada, un modelo
    # corrupto...) el micrófono nunca llegó a abrirse y no hay nada que
    # liberar.
    tts = Piper(cfg.ruta_voz)
    detector = Detector(cfg.modelo_wakeword, cfg.umbral_wakeword)
    vad = DetectorSilencio()
    cara = CaraCliente(cfg.host_cara, cfg.puerto_cara)
    stt = ClienteDeepgram(cfg.deepgram_api_key)
    llm = ClienteGemini(cfg.gemini_api_key, cfg.modelo_llm)
    reproductor = Reproductor(cfg.dispositivo_salida, tts.tasa_muestreo)

    with Captura(cfg.dispositivo_entrada) as captura:
        orquestador = Orquestador(
            captura=captura,
            detector=detector,
            vad=vad,
            stt=stt,
            llm=llm,
            tts=tts,
            reproductor=reproductor,
            cara=cara,
            modo_conversacion=cfg.modo_conversacion,
            segundos_para_cerrar=cfg.segundos_para_cerrar_conversacion,
            frases_de_despedida=cfg.frases_de_despedida,
        )

        palabra = cfg.modelo_wakeword.replace("_", " ")
        if cfg.modo_conversacion:
            print(
                f"modo conversación: di '{palabra}' una vez y sigue hablando. "
                f"Para cerrarla: '{cfg.frases_de_despedida[0]}', o "
                f"{cfg.segundos_para_cerrar_conversacion:.0f} s de silencio."
            )
        print(f"listo. di '{palabra}'. Ctrl+C para salir.")
        try:
            orquestador.ejecutar()
        except KeyboardInterrupt:
            print("\ncerrando...")
        finally:
            # cara.cerrar() vive en su propio finally, separado de la
            # liberación del micrófono (que hace `with Captura` al salir de
            # este bloque). Así, si detener la captura falla —un
            # dispositivo USB desconectado a media ejecución lanza
            # PortAudioError— eso no impide que la cara se cierre: cada
            # paso de limpieza es independiente del otro.
            cara.cerrar()

    return 0


if __name__ == "__main__":
    sys.exit(main())
