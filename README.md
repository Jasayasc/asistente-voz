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

### Modo conversación

La palabra clave se dice **una vez**. A partir de ahí el asistente se queda
escuchando turno tras turno y recuerda lo que lleváis hablado, así que las
preguntas de seguimiento no necesitan repetir el contexto:

```
tú:      hey jarvis, ¿quién fue Ada Lovelace?
jarvis:  Ada Lovelace fue una matemática británica considerada la primera
         programadora de la historia...
tú:      ¿en qué año nació?              <- sin decir "hey jarvis"
jarvis:  Ada Lovelace nació en el año mil ochocientos quince.
tú:      ¿y de qué trataba esa máquina?  <- "esa máquina" se resuelve sola
jarvis:  Era la máquina analítica de Charles Babbage...
tú:      desactívate
jarvis:  Hasta luego.
```

La conversación se cierra de tres formas:

| Cómo | Qué pasa |
|---|---|
| Una frase de despedida | «desactívate», «inactívate», «apágate», «adiós», «hasta luego», «duérmete», «me voy a dormir», «eso es todo», «nada más», «olvídalo», «cambio y corto»… Contesta «Hasta luego» y vuelve a reposo |
| Silencio | 8 segundos sin oír a nadie. Se cierra sin decir nada: si ya no hay nadie, hablarle a la habitación no ayuda |
| Un problema | Dos fallos de red seguidos, o dos veces sin entender nada. Uno suelto no cierra: los 503 pasajeros de Gemini son frecuentes |
| Un tope duro | 15 turnos o 5 minutos. Existe porque los contadores de arriba se reinician con cada turno que sale bien: una televisión encendida produce habla real, que se transcribe, no es una despedida y no falla. Sin tope, el asistente le contestaría a la tele hasta que alguien la apagase |

Cada palabra clave abre una conversación **limpia**: el asistente no
arrastra de qué hablasteis hace tres horas. Dentro de una conversación
recuerda los últimos diez intercambios.

Se ajusta todo en el `.env` (ver `.env.example`): `MODO_CONVERSACION=false`
lo devuelve al comportamiento anterior de una pregunta por palabra clave,
`SEGUNDOS_PARA_CERRAR_CONVERSACION` alarga la espera si te corta mientras
piensas, y `FRASES_DE_DESPEDIDA` acepta las tuyas separadas por comas.

> Una precaución de diseño: de los dos errores posibles, el grave es
> confundir una **pregunta** con una despedida, porque apaga el asistente
> justo cuando le estás preguntando algo. No reconocer una despedida solo
> cuesta ocho segundos de silencio. Por eso una frase cuenta como
> despedida solo si tiene cinco palabras o menos, no lleva interrogación,
> la despedida va al final y no la precede ningún verbo de petición. Así
> «¿cómo se dice adiós en francés?», «traduce hasta luego al alemán»,
> «¿eso es todo?» y «ayúdame a dormir» son preguntas, no órdenes de
> apagado. Probado contra 78 frases reales.

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

## Tocar la cara

La cara reacciona a que la toquen. En la Raspberry Pi con la pantalla
táctil se hace con el dedo; en el ordenador de desarrollo, arrastrando con
el ratón. Funciona con `python -m cara` a secas, sin el asistente
arrancado.

| Gesto | Qué hace |
|---|---|
| Apoyar el dedo | Te sigue con la mirada mientras lo tengas puesto |
| Acariciar (recorrer la cara sin levantar) | Le da cosquillas: entrecierra los ojos, sonríe y se ríe a carcajadas mientras sigas |
| Un toque seco | Se sobresalta, abre los ojos y mira hacia donde le has tocado |
| Dos toques seguidos o más | Se molesta: mirada de reojo hacia ti, ojos entornados y boca hacia abajo, con un respingo. Cuanto más insistas, peor cara |

La reacción se pinta **encima** de la expresión del estado, no en lugar de
ella: se puede estar pensando y tener cosquillas a la vez. Mientras el
asistente habla, la boca la sigue gobernando el lipsync, para no
desincronizar la voz de la cara.

Lo que separa una caricia de un golpe son dos medidas distintas: la
caricia recorre distancia (da igual cuánto dure) y el golpe es corto en
tiempo y no recorre nada. Los umbrales están en `src/cara/tacto.py`, en
fracciones del lado de la pantalla para que los gestos se sientan iguales
en la pantalla de cinco pulgadas y en el monitor.

### En la Raspberry Pi

Dos cosas que solo aparecen allí y ya están resueltas en el código:

- SDL entrega cada gesto **dos veces**: como evento de dedo y, además,
  como un evento de ratón sintético para las aplicaciones que solo saben
  de ratón. Sin filtrarlo, cada caricia recorrería el doble y cada golpe
  valdría por dos. Se descartan los de ratón marcados con `touch=True`.
- La pantalla es **multitáctil**. Apoyar un segundo dedo haría saltar el
  punto de uno a otro, y ese salto contaría como recorrido: bastaría con
  posar dos dedos separados para disparar unas cosquillas que nadie ha
  hecho. Manda el primer dedo hasta que se levanta.

Si al tocar la cara reacciona en el sitio equivocado (por ejemplo, en
espejo), no es cosa del código: es la matriz de calibración del panel
táctil, que se configura en el sistema con `libinput`. Muchos paneles DSI
vienen girados respecto a la imagen.

## Tests

```bash
.venv/Scripts/python.exe -m pytest -v
```

Los tests no necesitan micrófono, altavoz ni conexión: todas las
dependencias externas están detrás de interfaces y se sustituyen por
dobles. Hay 358 tests, todos en verde.

## Estado del Hito 1

El código y los 358 tests automatizados están completos, y la conversación
se ha verificado contra las dos APIs reales: preguntas generales, preguntas
encadenadas con memoria, y las dos herramientas (hora y clima).

Queda por comprobar con el aparato delante la calidad de la detección de la
palabra clave con el micrófono definitivo, y el comportamiento de la cara
durante una conversación larga.

## Cambiar de proveedor

El STT y el LLM están aislados tras interfaces (`stt/base.py`, `llm/base.py`).
Cambiar de proveedor es escribir una subclase nueva y sustituir una línea en
`src/asistente/__main__.py`.

## Cambiar la palabra de activación

El Hito 1 usa el modelo pre-entrenado `hey_jarvis`. Para un nombre propio hay
que entrenar un modelo con openWakeWord y apuntar `MODELO_WAKEWORD` a él (o a
la ruta del archivo, si no está entre los modelos preentrenados del
paquete).
