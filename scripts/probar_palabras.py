# scripts/probar_palabras.py
"""Compara todas las palabras de activación preentrenadas con tu voz.

`hey_jarvis` viene de un modelo entrenado con voces inglesas, y "jarvis" no
tiene una pronunciación natural en castellano: cada hablante la aproxima de
una manera, y el modelo puntúa bajo e irregular. Otras palabras del mismo
paquete se pronuncian casi igual en los dos idiomas —"alexa" es el caso
claro— y suelen reconocerse mucho mejor sin cambiar nada más.

Este script carga todos los modelos preentrenados a la vez y los puntúa con
el mismo audio, así que una sola sesión sirve para compararlos. Di cada
palabra varias veces y quédate con la que puntúe más alto y más constante.

Uso:  .venv\\Scripts\\python.exe scripts\\probar_palabras.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402
import openwakeword  # noqa: E402
from openwakeword.model import Model  # noqa: E402

from asistente.audio.captura import Captura  # noqa: E402
from asistente.config import Config  # noqa: E402

# Cómo decir cada palabra, para quien no venga del inglés.
PRONUNCIACION = {
    "alexa": "alexa (igual que en castellano)",
    "hey_jarvis": "jei yárvis",
    "hey_mycroft": "jei máicroft",
    "hey_rhasspy": "jei ráspi",
    "timer": "táimer",
    "weather": "wéder",
}


def main() -> int:
    cfg = Config.cargar()

    rutas = openwakeword.get_pretrained_model_paths(inference_framework="onnx")
    # Se descartan dos cosas. Los modelos auxiliares (embeddings,
    # melspectrograma, VAD) no son palabras de activación y cargarlos como
    # tales falla. `timer` y `weather` sí son modelos, pero de órdenes
    # concretas, no de activación: `timer` además se expande por dentro en
    # varias clases ("1_minute_timer", "5_minute_timer"...), así que su
    # nombre no aparece como tal en el resultado de `predict`.
    descartados = (
        "embedding_model", "melspectrogram", "silero_vad", "timer", "weather",
    )
    modelos = sorted(
        {
            Path(r).stem.replace("_v0.1", "")
            for r in rutas
            if not any(d in Path(r).stem for d in descartados)
        }
    )
    if not modelos:
        print('No hay modelos. Descárgalos: python -c "import openwakeword.utils; '
              'openwakeword.utils.download_models()"')
        return 1

    print("modelos cargados:", ", ".join(modelos))
    modelo = Model(wakeword_models=modelos, inference_framework="onnx")
    # Las claves se toman del resultado de `predict`, no de `modelo.models`:
    # son las dos listas las que tienen que coincidir al puntuar, y no
    # siempre son la misma.
    claves = sorted(modelo.predict(np.zeros(1280, dtype=np.int16)).keys())
    modelo.reset()

    print("\nDi cada palabra 3 o 4 veces, con pausas. Ctrl+C para el resumen.")
    for c in claves:
        print(f"  - {PRONUNCIACION.get(c, c)}")
    print()

    mejores = {c: 0.0 for c in claves}
    picos: dict[str, list[float]] = {c: [] for c in claves}
    en_curso: dict[str, float] = {c: 0.0 for c in claves}

    with Captura(cfg.dispositivo_entrada) as captura:
        try:
            while True:
                bloque = captura.leer_bloque()
                if bloque is None:
                    continue
                puntuaciones = modelo.predict(bloque)
                for c in claves:
                    p = float(puntuaciones[c])
                    mejores[c] = max(mejores[c], p)
                    if p > 0.1:
                        en_curso[c] = max(en_curso[c], p)
                    elif en_curso[c]:
                        picos[c].append(en_curso[c])
                        en_curso[c] = 0.0
                mejor = max(claves, key=lambda c: puntuaciones[c])
                if puntuaciones[mejor] > 0.1:
                    nivel = float(np.sqrt(np.mean((bloque.astype(np.float32) / 32768) ** 2)))
                    print(f"  {mejor:14} {float(puntuaciones[mejor]):.3f}   (nivel {nivel:.3f})")
        except KeyboardInterrupt:
            pass

    for c in claves:
        if en_curso[c]:
            picos[c].append(en_curso[c])

    print("\n--- resumen: qué palabra reconoce mejor tu voz ---")
    orden = sorted(claves, key=lambda c: mejores[c], reverse=True)
    for c in orden:
        lista = sorted(picos[c], reverse=True)[:5]
        detalle = ", ".join(f"{p:.3f}" for p in lista) if lista else "sin intentos"
        print(f"  {c:14} máximo={mejores[c]:.3f}  intentos: {detalle}")

    ganadora = orden[0]
    if mejores[ganadora] >= 0.5:
        print(
            f"\nUsa '{ganadora}': pon MODELO_WAKEWORD={ganadora} en .env "
            "(y UMBRAL_WAKEWORD=0.5, que ya te sobra margen)."
        )
    elif mejores[ganadora] >= 0.3:
        print(
            f"\n'{ganadora}' es la mejor, pero justa. Pon "
            f"MODELO_WAKEWORD={ganadora} y calibra el umbral con "
            "scripts/probar_wakeword.py."
        )
    else:
        print(
            "\nNinguna llega. Con el micrófono ya descartado, lo que queda "
            "es entrenar un modelo con tu propia voz (ver README)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
