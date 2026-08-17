# Revisión final de rama — Hito 1 (Windows)

**Rama:** hito-1 · **Base:** c2a13aa · **Head:** 6aedf6e · **28 commits, 18 tareas, 157 tests**
**Fecha:** 2026-08-17
**Alcance:** revisión transversal de rama completa. Solo lectura. No se ha ejecutado el
asistente, ni abierto dispositivos de audio, ni hecho llamadas de red. No se ha ejecutado
la suite de tests: ninguna de las dudas de esta revisión se resolvía ejecutándola (todos
los hallazgos están en código sin cobertura o en contratos entre módulos).

---

## 1. Verdicto

**No listo para fusionar todavía. Tres defectos bloquean.** Ninguno es estructural: los tres
son de pocas líneas y ninguno obliga a rediseñar nada. La arquitectura es sólida, los
contratos entre módulos son coherentes, y la disciplina de manejo de recursos es
notablemente buena para una rama de este tamaño.

Los tres bloqueantes son:

1. **`gemini.py:84` — la llamada al LLM no tiene timeout.** Es el único cliente de red de
   los tres que no lo tiene, y es el único camino por el que el asistente se queda colgado
   para siempre sin posibilidad de recuperación. Contradice una fila explícita de la tabla
   de errores del diseño.
2. **`cara/__main__.py:50-54` — la boca pasa por dos suavizados encadenados.** Anula el
   paso que el propio diseño señala como "el que hace la diferencia entre parecer que habla
   y parecer que tiembla". Medido: una sílaba de 100 ms abre la boca al 61 % de lo que
   debería, y el ataque pasa de 67 ms a ~250 ms.
3. **`vad.py:48-53` — un falso positivo deja al asistente sordo 12 segundos**, no ~3 como
   dice el diseño. Durante esa ventana no se evalúa la palabra clave y cualquier
   conversación ambiental se transcribe y se contesta sin que nadie lo haya pedido.

Los tres son verificables por inspección y los tres tienen arreglo local. Con ellos
resueltos, la rama está lista para fusionar y pasar al bloque de verificación manual.

---

## 2. Fortalezas

Esto no es cortesía: son cosas concretas que esta rama hace mejor que la media.

**La cadena del formato de audio es correcta de extremo a extremo, y está anclada en un
único sitio.** Era el punto que más fácilmente se rompe y no está roto:
`captura.py:7` define `TASA_MUESTREO = 16000`; `vad.py:3` y `deepgram.py:4` lo **importan**
en vez de repetirlo, así que `deepgram.py:47` manda a la API exactamente la tasa con la que
se grabó, por construcción. El bloque de 1280 muestras (`captura.py:8`) es el que
openWakeWord espera y se le entrega sin remuestrear. `int16` mono se mantiene desde el
callback de PortAudio hasta `audio.tobytes()`. No hay un solo punto donde el formato se
asuma en vez de derivarse.

**El cambio de tasa a 22050 Hz se resolvió bien en el punto correcto.** `piper.py:18` lee
`self._voz.config.sample_rate` del modelo en vez de fijarlo, y `__main__.py:71` lo inyecta
en el reproductor. Se descubrió tarde (Tarea 13) y no obligó a tocar la Tarea 12: eso es
mérito de haber puesto la costura donde tocaba.

**No hay forma de que los dos procesos se bloqueen mutuamente.** El protocolo es
estrictamente unidireccional: `cara_cliente.py` solo escribe, `servidor.py:_atender` solo
lee y nunca responde. Además el servidor lee en un hilo propio (`servidor.py:47`) con
`recv` de 0.2 s, así que el ritmo del bucle de render no ejerce contrapresión sobre el
socket. Y `create_connection(..., timeout=1.0)` (`cara_cliente.py:44-46`) deja el socket con
timeout, así que un `sendall` contra una cara atascada levanta `TimeoutError` —que es
subclase de `OSError`— y cae en el `except OSError` de la línea 32. Deadlock descartado por
construcción, no por suerte.

**El manejo de recursos de audio es de los mejores que se ven.** `captura.py:66-76` cierra
el stream si `start()` lanza, con el razonamiento correcto escrito en el comentario (si se
llamó desde `__enter__`, Python no invocará `__exit__`). `reproductor.py:50-70` anida dos
`try/finally` de forma que el stream se cierra por las seis vías de salida y la excepción
original nunca queda enmascarada. `__main__.py:90-97` separa el cierre de la cara del
cierre del micrófono a propósito, para que el fallo de uno no impida el otro. Los tres
llevan comentario explicando por qué, no qué.

**La red de seguridad del orquestador está bien pensada.** `orquestador.py:74-85`: backoff
exponencial con tope, contador que se reinicia por cláusula `else` (solo en ciclo correcto,
no en `finally`), y deduplicación de trazas por firma. `KeyboardInterrupt` y `SystemExit`
propagan porque no son `Exception`, y está documentado que es deliberado. Es la diferencia
entre "no muere" y "no muere y además no llena la SD".

**El aislamiento tras interfaces es real, no nominal.** El orquestador no importa
`sounddevice`, ni `httpx`, ni `google-genai`, ni `pygame`. Los 24 tests de
`test_orquestador.py` ejercitan la máquina de estados completa, incluidos los cinco caminos
de error, sin tocar hardware. Es exactamente lo que el diseño prometía y muy pocas veces se
cumple.

**No hay riesgo de secreto.** `.gitignore:1` ignora `.env`; solo `.env.example` está
versionado y tiene los campos vacíos. Búsqueda de patrones de clave sobre los 162 KB del
diff: cero, salvo un literal `"clave-falsa"` en un test.

---

## 3. Debe arreglarse antes de fusionar

### M1 — La llamada a Gemini no tiene timeout: el asistente puede colgarse para siempre

`src/asistente/llm/gemini.py:84`

```python
self._cliente = genai.Client(api_key=api_key)
```

Sin `http_options`. Verificado sobre el SDK instalado:
`.venv/Lib/site-packages/google/genai/_api_client.py:248-258` — `get_timeout_in_seconds(None)`
devuelve `None`; línea 1450 pasa ese `None` a `HttpRequest.timeout`; línea 1131-1132 fija
además `timeout=None` en el propio `httpx.Client`. `httpx` con `timeout=None` espera
indefinidamente.

Consecuencia: una conexión medio abierta —el caso típico de wifi doméstico: el router se
reinicia, el AP cambia de canal, el portátil suspende— deja `generate_content_stream`
bloqueado sin límite. El asistente se queda en PENSANDO o a mitad de HABLANDO, la cara se
queda congelada en esa expresión, y **no hay recuperación posible**: no es un fallo que la
red de seguridad de `ejecutar()` pueda atrapar, porque nunca se lanza nada. Hace falta
Ctrl+C. En una Raspberry Pi desatendida eso es el asistente muerto hasta que alguien lo
note.

Esto es además una **inconsistencia transversal sin justificación**: los otros dos clientes
de red sí tienen timeout, `deepgram.py:9` (`TIMEOUT = 15.0`) y `herramientas.py:4`
(`TIMEOUT = 6.0`). Y el diseño lo pide explícitamente:

> | Timeout global (>15 s) | Corta y emite el mensaje de error |

Esa fila de la tabla de errores del diseño no está implementada en ninguna parte de la rama.

**Arreglo:** `genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15000))`
(milisegundos). El `httpx.TimeoutException` resultante es subclase de `httpx.HTTPError`, que
ya está en la tupla de `gemini.py:152`, así que se traduce solo a `ErrorDeRed` y el
orquestador ya sabe qué hacer con eso: dice el mensaje de red y vuelve a reposo. Es decir,
la fila del diseño se cumple entera con un parámetro.

---

### M2 — La boca pasa por dos suavizados encadenados; el ataque rápido del lipsync queda anulado

`src/cara/__main__.py:49-54`

```python
if mensaje.estado is Estado.HABLANDO:
    objetivo.boca = lipsync.procesar(mensaje.rms)   # ya trae ataque 0.5 / liberación 0.15
else:
    objetivo.boca = lipsync.reposar()

actual = interpolar(actual, objetivo, SUAVIZADO)     # vuelve a suavizar TODOS los campos
```

`interpolar` (`parametros.py:33-38`) itera `fields(actual)`, así que aplica el factor 0.15 a
los seis parámetros **incluida `boca`**, que ya venía filtrada por `Lipsync.procesar`
(`lipsync.py:29-31`). El resultado es un filtro de primer orden en cascada con otro.

El diseño no deja lugar a dudas sobre qué se rompe aquí:

> 3. **Ataque rápido, liberación lenta:** la boca abre con factor ~0.5 y cierra con ~0.15.
>
> El tercer paso es el que hace la diferencia entre parecer que habla y parecer que tiembla.

Medido numéricamente sobre las constantes reales (60 fps):

| | solo Lipsync | en cascada con `interpolar(0.15)` |
|---|---|---|
| Escalón al 90 % | 4 frames (67 ms) | ~15 frames (~250 ms) |
| Pico de una sílaba de 100 ms | 0.98 | **0.61** (61 % de la amplitud) |

Es decir: el ataque se degrada de 67 ms a 250 ms —el factor 0.5 deja de tener efecto, la
cascada queda gobernada por el 0.15— y en habla normal, donde las sílabas duran 80-150 ms,
la boca se abre a **menos de dos tercios** de lo que debería. El movimiento resulta a la vez
retrasado y apagado, que es justo el resultado que el paso 3 existía para evitar.

Esto es un defecto de composición puro: la Tarea 5 construyó `Lipsync` bien, la Tarea 3
construyó `interpolar` bien, y ninguna revisión por tarea podía ver que al cablearlas en el
bucle de render se aplican una detrás de otra. `src/cara/__main__.py` no tiene tests.

Amenaza directamente el criterio de aceptación 7 ("La boca se mueve de forma
reconociblemente sincronizada con la voz"), que además sigue pendiente de verificación
visual.

**Arreglo:** excluir `boca` del suavizado genérico. La forma mínima es asignarla después:

```python
actual = interpolar(actual, objetivo, SUAVIZADO)
actual.boca = objetivo.boca   # el lipsync ya trae su propio ataque/liberación
```

---

### M3 — Un falso positivo deja al asistente sordo 12 segundos, no ~3

`src/asistente/wake/vad.py:22-53` y `src/asistente/orquestador.py:153-165`

Cuando el wake word dispara y nadie habla, `DetectorSilencio.procesar` nunca devuelve True
por la vía del silencio, porque la línea 51-52 corta antes:

```python
if not self.hubo_voz:
    # Todavía no ha empezado a hablar: nada que cerrar.
    return False
```

La única salida es el tope duro de la línea 48-49, `self._bloques >= self._bloques_maximos`,
que con el `maximo_segundos: float = 12.0` por defecto (línea 26) son **12 segundos**.

El diseño especifica otra cosa:

> | Falso positivo del wake word | Tras ~3 s de silencio vuelve a REPOSO **sin hablar** |

Durante esos 12 s, `_grabar_intervencion` está consumiendo bloques de la cola y
acumulándolos, y **el detector de palabra clave no se ejecuta sobre ninguno**. El asistente
está sordo a su propio nombre durante 12 segundos después de cada falso positivo. Peor: si
alguien dice cualquier cosa en la habitación dentro de esa ventana, `hubo_voz` pasa a True,
la grabación se cierra por silencio y el asistente **transcribe y contesta una conversación
que no iba con él**. El diseño acota esa exposición a ~3 s; la implementación la cuadruplica.

El criterio de aceptación 2 ("Un falso positivo no produce ninguna respuesta hablada") se
cumple en el caso puro (silencio total), pero el comportamiento observable es el de un
aparato que se cuelga 12 segundos cada vez que se equivoca.

El origen es el plan (línea 1863 fija `maximo_segundos: float = 12.0`), así que ninguna
revisión por tarea podía marcarlo: la Tarea 10 implementó su brief correctamente. Es el tipo
de divergencia diseño↔plan que solo aparece leyendo los dos a la vez.

**Arreglo:** un segundo umbral, para el silencio previo a cualquier voz:

```python
def __init__(self, umbral=0.02, segundos_silencio=1.0,
             segundos_sin_voz=3.0, maximo_segundos=12.0):
    ...
    self._bloques_sin_voz = max(1, int(segundos_sin_voz / SEGUNDOS_POR_BLOQUE + 0.5))

# en procesar(), sustituyendo el `return False`:
if not self.hubo_voz:
    return self._silencios >= self._bloques_sin_voz
```

`maximo_segundos=12.0` sigue haciendo falta como tope de una intervención larga; lo que
falta es el tope corto de "nadie ha dicho nada todavía". Nótese que
`test_orquestador.py` no lo detectaría: sus dobles de VAD deciden por bandera, no por tiempo.

---

## 4. Debería arreglarse pronto

### S1 — La cola de audio no se vacía tras un ciclo que ha hablado (asimetría con el arreglo de la Tarea 17)

`src/asistente/orquestador.py:79` vs `:145`

La Tarea 17 añadió `self._captura.vaciar()` en el camino de excepción (línea 79) con este
razonamiento, textual del ledger: *"conserva la propia voz sintetizada del asistente y puede
auto-despertarlo en el ciclo siguiente"*. El razonamiento es correcto — y se aplica igual al
camino normal, donde **no** se hizo. `un_ciclo()` termina en la línea 145 con
`set_estado(REPOSO)` y vuelve; la cola conserva los últimos ~4 s capturados durante la
reproducción (`MAX_BLOQUES_EN_COLA = 50` × 80 ms), que por el altavoz son la propia voz del
asistente. Lo mismo en las tres salidas por `_avisar`.

Honestamente: la probabilidad de auto-despertar es baja (haría falta que la propia respuesta
sonase a "hey jarvis"), y los 50 bloques rancios se consumen en milisegundos. Pero es el
mismo peligro que el proyecto ya decidió que merecía arreglo, dejado a medias sin una razón
escrita, y el arreglo es una línea. `test_orquestador.py:246` cubre la mitad que se arregló
(`test_un_fallo_inesperado_vacia_la_cola_de_audio`) y no existe su equivalente para el
camino normal.

**Arreglo:** mover el `vaciar()` al final de `un_ciclo()` para cubrir ambos, o añadirlo en
la cláusula `else` de `ejecutar()`.

### S2 — La expresión ERROR no llega a verse nunca

`src/asistente/orquestador.py:188-195` con `:182-186`

`_avisar` pone la cara en ERROR y acto seguido llama a `_decir`, cuyo callback
`al_rms=lambda rms: self._cara.set_estado(Estado.HABLANDO, rms=rms)` la devuelve a HABLANDO
en el primer trozo de audio. Con `interpolar` a 0.15, en el tiempo que Piper tarda en
entregar el primer chunk la cara apenas se ha movido hacia el gesto de ERROR antes de
volverse. En la práctica el usuario nunca ve la cara triste: ve la cara de hablar diciendo
"No puedo ayudarte con esto hasta que estés conectado a una red".

El diseño dice: *"Existe además un estado ERROR ... que siempre vuelve a REPOSO tras emitir
su mensaje"*, lo que implica que ERROR se muestra **mientras** emite. Como el criterio 6
solo exige los cuatro estados principales y el 5 solo exige que el mensaje se pronuncie,
esto no bloquea; pero es una pieza construida (`expresiones.py:13`, con su test en
`test_expresiones.py`) que el sistema nunca llega a mostrar.

Relacionado y menor: `_avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)` (línea 136 y 180) pasa
PENSANDO donde el otro llamador pasa ERROR. Defendible —no entender no es un error de
sistema— pero conviene que sea una decisión escrita y no una asimetría.

### S3 — `pygame.display.set_mode` con resolución fija y `FULLSCREEN`: fallará o recortará en la Pi

`src/cara/__main__.py:27-28`

```python
banderas = pygame.FULLSCREEN if cfg.pantalla_completa else 0
pantalla = pygame.display.set_mode((cfg.ancho, cfg.alto), banderas)
```

En pantalla completa esto pide a SDL un **modo de vídeo de 800×480**, no la resolución del
escritorio. En el monitor HDMI del entorno de pruebas (criterio 10) 800×480 no es un modo
soportado habitual: SDL o bien falla, o bien escala a un modo cercano con bandas. El diseño
dice que el cambio debe ser "una bandera de configuración" y que el renderizador se escala
"a la resolución detectada" — y `Renderizador(*pantalla.get_size())` (línea 31) ya está
preparado para cualquier tamaño, así que el idiomático `set_mode((0, 0), pygame.FULLSCREEN)`
haría exactamente lo que el diseño describe.

En la misma línea: `FPS = 60` (`cara/__main__.py:14`) está fijado en código y no en
configuración. En la Pi 3B interesa bajarlo a 30 —el diseño acepta 30-60— para dejar CPU al
proceso `asistente`, que necesita un núcleo para ONNX y otro para Piper.

### S4 — `gemini-2.5-flash` con "thinking" activado por defecto: es el mayor riesgo de latencia

`src/asistente/llm/gemini.py:86-93`

La `GenerateContentConfig` no fija `thinking_config`. `gemini-2.5-flash` es un modelo de
razonamiento y su presupuesto de pensamiento está **activado por defecto en modo dinámico**;
se desactiva explícitamente con `thinking_budget=0`. Con él activo, el tiempo hasta el primer
token de texto pasa de décimas a varios segundos, porque el modelo piensa antes de emitir.

Eso ataca el objetivo del diseño de forma directa:

> El objetivo es ~1-1.5 s desde que el usuario calla hasta que empieza la respuesta.

y el criterio 11 del Hito 2 (≤ 3 s en la 3B), donde el presupuesto ya está muy justo: a los
segundos de pensamiento hay que sumarles la petición de Deepgram y la síntesis completa de
la primera frase con Piper. Para las respuestas de dos o tres frases que pide
`INSTRUCCIONES`, el razonamiento no aporta nada.

**Arreglo:** `thinking_config=types.ThinkingConfig(thinking_budget=0)` en la config.
Merece medirse con clave real durante el bloque de verificación manual antes de decidir.

Riesgo secundario del mismo origen: `gemini.py:122-124` hace `if parte.text: yield parte.text`
sin filtrar `parte.thought`. Hoy es inofensivo porque `include_thoughts` es False por
defecto y el API no devuelve partes de pensamiento; pero si alguien lo activa, **el asistente
leerá en voz alta su propio razonamiento**. Una guarda `if parte.text and not
getattr(parte, "thought", False)` lo cierra por un coste nulo.

### S5 — `Reproductor` tiene por defecto la tasa de *captura*, y `MUESTRAS_POR_TROZO` ya no son 20 ms

`src/asistente/audio/reproductor.py:6,9,32`

```python
from asistente.audio.captura import TASA_MUESTREO
MUESTRAS_POR_TROZO = 320  # 20 ms — resolución del movimiento de boca
...
def __init__(self, dispositivo=None, tasa: int = TASA_MUESTREO) -> None:
```

Dos secuelas del cambio a 22050 Hz que quedaron sin barrer:

1. El valor por defecto de un parámetro de **reproducción** es la constante de **captura**
   (16000). Los dos llamadores actuales pasan la tasa correcta (`__main__.py:71`,
   `probar_voz.py:20`), así que hoy no hay defecto — pero es una trampa cargada: quien
   construya `Reproductor(dispositivo)` sin el segundo argumento reproducirá el audio de
   Piper un 26 % más lento y un tono por debajo, y nada avisará. El valor por defecto
   correcto es ninguno (parámetro obligatorio) o `22050`, no la tasa del micrófono.
2. El comentario "20 ms" es ahora falso: 320 muestras a 22050 Hz son **14.5 ms**. No es un
   defecto funcional (el ritmo de RMS resultante, ~69 msg/s, sobra para 60 fps), pero el
   número está desconectado de la tasa real y el comentario miente. Derivarlo:
   `int(self._tasa * 0.020)`.

Nota relacionada, ya en el ledger de la Tarea 12: el troceado reinicia la ventana de 320 en
cada chunk entrante. Como Piper entrega un `AudioChunk` por frase, en la práctica hay un
solo chunk grande por llamada y el troceado es uniforme; deja de importar.

### S6 — `probar_wakeword.py` ignora la configuración, justo el script que existe para calibrarla

`scripts/probar_wakeword.py:20,31`

```python
detector = Detector()                                  # ignora cfg.modelo_wakeword y cfg.umbral_wakeword
...
marca = "  <<< DETECTADO" if p >= 0.5 else ""          # umbral fijado a mano
```

El script cuyo propósito documentado es *"calibrar el umbral"* (y que el README lista como
el diagnóstico del wake word) no lee ni el modelo ni el umbral del `.env`. Si el usuario
apunta `MODELO_WAKEWORD` a un modelo propio —el camino que el README describe en "Cambiar la
palabra de activación"— calibra el modelo equivocado y no lo dice. Los otros seis scripts sí
usan `Config`. **Arreglo:** `Detector(cfg.modelo_wakeword, cfg.umbral_wakeword)` y comparar
contra `cfg.umbral_wakeword`.

---

## 5. Anotado

**A1 — Los dos ficheros de cableado son los únicos sin tests, y es donde están dos de los
tres bloqueantes.** `src/asistente/__main__.py` y `src/cara/__main__.py` no tienen fichero de
test. Los 18 módulos tienen cobertura excelente; las dos raíces de composición, ninguna.
M2 vive en una de ellas, y M1 en el constructor que la otra invoca. No es casualidad: es
donde los contratos entre módulos se atan, y es lo que una revisión por tarea no mira. La
auditoría manual de constructores que hizo el revisor de la Tarea 18 fue la mitigación
correcta; conviene dejarla escrita como práctica.

**A2 — El RMS está implementado dos veces.** `reproductor.py:12-17` (`calcular_rms`, recorta
a 1.0) y `vad.py:55-58` (`_energia`, no recorta) hacen el mismo cálculo sobre el mismo
formato. `MAXIMO_INT16 = 32768.0` está declarado dos veces (`reproductor.py:8`, `vad.py:6`).
Es el patrón "el mismo problema resuelto dos veces" que esta revisión buscaba; sin
consecuencia funcional, pero si algún día cambia la normalización hay que acordarse de los
dos sitios.

**A3 — Dependencias muertas.** `pyproject.toml:13` declara `websockets>=12.0` y la línea 18
`pytest-asyncio`, con `asyncio_mode = "auto"` en la línea 30. No hay un solo `async def`,
`await` ni import de `asyncio` o `websockets` en `src/`, `tests/` ni `scripts/`: son restos
del Deepgram en streaming que el plan asumía y que la Tarea 16 sustituyó por una petición
HTTP. Peso muerto en una Pi de 1 GB y una configuración de pytest que sugiere algo que no
existe.

**A4 — `ClienteLLM.reiniciar()` es API muerta.** Está declarado abstracto
(`llm/base.py:31-33`), implementado en `gemini.py:96-97`, y **nadie lo llama**. El historial
de conversación (acotado a 6 turnos, `gemini.py:191`) persiste entre despertares para
siempre. Puede ser deseable —da continuidad entre preguntas— pero es una decisión que no
está escrita en ningún sitio, y obliga a toda implementación futura de proveedor a escribir
un método que nunca se invoca.

**A5 — La boca adelanta al audio en el tiempo de buffer de salida.** `reproductor.py:61-62`
llama a `al_rms(...)` *antes* de `stream.write(trozo)`, y `write` solo bloquea cuando el
buffer de PortAudio está lleno. Es decir, la cara recibe el RMS de un trozo que aún no ha
sonado, adelantada exactamente la latencia del buffer de salida: decenas de ms en WASAPI,
potencialmente 100-200 ms con un buffer ALSA generoso en la Pi. Curiosamente compensa en
parte el retraso de M2 y el del riesgo del Hito 2 (§7). Si tras arreglar M2 la boca se ve
adelantada, esta es la causa, y el arreglo es intercambiar las dos líneas.

**A6 — Piper entrega un `AudioChunk` por frase, no sub-frase: el primer audio no empieza
hasta sintetizar la frase entera.** Como `acumular_frases` ya corta por frases, cada llamada
a `sintetizar` produce un único chunk grande. En Windows es imperceptible; en la Pi 3B, con
la voz `medium` (`.env.example:12`), sintetizar una frase de 3 s puede costar del orden de
segundos y va **en serie** delante del primer sonido. Junto con S4 es el otro gran sumando
del presupuesto de 3 s del criterio 11. Recomendación para el Hito 2: probar una voz
`es_ES-*-low` en la Pi y comparar.

**A7 — Se abre y cierra el dispositivo de salida una vez por frase.** `_decir` construye un
`sd.OutputStream` nuevo en cada llamada (`reproductor.py:44`), y el orquestador llama a
`_decir` por frase (`orquestador.py:174-178`). En Windows cuesta poco; en ALSA añade un
hueco audible entre frases y abre una ventana para que otro proceso se lleve el dispositivo
a mitad de respuesta. Vigilar en el Hito 2; si molesta, la solución es mantener el stream
abierto durante toda la respuesta.

**A8 — El estado ERROR es un quinto estado que el criterio 6 no menciona.** El criterio pide
"los cuatro estados"; el enum y `EXPRESIONES` tienen cinco. No es un problema —el diseño
describe ERROR aparte— pero conviene que quien verifique el criterio 6 sepa que ERROR se
prueba con `probar_cara.py`, no con el ciclo normal (y ver S2: hoy no se ve).

**A9 — Dos mensajes de commit en inglés** (`b9303cf`, `1709c86`), contra la norma de la
rama. Ya está en el ledger; el historial no se reescribe. Los 26 restantes cumplen.

---

## 6. Triaje de los minors diferidos del ledger

Veredicto para cada uno. "Cerrar" = no merece trabajo, se descarta conscientemente.

| # | Tarea | Hallazgo | Veredicto |
|---|---|---|---|
| 1 | 1 | `import os` sin usar en `tests/test_config.py:2` | **Arreglar ya** — verificado presente. Coste: borrar una línea. No hay razón para que sobreviva a la fusión. |
| 2 | 1 | README placeholder | **Cerrado** — resuelto; la Tarea 18 lo reescribió entero (116 líneas, completo y correcto). |
| 3 | 3 | Constante `CAMPOS` muerta en `parametros.py:3` | **Arreglar ya** — verificado: cero usos en `src/`, `tests/` y `scripts/`. Borrar. |
| 4 | 4 | Umbral 0.1 del test de parpadeo acoplado a `DURACION_PARPADEO` y a `dt=1/60` | **Diferir, con una condición**: si se aplica el arreglo del riesgo del Hito 2 (§7), este test se toca sí o sí. Rehacerlo entonces, no antes. |
| 5 | 4 | `INTERVALO_PARPADEO_LENTO` sin test cuantitativo | **Diferir** — la constante se usa en `expresiones.py:65-69` y hay test de que PENSANDO elige la rama lenta. Un test de la distribución aportaría poco. |
| 6 | 5 | Docstring dice "tres pasos" y enumera dos (`lipsync.py:12-16`) | **Arreglar ya** — verificado presente. Es una línea, y la vale: el paso que falta enumerar es exactamente el que M2 rompe. Que la documentación del módulo lo nombre ayuda a que no vuelva a perderse. |
| 7 | 5 | Un `rms` infinito envenenaría el máximo móvil permanentemente | **Cerrar** — no es alcanzable: el RMS que llega viene de `calcular_rms`, que aplica `min(1.0, ...)` sobre int16. Y `protocolo.decodificar` lo pasaría por `float()`, que sí acepta `Infinity`... pero el único emisor es el propio asistente. Riesgo teórico; no vale una guarda. |
| 8 | 5 | El máximo móvil no decae en `reposar()`, solo en `procesar()` | **Diferir** — como el máximo solo se usa mientras hay audio, y `procesar` lo hace decaer en cuanto vuelve el habla, el efecto observable es que la primera sílaba tras un silencio largo puede salir algo apagada. Menor. |
| 9 | 6 | Topes `max(1,..)`/`max(2,..)` en píxeles crudos | **Diferir** — solo importa en lienzos diminutos. 800×480 y 1920×1080 quedan lejos. |
| 10 | 6 | Literales 0.02/0.05 de la sonrisa sin constante nombrada | **Diferir** — cosmético. Si se toca `renderizador.py` por otra razón, aprovechar. |
| 11 | 6 | `test_el_lienzo_esta_centrado` no cubre `origen_y` en vertical | **Diferir** — `renderizador.py:35-36` es simétrico por construcción; el hueco de test es real pero el riesgo es nulo. |
| 12 | 7 | `import time` sin usar en `cara/__main__.py:2` | **Arreglar ya** — verificado presente (la línea 29 usa `pygame.time`, no el módulo). Borrar. |
| 13 | 7 | `SO_REUSEADDR` permite una segunda instancia en Windows | **Diferir, pero documentarlo** — es un pie de verdad: dos `python -m cara` en Windows arrancan los dos sin `EADDRINUSE` y el asistente habla con uno cualquiera, con síntomas desconcertantes. En Linux (la Pi) el comportamiento es el correcto. Una línea en el README ("un solo proceso `cara`") cuesta menos que el arreglo. |
| 14 | 7 | Los 6 tests de socket pasarían sin el lock; no cubren acumulación entre `recv` | **Diferir** — el hueco es real, pero `_atender` sí acumula en `pendiente` (`servidor.py:105`) y el `TAM_MAXIMO_BUFFER` sí tiene test. Aporta poco. |
| 15 | 7 | `main` en inglés | **Cerrar** — es idiomático de Python y lo manda el plan. No es una violación real de la norma. |
| 16 | 7 | El reintento de `accept()` no tiene backoff (`servidor.py:81`) — **marcado para triaje** | **Arreglar ya.** Verificado: el `continue` de la línea 81 vuelve directo al `accept()`. Con `EMFILE` sostenido eso es un bucle cerrado de `accept` + `logger.warning(exc_info=True)` —que además formatea una traza completa cada vuelta— quemando un núcleo de la Pi y llenando el log. La probabilidad es baja (exige fuga de descriptores) pero el arreglo es un `time.sleep(0.1)` antes del `continue`, y este proceso es precisamente el que "nunca debe morir" y debe seguir siendo barato. Coste/beneficio inmejorable. |
| 17 | 8 | `_puerto_cerrado` tiene una ventana TOCTOU teórica | **Cerrar** — es código de test, la ventana es teórica, y el margen del test ya se llevó a 2.8x medido. |
| 18 | 9 | `datos[:,0].copy()` fuera del try en `_callback` (`captura.py:30`) — **marcado para triaje** | **Diferir, con razón escrita.** Es cierto que es la única vía por la que una excepción escapa del callback de PortAudio, y que un `MemoryError` ahí es feo. Pero: (a) el bloque es de 2.5 KB, un `MemoryError` en ese punto significa que la Pi ya está perdida; (b) envolverlo obliga a decidir qué hacer sin bloque, y las dos opciones (encolar basura o no encolar) son peores que fallar; (c) si el proceso muere por OOM, el `cara` sigue vivo y parpadeando, que es lo que el diseño pide. Dejar como está y anotar el razonamiento junto al código. |
| 19 | 9 | Si `stream.close()` lanza dentro del manejo de fallo de `iniciar()`, sustituye la excepción original | **Diferir** — `captura.py:74-75`; el caso exige que fallen `start()` y `close()` a la vez. Si se toca, `with contextlib.suppress(Exception): stream.close()` lo resuelve. |
| 20 | 10 | Mensajes de commit de dos rondas en inglés | **Cerrar** — historial escrito, no se reescribe. Anotado en A9. |
| 21 | 11 | La carga del modelo ONNX no maneja errores (`detector.py:17`) | **Cerrar como diferido — ya mitigado.** `__main__.py:51-58` comprueba que el modelo existe *antes* de construir el `Detector`, y con más rigor que la propia librería. Lo que queda sin cubrir es el fichero presente pero corrupto, que sale como excepción cruda del runtime ONNX **antes de abrir el micrófono** (`__main__.py:60-66`, deliberadamente ordenado así). Fallar ruidosamente al arrancar es el comportamiento correcto. |
| 22 | 12 | El fallo del `al_rms(0.0)` terminal se traga sin log (`reproductor.py:67-68`) | **Arreglar pronto** — no bloquea, pero el argumento del ledger es bueno: si la cara está caída, el desarrollador no recibe ninguna señal. `logger.debug(..., exc_info=True)` mantiene el contrato (no lanza) y devuelve visibilidad. Coste: dos líneas. |
| 23 | 12 | `MUESTRAS_POR_TROZO=320` fijado a mano | **Promovido a S5** — el cambio a 22050 Hz lo convirtió en un comentario falso. Ver §4. |
| 24 | 12 | El troceado reinicia la ventana en cada chunk | **Cerrar** — resuelto por los hechos: Piper entrega un chunk por frase (Tarea 13), así que hay un solo chunk y el troceado es uniforme. La condición que lo hacía relevante no se da. |
| 25 | 13 | `PiperVoice.load` sin manejo de errores | **Cerrar** — mismo argumento que el #21, y con la misma mitigación previa en `__main__.py:44-49`. |
| 26 | 13 | `_VozFalsa.load` es `classmethod` y la real es `staticmethod` | **Diferir** — código de test; ambas son invocables igual. |
| 27 | 14 | `weather_code` con `Infinity` lanzaría `OverflowError` | **Cerrar** — inalcanzable con respuestas reales de Open-Meteo, y el contrato "nunca lanza" no puede blindarse contra el infinito de todos los tipos. |
| 28 | 14 | La tupla ampliada convierte errores de programación en la frase genérica sin log — **marcado para triaje** | **Arreglar pronto.** El ledger tiene razón y el arreglo que propone es el correcto: `logger.warning("fallo consultando el clima", exc_info=True)` dentro del `except` de `herramientas.py:89`. No rompe el contrato "nunca lanza", y sin él un typo en la interpolación de campos se manifiesta como "no se ha podido consultar el clima ahora mismo" para siempre, sin rastro. Es el único `except` ancho de la rama que no registra nada. |
| 29 | 14 | "cielo estado desconocido" no se lee con naturalidad | **Diferir** — cosmético y solo alcanzable con un código WMO fuera de tabla. Un `"con el cielo en un estado que no reconozco"` lo arreglaría cuando se toque. |
| 30 | 15 | `types.Content/Part` construidos fuera del try en dos sitios | **Cerrar** — el revisor de la Tarea 15 verificó con un control negativo aislado que la colocación actual sí atrapa el `ValidationError` que importaba. Lo que queda es asimetría estética. |
| 31 | 15 | Los tests acceden a `_historial` | **Diferir** — es la única forma razonable de verificar el recorte sin abrir API pública que nadie necesita. |
| 32 | 16 | Ningún test ejercita la rama `propio=True` | **Diferir** — el patrón es idéntico al de `herramientas.py`, que sí está cubierto. Riesgo bajo. |
| 33 | 16 | El informe dice "no se hizo commit" y sí existe | **Cerrar** — texto de informe obsoleto, sin efecto sobre el código. |
| 34 | 17 | `vaciar()` se llama sin guarda dentro del `except` (`orquestador.py:79`) | **Diferir** — hoy `Captura.vaciar` solo captura `queue.Empty` y no puede lanzar. Si algún día cambia, el `try` alrededor cuesta nada; anotarlo en el docstring basta por ahora. |
| 35 | 17 | La firma `(tipo, str(exc))` confunde dos bugs con misma clase y mensaje | **Cerrar** — es deduplicación de logs, no diagnóstico. La primera traza va completa. El coste del falso emparejamiento es un aviso corto donde habría ido una traza; aceptable. |
| 36 | 18 | `_wakeword_disponible` depende de `openwakeword.get_pretrained_model_paths` | **Arreglar pronto** — el ledger identifica bien la ironía: un `AttributeError` crudo desde la comprobación que existe para evitar trazas crudas. `__main__.py:33`, envuelto en `try/except AttributeError: return True` (degradar a "asumo que está y que la librería se queje ella"), cierra el caso en tres líneas. |
| 37 | 18 | El mensaje de wake word siempre sugiere `download_models()` | **Diferir** — solo desorienta a quien ya sabe que usa un modelo propio. Menor. |
| 38 | 18 | `_wakeword_disponible` es testeable y no tiene tests | **Arreglar pronto** — está ligado a A1: es la única lógica no trivial de `__main__.py`, es pura (recibe un nombre, devuelve bool), y monkeypatchear `get_pretrained_model_paths` es trivial. Tres tests cierran el hueco y de paso abren el fichero a tener tests. |

**Resumen del triaje:** 4 arreglar ya (#1, #3, #6, #12, #16 — cinco, contando el backoff de
`accept()`), 5 arreglar pronto (#22, #28, #36, #38, y #23 ya promovido a S5), 12 cerrar,
el resto diferir. Los "arreglar ya" son todos de una a tres líneas y suman menos de media
hora; conviene barrerlos en el mismo commit que los bloqueantes para que la rama no arrastre
una lista abierta a `main`.

---

## 7. Los dos elementos señalados

### 7.1 — El dictamen aparcado de la Tarea 11 (`detector.py:22`, lectura directa sin fallback)

**El dictamen se sostiene. Confírmese y ciérrese, con una corrección al razonamiento y una
sugerencia opcional.**

El código en cuestión:

```python
# detector.py:18
self._clave = list(self._modelo.models.keys())[0]
# detector.py:21-22
puntuaciones = self._modelo.predict(bloque)
return puntuaciones[self._clave] >= self._umbral
```

He verificado la librería instalada en vez de razonar sobre ella.
`.venv/Lib/site-packages/openwakeword/model.py:281-282`:

```python
predictions = {}
for mdl in self.models.keys():
```

y línea 313-314:

```python
if self.model_outputs[mdl] == 1:
    predictions[mdl] = prediction[0][0][0]
```

Es decir: para un modelo de salida única, `predict` **construye el diccionario iterando el
mismísimo `self.models` del que `__init__` sacó la clave**. El `KeyError` no es improbable:
es estructuralmente imposible. Eso refuerza el dictamen más de lo que el dictamen mismo
afirmaba.

**Corrección al razonamiento del dictamen.** El dictamen dice que el fallo "exige que
openWakeWord cambie de comportamiento". No es exacto: hay un camino alcanzable **hoy**, en
las líneas 315-317 de esa misma función:

```python
else:
    for int_label, cls in self.class_mapping[mdl].items():
        predictions[cls] = prediction[0][0][int(int_label)]
```

Con un modelo **multiclase** (`model_outputs[mdl] != 1`), `predictions` queda indexado por
etiquetas de clase, no por el nombre del modelo, y `puntuaciones[self._clave]` lanzaría
`KeyError`. Los preentrenados —`hey_jarvis` incluido— son de salida única, y los modelos
entrenados a medida con openWakeWord también lo son por defecto, así que la condición sigue
siendo remota. Pero el disparador real no es "que la librería cambie", sino "que alguien
apunte `MODELO_WAKEWORD` a un modelo multiclase" — y el README describe exactamente el
camino de apuntar `MODELO_WAKEWORD` a un modelo propio.

**Y aun así el dictamen aguanta**, por dos razones:

1. Ese `KeyError` ocurriría en el **primer bloque de audio**, es decir, a los 80 ms de
   arrancar. No es un fallo latente que aparece de madrugada: es un arranque que revienta al
   instante con una traza que nombra la clave que falta. Es precisamente el fallo ruidoso e
   inmediato que el dictamen prefiere.
2. `.get(clave, 0.0)` sería un arreglo activamente malo, y por la razón exacta que da el
   dictamen: convertiría "este modelo no encaja con este código" en "el detector nunca
   supera el umbral", que es indistinguible de un micrófono mudo o un umbral mal calibrado.
   En un detector de palabra clave ese es el peor modo de fallo posible.

**Sugerencia opcional (no bloquea).** Si en algún momento se quiere convertir la traza en un
mensaje útil, el sitio es `__init__`, no `procesar` — falla igual de alto, pero antes de
abrir el micrófono y con un mensaje que dice qué hacer:

```python
if self._modelo.model_outputs[self._clave] != 1:
    raise ValueError(
        f"El modelo '{modelo}' es multiclase; este detector espera salida única."
    )
```

Eso conserva el fallo ruidoso, lo adelanta al arranque y lo hace legible. Lo que no debe
hacerse, bajo ningún concepto, es poner un `.get` en `procesar`.

**Veredicto: dictamen ratificado. Riesgo aceptado. Cerrar el aparcamiento.**

---

### 7.2 — El riesgo del Hito 2: suavizado dependiente del framerate

**El diagnóstico es correcto, está bien acotado, y estoy de acuerdo en diferirlo al Hito 2.
Con tres precisiones que conviene anotar junto al riesgo.**

Diagnóstico verificado línea a línea:

- `parametros.py:37` — `valores[campo.name] = a + (b - a) * factor`, con `factor = SUAVIZADO`
  constante desde `cara/__main__.py:14,54`. **No recibe `dt`.**
- `lipsync.py:29-30` — `factor = ATAQUE if objetivo > self._apertura else LIBERACION`, ambas
  constantes de módulo. **No recibe `dt`.**
- Por contraste, `expresiones.py:41,57-88` — `Comportamiento.actualizar(estado, dt)` **sí**
  usa `dt` para el parpadeo y la deriva.

La asimetría es exactamente la que el ledger describe: el comportamiento "vivo" es correcto
respecto al tiempo, y la interpolación y el lipsync no. A 60 fps una transición dura ~200 ms;
a 20 fps en la Pi 3B durará ~600 ms. Confirmado.

**Precisión 1 — el problema del lipsync no es solo que vaya lento; es que además submuestrea.**
El asistente emite RMS a ~69 mensajes por segundo (22050 Hz / 320 muestras). El bucle de la
cara lee **un solo mensaje por frame** (`cara/__main__.py:46`), el último que haya llegado.
A 60 fps se pierde el 13 % de los valores y no se nota. A 20 fps la cara muestrea la
envolvente del habla a 20 Hz, quedándose con uno de cada tres y descartando los picos que
caigan entre frames. Escalar los factores por `dt` corrige el **retraso** pero no la
**pérdida de picos**: la boca irá a tiempo y seguirá saliendo apagada. Si el arreglo del
Hito 2 quiere resolverlo entero, el servidor debería acumular el máximo de los RMS recibidos
desde el último frame en vez de quedarse con el último (`servidor.py:61-63`, `_fijar`), y el
bucle consumir y resetear ese máximo. Es un cambio pequeño y encaja en el mismo commit.

**Precisión 2 — al escalar por `dt` hay que acotar el factor.** La forma correcta es
`factor = 1 - exp(-k * dt)`, o como mínimo `min(1.0, base * dt * 60)`. Sin el tope, un
frame largo aislado (un GC, una recarga de página de la SD) produce un factor > 1 y la
interpolación **sobrepasa** el objetivo y oscila. En una Pi con hipos de scheduling eso pasa.

**Precisión 3 — hay un adelanto que compensa parte del retraso, y desaparecerá al arreglarlo.**
Ver A5: `reproductor.py:61-62` emite el RMS antes de escribir el audio, así que la boca va
adelantada la latencia del buffer de salida. Hoy ese adelanto cancela parcialmente el
retraso del suavizado. Al corregir el suavizado por `dt` sin tocar lo otro, el adelanto
queda al descubierto y la boca puede pasar a ir **por delante** del audio. Los dos cambios
deben evaluarse juntos, no por separado.

**Sobre diferirlo:** de acuerdo, y por una razón que va más allá de "no toca ahora". El
factor de corrección depende del framerate real de la Pi 3B, que nadie ha medido todavía;
"escalar por `dt`" es la forma correcta precisamente porque no hay que elegir un número, pero
las tres precisiones de arriba sí piden datos reales (¿cuántos fps de verdad? ¿cuánta
latencia de buffer ALSA?). Arreglarlo hoy a ciegas en Windows, donde va a 60 fps y no se
observa ningún síntoma, sería optimizar contra una hipótesis sin forma de validarla. El
Hito 2 empieza con la Pi delante y ahí se mide en minutos.

**Condición que sí pido: que no se pierda.** Está en `progress.md`, que se cierra con esta
revisión. Conviene que quede también donde se va a leer: un comentario en `parametros.py`
sobre `interpolar` y otro en `lipsync.py` sobre `ATAQUE`/`LIBERACION`, diciendo que los
factores son por frame y asumen ~60 fps, y que hay que escalarlos por `dt` antes de portar.
Dos comentarios, y el riesgo viaja con el código que lo tiene.

**Veredicto: diagnóstico confirmado, diferimiento aprobado, con las tres precisiones
anotadas y el riesgo replicado en comentarios del código.**

---

## 8. Criterios de aceptación

Juicio sobre el código tal como está escrito. Ninguno de los ocho se ha verificado en
ejecución: el README lo declara abiertamente en su línea 99-103 (*"no se ha ejecutado
`python -m asistente` en este hito"*), y esta revisión tampoco lo ha hecho.

| # | Criterio | Juicio sobre el código |
|---|---|---|
| 1 | Despierta al oír su nombre y no con conversación de fondo | **Implementado; el margen exige hardware.** La cadena está entera y bien: `captura.py` entrega los bloques de 1280 muestras que openWakeWord espera, sin remuestrear, y `detector.py:22` compara con `cfg.umbral_wakeword`. La segunda mitad del criterio ("no despierta con conversación normal") es puramente una cuestión de calibración de umbral, y `probar_wakeword.py` existe para eso — **pero ver S6: hoy calibra con el modelo y el umbral por defecto, no con los configurados.** Arréglese antes de usarlo para calibrar. |
| 2 | Un falso positivo no produce respuesta hablada | **Se cumple en el caso puro, con una salvedad grave.** `orquestador.py:122-126` vuelve a REPOSO en silencio si `hubo_voz` es False, y `test_un_falso_positivo_no_produce_respuesta` lo cubre. Pero **M3**: la ventana en la que un falso positivo puede capturar conversación ajena y contestarla es de 12 s, no de los ~3 s del diseño. La letra del criterio se cumple; su intención, a medias. |
| 3 | Conversación completa: pregunta hablada → respuesta hablada | **Implementado de extremo a extremo.** Los 24 tests de `test_orquestador.py` recorren el ciclo con dobles. Riesgo abierto: **M1** (si Gemini cuelga, la conversación no termina nunca) y **S4** (el "thinking" por defecto puede llevar la latencia muy por encima del objetivo del diseño). |
| 4 | Una pregunta sobre el clima devuelve datos reales | **Implementado; requiere clave real para confirmar.** `herramientas.py` está sólido (Open-Meteo sin clave, contrato "nunca lanza" auditado en la Tarea 14), y `gemini.py:45-71` traduce el esquema neutro correctamente. Lo que no se puede juzgar sin ejecutar es si el modelo **decide** llamar a la herramienta y deduce bien las coordenadas: eso depende del texto de `ESQUEMA_CLIMA["descripcion"]`, que está bien redactado pero solo lo dirá la prueba. |
| 5 | Sin internet, pronuncia el mensaje de red y vuelve a reposo | **Implementado y cubierto por tests** (`test_sin_red_en_el_stt_avisa_por_voz`, `test_sin_red_en_el_llm_avisa_por_voz`). La traducción a `ErrorDeRed` está auditada en las dos fronteras. **Salvedad M1:** con el wifi *caído* (rechazo inmediato) funciona; con el wifi *colgado* (conexión medio abierta), Gemini no lanza nunca y este criterio no se alcanza. Arreglar M1 lo cierra. |
| 6 | La cara muestra los cuatro estados con transiciones suaves y parpadeo | **Implementado; pendiente de verificación visual.** Los cuatro estados están en `EXPRESIONES`, `interpolar` da las transiciones y `Comportamiento` el parpadeo y la deriva, todo con tests. Dos notas: el quinto estado ERROR no llega a verse (**S2**), y en la Pi hay que arreglar **S3** para que la pantalla completa funcione. |
| 7 | La boca se mueve de forma reconociblemente sincronizada con la voz | **No, tal como está el código.** Es **M2**: el doble suavizado deja la boca al 61 % de amplitud en habla normal y le añade ~180 ms de retraso. Se mueve, y probablemente se lea como "sincronizada" en una mirada rápida, pero el criterio dice *reconociblemente* y el diseño identifica el paso que se anula como el que decide entre parecer que habla y parecer que tiembla. **Arréglese M2 antes de someter este criterio a juicio visual**, o se juzgará un sistema peor que el diseñado. |
| 8 | La cara mantiene el framerate sin tirones, incluida la fase de red | **Bien diseñado; solo se juzga ejecutando.** La arquitectura es la correcta y por las razones correctas: proceso aparte, servidor en hilo propio (`servidor.py:47`) que no bloquea el render, `estado_actual()` con lock y sin espera, y ninguna operación de red en el bucle de dibujo. En Windows a 60 fps no debería haber discusión. En la Pi 3B es donde se decide, y ahí influyen **S3** (modo de vídeo) y el `FPS = 60` fijo. |

**No juzgables sin hardware:** el margen real del wake word (1), la latencia extremo a
extremo (3), que el LLM invoque la herramienta (4), la inteligibilidad de la voz de Piper, y
el framerate sostenido (8). Todos están en la lista de PENDIENTE MANUAL del ledger, que
sigue siendo el plan correcto.

**Recomendación de orden para el bloque manual:** arreglar primero M1, M2 y M3, y solo
entonces ejecutar la verificación de los ocho criterios. Dos de ellos (5 y 7) darían hoy un
veredicto falso, y sería un veredicto sobre un sistema que ya sabemos que no es el diseñado.

---

## Cierre

Esta rama está bien construida. Dieciocho tareas, nueve rondas de arreglo y 157 tests han
dejado un código con contratos explícitos, manejo de recursos disciplinado y razonamiento
escrito donde importa. Los tres bloqueantes no son producto de descuido: dos viven en los
únicos dos ficheros sin tests (las raíces de composición), y el tercero viene de una cifra
del plan que nadie contrastó con la tabla de errores del diseño. Es exactamente el residuo
que una revisión por tarea no puede dejar de producir, y la razón por la que existe esta
pasada.
