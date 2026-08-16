# Asistente de voz con cara animada en Raspberry Pi

**Fecha:** 2026-08-16
**Estado:** diseño aprobado, pendiente de plan de implementación

## Resumen

Asistente de voz tipo Alexa que corre en una Raspberry Pi, se activa por una palabra
clave personalizada, responde hablando, y muestra una cara animada en una pantalla que
reacciona al estado de la conversación: parpadea en reposo, presta atención cuando
escucha, mira hacia arriba cuando piensa, y mueve la boca sincronizada con lo que dice.

## Alcance

### Dentro de la v1

- Activación por palabra clave personalizada, detectada localmente.
- Conversación por voz: pregunta hablada → respuesta hablada.
- Una única herramienta: consulta del clima mediante API.
- Cara animada con cuatro estados y sincronía labial.
- Modo degradado sin internet.
- **Ejecución en Windows sin ningún hardware de la Pi**, como entorno de desarrollo. No es
  una maqueta ni un simulador: es el sistema completo con otros dispositivos de audio y
  vídeo.

### Fuera de la v1

- Temporizadores, alarmas, gestión de hora y fecha.
- Control de dispositivos del hogar.
- Reproducción de música.
- Pantalla táctil como entrada.
- Sincronía labial por fonemas (se usa amplitud; ver sección Lipsync).

## Entornos

El sistema se desarrolla y valida en tres entornos sucesivos. **El mismo código corre en
los tres**; solo cambia la configuración de dispositivos.

| Entorno | Equipo | Micrófono | Pantalla | Propósito |
|---|---|---|---|---|
| **Desarrollo** | PC Windows | Micrófono del PC o USB | Ventana `pygame` | Construir y depurar todo el sistema |
| **Pruebas** | Raspberry Pi 3B | MEMS I2S por GPIO | Monitor HDMI | Validar hardware real y rendimiento en el peor caso |
| **Producción** | Raspberry Pi 4B | MEMS I2S por GPIO | DSI 7" 800×480 | Uso final |

El orden importa: **todo el pipeline debe funcionar en Windows antes de tocar la Pi.** El
ciclo de edición y prueba en el PC es de segundos; en la Pi, de minutos. Cuando se llega al
hardware real, los únicos problemas que quedan son problemas de hardware, no de lógica.

Que la 3B sea el entorno de pruebas es deliberado: si el sistema va fluido en la 3B, en la
4B sobra margen.

### Requisitos de portabilidad

Estos tres puntos son lo que hace que el mismo código corra en Windows y en Linux:

1. **IPC por TCP sobre `127.0.0.1`**, no por socket Unix. Windows no soporta sockets Unix de
   forma fiable desde Python. El protocolo y la arquitectura no cambian.
2. **Captura y reproducción de audio vía `sounddevice`** (PortAudio). Habla con WASAPI en
   Windows y con ALSA en la Pi; el micrófono I2S aparece como un dispositivo ALSA normal.
   El código es el mismo, cambia el nombre del dispositivo en configuración.
3. **Renderizado con `pygame`**, en ventana durante el desarrollo y a pantalla completa en
   la Pi. El renderizador ya es independiente de la resolución (ver sección
   correspondiente), así que el cambio es una bandera de configuración.

Piper y openWakeWord distribuyen binarios para Windows y para ARM64, así que ninguno de los
dos ata el proyecto a la Pi.

## Hardware de la Pi

| Pieza | Elección | Conexión |
|---|---|---|
| Micrófono | MEMS I2S (INMP441 o equivalente) | GPIO 18 (BCLK), 19 (LRCL), 20 (DOUT) |
| Pantalla (producción) | DSI 7" 800×480 | Conector DSI |
| Pantalla (pruebas) | Monitor HDMI | HDMI |
| Altavoz | Altavoz con entrada AUX 3.5 mm | Jack 3.5 mm de la Pi |
| Mejora opcional | Adaptador de audio USB | USB → AUX del altavoz |

**Alimentación del altavoz:** desde un cargador independiente, nunca desde los puertos USB
de la Pi. El presupuesto de corriente de la Pi con pantalla y CPU en carga no admite el
consumo extra, y la caída de tensión provoca throttling y cuelgues.

**Sobre el audio de salida:** se descarta un DAC I2S (MAX98357A). La Pi tiene un único
periférico I2S y hacer convivir un micrófono I2S de entrada con un DAC I2S de salida exige
modo full-duplex con relojes compartidos. Es una fuente conocida de problemas de
configuración. La salida analógica basta para arrancar; el adaptador USB la mejora sin
tocar el I2S.

## Arquitectura

### Reparto local / nube

| Etapa | Ubicación | Razón |
|---|---|---|
| Wake word | Local | Es permanente; no puede enviarse audio continuo a la red |
| STT | Nube, en streaming | Transcribe mientras el usuario habla; en local añadiría segundos de espera |
| LLM | Nube, en streaming | Ningún modelo conversacional útil cabe en la Pi |
| TTS | Local (Piper) | Empieza a sonar sin viaje de red, y permite hablar sin internet |
| Cara | Local | Es la pantalla |

### Dos procesos

```
┌─────────────────────┐  TCP 127.0.0.1   ┌──────────────────┐
│    asistente        │  JSON por línea  │      cara        │
│                     │ ───────────────▶ │                  │
│ audio, wake word,   │                  │ bucle 30-60 fps  │
│ STT, LLM, TTS       │                  │ solo dibuja      │
└─────────────────────┘                  └──────────────────┘
```

La cara vive en su propio proceso para quedar aislada del GIL de Python y de cualquier
bloqueo de red o de audio. Un tartamudeo en la animación se percibe de inmediato; una
décima de retraso en la respuesta, no.

El wake word y la captura de audio comparten el flujo del micrófono, así que van juntos en
`asistente`. Separarlos obligaría a transportar audio entre procesos sin ganancia.

**Protocolo:** JSON delimitado por saltos de línea sobre TCP en `127.0.0.1`, puerto
configurable. Se usa TCP en lugar de socket Unix por portabilidad a Windows; el tráfico
nunca sale del equipo.

```json
{"estado": "pensando"}
{"estado": "hablando", "rms": 0.42}
{"estado": "reposo"}
```

### Flujo de datos

```
                    ┌──────────── siempre activo, local ────────────┐
  micro I2S ──▶ buffer circular ──▶ wake word ──▶ ¿detectado?
                                                      │ sí
                                                      ▼
                                              grabar hasta silencio (VAD)
                                                      │
                    ┌───────── nube ─────────┐        ▼
                    │  STT (streaming)  ◀─────────────┘
                    │      │ texto
                    │      ▼
                    │  LLM (streaming) ──▶ ¿pide clima? ──▶ API clima
                    │      │ tokens                              │
                    └──────┼──────────────────◀─────────────────┘
                           ▼  frase a frase
                    Piper (local) ──▶ chunks de audio
                           │                    │
                           │                    └──▶ RMS ──▶ cara (boca)
                           ▼
                    salida de audio ──▶ altavoz
```

**Ninguna etapa espera a que la anterior termine.** El STT transcribe mientras el usuario
habla; Piper sintetiza la primera frase mientras el LLM todavía genera la segunda. El
objetivo es ~1-1.5 s desde que el usuario calla hasta que empieza la respuesta.

El reproductor de audio alimenta dos destinos: escribe el bloque a la tarjeta de sonido y
en paralelo envía su RMS a la cara. La boca queda sincronizada con lo que suena sin
análisis de fonemas.

## Módulos e interfaces

Dentro del proceso `asistente`:

| Módulo | Responsabilidad | Interfaz |
|---|---|---|
| `audio/captura` | Abre el I2S, mantiene buffer circular | `leer_bloque() -> bytes` |
| `audio/reproductor` | Reproduce PCM y emite RMS por bloque | `reproducir(chunks, al_rms)` |
| `wake/detector` | Detecta la palabra clave | `procesar(bloque) -> bool` |
| `wake/vad` | Detecta fin de intervención | `hay_silencio(bloque) -> bool` |
| `stt/cliente` | Interfaz abstracta + implementación | `transcribir(stream) -> str` |
| `llm/cliente` | Interfaz abstracta + implementación | `conversar(msgs, tools) -> iter[str]` |
| `llm/herramientas` | Registro de herramientas | `ejecutar(nombre, args) -> str` |
| `tts/piper` | Sintetiza voz | `sintetizar(texto) -> iter[chunk]` |
| `cara_cliente` | Envía estado por el socket | `set_estado(...)` |
| `orquestador` | Máquina de estados | — |

`stt/cliente` y `llm/cliente` son **interfaces abstractas con implementaciones
intercambiables**. Cambiar de proveedor es escribir una clase nueva y ajustar la
configuración; ningún otro módulo se entera.

**Regla de aislamiento:** el orquestador no toca hardware ni red directamente, solo
interfaces. De ahí sale su testeabilidad fuera de la Pi.

## Máquina de estados

```
        ┌──────────────────────────────────────────┐
        ▼                                          │
    ┌────────┐  wake   ┌────────────┐  silencio    │
    │ REPOSO │────────▶│ ESCUCHANDO │──────────┐   │
    └────────┘         └────────────┘          ▼   │
        ▲                                 ┌──────────┐
        │                                 │ PENSANDO │
        │                                 └──────────┘
        │              ┌──────────┐             │
        └──────────────│ HABLANDO │◀────────────┘
                       └──────────┘
```

Existe además un estado ERROR, alcanzable desde PENSANDO o HABLANDO, que siempre vuelve a
REPOSO tras emitir su mensaje.

Cada transición envía el estado nuevo a la cara. HABLANDO emite además el RMS de cada
bloque de audio conforme suena.

## El renderizador de la cara

### Parámetros

La cara completa son seis números:

```
ojo_izq      0.0 – 1.0    cerrado ↔ muy abierto
ojo_der      0.0 – 1.0
pupila_x    -1.0 – 1.0    izquierda ↔ derecha
pupila_y    -1.0 – 1.0    arriba ↔ abajo
boca         0.0 – 1.0    cerrada ↔ abierta
sonrisa     -1.0 – 1.0    triste ↔ contento
```

Se dibuja proceduralmente en cada frame. No hay sprites ni animaciones pre-renderizadas.

### Interpolación

Cada estado define valores **objetivo**. El renderizador nunca salta a ellos:

```python
actual += (objetivo - actual) * 0.15   # a 60 fps ≈ 200 ms de transición
```

Las transiciones entre expresiones salen de aquí, sin animaciones escritas a mano.

### Expresiones por estado

| Estado | ojos | pupilas | sonrisa | boca |
|---|---|---|---|---|
| REPOSO | 0.85 | deriva lenta | 0.15 | 0.0 |
| ESCUCHANDO | 1.0 | centro | 0.30 | 0.0 |
| PENSANDO | 0.6 | arriba-izquierda | 0.0 | 0.0 |
| HABLANDO | 0.85 | centro | 0.20 | f(rms) |
| ERROR | 0.5 | centro | -0.30 | 0.0 |

Comportamientos que aportan la sensación de estar vivo:

- **Parpadeo:** intervalo aleatorio de 3-6 s en reposo. Los ojos bajan a 0 y vuelven en
  ~120 ms.
- **Deriva de pupilas en reposo:** cada pocos segundos elige un punto cercano al centro y
  se desplaza despacio. Sin esto la cara parece congelada.
- **En PENSANDO el parpadeo se ralentiza.** Se lee como concentración.

### Lipsync

Mapear volumen a apertura de boca directamente produce un movimiento nervioso. El proceso
correcto es de tres pasos:

1. RMS por bloque de ~20 ms del audio que está sonando.
2. Normalizar contra un máximo móvil, para que funcione igual con voz fuerte o suave.
3. **Ataque rápido, liberación lenta:** la boca abre con factor ~0.5 y cierra con ~0.15.

El tercer paso es el que hace la diferencia entre parecer que habla y parecer que tiembla.

### Independencia de resolución

El renderizador dibuja sobre un **lienzo virtual de proporción fija, centrado** en la
pantalla real, con coordenadas normalizadas escaladas a la resolución detectada. El mismo
código sirve para el monitor HDMI de pruebas (16:9) y para la pantalla DSI de producción
(800×480, 5:3) sin cambios.

### Robustez

El proceso `cara` nunca debe morir. Si el socket se cierra o `asistente` falla, pasa a
REPOSO y sigue parpadeando a la espera de reconexión. Desde fuera el asistente parece
tranquilo, no roto.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| Sin red (falla STT o LLM) | ERROR → *"No puedo ayudarte con esto hasta que estés conectado a una red"* → REPOSO |
| Red caída a media respuesta | Termina de decir lo ya sintetizado, luego el mensaje de error |
| Audio vacío o no reconocido | *"No te he entendido"* → REPOSO. **No se invoca al LLM** con texto vacío |
| Falla la API del clima | El error se devuelve al LLM como resultado de la herramienta, y el modelo lo verbaliza. Sin manejo especial |
| Timeout global (>15 s) | Corta y emite el mensaje de error |
| Falso positivo del wake word | Tras ~3 s de silencio vuelve a REPOSO **sin hablar** |

**Detección de conectividad:** no se hace sondeo periódico. El fallo se detecta por
excepción cuando ocurre, y el estado se cachea unos segundos para no reintentar en bucle
contra una red caída.

Que el TTS sea local es lo que permite comunicar el fallo de red hablando. Con un TTS en la
nube, un corte de internet dejaría al asistente mudo.

## Decisiones aplazadas

| Decisión | Estado | Impacto |
|---|---|---|
| Proveedor del LLM | Sin decidir | Aislado tras `llm/cliente`. Una clase nueva y un cambio de configuración |
| Proveedor del STT | Sin decidir | Aislado tras `stt/cliente`. Igual que el anterior |
| Palabra de activación | Sin decidir | Reentrenar el modelo del wake word, minutos de trabajo |
| API de clima concreta | Sin decidir | Aislada tras `llm/herramientas` |

**Criterios para elegir la palabra de activación:** mínimo 3-4 sílabas, fonéticamente
distintiva en español, y que no sea una palabra de uso corriente en conversación. Los
nombres compuestos ("Oye Nova") funcionan bien y reducen los falsos positivos.

## Estrategia de pruebas

Cuatro niveles, en orden estricto. No se pasa al siguiente hasta que el anterior está
verde.

| # | Nivel | Dónde | Qué valida |
|---|---|---|---|
| 1 | Orquestador con dobles | Windows, sin audio | Máquina de estados, transiciones, todos los casos de error |
| 2 | Cara aislada | Windows | Script que envía estados por el socket manualmente. Se ve la animación sin el resto del sistema |
| 3 | Pipeline completo | Windows | Conversación real de extremo a extremo, con micrófono y altavoz del PC |
| 4 | Portado a la Pi | Pi 3B + HDMI | Micrófono I2S, rendimiento y latencia en hardware real |

**Los niveles 1 a 3 no tocan la Raspberry Pi.** Al llegar al nivel 4, la lógica ya está
validada, así que cualquier fallo que aparezca es de hardware o de configuración de
dispositivos — que es exactamente lo que se quiere aislar.

**Dentro del nivel 4, el primer hito es grabar un WAV limpio del micrófono I2S** con
`arecord`, antes de ejecutar nada del proyecto. Es el punto donde más proyectos de este
tipo se atascan, y todo lo demás depende de él.

Las interfaces abstractas del diseño son lo que hace testeable el orquestador sin hardware:
al no tocar dispositivos ni red directamente, se sustituyen por dobles.

## Criterios de aceptación

### Hito 1 — Versión de desarrollo en Windows

1. El asistente despierta al oír su nombre por el micrófono del PC, y no despierta con
   conversación normal de fondo.
2. Un falso positivo no produce ninguna respuesta hablada.
3. Conversación completa funcional: pregunta hablada → respuesta hablada.
4. Una pregunta sobre el clima devuelve datos reales de la API.
5. Sin internet, el asistente pronuncia el mensaje de red y vuelve a reposo.
6. La cara muestra los cuatro estados con transiciones suaves y parpadeo en reposo.
7. La boca se mueve de forma reconociblemente sincronizada con la voz.
8. La cara mantiene su framerate sin tirones durante todo el ciclo, incluida la fase de red.

### Hito 2 — Portado a la Raspberry Pi 3B

9. El micrófono I2S graba audio limpio y reconocible con `arecord`.
10. Todos los criterios del Hito 1 se cumplen en la Pi 3B con pantalla HDMI.
11. Latencia desde que el usuario calla hasta que empieza la respuesta: ≤ 3 s en la 3B.

### Hito 3 — Producción en Raspberry Pi 4B

12. Todos los criterios anteriores se cumplen con la pantalla DSI.
13. Latencia ≤ 2 s en la 4B.
