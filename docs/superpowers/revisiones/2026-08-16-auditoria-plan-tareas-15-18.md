# Auditoría de defectos latentes — Tasks 15-18

Alcance: `task-15-brief.md` (LLM/Gemini), `task-16-brief.md` (STT/Deepgram),
`task-17-brief.md` (Orquestador), `task-18-brief.md` (arranque + docs).
Auditoría estática, sin ejecutar nada. Se contrastó el código de referencia de
cada brief contra:

- El código ya implementado y revisado en `src/` (para comprobar contratos de
  interfaz).
- El código fuente instalado en `.venv` de `google-genai` (2.18.1) y `httpx`
  (0.28.1), para comprobar qué excepciones son realmente alcanzables.
- `task-14-brief.md` vs. `src/asistente/llm/herramientas.py` real, que muestra
  exactamente qué defecto se corrigió ahí en revisión — el mismo defecto
  reaparece, sin corregir, en el brief de la Tarea 16.

## Resumen de severidad

| # | Brief | Hallazgo | Severidad |
|---|---|---|---|
| 1 | 15 (Gemini) | `except (APIError, OSError)` no captura los errores reales de conectividad del SDK (`httpx.ConnectError`/`TimeoutException`, `UnknownApiResponseError`) | **Crítica** |
| 2 | 16 (Deepgram) | `respuesta.json()` dentro de un `try` que solo captura `httpx.HTTPError`; un 200 con cuerpo no-JSON escapa como `JSONDecodeError` | **Crítica** |
| 3 | 18 (`__main__.py`) | `captura.iniciar()` se ejecuta fuera del `try/finally` que libera el micrófono | **Alta** |
| 4 | 17 (Orquestador) | `un_ciclo()` solo atrapa `ErrorDeRed`; no hay red de seguridad si STT/LLM filtran un tipo de excepción distinto (justo lo que hacen los hallazgos 1 y 2) | **Alta** (sistémica, agrava 1 y 2) |
| 5 | 15 (Gemini) | Construcción de `types.Content`/`Part.from_function_response` tras la llamada a herramienta queda fuera del `try/except` | **Media** |
| 6 | 16 (Deepgram) | Segundo `except (KeyError, IndexError, TypeError)` no cubre `AttributeError` si `alternatives` no es una lista | **Baja-Media** |
| 7 | 18 (`__main__.py`) | `finally: captura.detener(); cara.cerrar()` — si la primera lanza, la segunda no se ejecuta | **Baja** |
| 8 | 15 (Gemini) | `_construir_herramientas()` ignora `definicion["tipo"]` y fuerza `NUMBER` para todos los parámetros | **Baja** |
| 9 | 18 (`__main__.py`) | Sin comprobación amigable de que `ruta_voz` / modelo de wake word existan antes de instanciar `Piper`/`Detector` | **Baja** |

---

## 1. Task 15 — `ClienteGemini.conversar` no cumple su propio contrato de `ErrorDeRed` (CRÍTICO)

**Ubicación:** `gemini.py`, método `_tokens`:

```python
except (genai_errors.APIError, OSError) as exc:
    raise ErrorDeRed(str(exc)) from exc
```

El docstring de `ClienteLLM.conversar` (en `base.py`) promete: *"Debe lanzar
ErrorDeRed si no hay conectividad."* Se verificó contra el código fuente
instalado de `google-genai` 2.18.1 (`.venv/Lib/site-packages/google/genai/`):

- El cliente HTTP interno de `google-genai` es **httpx** (`_api_client.py`,
  `import httpx`). Los fallos de conexión (DNS caído, wifi desconectado,
  timeout) se manifiestan como `httpx.ConnectError` / `httpx.TimeoutException`.
  El wrapper de reintentos usa `tenacity` con `reraise=True`
  (`_api_client.py:591`): agotados los reintentos, **relanza la excepción
  original de httpx tal cual**, sin envolverla en `genai_errors.APIError`.
- `httpx.HTTPError` hereda de `Exception`, no de `OSError`
  (`.venv/Lib/site-packages/httpx/_exceptions.py:74`). Por tanto
  `httpx.ConnectError` no es instancia ni de `genai_errors.APIError` ni de
  `OSError`.
- Además, si el cuerpo de un chunk del stream no es JSON válido (conexión
  cortada a mitad de respuesta, proxy cautivo, etc.), `_api_client.py:536-540`
  lanza `errors.UnknownApiResponseError`, que **hereda de `ValueError`**, no
  de `APIError` (`errors.py:319`).

Consecuencia: el escenario exacto que el propio Step 7 del brief pide
verificar a mano — *"Desconectar el wifi y preguntar produce `[sin red]`, no
una traza de error"* — es precisamente el que **no** queda cubierto. Con el
wifi desconectado, `conversar()` no lanza `ErrorDeRed`: deja escapar
`httpx.ConnectError` sin traducir. Esa excepción no es capturada por
`except ErrorDeRed` en `Orquestador.un_ciclo` (Task 17), así que sube sin
control por `ejecutar()` y tumba el proceso completo del asistente en vez de
decir el mensaje de "sin red". Esto rompe directamente el criterio de
aceptación 5 del Hito 1 listado en la Tarea 18.

**Corrección sugerida:** ampliar la tupla a
`except (genai_errors.APIError, httpx.HTTPError, genai_errors.UnknownApiResponseError, OSError)`
(o más simple, añadir `ValueError` dado que ya se envuelve todo el bloque de
interpretación de la respuesta). El `OSError` de la tupla actual es en la
práctica código muerto para esta llamada.

## 2. Task 16 — `ClienteDeepgram.transcribir`: `respuesta.json()` puede escapar sin traducir (CRÍTICO)

**Ubicación:** `deepgram.py`:

```python
try:
    respuesta = httpx.post(...)
    respuesta.raise_for_status()
    datos = respuesta.json()
except httpx.HTTPError as exc:
    raise ErrorDeRed(str(exc)) from exc
```

`raise_for_status()` solo lanza para códigos 4xx/5xx. Un 200 con cuerpo no
JSON (página HTML de un portal cautivo, proxy corporativo, respuesta
truncada) hace que `respuesta.json()` lance `json.JSONDecodeError`, que es
subclase de `ValueError`, **no** de `httpx.HTTPError`. Esa excepción escapa
de `transcribir()` sin convertirse en `ErrorDeRed`, viola el contrato
documentado en `ClienteSTT.transcribir` ("Debe lanzar ErrorDeRed si no hay
conectividad") y, como en el hallazgo 1, sube sin control por el orquestador.

Esto es exactamente el mismo defecto que ya apareció y se corrigió en la
Tarea 14 ya implementada: compárese `task-14-brief.md` (que también tenía
`except (httpx.HTTPError, KeyError, ValueError)`, faltando `TypeError` y
`AttributeError`) contra `src/asistente/llm/herramientas.py` real, donde la
tupla final es `(httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError)`.
El mismo tipo de brecha (falta `ValueError`/`json.JSONDecodeError` en la
captura de la petición HTTP) vuelve a colarse aquí, sin corregir.

**Corrección sugerida:** `except (httpx.HTTPError, ValueError):` en el primer
bloque (o separar explícitamente `except json.JSONDecodeError` además de
`httpx.HTTPError`).

Nota de severidad relativa: a diferencia del hallazgo 1, aquí el escenario
"wifi desconectado" normal **sí** queda cubierto (`httpx.ConnectError` es
subclase de `httpx.HTTPError`, que sí se captura). El hueco es solo para
respuestas 200 con cuerpo corrupto — menos frecuente que una desconexión
completa, pero real (proxies, portales cautivos, cambios de contrato de la
API).

## 3. Task 18 — `captura.iniciar()` fuera del `try/finally` que la libera (ALTA)

**Ubicación:** `src/asistente/__main__.py`, `main()`:

```python
captura = Captura(cfg.dispositivo_entrada)
captura.iniciar()                      # <- abre el stream de audio aquí

cara = CaraCliente(cfg.host_cara, cfg.puerto_cara)

orquestador = Orquestador(
    captura=captura,
    detector=detector,
    vad=DetectorSilencio(),
    stt=ClienteDeepgram(cfg.deepgram_api_key),
    llm=ClienteGemini(cfg.gemini_api_key, cfg.modelo_llm),   # <- puede lanzar
    tts=tts,
    reproductor=Reproductor(cfg.dispositivo_salida, tts.tasa_muestreo),
    cara=cara,
)

try:
    orquestador.ejecutar()
except KeyboardInterrupt:
    ...
finally:
    captura.detener()
    cara.cerrar()
```

`captura.iniciar()` abre y arranca el `sd.InputStream` (recurso del sistema
operativo) fuera de cualquier bloque protegido. Si cualquier construcción
posterior falla — la más plausible es `ClienteGemini(...)`, que instancia
`genai.Client(api_key=...)` — el `try/finally` nunca se alcanza y
`captura.detener()` no se ejecuta: el stream de micrófono queda abierto sin
que nadie lo cierre explícitamente.

Es exactamente la misma forma del defecto ya encontrado y corregido dos veces
en este mismo plan (comparar `task-9-brief.md`, que tenía
`self._stream = sd.InputStream(...); self._stream.start()` sin protección,
contra `src/asistente/audio/captura.py` real, que ya envuelve `stream.start()`
en `try/except` con `stream.close()` en el fallo). `Captura.iniciar()` ya se
protegió a sí misma; lo que falta proteger es la *secuencia de construcción*
en `__main__.py` que la rodea.

**Corrección sugerida:** mover `captura.iniciar()` para que sea la última
acción antes del `try:`, o mejor, envolver todo el ciclo de vida con
`with Captura(cfg.dispositivo_entrada) as captura:` (la clase ya soporta el
protocolo de contexto) y construir el resto de dependencias del `Orquestador`
antes de entrar en el `with`.

## 4. Task 17 — El orquestador no tiene red de seguridad ante excepciones no previstas (ALTA, sistémica)

**Ubicación:** `orquestador.py`, `un_ciclo()`:

```python
try:
    texto = self._stt.transcribir(audio)
except ErrorDeRed:
    self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
    return
...
try:
    self._responder(texto)
except ErrorDeRed:
    self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
    return
```

`ejecutar()` es `while True: self.un_ciclo()`, sin ningún `try/except`
alrededor. `__main__.py` (Task 18) solo captura `KeyboardInterrupt` alrededor
de `orquestador.ejecutar()`. El diseño del brief da por hecho que STT y LLM
"nunca lanzan nada que no sea `ErrorDeRed`" — pero los hallazgos 1 y 2 de
esta misma auditoría muestran que, tal como está escrito el código de
referencia de las Tareas 15 y 16, eso no es cierto en los escenarios de red
más comunes. El resultado combinado: una interrupción de red a mitad de
respuesta del LLM, o un proxy que devuelve una página HTML en vez de JSON
para el STT, no produce "no puedo ayudarte sin red" — tumba el proceso
completo del asistente, que se queda "pillado" hasta reiniciarlo a mano. Esto
contradice directamente el criterio de aceptación 8 de la Tarea 18: *"La cara
no se atasca en ningún momento, ni durante la espera de red."* Atascarse es
mejor que esto: aquí el proceso entero muere.

Esto encaja con el patrón "una captura demasiado estrecha para un bucle que
no debe morir" señalado en el resto de este plan (allí, un hilo en segundo
plano; aquí, el bucle principal del asistente).

**Corrección sugerida:** arreglar la causa raíz en 15 y 16 (ampliar las
tuplas de excepción) es lo prioritario. Como defensa en profundidad, dado que
el propio diseño reconoce que un proveedor de terceros es una superficie no
controlada, valdría la pena que `un_ciclo()` capture también una excepción
genérica alrededor de las fases de red (STT/LLM) y la trate igual que
`ErrorDeRed` en vez de dejarla subir — o que `ejecutar()`/`__main__.py`
capturen `Exception` a ese nivel para no morir en producción.

## 5. Task 15 — Construcción de la respuesta de función queda fuera del `try/except` (MEDIA)

**Ubicación:** `gemini.py`, `_tokens`, tras el bucle de streaming:

```python
contenidos = contenidos + [
    types.Content(
        role="model",
        parts=[types.Part(function_call=ll) for ll in llamadas],
    ),
    types.Content(
        role="user",
        parts=[
            types.Part.from_function_response(
                name=ll.name,
                response={"resultado": ejecutar(ll.name, dict(ll.args or {}))},
            )
            for ll in llamadas
        ],
    ),
]
```

Este bloque vive fuera del `try/except (genai_errors.APIError, OSError)` que
protege la llamada de streaming. `ejecutar()` (Task 14, ya implementada y
endurecida) está documentada como "nunca lanza", así que ese componente es
seguro. El riesgo está en la construcción de los objetos Pydantic del SDK
(`types.Content`, `types.Part`, `Part.from_function_response`): se verificó
en `types.py` que `FunctionCall.args` es `Optional[dict[str, Any]]`, así que
`dict(ll.args or {})` no debería fallar en el caso normal, pero si el modelo
devolviera una `function_call` sin `name`, o el SDK cambia su validación de
tipos en una versión futura, una excepción de validación aquí no sería
`ErrorDeRed` ni pasaría por la traducción del bloque de arriba. Riesgo bajo
en la práctica (el propio SDK ya generó esas estructuras a partir de una
respuesta bien formada), pero es la misma forma de bug que el patrón
"post-procesado fuera de la guarda" señalado como recurrente en este plan.

## 6. Task 16 — El segundo `except` no cubre `AttributeError` (BAJA-MEDIA)

```python
try:
    alternativas = datos["results"]["channels"][0]["alternatives"]
except (KeyError, IndexError, TypeError):
    return ""
if not alternativas:
    return ""
return alternativas[0].get("transcript", "").strip()
```

Si `alternativas` fuera, por ejemplo, una cadena no vacía en vez de una
lista (contrato de la API incumplido o cambiado), `alternativas[0]` no
lanza (indexar un string da un carácter), pero `.get(...)` sobre ese
carácter sí lanza `AttributeError`, que no está en la tupla capturada.
Probabilidad baja (requiere que Deepgram cambie la forma de su respuesta),
pero es la misma familia de defecto que el hallazgo 2.

## 7. Task 18 — Limpieza en `finally` que puede saltarse el segundo paso (BAJA)

```python
finally:
    captura.detener()
    cara.cerrar()
```

Si `captura.detener()` lanza (p. ej. `sd.PortAudioError` si el dispositivo
USB se desconectó durante la ejecución), `cara.cerrar()` no se ejecuta y el
socket hacia el proceso `cara` queda sin cerrar explícitamente. Impacto
real bajo porque el proceso termina inmediatamente después de todos modos
(el SO libera el socket), pero es la misma forma que el patrón "limpieza que
puede saltarse" señalado en el resto del plan. Bastaría envolver cada
llamada en su propio `try/except Exception: pass`, o invertir el orden y
proteger cada paso independientemente.

## 8. Task 15 — `_construir_herramientas()` ignora el campo `"tipo"` del esquema neutro (BAJA)

```python
propiedades = {
    nombre: types.Schema(
        type=types.Type.NUMBER, description=definicion["descripcion"]
    )
    for nombre, definicion in ESQUEMA_CLIMA["parametros"].items()
}
```

`ESQUEMA_CLIMA["parametros"][...]` incluye un campo `"tipo"` (verificado en
`herramientas.py` real: `{"tipo": "number", "descripcion": ...}`), pero el
traductor de Gemini lo ignora por completo y fuerza `types.Type.NUMBER` para
cualquier parámetro. Con la única herramienta actual (`latitud`, `longitud`,
ambas numéricas) no se nota. El día que se añada una herramienta con un
parámetro `"tipo": "string"`, este código seguiría anunciándolo como
`NUMBER` a Gemini sin que ningún test lo detecte — precisamente el tipo de
"esquema no consumido" que hace que cambiar de proveedor deje de ser trivial,
que es el objetivo explícito de tener `ESQUEMA_CLIMA` en formato neutro.

**Corrección sugerida:** mapear `definicion["tipo"]` (`"number"`, `"string"`,
...) al `types.Type` correspondiente en vez de asumir `NUMBER`.

## 9. Task 18 — Sin verificación amigable de archivos de modelo antes de instanciar (BAJA)

`main()` comprueba `cfg.gemini_api_key` y `cfg.deepgram_api_key`, pero no
comprueba que `cfg.ruta_voz` apunte a un archivo existente ni que el modelo
de wake word esté descargado, antes de llamar a `Piper(cfg.ruta_voz)` /
`Detector(cfg.modelo_wakeword, ...)`. El README documenta ambos como pasos
manuales de instalación fáciles de olvidar en un primer arranque. El fallo
resultante es una traza cruda de `PiperVoice.load` u `openwakeword`, en vez
de un mensaje del mismo estilo que el de las claves de API. No es un defecto
de los patrones señalados, es una oportunidad de pulido de UX de bajo coste.

---

## Tests faltantes

- **Task 15**: no existe ningún test automático para `ClienteGemini`, solo
  verificación manual (Step 7). En particular, no hay ningún test que
  simule que `self._cliente.models.generate_content_stream` lanza
  `httpx.ConnectError` o `UnknownApiResponseError` y compruebe que
  `conversar()` lo traduce a `ErrorDeRed` — ese test habría detectado el
  hallazgo 1 antes de escribir una sola línea de implementación (se puede
  hacer sin red real, monkeypatcheando el método del cliente).
- **Task 15**: no hay test de `_recordar` / recorte del historial a
  `TURNOS_DE_HISTORIAL`, pese a que el propio comentario del código lo
  describe como comportamiento deliberado ("mantiene el historial corto").
- **Task 16**: no existe ningún test automático para `ClienteDeepgram`. Un
  test con `httpx.MockTransport` que devuelva `httpx.Response(200, text="no es json")`
  y compruebe que se lanza `ErrorDeRed` habría detectado el hallazgo 2
  directamente — es el mismo patrón de test que ya existe en
  `tests/test_herramientas.py` (Task 14) para el caso HTTP 500, solo que
  falta el caso "200 con cuerpo corrupto".
- **Task 17**: la lista de 10 tests no cubre el caso "el LLM no genera
  ninguna frase sin lanzar ningún error" (`LlmFalso(frases=())`). El propio
  código de `_responder` tiene una rama explícita para esto
  (`if not hablando: self._avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)`),
  pero ningún test la ejercita.
- **Task 17**: no hay ningún test que compruebe que una excepción que no sea
  `ErrorDeRed` (p. ej. `ValueError` simulado desde `LlmFalso` o `STTFalso`)
  no tumba `un_ciclo()`. Dado el hallazgo 4, este test fallaría hoy con el
  código de referencia tal cual está escrito, y es exactamente el tipo de
  test que habría hecho visible el problema sistémico antes de integrarlo
  con proveedores reales.
- **Task 18**: `__main__.py` no es fácilmente testeable con pytest (es un
  script de arranque), así que no se espera una batería automática aquí;
  pero el hallazgo 3 (fuga del stream de audio) tampoco se detectaría con
  ningún test unitario razonable — solo con lectura de código o con una
  prueba de integración que fuerce el fallo de un constructor intermedio.

## Suposiciones sobre APIs de terceros a verificar antes de codificar

- **`google-genai` (instalado: 2.18.1, `pyproject.toml` solo exige `>=1.0`)**:
  el propio Step 5 de la Tarea 15 ya pide verificar `types.Tool`,
  `types.FunctionDeclaration`, `types.Schema`, `types.Part.from_function_response`
  y el nombre exacto del modelo — buena práctica, mantenerla. Se confirmó
  por lectura de código que las cuatro clases existen en 2.18.1 y que
  `FunctionCall.args` es `dict[str, Any]`, así que la traducción de
  `gemini.py` es compatible con la versión instalada. Lo que el Step 5 **no**
  pide verificar y debería: la jerarquía real de excepciones que puede lanzar
  `generate_content_stream()` — confirmar que `httpx.HTTPError` y
  `errors.UnknownApiResponseError` deben añadirse a la traducción a
  `ErrorDeRed` (ver hallazgo 1). Dado el salto de versión mínima declarada
  (`>=1.0`) a la instalada (2.18.1), conviene además re-verificar el nombre
  de modelo por defecto (`gemini-2.5-flash`) contra `c.models.list()` antes
  de dar el cliente por bueno.
- **`httpx` (instalado: 0.28.1, `pyproject.toml` exige `>=0.27`)**: confirmar
  que `Response.json()` sigue sin capturar internamente los errores de
  decodificación (comportamiento estable de httpx, pero vale la pena
  confirmarlo en la versión instalada) — es la base del hallazgo 2.
- **Deepgram `nova-2` + `language=es`**: el brief asume que el modelo
  `nova-2` sigue disponible y soporta español vía HTTP síncrono con
  `encoding=linear16`. Verificar contra la documentación actual de Deepgram
  antes de codificar, ya que Deepgram deprecia modelos con cierta
  regularidad (p. ej. sustitución por `nova-3`).
- **`numpy` (instalado: 2.5.2, `pyproject.toml` exige `>=1.26`)**: salto de
  versión mayor considerable. No se encontró en el código de referencia de
  las Tareas 15-18 (ni en el resto de `src/`) ningún uso de API de NumPy
  retirada en 2.x (todo son `np.zeros`, `.astype`, `np.sqrt`, `np.mean`,
  `np.concatenate`, `np.frombuffer` — estables entre 1.x y 2.x), así que no
  se identificó un problema concreto aquí, pero conviene confirmarlo si se
  amplía el uso de NumPy más adelante.

## Contratos cruzados entre tareas

- **Task 15 ← Task 14** (`ESQUEMA_CLIMA`, `ejecutar`): se comparó
  `gemini.py` contra el `herramientas.py` real (ya implementado y
  endurecido en revisión). Los nombres y la forma del diccionario
  (`nombre`, `descripcion`, `parametros` con `tipo`/`descripcion` por
  parámetro) coinciden exactamente con lo que Task 15 consume. Sin
  incidencias de contrato, más allá del hallazgo 8 (el campo `tipo` existe
  y Task 15 lo ignora).
- **Task 16 ← Task 15** (`ErrorDeRed`) y **Task 16 ← Task 9** (`TASA_MUESTREO`):
  ambos imports (`from asistente.llm.base import ErrorDeRed`,
  `from asistente.audio.captura import TASA_MUESTREO`) apuntan a símbolos que
  existen tal cual en el código de referencia de la Tarea 15 y en el
  `captura.py` real. Sin incidencias.
- **Task 17 ← Tasks 12, 13, 15, 16**: se verificaron las firmas reales contra
  los dobles de test del brief:
  - `Reproductor.reproducir(self, chunks: Iterable[bytes], al_rms: Callable[[float], None]) -> None`
    (Task 12, real) coincide con `ReproductorFalso.reproducir(self, chunks, al_rms)`
    y con la llamada real en `Orquestador._decir`.
  - `Piper.sintetizar(self, texto: str) -> Iterator[bytes]` (Task 13, real)
    coincide con `TtsFalso.sintetizar`.
  - `ClienteSTT.transcribir` / `ClienteLLM.conversar` coinciden con
    `STTFalso`/`LlmFalso` en forma y en el uso de `ErrorDeRed`.
  Sin incidencias de contrato — el problema en este eje no es de forma sino
  de robustez (hallazgo 4): el contrato "nunca lanza salvo `ErrorDeRed`" que
  Task 17 asume de Tasks 15 y 16 no se cumple tal como están escritas esas
  dos tareas.
- **Task 18 ← todo lo anterior**: se verificaron una por una las firmas de
  construcción en `__main__.py` contra las clases reales/de referencia:
  `Detector(modelo, umbral)`, `ClienteGemini(api_key, modelo)`,
  `ClienteDeepgram(api_key)`, `Reproductor(dispositivo, tasa)`,
  `CaraCliente(host, puerto)`, `Orquestador(captura=..., detector=..., vad=..., stt=..., llm=..., tts=..., reproductor=..., cara=...)`.
  Todas coinciden en orden y tipo. El único problema de esta tarea no es de
  forma sino de orden de construcción frente a limpieza (hallazgo 3).

## Zonas auditadas sin defectos

- `acumular_frases` (Task 15): la implementación y los 7 tests son
  correctos, incluido el caso límite del decimal (`18.4`), que sí se
  sitúa justo en el borde que ejercita el lookbehind negativo — sustituir o
  quitar esa parte del regex rompe el test correspondiente.
- La máquina de estados de `Orquestador.un_ciclo` (Task 17) se trazó contra
  los 10 tests uno por uno: la secuencia de estados, el manejo del falso
  positivo del wake word, y el reinicio del detector son correctos y los
  tests están bien anclados (aserciones exactas de listas, no comparaciones
  laxas que un cambio de constante pudiera seguir pasando).
- `STTFalso` (Task 16) y su interacción con `ErrorDeRed` son correctos.
