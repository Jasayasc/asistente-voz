# Asistente de voz con cara animada

Asistente tipo Alexa que despierta al oír su nombre, responde hablando, y
muestra una cara animada que reacciona a cada fase de la conversación.

Diseño completo en [`docs/superpowers/specs/`](docs/superpowers/specs/).

## Piezas

- **Wake word**: [openWakeWord](https://github.com/dscripka/openWakeWord),
  con el modelo preentrenado `hey_jarvis`. Entrenar una palabra propia queda
  fuera de este hito (ver "Cambiar la palabra de activación" más abajo).
- **Transcripción (STT)**: [Deepgram](https://console.deepgram.com), en la
  nube.
- **Modelo de lenguaje (LLM)**: [Gemini](https://aistudio.google.com/apikey),
  vía el SDK `google-genai`. La clave se obtiene en Google AI Studio.
- **Herramienta de clima**: [Open-Meteo](https://open-meteo.com/), que no
  necesita clave ni registro.
- **Síntesis de voz (TTS)**: [Piper](https://github.com/rhasspy/piper),
  local, con la voz en español `es_ES-davefx-medium` (22050 Hz).
- **Cara**: proceso aparte con `pygame`, que recibe estados por socket.

> El plan gratuito de Gemini tiene límites de peticiones por minuto, y
> Google puede usar los datos enviados para mejorar sus productos. Tenlo en
> cuenta en un aparato que escucha en casa: conviene revisar la política de
> privacidad de Google AI Studio antes de dejarlo escuchando de forma
> habitual.

## Requisitos

- Python 3.11 o superior
- Un micrófono y un altavoz
- Claves de API de [Deepgram](https://console.deepgram.com) y de
  [Google AI Studio](https://aistudio.google.com/apikey)

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux

pip install -e ".[dev]"
python -c "import openwakeword.utils; openwakeword.utils.download_models()"
```

El comando anterior descarga los modelos preentrenados de openWakeWord
(incluido `hey_jarvis`) dentro del propio paquete instalado. `python -m
asistente` comprueba que estén antes de arrancar y, si faltan, imprime este
mismo comando en pantalla.

Descargar además un modelo de voz de Piper en español a `modelos/`:
`es_ES-davefx-medium.onnx` y su `.json`, desde
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

Copiar `.env.example` a `.env` y rellenar las claves de API.

## Uso

Dos procesos, en dos terminales:

```bash
python -m cara         # la pantalla
python -m asistente    # el resto
```

Di "hey jarvis" y haz una pregunta.

`python -m asistente` comprueba al arrancar que están las dos claves de API
y los dos modelos (voz y wake word); si falta algo, lo dice por pantalla en
vez de fallar con una traza a medio arrancar.

## Scripts de diagnóstico

Cada uno prueba una pieza por separado. Úsalos en este orden si algo falla:

| Script | Comprueba |
|---|---|
| `scripts/listar_dispositivos.py` | Qué dispositivos de audio hay |
| `scripts/probar_microfono.py` | Que el micrófono graba (crea `prueba.wav`) |
| `scripts/probar_voz.py` | Que Piper sintetiza y se oye |
| `scripts/probar_wakeword.py` | Que detecta la palabra clave, y con qué margen |
| `scripts/probar_stt.py` | Que la transcripción funciona |
| `scripts/probar_llm.py` | Que el LLM responde y consulta el clima |
| `scripts/probar_cara.py` | Que la cara anima todos los estados |

## Tests

```bash
.venv/Scripts/python.exe -m pytest -v
```

Los tests no necesitan micrófono, altavoz ni conexión: todas las
dependencias externas están detrás de interfaces y se sustituyen por
dobles. A fecha de este hito hay 157 tests, todos en verde.

## Estado del Hito 1

El código y los 157 tests automatizados están completos. La prueba de
integración manual con micrófono, altavoz y las dos claves de API reales
—los ocho criterios de aceptación del Hito 1— queda pendiente de
verificación con el dueño del proyecto: no se ha ejecutado
`python -m asistente` en este hito.

## Cambiar de proveedor

El STT y el LLM están aislados tras interfaces (`stt/base.py`, `llm/base.py`).
Cambiar de proveedor es escribir una subclase nueva y sustituir una línea en
`src/asistente/__main__.py`.

## Cambiar la palabra de activación

El Hito 1 usa el modelo pre-entrenado `hey_jarvis`. Para un nombre propio hay
que entrenar un modelo con openWakeWord y apuntar `MODELO_WAKEWORD` a él (o a
la ruta del archivo, si no está entre los modelos preentrenados del
paquete).
