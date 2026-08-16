# Hito 1 — Versión de desarrollo en Windows

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un asistente de voz completo y funcional en Windows: despierta al oír su nombre, escucha una pregunta, la responde hablando, consulta el clima cuando hace falta, y muestra una cara animada que reacciona a cada fase.

**Architecture:** Dos procesos Python independientes — `asistente` (audio, wake word, STT, LLM, TTS) y `cara` (renderizado) — comunicados por TCP en `127.0.0.1` con JSON delimitado por saltos de línea. Todos los servicios externos y dispositivos de hardware están detrás de interfaces abstractas, lo que hace el orquestador testeable sin audio ni red.

**Tech Stack:** Python 3.11, `sounddevice` (audio), `numpy`, `openwakeword` (palabra clave), `pygame` (renderizado), `piper-tts` (voz local), `google-genai` (LLM), `httpx` (Deepgram y Open-Meteo), `pytest`.

## Global Constraints

- **Python 3.11 o superior.** No usar sintaxis que rompa en 3.11.
- **Todo el código debe correr sin modificación en Windows y en Linux ARM.** Nada de rutas con `\` literales, nada de sockets Unix, nada de dependencias exclusivas de una plataforma.
- **IPC siempre por TCP en `127.0.0.1`.** Nunca sockets Unix.
- **El proceso `cara` nunca debe bloquear ni morir.** Ninguna operación de red, disco o audio dentro de su bucle de render.
- **El orquestador no importa `sounddevice`, `httpx`, `google-genai` ni `pygame` directamente.** Solo interfaces. Esta regla es lo que lo hace testeable.
- **Nombres de módulos, clases y funciones en español**, consistente con el resto del proyecto. Los mensajes de commit también.
- **Todo secreto va en `.env`**, nunca en el código. `.env` está en `.gitignore`.
- **Frecuencia de muestreo del audio: 16000 Hz, mono, PCM 16 bits.** Es lo que esperan openWakeWord y Deepgram. Un solo formato en todo el sistema.
- **Tamaño de bloque de audio: 1280 muestras (80 ms).** Es el que espera openWakeWord.

---

## Estructura de archivos

```
asistente-voz/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── src/
│   ├── comun/
│   │   ├── __init__.py
│   │   ├── estados.py          # enum Estado — compartido por ambos procesos
│   │   └── protocolo.py        # serialización de mensajes
│   ├── asistente/
│   │   ├── __init__.py
│   │   ├── __main__.py         # arranque del proceso
│   │   ├── config.py           # configuración desde .env
│   │   ├── cara_cliente.py     # emisor TCP hacia el proceso cara
│   │   ├── orquestador.py      # máquina de estados
│   │   ├── audio/
│   │   │   ├── __init__.py
│   │   │   ├── captura.py      # micrófono → bloques
│   │   │   └── reproductor.py  # PCM → altavoz, emite RMS
│   │   ├── wake/
│   │   │   ├── __init__.py
│   │   │   ├── detector.py     # openWakeWord
│   │   │   └── vad.py          # detección de fin de intervención
│   │   ├── stt/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # interfaz abstracta
│   │   │   └── deepgram.py     # implementación
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # interfaz abstracta
│   │   │   ├── gemini.py       # implementación
│   │   │   └── herramientas.py # registro + clima
│   │   └── tts/
│   │       ├── __init__.py
│   │       └── piper.py
│   └── cara/
│       ├── __init__.py
│       ├── __main__.py         # bucle principal pygame
│       ├── parametros.py       # los 6 valores + interpolación
│       ├── expresiones.py      # estado → parámetros objetivo
│       ├── lipsync.py          # RMS → apertura de boca
│       ├── renderizador.py     # dibujo
│       └── servidor.py         # receptor TCP
├── scripts/
│   ├── listar_dispositivos.py
│   └── probar_cara.py
└── tests/
    ├── test_protocolo.py
    ├── test_parametros.py
    ├── test_expresiones.py
    ├── test_lipsync.py
    ├── test_vad.py
    ├── test_herramientas.py
    └── test_orquestador.py
```

---

### Task 1: Andamiaje del proyecto

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`
- Create: `src/comun/__init__.py`, `src/asistente/__init__.py`, `src/cara/__init__.py`
- Create: `src/asistente/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada
- Produces: `Config` (dataclass) con `cargar() -> Config` como método de clase. Campos: `puerto_cara: int`, `host_cara: str`, `deepgram_api_key: str`, `gemini_api_key: str`, `modelo_llm: str`, `dispositivo_entrada: str | None`, `dispositivo_salida: str | None`, `pantalla_completa: bool`, `ancho: int`, `alto: int`

- [ ] **Step 1: Crear `pyproject.toml`**

```toml
[project]
name = "asistente-voz"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "sounddevice>=0.4.6",
    "numpy>=1.26",
    "openwakeword>=0.6.0",
    "pygame>=2.5",
    "piper-tts>=1.2.0",
    "google-genai>=1.0",
    "httpx>=0.27",
    "websockets>=12.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Crear `.gitignore`**

```
.env
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
.pytest_cache/
modelos/
*.onnx
*.wav
```

- [ ] **Step 3: Crear `.env.example`**

```
# Deepgram — https://console.deepgram.com
DEEPGRAM_API_KEY=

# Gemini — https://aistudio.google.com/apikey
GEMINI_API_KEY=

# Modelo del LLM. Los modelos "flash" priorizan latencia, que es lo que
# importa en un asistente de voz.
MODELO_LLM=gemini-2.5-flash

# Comunicación entre procesos
HOST_CARA=127.0.0.1
PUERTO_CARA=8765

# Dispositivos de audio. Vacío = el predeterminado del sistema.
# Usa scripts/listar_dispositivos.py para ver los nombres disponibles.
DISPOSITIVO_ENTRADA=
DISPOSITIVO_SALIDA=

# Pantalla
PANTALLA_COMPLETA=false
ANCHO=800
ALTO=480
```

- [ ] **Step 4: Crear los `__init__.py` vacíos**

Crear archivos vacíos en: `src/comun/`, `src/asistente/`, `src/asistente/audio/`, `src/asistente/wake/`, `src/asistente/stt/`, `src/asistente/llm/`, `src/asistente/tts/`, `src/cara/`

- [ ] **Step 5: Escribir el test de configuración**

```python
# tests/test_config.py
import os
from asistente.config import Config


def test_cargar_usa_valores_del_entorno(monkeypatch):
    monkeypatch.setenv("PUERTO_CARA", "9999")
    monkeypatch.setenv("MODELO_LLM", "gemini-2.5-pro")
    cfg = Config.cargar()
    assert cfg.puerto_cara == 9999
    assert cfg.modelo_llm == "gemini-2.5-pro"


def test_cargar_aplica_predeterminados(monkeypatch):
    monkeypatch.delenv("PUERTO_CARA", raising=False)
    monkeypatch.delenv("DISPOSITIVO_ENTRADA", raising=False)
    cfg = Config.cargar()
    assert cfg.puerto_cara == 8765
    assert cfg.dispositivo_entrada is None


def test_dispositivo_vacio_se_convierte_en_none(monkeypatch):
    monkeypatch.setenv("DISPOSITIVO_ENTRADA", "")
    cfg = Config.cargar()
    assert cfg.dispositivo_entrada is None
```

- [ ] **Step 6: Ejecutar el test para verificar que falla**

Run: `pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.config'`

- [ ] **Step 7: Implementar `config.py`**

```python
# src/asistente/config.py
import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _texto_o_none(valor: str | None) -> str | None:
    """Convierte cadenas vacías en None. Una variable de entorno sin valor
    y una variable ausente significan lo mismo aquí."""
    if valor is None or valor.strip() == "":
        return None
    return valor.strip()


@dataclass(frozen=True)
class Config:
    puerto_cara: int
    host_cara: str
    deepgram_api_key: str
    gemini_api_key: str
    modelo_llm: str
    dispositivo_entrada: str | None
    dispositivo_salida: str | None
    pantalla_completa: bool
    ancho: int
    alto: int

    @classmethod
    def cargar(cls) -> "Config":
        load_dotenv()
        return cls(
            puerto_cara=int(os.getenv("PUERTO_CARA", "8765")),
            host_cara=os.getenv("HOST_CARA", "127.0.0.1"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            modelo_llm=os.getenv("MODELO_LLM", "gemini-2.5-flash"),
            dispositivo_entrada=_texto_o_none(os.getenv("DISPOSITIVO_ENTRADA")),
            dispositivo_salida=_texto_o_none(os.getenv("DISPOSITIVO_SALIDA")),
            pantalla_completa=os.getenv("PANTALLA_COMPLETA", "false").lower() == "true",
            ancho=int(os.getenv("ANCHO", "800")),
            alto=int(os.getenv("ALTO", "480")),
        )
```

- [ ] **Step 8: Ejecutar los tests**

Run: `pytest tests/test_config.py -v`
Expected: 3 PASSED

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/ tests/
git commit -m "Andamiaje del proyecto y carga de configuración"
```

---

### Task 2: Estados y protocolo de comunicación

**Files:**
- Create: `src/comun/estados.py`, `src/comun/protocolo.py`
- Test: `tests/test_protocolo.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `Estado` — enum con miembros `REPOSO`, `ESCUCHANDO`, `PENSANDO`, `HABLANDO`, `ERROR`; valores en minúscula (`"reposo"`, etc.)
  - `Mensaje` — dataclass con `estado: Estado` y `rms: float = 0.0`
  - `codificar(mensaje: Mensaje) -> bytes` — devuelve JSON UTF-8 terminado en `\n`
  - `decodificar(linea: bytes) -> Mensaje` — lanza `ValueError` si la línea es inválida

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_protocolo.py
import pytest

from comun.estados import Estado
from comun.protocolo import Mensaje, codificar, decodificar


def test_ida_y_vuelta():
    original = Mensaje(estado=Estado.HABLANDO, rms=0.42)
    assert decodificar(codificar(original)) == original


def test_codificar_termina_en_salto_de_linea():
    datos = codificar(Mensaje(estado=Estado.REPOSO))
    assert datos.endswith(b"\n")
    assert b"\n" not in datos[:-1]


def test_rms_predeterminado_es_cero():
    assert Mensaje(estado=Estado.REPOSO).rms == 0.0


def test_decodificar_rechaza_json_invalido():
    with pytest.raises(ValueError):
        decodificar(b"esto no es json\n")


def test_decodificar_rechaza_estado_desconocido():
    with pytest.raises(ValueError):
        decodificar(b'{"estado": "bailando", "rms": 0.0}\n')


def test_decodificar_rechaza_mensaje_sin_estado():
    with pytest.raises(ValueError):
        decodificar(b'{"rms": 0.5}\n')
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_protocolo.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'comun.estados'`

- [ ] **Step 3: Implementar `estados.py`**

```python
# src/comun/estados.py
from enum import Enum


class Estado(str, Enum):
    """Estados del asistente. Heredar de str hace que el enum sea
    serializable a JSON directamente."""

    REPOSO = "reposo"
    ESCUCHANDO = "escuchando"
    PENSANDO = "pensando"
    HABLANDO = "hablando"
    ERROR = "error"
```

- [ ] **Step 4: Implementar `protocolo.py`**

```python
# src/comun/protocolo.py
import json
from dataclasses import dataclass

from comun.estados import Estado


@dataclass(frozen=True)
class Mensaje:
    estado: Estado
    rms: float = 0.0


def codificar(mensaje: Mensaje) -> bytes:
    payload = {"estado": mensaje.estado.value, "rms": mensaje.rms}
    return (json.dumps(payload) + "\n").encode("utf-8")


def decodificar(linea: bytes) -> Mensaje:
    try:
        payload = json.loads(linea.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"línea inválida: {linea!r}") from exc

    if not isinstance(payload, dict) or "estado" not in payload:
        raise ValueError(f"mensaje sin campo 'estado': {payload!r}")

    try:
        estado = Estado(payload["estado"])
    except ValueError as exc:
        raise ValueError(f"estado desconocido: {payload['estado']!r}") from exc

    return Mensaje(estado=estado, rms=float(payload.get("rms", 0.0)))
```

- [ ] **Step 5: Ejecutar los tests**

Run: `pytest tests/test_protocolo.py -v`
Expected: 6 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/comun/ tests/test_protocolo.py
git commit -m "Estados del asistente y protocolo de mensajes"
```

---

### Task 3: Parámetros de la cara e interpolación

**Files:**
- Create: `src/cara/parametros.py`
- Test: `tests/test_parametros.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `Parametros` — dataclass mutable con `ojo_izq`, `ojo_der`, `pupila_x`, `pupila_y`, `boca`, `sonrisa` (todos `float`)
  - `Parametros.copia() -> Parametros`
  - `interpolar(actual: Parametros, objetivo: Parametros, factor: float) -> Parametros` — devuelve un objeto nuevo, no muta

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_parametros.py
from cara.parametros import Parametros, interpolar


def test_valores_predeterminados_son_cara_neutra():
    p = Parametros()
    assert p.ojo_izq == 1.0
    assert p.ojo_der == 1.0
    assert p.pupila_x == 0.0
    assert p.pupila_y == 0.0
    assert p.boca == 0.0
    assert p.sonrisa == 0.0


def test_interpolar_se_acerca_al_objetivo():
    actual = Parametros(ojo_izq=0.0)
    objetivo = Parametros(ojo_izq=1.0)
    resultado = interpolar(actual, objetivo, 0.5)
    assert resultado.ojo_izq == 0.5


def test_interpolar_con_factor_uno_alcanza_el_objetivo():
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=0.8)
    assert interpolar(actual, objetivo, 1.0).boca == 0.8


def test_interpolar_no_muta_los_originales():
    actual = Parametros(boca=0.0)
    objetivo = Parametros(boca=1.0)
    interpolar(actual, objetivo, 0.5)
    assert actual.boca == 0.0
    assert objetivo.boca == 1.0


def test_interpolar_converge_por_repeticion():
    actual = Parametros(sonrisa=0.0)
    objetivo = Parametros(sonrisa=1.0)
    for _ in range(60):
        actual = interpolar(actual, objetivo, 0.15)
    assert actual.sonrisa > 0.99


def test_copia_es_independiente():
    p = Parametros(boca=0.5)
    c = p.copia()
    c.boca = 0.9
    assert p.boca == 0.5
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_parametros.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cara.parametros'`

- [ ] **Step 3: Implementar `parametros.py`**

```python
# src/cara/parametros.py
from dataclasses import dataclass, fields, replace

CAMPOS = ("ojo_izq", "ojo_der", "pupila_x", "pupila_y", "boca", "sonrisa")


@dataclass
class Parametros:
    """Los seis valores que definen la cara completa.

    ojo_izq / ojo_der : 0.0 cerrado, 1.0 muy abierto
    pupila_x / pupila_y : -1.0 a 1.0, desplazamiento desde el centro
    boca : 0.0 cerrada, 1.0 muy abierta
    sonrisa : -1.0 triste, 0.0 neutra, 1.0 contenta
    """

    ojo_izq: float = 1.0
    ojo_der: float = 1.0
    pupila_x: float = 0.0
    pupila_y: float = 0.0
    boca: float = 0.0
    sonrisa: float = 0.0

    def copia(self) -> "Parametros":
        return replace(self)


def interpolar(actual: Parametros, objetivo: Parametros, factor: float) -> Parametros:
    """Acerca `actual` a `objetivo` en la proporción `factor`.

    Aplicado cada frame produce transiciones suaves sin escribir animaciones
    a mano: con factor 0.15 a 60 fps, una transición completa dura ~200 ms.
    """
    valores = {}
    for campo in fields(actual):
        a = getattr(actual, campo.name)
        b = getattr(objetivo, campo.name)
        valores[campo.name] = a + (b - a) * factor
    return Parametros(**valores)
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_parametros.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/cara/parametros.py tests/test_parametros.py
git commit -m "Parámetros de la cara e interpolación suavizada"
```

---

### Task 4: Expresiones, parpadeo y deriva de pupilas

**Files:**
- Create: `src/cara/expresiones.py`
- Test: `tests/test_expresiones.py`

**Interfaces:**
- Consumes: `Estado` (Task 2), `Parametros` (Task 3)
- Produces:
  - `EXPRESIONES: dict[Estado, Parametros]` — valores objetivo por estado
  - `Comportamiento` — clase con `__init__(self, aleatorio: random.Random | None = None)` y `actualizar(self, estado: Estado, dt: float) -> Parametros`. Devuelve los parámetros objetivo del estado con parpadeo y deriva de pupilas ya aplicados.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_expresiones.py
import random

from cara.expresiones import EXPRESIONES, Comportamiento
from comun.estados import Estado


def test_todos_los_estados_tienen_expresion():
    for estado in Estado:
        assert estado in EXPRESIONES


def test_escuchando_abre_mas_los_ojos_que_pensando():
    assert EXPRESIONES[Estado.ESCUCHANDO].ojo_izq > EXPRESIONES[Estado.PENSANDO].ojo_izq


def test_pensando_mira_hacia_arriba():
    assert EXPRESIONES[Estado.PENSANDO].pupila_y < 0


def test_error_tiene_sonrisa_negativa():
    assert EXPRESIONES[Estado.ERROR].sonrisa < 0


def test_el_parpadeo_cierra_los_ojos_en_algun_momento():
    c = Comportamiento(aleatorio=random.Random(1))
    aperturas = [c.actualizar(Estado.REPOSO, 1 / 60).ojo_izq for _ in range(60 * 20)]
    assert min(aperturas) < 0.1, "en 20 segundos debería haber parpadeado"


def test_el_parpadeo_cierra_ambos_ojos_a_la_vez():
    c = Comportamiento(aleatorio=random.Random(1))
    for _ in range(60 * 20):
        p = c.actualizar(Estado.REPOSO, 1 / 60)
        assert abs(p.ojo_izq - p.ojo_der) < 1e-9


def test_las_pupilas_derivan_en_reposo():
    c = Comportamiento(aleatorio=random.Random(2))
    posiciones = {
        (round(p.pupila_x, 3), round(p.pupila_y, 3))
        for p in (c.actualizar(Estado.REPOSO, 1 / 60) for _ in range(60 * 20))
    }
    assert len(posiciones) > 1, "las pupilas deberían moverse en reposo"


def test_las_pupilas_no_derivan_al_escuchar():
    c = Comportamiento(aleatorio=random.Random(2))
    for _ in range(60 * 20):
        p = c.actualizar(Estado.ESCUCHANDO, 1 / 60)
        assert p.pupila_x == EXPRESIONES[Estado.ESCUCHANDO].pupila_x


def test_hablando_no_fija_la_boca():
    """La boca en HABLANDO la controla el lipsync, no la expresión."""
    c = Comportamiento(aleatorio=random.Random(3))
    assert c.actualizar(Estado.HABLANDO, 1 / 60).boca == 0.0
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_expresiones.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cara.expresiones'`

- [ ] **Step 3: Implementar `expresiones.py`**

```python
# src/cara/expresiones.py
import random

from cara.parametros import Parametros
from comun.estados import Estado

EXPRESIONES: dict[Estado, Parametros] = {
    Estado.REPOSO: Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.15),
    Estado.ESCUCHANDO: Parametros(ojo_izq=1.0, ojo_der=1.0, sonrisa=0.30),
    Estado.PENSANDO: Parametros(
        ojo_izq=0.6, ojo_der=0.6, pupila_x=-0.5, pupila_y=-0.6, sonrisa=0.0
    ),
    Estado.HABLANDO: Parametros(ojo_izq=0.85, ojo_der=0.85, sonrisa=0.20),
    Estado.ERROR: Parametros(ojo_izq=0.5, ojo_der=0.5, sonrisa=-0.30),
}

# Estados en los que la cara se comporta de forma "ociosa": parpadeo normal
# y pupilas que se mueven solas. Sin esto la cara parece congelada.
ESTADOS_OCIOSOS = {Estado.REPOSO}

DURACION_PARPADEO = 0.12       # segundos que tarda el ciclo completo
INTERVALO_PARPADEO = (3.0, 6.0)
INTERVALO_PARPADEO_LENTO = (7.0, 12.0)  # en PENSANDO: se lee como concentración
INTERVALO_DERIVA = (2.0, 5.0)
RADIO_DERIVA = 0.25


class Comportamiento:
    """Añade vida a la expresión base: parpadeo y deriva de pupilas.

    Mantiene estado entre frames, así que hay una única instancia viva
    durante toda la ejecución del proceso `cara`.
    """

    def __init__(self, aleatorio: random.Random | None = None) -> None:
        self._az = aleatorio or random.Random()
        self._t_parpadeo = self._az.uniform(*INTERVALO_PARPADEO)
        self._parpadeando = 0.0
        self._t_deriva = self._az.uniform(*INTERVALO_DERIVA)
        self._deriva = (0.0, 0.0)

    def actualizar(self, estado: Estado, dt: float) -> Parametros:
        base = EXPRESIONES[estado].copia()
        self._avanzar_parpadeo(estado, dt)
        self._avanzar_deriva(estado, dt)

        if self._parpadeando > 0.0:
            factor = self._factor_parpadeo()
            base.ojo_izq *= factor
            base.ojo_der *= factor

        if estado in ESTADOS_OCIOSOS:
            base.pupila_x += self._deriva[0]
            base.pupila_y += self._deriva[1]

        return base

    def _avanzar_parpadeo(self, estado: Estado, dt: float) -> None:
        if self._parpadeando > 0.0:
            self._parpadeando = max(0.0, self._parpadeando - dt)
            return

        self._t_parpadeo -= dt
        if self._t_parpadeo <= 0.0:
            self._parpadeando = DURACION_PARPADEO
            intervalo = (
                INTERVALO_PARPADEO_LENTO
                if estado is Estado.PENSANDO
                else INTERVALO_PARPADEO
            )
            self._t_parpadeo = self._az.uniform(*intervalo)

    def _factor_parpadeo(self) -> float:
        """0.0 en mitad del parpadeo, 1.0 en los extremos. Triangular."""
        mitad = DURACION_PARPADEO / 2
        distancia = abs(self._parpadeando - mitad)
        return distancia / mitad

    def _avanzar_deriva(self, estado: Estado, dt: float) -> None:
        if estado not in ESTADOS_OCIOSOS:
            self._deriva = (0.0, 0.0)
            return
        self._t_deriva -= dt
        if self._t_deriva <= 0.0:
            self._deriva = (
                self._az.uniform(-RADIO_DERIVA, RADIO_DERIVA),
                self._az.uniform(-RADIO_DERIVA, RADIO_DERIVA),
            )
            self._t_deriva = self._az.uniform(*INTERVALO_DERIVA)
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_expresiones.py -v`
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/cara/expresiones.py tests/test_expresiones.py
git commit -m "Expresiones por estado, parpadeo y deriva de pupilas"
```

---

### Task 5: Sincronía labial

**Files:**
- Create: `src/cara/lipsync.py`
- Test: `tests/test_lipsync.py`

**Interfaces:**
- Consumes: nada
- Produces: `Lipsync` — clase con `procesar(self, rms: float) -> float` (devuelve apertura 0.0–1.0) y `reposar(self) -> float` (cierra la boca progresivamente cuando no hay audio)

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_lipsync.py
from cara.lipsync import Lipsync


def test_silencio_mantiene_la_boca_cerrada():
    ls = Lipsync()
    for _ in range(50):
        assert ls.procesar(0.0) == 0.0


def test_la_boca_se_abre_con_audio():
    ls = Lipsync()
    for _ in range(10):
        apertura = ls.procesar(0.5)
    assert apertura > 0.3


def test_la_apertura_nunca_sale_del_rango():
    ls = Lipsync()
    for valor in (0.0, 0.1, 5.0, 100.0, 0.3):
        for _ in range(20):
            apertura = ls.procesar(valor)
            assert 0.0 <= apertura <= 1.0


def test_normaliza_voz_suave_y_voz_fuerte_por_igual():
    """Una voz suave sostenida debe acabar abriendo la boca tanto como una
    fuerte: el máximo móvil se adapta al nivel de la señal."""
    suave = Lipsync()
    fuerte = Lipsync()
    for _ in range(60):
        a_suave = suave.procesar(0.05)
        a_fuerte = fuerte.procesar(0.9)
    assert abs(a_suave - a_fuerte) < 0.2


def test_abre_mas_rapido_de_lo_que_cierra():
    """Ataque rápido, liberación lenta. Es lo que separa 'parece que habla'
    de 'parece que tiembla'."""
    ls = Lipsync()
    for _ in range(30):
        ls.procesar(0.8)
    pico = ls.procesar(0.8)

    apertura = pico
    pasos_para_cerrar = 0
    while apertura > pico / 2 and pasos_para_cerrar < 500:
        apertura = ls.procesar(0.0)
        pasos_para_cerrar += 1

    subida = Lipsync()
    pasos_para_abrir = 0
    apertura = 0.0
    while apertura < pico / 2 and pasos_para_abrir < 500:
        apertura = subida.procesar(0.8)
        pasos_para_abrir += 1

    assert pasos_para_abrir < pasos_para_cerrar


def test_reposar_cierra_la_boca():
    ls = Lipsync()
    for _ in range(30):
        ls.procesar(0.8)
    for _ in range(200):
        apertura = ls.reposar()
    assert apertura < 0.05
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_lipsync.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cara.lipsync'`

- [ ] **Step 3: Implementar `lipsync.py`**

```python
# src/cara/lipsync.py
ATAQUE = 0.5          # la boca abre rápido
LIBERACION = 0.15     # y cierra despacio, por inercia
DECAIMIENTO_MAXIMO = 0.999  # el máximo móvil baja lentamente
MAXIMO_MINIMO = 1e-4  # suelo para no dividir por cero en silencio
UMBRAL_SILENCIO = 1e-5


class Lipsync:
    """Convierte el volumen del audio que suena en apertura de boca.

    Mapear RMS directamente a apertura produce un movimiento nervioso.
    Los tres pasos que lo arreglan son: normalizar contra un máximo móvil
    (para que funcione igual con voz suave o fuerte), y usar constantes
    distintas para abrir y cerrar (la boca humana abre de golpe y cierra
    con inercia).
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
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_lipsync.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/cara/lipsync.py tests/test_lipsync.py
git commit -m "Sincronía labial por amplitud con ataque y liberación"
```

---

### Task 6: Renderizador de la cara

**Files:**
- Create: `src/cara/renderizador.py`
- Test: `tests/test_renderizador.py`

**Interfaces:**
- Consumes: `Parametros` (Task 3)
- Produces: `Renderizador` — clase con `__init__(self, ancho: int, alto: int)` y `dibujar(self, superficie, parametros: Parametros) -> None`

**Nota de diseño:** el renderizador dibuja sobre un **lienzo virtual cuadrado centrado** en la superficie real. Así el mismo código produce proporciones correctas en un monitor 16:9 de desarrollo y en la pantalla DSI 5:3 de producción.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_renderizador.py
import pygame
import pytest

from cara.parametros import Parametros
from cara.renderizador import Renderizador


@pytest.fixture(scope="module", autouse=True)
def pygame_headless(monkeypatch_session=None):
    import os

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    yield
    pygame.quit()


def _superficie(ancho, alto):
    return pygame.Surface((ancho, alto))


@pytest.mark.parametrize("ancho,alto", [(800, 480), (1920, 1080), (480, 800)])
def test_dibuja_sin_error_en_cualquier_resolucion(ancho, alto):
    r = Renderizador(ancho, alto)
    r.dibujar(_superficie(ancho, alto), Parametros())


def test_el_lienzo_virtual_es_cuadrado_y_cabe():
    r = Renderizador(1920, 1080)
    assert r.lado == 1080
    r2 = Renderizador(480, 800)
    assert r2.lado == 480


def test_el_lienzo_esta_centrado():
    r = Renderizador(1920, 1080)
    assert r.origen_x == (1920 - 1080) // 2
    assert r.origen_y == 0


def test_los_ojos_cerrados_pintan_menos_que_los_abiertos():
    """Comprobación indirecta pero real: con los ojos cerrados hay menos
    píxeles no-fondo que con los ojos abiertos."""
    r = Renderizador(400, 400)

    abierta = _superficie(400, 400)
    r.dibujar(abierta, Parametros(ojo_izq=1.0, ojo_der=1.0))

    cerrada = _superficie(400, 400)
    r.dibujar(cerrada, Parametros(ojo_izq=0.0, ojo_der=0.0))

    def no_fondo(sup):
        fondo = sup.get_at((0, 0))
        return sum(
            1
            for x in range(0, 400, 4)
            for y in range(0, 400, 4)
            if sup.get_at((x, y)) != fondo
        )

    assert no_fondo(abierta) > no_fondo(cerrada)


def test_la_boca_abierta_pinta_mas_que_la_cerrada():
    r = Renderizador(400, 400)

    abierta = _superficie(400, 400)
    r.dibujar(abierta, Parametros(ojo_izq=0.0, ojo_der=0.0, boca=1.0))

    cerrada = _superficie(400, 400)
    r.dibujar(cerrada, Parametros(ojo_izq=0.0, ojo_der=0.0, boca=0.0))

    def no_fondo(sup):
        fondo = sup.get_at((0, 0))
        return sum(
            1
            for x in range(0, 400, 4)
            for y in range(0, 400, 4)
            if sup.get_at((x, y)) != fondo
        )

    assert no_fondo(abierta) > no_fondo(cerrada)
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_renderizador.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cara.renderizador'`

- [ ] **Step 3: Implementar `renderizador.py`**

```python
# src/cara/renderizador.py
import pygame

from cara.parametros import Parametros

FONDO = (12, 14, 20)
COLOR_OJO = (120, 220, 255)
COLOR_PUPILA = (10, 12, 18)
COLOR_BOCA = (120, 220, 255)

# Todas las medidas son fracciones del lado del lienzo virtual, para que
# el dibujo sea idéntico a cualquier resolución.
SEPARACION_OJOS = 0.20   # distancia de cada ojo al centro horizontal
ALTURA_OJOS = 0.38       # posición vertical de los ojos
RADIO_OJO = 0.13
RADIO_PUPILA = 0.055
RECORRIDO_PUPILA = 0.05  # cuánto se desplaza la pupila dentro del ojo
ALTURA_BOCA = 0.68
ANCHO_BOCA = 0.26
ALTURA_MAX_BOCA = 0.18
GROSOR_BOCA = 0.022


class Renderizador:
    """Dibuja la cara sobre un lienzo virtual cuadrado y centrado.

    Al trabajar en coordenadas normalizadas y escalar al lado del cuadrado,
    la cara mantiene proporciones correctas en cualquier pantalla: el
    monitor 16:9 de desarrollo y la DSI 5:3 de producción.
    """

    def __init__(self, ancho: int, alto: int) -> None:
        self.ancho = ancho
        self.alto = alto
        self.lado = min(ancho, alto)
        self.origen_x = (ancho - self.lado) // 2
        self.origen_y = (alto - self.lado) // 2

    def _punto(self, x: float, y: float) -> tuple[int, int]:
        """Convierte coordenadas normalizadas (0..1) a píxeles de pantalla."""
        return (
            self.origen_x + int(x * self.lado),
            self.origen_y + int(y * self.lado),
        )

    def _escala(self, valor: float) -> int:
        return max(1, int(valor * self.lado))

    def dibujar(self, superficie: pygame.Surface, p: Parametros) -> None:
        superficie.fill(FONDO)
        self._dibujar_ojo(superficie, 0.5 - SEPARACION_OJOS, p.ojo_izq, p)
        self._dibujar_ojo(superficie, 0.5 + SEPARACION_OJOS, p.ojo_der, p)
        self._dibujar_boca(superficie, p)

    def _dibujar_ojo(
        self, superficie: pygame.Surface, cx: float, apertura: float, p: Parametros
    ) -> None:
        radio = self._escala(RADIO_OJO)
        alto_ojo = max(2, int(radio * 2 * max(0.04, apertura)))
        centro = self._punto(cx, ALTURA_OJOS)

        rect = pygame.Rect(0, 0, radio * 2, alto_ojo)
        rect.center = centro
        pygame.draw.ellipse(superficie, COLOR_OJO, rect)

        # La pupila solo se dibuja si el ojo está lo bastante abierto para
        # contenerla; si no, asoma fuera del párpado y se ve mal.
        if apertura > 0.35:
            pupila = self._punto(
                cx + p.pupila_x * RECORRIDO_PUPILA,
                ALTURA_OJOS + p.pupila_y * RECORRIDO_PUPILA,
            )
            pygame.draw.circle(
                superficie, COLOR_PUPILA, pupila, self._escala(RADIO_PUPILA)
            )

    def _dibujar_boca(self, superficie: pygame.Surface, p: Parametros) -> None:
        medio_ancho = self._escala(ANCHO_BOCA / 2)
        izq = self._punto(0.5 - ANCHO_BOCA / 2, ALTURA_BOCA)
        der = self._punto(0.5 + ANCHO_BOCA / 2, ALTURA_BOCA)
        grosor = self._escala(GROSOR_BOCA)

        alto_abertura = int(p.boca * self._escala(ALTURA_MAX_BOCA))

        if alto_abertura > grosor:
            # Boca abierta: elipse. La curva de sonrisa la desplaza vertical.
            desplazamiento = int(p.sonrisa * self._escala(0.02))
            rect = pygame.Rect(0, 0, medio_ancho * 2, alto_abertura)
            rect.center = (izq[0] + medio_ancho, izq[1] + desplazamiento)
            pygame.draw.ellipse(superficie, COLOR_BOCA, rect)
        else:
            # Boca cerrada: arco aproximado por una polilínea de 3 puntos,
            # cuya altura central marca la sonrisa.
            curva = int(-p.sonrisa * self._escala(0.05))
            centro = (izq[0] + medio_ancho, izq[1] + curva)
            pygame.draw.lines(
                superficie, COLOR_BOCA, False, [izq, centro, der], grosor
            )
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_renderizador.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/cara/renderizador.py tests/test_renderizador.py
git commit -m "Renderizador de la cara independiente de la resolución"
```

---

### Task 7: Proceso `cara` completo — primer hito visible

**Files:**
- Create: `src/cara/servidor.py`, `src/cara/__main__.py`, `scripts/probar_cara.py`
- Test: `tests/test_servidor_cara.py`

**Interfaces:**
- Consumes: `Mensaje`, `decodificar` (Task 2), `Comportamiento` (Task 4), `Lipsync` (Task 5), `Renderizador` (Task 6), `Parametros`, `interpolar` (Task 3)
- Produces: `ServidorCara` — clase con `__init__(self, host: str, puerto: int)`, `iniciar(self) -> None` (arranca un hilo en segundo plano), `estado_actual(self) -> Mensaje`, `detener(self) -> None`

**Al terminar esta tarea ves la cara en pantalla y puedes cambiarle el estado a mano.** Es el primer momento en que el proyecto es tangible.

- [ ] **Step 1: Escribir los tests del servidor**

```python
# tests/test_servidor_cara.py
import socket
import time

from cara.servidor import ServidorCara
from comun.estados import Estado
from comun.protocolo import Mensaje, codificar


def _esperar(condicion, timeout=2.0):
    limite = time.time() + timeout
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_arranca_en_reposo():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        assert servidor.estado_actual().estado is Estado.REPOSO
    finally:
        servidor.detener()


def test_recibe_un_cambio_de_estado():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(codificar(Mensaje(Estado.PENSANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.PENSANDO
            )
    finally:
        servidor.detener()


def test_recibe_varios_mensajes_en_un_solo_paquete():
    """El emisor puede mandar varias líneas juntas; el servidor debe
    procesarlas todas y quedarse con la última."""
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(
                codificar(Mensaje(Estado.ESCUCHANDO))
                + codificar(Mensaje(Estado.PENSANDO))
                + codificar(Mensaje(Estado.HABLANDO, rms=0.7))
            )
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.HABLANDO
            )
            assert servidor.estado_actual().rms == 0.7
    finally:
        servidor.detener()


def test_vuelve_a_reposo_si_el_cliente_se_desconecta():
    """Si el asistente muere, la cara no debe quedarse congelada
    'pensando' para siempre."""
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        sock = socket.create_connection(("127.0.0.1", servidor.puerto))
        sock.sendall(codificar(Mensaje(Estado.PENSANDO)))
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.PENSANDO)
        sock.close()
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.REPOSO)
    finally:
        servidor.detener()


def test_una_linea_invalida_no_tumba_el_servidor():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as sock:
            sock.sendall(b"basura sin sentido\n")
            sock.sendall(codificar(Mensaje(Estado.HABLANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.HABLANDO
            )
    finally:
        servidor.detener()


def test_acepta_una_reconexion():
    servidor = ServidorCara("127.0.0.1", 0)
    servidor.iniciar()
    try:
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as s1:
            s1.sendall(codificar(Mensaje(Estado.PENSANDO)))
            assert _esperar(lambda: servidor.estado_actual().estado is Estado.PENSANDO)
        assert _esperar(lambda: servidor.estado_actual().estado is Estado.REPOSO)
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as s2:
            s2.sendall(codificar(Mensaje(Estado.ESCUCHANDO)))
            assert _esperar(
                lambda: servidor.estado_actual().estado is Estado.ESCUCHANDO
            )
    finally:
        servidor.detener()
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_servidor_cara.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cara.servidor'`

- [ ] **Step 3: Implementar `servidor.py`**

```python
# src/cara/servidor.py
import socket
import threading

from comun.estados import Estado
from comun.protocolo import Mensaje, decodificar

REPOSO = Mensaje(Estado.REPOSO)


class ServidorCara:
    """Recibe estados del proceso `asistente` por TCP.

    Corre en un hilo aparte para que el bucle de render nunca se bloquee
    esperando en el socket. Acepta un cliente cada vez; al desconectarse,
    vuelve a REPOSO y espera al siguiente. Ninguna condición de error debe
    tumbar este servidor: la cara tiene que sobrevivir a que el asistente
    se caiga.
    """

    def __init__(self, host: str, puerto: int) -> None:
        self._host = host
        self._puerto_pedido = puerto
        self._mensaje = REPOSO
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self.puerto = puerto

    def iniciar(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._puerto_pedido))
        self._sock.listen(1)
        self._sock.settimeout(0.2)
        self.puerto = self._sock.getsockname()[1]
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def estado_actual(self) -> Mensaje:
        with self._lock:
            return self._mensaje

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
        if self._sock is not None:
            self._sock.close()

    def _fijar(self, mensaje: Mensaje) -> None:
        with self._lock:
            self._mensaje = mensaje

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                conexion, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conexion:
                self._atender(conexion)
            self._fijar(REPOSO)

    def _atender(self, conexion: socket.socket) -> None:
        conexion.settimeout(0.2)
        pendiente = b""
        while not self._parar.is_set():
            try:
                datos = conexion.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not datos:
                return
            pendiente += datos
            while b"\n" in pendiente:
                linea, pendiente = pendiente.split(b"\n", 1)
                if not linea.strip():
                    continue
                try:
                    self._fijar(decodificar(linea))
                except ValueError:
                    # Una línea corrupta se descarta. La cara sigue viva.
                    continue
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_servidor_cara.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Implementar `__main__.py` de la cara**

```python
# src/cara/__main__.py
import sys
import time

import pygame

from asistente.config import Config
from cara.expresiones import Comportamiento
from cara.lipsync import Lipsync
from cara.parametros import Parametros, interpolar
from cara.renderizador import Renderizador
from cara.servidor import ServidorCara
from comun.estados import Estado

FPS = 60
SUAVIZADO = 0.15


def main() -> int:
    cfg = Config.cargar()

    servidor = ServidorCara(cfg.host_cara, cfg.puerto_cara)
    servidor.iniciar()
    print(f"cara escuchando en {cfg.host_cara}:{servidor.puerto}")

    pygame.init()
    pygame.display.set_caption("asistente")
    banderas = pygame.FULLSCREEN if cfg.pantalla_completa else 0
    pantalla = pygame.display.set_mode((cfg.ancho, cfg.alto), banderas)
    reloj = pygame.time.Clock()

    renderizador = Renderizador(*pantalla.get_size())
    comportamiento = Comportamiento()
    lipsync = Lipsync()
    actual = Parametros()

    corriendo = True
    while corriendo:
        dt = reloj.tick(FPS) / 1000.0

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False
            elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                corriendo = False

        mensaje = servidor.estado_actual()
        objetivo = comportamiento.actualizar(mensaje.estado, dt)

        if mensaje.estado is Estado.HABLANDO:
            objetivo.boca = lipsync.procesar(mensaje.rms)
        else:
            objetivo.boca = lipsync.reposar()

        actual = interpolar(actual, objetivo, SUAVIZADO)
        renderizador.dibujar(pantalla, actual)
        pygame.display.flip()

    servidor.detener()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Implementar `scripts/probar_cara.py`**

```python
# scripts/probar_cara.py
"""Envía estados a la cara manualmente, para verla sin el resto del sistema.

Uso:
    python -m cara            (en una terminal)
    python scripts/probar_cara.py   (en otra)
"""
import math
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.config import Config  # noqa: E402
from comun.estados import Estado  # noqa: E402
from comun.protocolo import Mensaje, codificar  # noqa: E402

GUION = [
    (Estado.REPOSO, 4.0),
    (Estado.ESCUCHANDO, 3.0),
    (Estado.PENSANDO, 3.0),
    (Estado.HABLANDO, 5.0),
    (Estado.ERROR, 2.0),
]


def main() -> int:
    cfg = Config.cargar()
    with socket.create_connection((cfg.host_cara, cfg.puerto_cara)) as sock:
        for estado, duracion in GUION:
            print(f"-> {estado.value} ({duracion}s)")
            fin = time.time() + duracion
            while time.time() < fin:
                if estado is Estado.HABLANDO:
                    # Onda que imita el ritmo del habla, para ver la boca.
                    t = time.time() * 6
                    rms = abs(math.sin(t)) * (0.5 + 0.5 * abs(math.sin(t / 3)))
                else:
                    rms = 0.0
                sock.sendall(codificar(Mensaje(estado, rms=rms)))
                time.sleep(0.03)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Verificación visual manual**

En una terminal: `python -m cara`
En otra terminal: `python scripts/probar_cara.py`

Comprobar con los ojos:
- La cara aparece centrada y con proporciones correctas.
- En REPOSO parpadea cada pocos segundos y las pupilas se mueven solas.
- En ESCUCHANDO los ojos se abren más.
- En PENSANDO las pupilas miran arriba a la izquierda y el parpadeo se ralentiza.
- En HABLANDO la boca se mueve al ritmo de la onda, abriendo rápido y cerrando despacio.
- En ERROR la boca se curva hacia abajo.
- Las transiciones entre estados son suaves, sin saltos.

- [ ] **Step 8: Commit**

```bash
git add src/cara/ scripts/probar_cara.py tests/test_servidor_cara.py
git commit -m "Proceso cara completo con servidor TCP y script de prueba"
```

---

### Task 8: Cliente de la cara (lado del asistente)

**Files:**
- Create: `src/asistente/cara_cliente.py`
- Test: `tests/test_cara_cliente.py`

**Interfaces:**
- Consumes: `Mensaje`, `codificar` (Task 2), `Estado`
- Produces: `CaraCliente` — clase con `__init__(self, host: str, puerto: int)`, `set_estado(self, estado: Estado, rms: float = 0.0) -> None`, `cerrar(self) -> None`

**Regla crítica:** `set_estado` **nunca lanza excepción**. Si la cara no está corriendo, el asistente debe seguir funcionando sin ella.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_cara_cliente.py
import socket
import threading
import time

from asistente.cara_cliente import CaraCliente
from comun.estados import Estado
from comun.protocolo import decodificar


class ServidorFalso:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        self.recibidos = []
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def _bucle(self):
        try:
            conexion, _ = self.sock.accept()
        except OSError:
            return
        pendiente = b""
        with conexion:
            while True:
                try:
                    datos = conexion.recv(4096)
                except OSError:
                    return
                if not datos:
                    return
                pendiente += datos
                while b"\n" in pendiente:
                    linea, pendiente = pendiente.split(b"\n", 1)
                    if linea.strip():
                        self.recibidos.append(decodificar(linea))

    def cerrar(self):
        self.sock.close()


def _esperar(condicion, timeout=2.0):
    limite = time.time() + timeout
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_envia_el_estado():
    servidor = ServidorFalso()
    cliente = CaraCliente("127.0.0.1", servidor.puerto)
    try:
        cliente.set_estado(Estado.PENSANDO)
        assert _esperar(lambda: len(servidor.recibidos) >= 1)
        assert servidor.recibidos[0].estado is Estado.PENSANDO
    finally:
        cliente.cerrar()
        servidor.cerrar()


def test_envia_el_rms():
    servidor = ServidorFalso()
    cliente = CaraCliente("127.0.0.1", servidor.puerto)
    try:
        cliente.set_estado(Estado.HABLANDO, rms=0.65)
        assert _esperar(lambda: len(servidor.recibidos) >= 1)
        assert servidor.recibidos[0].rms == 0.65
    finally:
        cliente.cerrar()
        servidor.cerrar()


def test_no_lanza_si_no_hay_nadie_escuchando():
    """El asistente debe funcionar aunque la cara no esté arrancada."""
    cliente = CaraCliente("127.0.0.1", 1)  # puerto donde nadie escucha
    cliente.set_estado(Estado.PENSANDO)
    cliente.set_estado(Estado.HABLANDO, rms=0.5)
    cliente.cerrar()


def test_se_reconecta_cuando_la_cara_vuelve():
    cliente = CaraCliente("127.0.0.1", 1)
    cliente.set_estado(Estado.PENSANDO)  # falla en silencio

    servidor = ServidorFalso()
    cliente._puerto = servidor.puerto  # simula que la cara arrancó ahí
    try:
        assert _esperar(
            lambda: (cliente.set_estado(Estado.HABLANDO), servidor.recibidos)[1],
            timeout=3.0,
        )
    finally:
        cliente.cerrar()
        servidor.cerrar()
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_cara_cliente.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.cara_cliente'`

- [ ] **Step 3: Implementar `cara_cliente.py`**

```python
# src/asistente/cara_cliente.py
import socket
import time

from comun.estados import Estado
from comun.protocolo import Mensaje, codificar

ESPERA_RECONEXION = 1.0  # segundos entre intentos, para no martillear


class CaraCliente:
    """Envía estados al proceso `cara`.

    La cara es opcional: si no está corriendo, el asistente sigue
    funcionando sin ella. Por eso ningún método lanza excepción — un fallo
    de conexión se traga y se reintenta más tarde.
    """

    def __init__(self, host: str, puerto: int) -> None:
        self._host = host
        self._puerto = puerto
        self._sock: socket.socket | None = None
        self._proximo_intento = 0.0

    def set_estado(self, estado: Estado, rms: float = 0.0) -> None:
        if not self._asegurar_conexion():
            return
        try:
            self._sock.sendall(codificar(Mensaje(estado, rms=rms)))
        except OSError:
            self._descartar()

    def cerrar(self) -> None:
        self._descartar()

    def _asegurar_conexion(self) -> bool:
        if self._sock is not None:
            return True
        if time.monotonic() < self._proximo_intento:
            return False
        try:
            self._sock = socket.create_connection(
                (self._host, self._puerto), timeout=1.0
            )
            return True
        except OSError:
            self._sock = None
            self._proximo_intento = time.monotonic() + ESPERA_RECONEXION
            return False

    def _descartar(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._proximo_intento = time.monotonic() + ESPERA_RECONEXION
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_cara_cliente.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/asistente/cara_cliente.py tests/test_cara_cliente.py
git commit -m "Cliente de la cara con reconexión tolerante a fallos"
```

---

### Task 9: Captura de audio

**Files:**
- Create: `src/asistente/audio/captura.py`, `scripts/listar_dispositivos.py`
- Test: verificación manual (depende de hardware)

**Interfaces:**
- Consumes: nada
- Produces:
  - `TASA_MUESTREO = 16000`, `TAMANO_BLOQUE = 1280` (constantes del módulo)
  - `Captura` — clase con `__init__(self, dispositivo: str | None = None)`, `iniciar(self)`, `leer_bloque(self, timeout: float = 1.0) -> numpy.ndarray | None` (int16 mono de 1280 muestras), `detener(self)`
  - Soporta el protocolo de contexto (`with Captura() as c:`)

- [ ] **Step 1: Escribir `scripts/listar_dispositivos.py`**

```python
# scripts/listar_dispositivos.py
"""Lista los dispositivos de audio disponibles y sus índices.

Usa esto para rellenar DISPOSITIVO_ENTRADA y DISPOSITIVO_SALIDA en .env.
En la Raspberry Pi, el micrófono I2S aparecerá aquí como un dispositivo
ALSA más una vez configurado el overlay.
"""
import sounddevice as sd


def main() -> int:
    print(sd.query_devices())
    print()
    print(f"entrada predeterminada: {sd.default.device[0]}")
    print(f"salida predeterminada:  {sd.default.device[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Ejecutar el script y anotar los dispositivos**

Run: `python scripts/listar_dispositivos.py`
Expected: una tabla de dispositivos. Anotar el nombre del micrófono a usar y ponerlo en `.env` si no es el predeterminado.

- [ ] **Step 3: Implementar `captura.py`**

```python
# src/asistente/audio/captura.py
import queue

import numpy as np
import sounddevice as sd

TASA_MUESTREO = 16000
TAMANO_BLOQUE = 1280  # 80 ms — es el tamaño que espera openWakeWord
CANALES = 1
TIPO = "int16"

MAX_BLOQUES_EN_COLA = 50  # ~4 segundos; más allá se descartan los viejos


class Captura:
    """Lee del micrófono en bloques de tamaño fijo.

    `sounddevice` entrega el audio desde un hilo propio de PortAudio. Ese
    callback no puede bloquearse ni hacer trabajo pesado, así que solo
    encola. Si el consumidor se retrasa, se descartan los bloques más
    antiguos: en un asistente de voz, el audio viejo no sirve de nada.
    """

    def __init__(self, dispositivo: str | None = None) -> None:
        self._dispositivo = dispositivo
        self._cola: queue.Queue = queue.Queue(maxsize=MAX_BLOQUES_EN_COLA)
        self._stream: sd.InputStream | None = None

    def _callback(self, datos, frames, tiempo, estado) -> None:
        try:
            self._cola.put_nowait(datos[:, 0].copy())
        except queue.Full:
            try:
                self._cola.get_nowait()
                self._cola.put_nowait(datos[:, 0].copy())
            except (queue.Empty, queue.Full):
                pass

    def iniciar(self) -> None:
        self._stream = sd.InputStream(
            samplerate=TASA_MUESTREO,
            blocksize=TAMANO_BLOQUE,
            device=self._dispositivo,
            channels=CANALES,
            dtype=TIPO,
            callback=self._callback,
        )
        self._stream.start()

    def leer_bloque(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._cola.get(timeout=timeout)
        except queue.Empty:
            return None

    def vaciar(self) -> None:
        """Descarta lo acumulado. Se llama al despertar, para no procesar
        audio anterior a la palabra clave."""
        while True:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                return

    def detener(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "Captura":
        self.iniciar()
        return self

    def __exit__(self, *exc) -> None:
        self.detener()
```

- [ ] **Step 4: Verificación manual con un script temporal**

Crear `scripts/probar_microfono.py`:

```python
# scripts/probar_microfono.py
"""Graba 5 segundos y guarda prueba.wav. Verifica que el micrófono funciona."""
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from asistente.audio.captura import (  # noqa: E402
    TAMANO_BLOQUE,
    TASA_MUESTREO,
    Captura,
)
from asistente.config import Config  # noqa: E402

SEGUNDOS = 5


def main() -> int:
    cfg = Config.cargar()
    bloques_necesarios = int(SEGUNDOS * TASA_MUESTREO / TAMANO_BLOQUE)
    bloques = []

    print(f"grabando {SEGUNDOS} segundos, habla ahora...")
    with Captura(cfg.dispositivo_entrada) as captura:
        while len(bloques) < bloques_necesarios:
            bloque = captura.leer_bloque()
            if bloque is not None:
                bloques.append(bloque)

    audio = np.concatenate(bloques)
    pico = int(np.abs(audio).max())
    print(f"pico de amplitud: {pico} (de 32767)")
    if pico < 500:
        print("AVISO: señal muy débil. ¿Micrófono correcto? ¿Silenciado?")

    with wave.open("prueba.wav", "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TASA_MUESTREO)
        wav.writeframes(audio.tobytes())
    print("escrito prueba.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `python scripts/probar_microfono.py`
Expected: se crea `prueba.wav`, el pico de amplitud está muy por encima de 500, y al reproducir el archivo se oye la voz con claridad.

- [ ] **Step 5: Commit**

```bash
git add src/asistente/audio/ scripts/listar_dispositivos.py scripts/probar_microfono.py
git commit -m "Captura de audio con descarte de bloques atrasados"
```

---

### Task 10: Detección de fin de intervención (VAD)

**Files:**
- Create: `src/asistente/wake/vad.py`
- Test: `tests/test_vad.py`

**Interfaces:**
- Consumes: `TAMANO_BLOQUE`, `TASA_MUESTREO` (Task 9)
- Produces: `DetectorSilencio` — clase con `__init__(self, umbral: float = 0.02, segundos_silencio: float = 1.0, maximo_segundos: float = 12.0)`, `procesar(self, bloque: numpy.ndarray) -> bool` (True = terminó de hablar), `reiniciar(self)`, propiedad `hubo_voz: bool`

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_vad.py
import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE
from asistente.wake.vad import DetectorSilencio


def bloque_silencio():
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def bloque_voz(amplitud=8000):
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitud, TAMANO_BLOQUE)).astype(np.int16)


def test_el_silencio_inicial_no_termina_la_intervencion():
    """Si el usuario aún no ha empezado a hablar, no hay nada que cerrar."""
    vad = DetectorSilencio(segundos_silencio=0.5)
    for _ in range(50):
        assert vad.procesar(bloque_silencio()) is False


def test_termina_tras_hablar_y_callar():
    vad = DetectorSilencio(segundos_silencio=0.5)
    for _ in range(10):
        assert vad.procesar(bloque_voz()) is False
    terminado = False
    for _ in range(30):
        if vad.procesar(bloque_silencio()):
            terminado = True
            break
    assert terminado


def test_una_pausa_corta_no_termina_la_intervencion():
    vad = DetectorSilencio(segundos_silencio=1.0)
    for _ in range(10):
        vad.procesar(bloque_voz())
    for _ in range(5):  # 400 ms de pausa: menos que el umbral
        assert vad.procesar(bloque_silencio()) is False
    for _ in range(5):
        assert vad.procesar(bloque_voz()) is False


def test_hubo_voz_es_falso_si_solo_hubo_silencio():
    """Distingue un falso positivo del wake word de una pregunta real."""
    vad = DetectorSilencio()
    for _ in range(20):
        vad.procesar(bloque_silencio())
    assert vad.hubo_voz is False


def test_hubo_voz_es_verdadero_tras_hablar():
    vad = DetectorSilencio()
    for _ in range(10):
        vad.procesar(bloque_voz())
    assert vad.hubo_voz is True


def test_corta_al_llegar_al_maximo():
    """Si alguien habla sin parar, hay que cortar en algún momento."""
    vad = DetectorSilencio(maximo_segundos=1.0)
    terminado = False
    for _ in range(100):
        if vad.procesar(bloque_voz()):
            terminado = True
            break
    assert terminado


def test_reiniciar_limpia_el_estado():
    vad = DetectorSilencio()
    for _ in range(10):
        vad.procesar(bloque_voz())
    vad.reiniciar()
    assert vad.hubo_voz is False
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_vad.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.wake.vad'`

- [ ] **Step 3: Implementar `vad.py`**

```python
# src/asistente/wake/vad.py
import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE, TASA_MUESTREO

SEGUNDOS_POR_BLOQUE = TAMANO_BLOQUE / TASA_MUESTREO
MAXIMO_INT16 = 32768.0


class DetectorSilencio:
    """Decide cuándo el usuario ha terminado de hablar.

    Es un detector por energía, no un VAD entrenado: para un asistente que
    escucha a un metro de distancia en una habitación tranquila es
    suficiente, y no cuesta CPU ni añade dependencias.

    Distingue dos situaciones que parecen la misma pero no lo son: el
    usuario ha terminado de hablar (`procesar` devuelve True y `hubo_voz`
    es True), y el asistente despertó por error y nadie dijo nada
    (`hubo_voz` es False). La segunda no debe producir respuesta.
    """

    def __init__(
        self,
        umbral: float = 0.02,
        segundos_silencio: float = 1.0,
        maximo_segundos: float = 12.0,
    ) -> None:
        self._umbral = umbral
        self._bloques_silencio_necesarios = max(
            1, int(segundos_silencio / SEGUNDOS_POR_BLOQUE)
        )
        self._bloques_maximos = max(1, int(maximo_segundos / SEGUNDOS_POR_BLOQUE))
        self.reiniciar()

    def reiniciar(self) -> None:
        self._silencios = 0
        self._bloques = 0
        self.hubo_voz = False

    def procesar(self, bloque: np.ndarray) -> bool:
        self._bloques += 1
        if self._energia(bloque) >= self._umbral:
            self.hubo_voz = True
            self._silencios = 0
        else:
            self._silencios += 1

        if self._bloques >= self._bloques_maximos:
            return True
        if not self.hubo_voz:
            # Todavía no ha empezado a hablar: nada que cerrar.
            return False
        return self._silencios >= self._bloques_silencio_necesarios

    @staticmethod
    def _energia(bloque: np.ndarray) -> float:
        muestras = bloque.astype(np.float32) / MAXIMO_INT16
        return float(np.sqrt(np.mean(muestras**2)))
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_vad.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/asistente/wake/vad.py tests/test_vad.py
git commit -m "Detección de fin de intervención por energía"
```

---

### Task 11: Detector de palabra clave

**Files:**
- Create: `src/asistente/wake/detector.py`, `scripts/probar_wakeword.py`
- Test: verificación manual (el modelo es un binario externo)

**Interfaces:**
- Consumes: `TAMANO_BLOQUE` (Task 9)
- Produces: `Detector` — clase con `__init__(self, modelo: str = "hey_jarvis", umbral: float = 0.5)`, `procesar(self, bloque: numpy.ndarray) -> bool`, `reiniciar(self)`

**Nota:** el Hito 1 usa el modelo pre-entrenado `hey_jarvis` que trae openWakeWord. Entrenar un nombre personalizado es una tarea posterior, y solo cambia el valor de `modelo`.

- [ ] **Step 1: Descargar los modelos pre-entrenados**

Run: `python -c "import openwakeword.utils; openwakeword.utils.download_models()"`
Expected: descarga sin errores. Solo hace falta una vez.

- [ ] **Step 2: Verificar la superficie de la API de openWakeWord**

Run: `python -c "from openwakeword.model import Model; m = Model(wakeword_models=['hey_jarvis']); print(list(m.models.keys()))"`
Expected: imprime una lista con la clave del modelo cargado. Anotar el nombre exacto de la clave — es el que hay que usar para leer la puntuación.

- [ ] **Step 3: Implementar `detector.py`**

```python
# src/asistente/wake/detector.py
import numpy as np
from openwakeword.model import Model


class Detector:
    """Detecta la palabra de activación en el flujo de audio.

    openWakeWord mantiene estado interno entre bloques (usa una ventana
    deslizante), así que hay una única instancia viva y se le pasan los
    bloques en orden. Tras una detección hay que llamar a `reiniciar` para
    que no dispare varias veces con la misma palabra.
    """

    def __init__(self, modelo: str = "hey_jarvis", umbral: float = 0.5) -> None:
        self._umbral = umbral
        self._modelo = Model(wakeword_models=[modelo], inference_framework="onnx")
        self._clave = list(self._modelo.models.keys())[0]

    def procesar(self, bloque: np.ndarray) -> bool:
        puntuaciones = self._modelo.predict(bloque)
        return puntuaciones[self._clave] >= self._umbral

    def puntuacion(self, bloque: np.ndarray) -> float:
        """Para calibrar el umbral durante las pruebas."""
        return float(self._modelo.predict(bloque)[self._clave])

    def reiniciar(self) -> None:
        self._modelo.reset()
```

- [ ] **Step 4: Escribir `scripts/probar_wakeword.py`**

```python
# scripts/probar_wakeword.py
"""Escucha el micrófono e imprime la puntuación de la palabra clave.

Sirve para calibrar el umbral: di la palabra varias veces y mira qué
puntuaciones alcanza, luego habla normal y mira qué puntuaciones da el
ruido de fondo. El umbral debe quedar cómodamente entre ambos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.audio.captura import Captura  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.wake.detector import Detector  # noqa: E402


def main() -> int:
    cfg = Config.cargar()
    detector = Detector()
    print("escuchando. di 'hey jarvis'. Ctrl+C para salir.")

    with Captura(cfg.dispositivo_entrada) as captura:
        try:
            while True:
                bloque = captura.leer_bloque()
                if bloque is None:
                    continue
                p = detector.puntuacion(bloque)
                if p > 0.1:
                    marca = "  <<< DETECTADO" if p >= 0.5 else ""
                    print(f"{p:.3f}{marca}")
        except KeyboardInterrupt:
            print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Verificación manual y calibración**

Run: `python scripts/probar_wakeword.py`

Comprobar:
- Al decir "hey jarvis" la puntuación sube por encima de 0.5.
- Al hablar normalmente sin decirla, la puntuación se queda muy por debajo.
- Si hay falsos positivos, subir `umbral`. Si no detecta, bajarlo.

Anotar el umbral que funciona bien.

- [ ] **Step 6: Commit**

```bash
git add src/asistente/wake/detector.py scripts/probar_wakeword.py
git commit -m "Detector de palabra clave con openWakeWord"
```

---

### Task 12: Reproductor de audio con emisión de RMS

**Files:**
- Create: `src/asistente/audio/reproductor.py`
- Test: `tests/test_reproductor.py` (solo la parte de cálculo de RMS)

**Interfaces:**
- Consumes: `TASA_MUESTREO` (Task 9)
- Produces:
  - `calcular_rms(bloque: numpy.ndarray) -> float` — función pura, testeable
  - `Reproductor` — clase con `__init__(self, dispositivo: str | None = None)`, `reproducir(self, chunks: Iterable[bytes], al_rms: Callable[[float], None]) -> None`, `detener(self)`

- [ ] **Step 1: Escribir los tests de `calcular_rms`**

```python
# tests/test_reproductor.py
import numpy as np

from asistente.audio.reproductor import calcular_rms


def test_silencio_da_cero():
    assert calcular_rms(np.zeros(1000, dtype=np.int16)) == 0.0


def test_amplitud_maxima_da_uno():
    bloque = np.full(1000, 32767, dtype=np.int16)
    assert calcular_rms(bloque) > 0.99


def test_mas_amplitud_da_mas_rms():
    suave = np.full(1000, 3000, dtype=np.int16)
    fuerte = np.full(1000, 20000, dtype=np.int16)
    assert calcular_rms(fuerte) > calcular_rms(suave)


def test_resultado_siempre_en_rango():
    rng = np.random.default_rng(0)
    for amplitud in (100, 5000, 32767):
        bloque = rng.integers(-amplitud, amplitud, 1000, dtype=np.int16)
        assert 0.0 <= calcular_rms(bloque) <= 1.0


def test_bloque_vacio_da_cero():
    assert calcular_rms(np.array([], dtype=np.int16)) == 0.0
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_reproductor.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar `reproductor.py`**

```python
# src/asistente/audio/reproductor.py
from collections.abc import Callable, Iterable

import numpy as np
import sounddevice as sd

from asistente.audio.captura import TASA_MUESTREO

MAXIMO_INT16 = 32768.0
MUESTRAS_POR_TROZO = 320  # 20 ms — resolución del movimiento de boca


def calcular_rms(bloque: np.ndarray) -> float:
    """Energía del bloque, normalizada a 0.0–1.0."""
    if bloque.size == 0:
        return 0.0
    muestras = bloque.astype(np.float32) / MAXIMO_INT16
    return float(min(1.0, np.sqrt(np.mean(muestras**2))))


class Reproductor:
    """Reproduce PCM y va informando del volumen de cada trozo.

    Ese segundo trabajo es lo que sincroniza la boca de la cara con la voz:
    el mismo audio que sale por el altavoz alimenta el movimiento labial,
    así que van acompasados por construcción, sin analizar fonemas.

    Consume `chunks` perezosamente: el TTS puede ir generando mientras esto
    reproduce, que es lo que permite empezar a hablar antes de tener la
    respuesta completa.
    """

    def __init__(self, dispositivo: str | None = None) -> None:
        self._dispositivo = dispositivo
        self._cancelado = False

    def detener(self) -> None:
        self._cancelado = True

    def reproducir(
        self, chunks: Iterable[bytes], al_rms: Callable[[float], None]
    ) -> None:
        self._cancelado = False
        stream = sd.OutputStream(
            samplerate=TASA_MUESTREO,
            channels=1,
            dtype="int16",
            device=self._dispositivo,
        )
        stream.start()
        try:
            for chunk in chunks:
                if self._cancelado:
                    break
                muestras = np.frombuffer(chunk, dtype=np.int16)
                for inicio in range(0, len(muestras), MUESTRAS_POR_TROZO):
                    if self._cancelado:
                        break
                    trozo = muestras[inicio : inicio + MUESTRAS_POR_TROZO]
                    al_rms(calcular_rms(trozo))
                    stream.write(trozo)
        finally:
            al_rms(0.0)
            stream.stop()
            stream.close()
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_reproductor.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/asistente/audio/reproductor.py tests/test_reproductor.py
git commit -m "Reproductor de audio que emite RMS para la sincronía labial"
```

---

### Task 13: Síntesis de voz con Piper

**Files:**
- Create: `src/asistente/tts/piper.py`, `scripts/probar_voz.py`
- Test: verificación manual (depende del modelo de voz descargado)

**Interfaces:**
- Consumes: `TASA_MUESTREO` (Task 9)
- Produces: `Piper` — clase con `__init__(self, ruta_modelo: str)`, `sintetizar(self, texto: str) -> Iterator[bytes]` (PCM int16 a la tasa del modelo)

- [ ] **Step 1: Descargar un modelo de voz en español**

Descargar de `https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium` los dos archivos:
- `es_ES-davefx-medium.onnx`
- `es_ES-davefx-medium.onnx.json`

Guardarlos en `modelos/` (ya está en `.gitignore`).

- [ ] **Step 2: Verificar la superficie de la API de Piper**

Run: `python -c "from piper import PiperVoice; v = PiperVoice.load('modelos/es_ES-davefx-medium.onnx'); print(v.config.sample_rate)"`
Expected: imprime la tasa de muestreo del modelo (típicamente 22050). Anotarla — el reproductor tendrá que remuestrear o usar esta tasa.

- [ ] **Step 3: Añadir la ruta del modelo a la configuración**

Modificar `.env.example` añadiendo:

```
# Modelo de voz de Piper
RUTA_VOZ=modelos/es_ES-davefx-medium.onnx
```

Modificar `src/asistente/config.py`: añadir el campo `ruta_voz: str` a la dataclass (después de `modelo_llm`) y en `cargar()` añadir:

```python
ruta_voz=os.getenv("RUTA_VOZ", "modelos/es_ES-davefx-medium.onnx"),
```

- [ ] **Step 4: Implementar `piper.py`**

```python
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
        """Devuelve PCM int16 en trozos, a medida que se generan."""
        texto = texto.strip()
        if not texto:
            return
        for chunk in self._voz.synthesize_stream_raw(texto):
            yield chunk
```

- [ ] **Step 5: Escribir `scripts/probar_voz.py`**

```python
# scripts/probar_voz.py
"""Sintetiza una frase y la reproduce, mostrando el RMS por consola."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.audio.reproductor import Reproductor  # noqa: E402
from asistente.config import Config  # noqa: E402
from asistente.tts.piper import Piper  # noqa: E402

FRASE = "Hola. Soy tu asistente. Si me oyes con claridad, la voz funciona."


def main() -> int:
    cfg = Config.cargar()
    piper = Piper(cfg.ruta_voz)
    print(f"tasa de muestreo del modelo: {piper.tasa_muestreo} Hz")

    reproductor = Reproductor(cfg.dispositivo_salida)
    reproductor.reproducir(
        piper.sintetizar(FRASE),
        al_rms=lambda r: print(f"\rrms {r:.2f} {'#' * int(r * 40):<40}", end=""),
    )
    print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Ajustar el reproductor a la tasa del modelo**

Si la tasa de Piper (paso 2) no es 16000, el reproductor la está usando mal. Modificar `Reproductor.__init__` para aceptar la tasa:

```python
    def __init__(self, dispositivo: str | None = None, tasa: int = TASA_MUESTREO) -> None:
        self._dispositivo = dispositivo
        self._tasa = tasa
        self._cancelado = False
```

Y en `reproducir`, cambiar `samplerate=TASA_MUESTREO` por `samplerate=self._tasa`.

Actualizar `scripts/probar_voz.py` para pasarla: `Reproductor(cfg.dispositivo_salida, piper.tasa_muestreo)`.

- [ ] **Step 7: Verificación manual**

Run: `python scripts/probar_voz.py`
Expected: se oye la frase con claridad por el altavoz, y la barra de RMS se mueve al ritmo de la voz.

- [ ] **Step 8: Ejecutar toda la batería de tests para no haber roto nada**

Run: `pytest -v`
Expected: todos PASSED

- [ ] **Step 9: Commit**

```bash
git add src/asistente/tts/ src/asistente/audio/reproductor.py src/asistente/config.py .env.example scripts/probar_voz.py
git commit -m "Síntesis de voz local con Piper"
```

---

### Task 14: Herramienta del clima

**Files:**
- Create: `src/asistente/llm/herramientas.py`
- Test: `tests/test_herramientas.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `ESQUEMA_CLIMA: dict` — definición de la herramienta en formato de la API (campos `name`, `description`, `input_schema`)
  - `consultar_clima(latitud: float, longitud: float, cliente_http=None) -> str` — devuelve una descripción en texto
  - `ejecutar(nombre: str, argumentos: dict, cliente_http=None) -> str` — despachador; devuelve un texto de error si algo falla, **nunca lanza**

**Nota:** se usa Open-Meteo porque no requiere API key ni registro.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_herramientas.py
import httpx

from asistente.llm.herramientas import ESQUEMA_CLIMA, consultar_clima, ejecutar

RESPUESTA_OK = {
    "current": {
        "temperature_2m": 18.4,
        "apparent_temperature": 17.1,
        "relative_humidity_2m": 62,
        "wind_speed_10m": 11.2,
        "weather_code": 3,
    }
}


def _cliente(manejador):
    return httpx.Client(transport=httpx.MockTransport(manejador))


def test_el_esquema_tiene_los_campos_obligatorios():
    assert ESQUEMA_CLIMA["nombre"] == "consultar_clima"
    assert ESQUEMA_CLIMA["descripcion"]
    props = ESQUEMA_CLIMA["parametros"]
    assert set(props) == {"latitud", "longitud"}
    for definicion in props.values():
        assert definicion["tipo"] == "number"
        assert definicion["descripcion"]


def test_devuelve_la_temperatura():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "18.4" in texto


def test_describe_el_estado_del_cielo():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "nublado" in texto.lower()


def test_un_error_http_devuelve_texto_no_excepcion():
    cliente = _cliente(lambda req: httpx.Response(500))
    texto = consultar_clima(40.4, -3.7, cliente_http=cliente)
    assert "no" in texto.lower()


def test_un_fallo_de_red_devuelve_texto_no_excepcion():
    def falla(req):
        raise httpx.ConnectError("sin red")

    texto = consultar_clima(40.4, -3.7, cliente_http=_cliente(falla))
    assert "no" in texto.lower()


def test_ejecutar_despacha_a_la_herramienta():
    cliente = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK))
    texto = ejecutar(
        "consultar_clima", {"latitud": 40.4, "longitud": -3.7}, cliente_http=cliente
    )
    assert "18.4" in texto


def test_ejecutar_con_herramienta_desconocida_no_lanza():
    texto = ejecutar("volar", {})
    assert "volar" in texto


def test_ejecutar_con_argumentos_invalidos_no_lanza():
    texto = ejecutar("consultar_clima", {"latitud": "no soy un número"})
    assert isinstance(texto, str)
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_herramientas.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.llm.herramientas'`

- [ ] **Step 3: Implementar `herramientas.py`**

```python
# src/asistente/llm/herramientas.py
import httpx

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 6.0

# Descripción de la herramienta en formato neutro, no en el de ningún
# proveedor. Cada cliente de LLM la traduce al formato que espera su API.
# Así cambiar de proveedor no obliga a tocar este archivo.
ESQUEMA_CLIMA = {
    "nombre": "consultar_clima",
    "descripcion": (
        "Consulta el clima actual en unas coordenadas. Úsala siempre que el "
        "usuario pregunte por el tiempo, la temperatura, si va a llover, o si "
        "necesita abrigo o paraguas. Deduce tú las coordenadas de la ciudad "
        "que mencione el usuario."
    ),
    "parametros": {
        "latitud": {"tipo": "number", "descripcion": "Latitud en grados decimales"},
        "longitud": {"tipo": "number", "descripcion": "Longitud en grados decimales"},
    },
}

# Códigos WMO de Open-Meteo, agrupados en lo que un asistente diría en voz alta.
DESCRIPCIONES = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "con niebla",
    48: "con niebla helada",
    51: "con llovizna ligera",
    53: "con llovizna",
    55: "con llovizna intensa",
    61: "con lluvia ligera",
    63: "con lluvia",
    65: "con lluvia fuerte",
    71: "con nieve ligera",
    73: "con nieve",
    75: "con nieve intensa",
    80: "con chubascos",
    81: "con chubascos fuertes",
    82: "con chubascos muy fuertes",
    95: "con tormenta",
    96: "con tormenta y granizo",
    99: "con tormenta fuerte y granizo",
}


def consultar_clima(
    latitud: float, longitud: float, cliente_http: httpx.Client | None = None
) -> str:
    """Devuelve una descripción del clima en texto llano.

    Nunca lanza: un fallo se devuelve como texto, y el LLM lo verbaliza al
    usuario con sus propias palabras. Esto es lo que hace que no haga falta
    manejo de errores especial para las herramientas.
    """
    propio = cliente_http is None
    cliente = cliente_http or httpx.Client(timeout=TIMEOUT)
    try:
        respuesta = cliente.get(
            URL_OPEN_METEO,
            params={
                "latitude": latitud,
                "longitude": longitud,
                "current": (
                    "temperature_2m,apparent_temperature,"
                    "relative_humidity_2m,wind_speed_10m,weather_code"
                ),
            },
        )
        respuesta.raise_for_status()
        actual = respuesta.json()["current"]
    except (httpx.HTTPError, KeyError, ValueError):
        return "No se ha podido consultar el clima ahora mismo."
    finally:
        if propio:
            cliente.close()

    cielo = DESCRIPCIONES.get(int(actual.get("weather_code", -1)), "sin datos del cielo")
    return (
        f"Temperatura {actual['temperature_2m']} grados, "
        f"sensación térmica {actual['apparent_temperature']} grados, "
        f"humedad {actual['relative_humidity_2m']} por ciento, "
        f"viento {actual['wind_speed_10m']} kilómetros por hora, "
        f"cielo {cielo}."
    )


HERRAMIENTAS = [ESQUEMA_CLIMA]


def ejecutar(
    nombre: str, argumentos: dict, cliente_http: httpx.Client | None = None
) -> str:
    """Despacha una llamada de herramienta. Nunca lanza."""
    if nombre != "consultar_clima":
        return f"La herramienta '{nombre}' no existe."
    try:
        return consultar_clima(
            float(argumentos["latitud"]),
            float(argumentos["longitud"]),
            cliente_http=cliente_http,
        )
    except (KeyError, TypeError, ValueError):
        return "Faltan las coordenadas o no son válidas."
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_herramientas.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Verificación manual contra la API real**

Run: `python -c "import sys; sys.path.insert(0,'src'); from asistente.llm.herramientas import consultar_clima; print(consultar_clima(40.4168, -3.7038))"`
Expected: una frase con datos reales del clima de Madrid.

- [ ] **Step 6: Commit**

```bash
git add src/asistente/llm/herramientas.py tests/test_herramientas.py
git commit -m "Herramienta de consulta del clima con Open-Meteo"
```

---

### Task 15: Interfaz del LLM e implementación con Gemini

**Files:**
- Create: `src/asistente/llm/base.py`, `src/asistente/llm/gemini.py`
- Test: `tests/test_llm_base.py`

**Interfaces:**
- Consumes: `ESQUEMA_CLIMA`, `ejecutar` (Task 14)
- Produces:
  - `ClienteLLM` — clase base abstracta con `conversar(self, texto_usuario: str) -> Iterator[str]` que **emite frases completas**, no tokens sueltos
  - `ErrorDeRed` — excepción propia; cualquier fallo de conectividad se traduce a ella
  - `acumular_frases(tokens: Iterable[str]) -> Iterator[str]` — función pura que agrupa tokens en frases
  - `ClienteGemini(ClienteLLM)` — implementación

**Por qué emite frases y no tokens:** el TTS necesita unidades pronunciables. Sintetizar token a token da una voz entrecortada; esperar la respuesta completa mata la latencia. La frase es el punto medio correcto.

- [ ] **Step 1: Escribir los tests de `acumular_frases`**

```python
# tests/test_llm_base.py
from asistente.llm.base import acumular_frases


def test_agrupa_tokens_en_una_frase():
    assert list(acumular_frases(["Hola", " mun", "do", "."])) == ["Hola mundo."]


def test_separa_dos_frases():
    tokens = ["Hola.", " ¿Qué", " tal", "?"]
    assert list(acumular_frases(tokens)) == ["Hola.", "¿Qué tal?"]


def test_emite_el_resto_sin_puntuacion_final():
    assert list(acumular_frases(["Sin", " punto", " final"])) == ["Sin punto final"]


def test_ignora_la_entrada_vacia():
    assert list(acumular_frases([])) == []


def test_no_emite_frases_en_blanco():
    assert list(acumular_frases(["...", "   ", "Hola."])) == ["...", "Hola."]


def test_corta_por_signos_de_cierre():
    tokens = ["Uno!", " Dos?", " Tres."]
    assert list(acumular_frases(tokens)) == ["Uno!", "Dos?", "Tres."]


def test_no_corta_dentro_de_un_numero_decimal():
    """Un punto entre dígitos no cierra frase: '18.4 grados' es una sola."""
    tokens = ["Hace", " 18.4", " grados", " fuera."]
    assert list(acumular_frases(tokens)) == ["Hace 18.4 grados fuera."]
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_llm_base.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.llm.base'`

- [ ] **Step 3: Implementar `base.py`**

```python
# src/asistente/llm/base.py
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

# Cierre de frase: signo de puntuación seguido de espacio o final de texto.
# El lookbehind negativo evita cortar en decimales como "18.4".
CORTE_FRASE = re.compile(r"(?<!\d)([.!?…])(?=\s|$)")


class ErrorDeRed(Exception):
    """Cualquier fallo de conectividad, sea del proveedor que sea.

    Las implementaciones traducen sus excepciones propias a esta, para que
    el orquestador no tenga que conocer ningún SDK."""


class ClienteLLM(ABC):
    """Interfaz del cerebro del asistente.

    Cambiar de proveedor es escribir otra subclase. Ningún otro módulo del
    sistema importa un SDK de LLM.
    """

    @abstractmethod
    def conversar(self, texto_usuario: str) -> Iterator[str]:
        """Emite la respuesta como frases completas, en orden.

        Debe lanzar ErrorDeRed si no hay conectividad."""

    @abstractmethod
    def reiniciar(self) -> None:
        """Olvida el historial de la conversación."""


def acumular_frases(tokens: Iterable[str]) -> Iterator[str]:
    """Agrupa tokens sueltos en frases pronunciables.

    El TTS necesita unidades con sentido: sintetizar token a token suena
    entrecortado, y esperar la respuesta entera arruina la latencia. La
    frase es el punto medio.
    """
    buffer = ""
    for token in tokens:
        buffer += token
        while True:
            coincidencia = CORTE_FRASE.search(buffer)
            if coincidencia is None:
                break
            corte = coincidencia.end()
            frase = buffer[:corte].strip()
            buffer = buffer[corte:]
            if frase:
                yield frase
    resto = buffer.strip()
    if resto:
        yield resto
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_llm_base.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Verificar la superficie del SDK de Gemini y el modelo disponible**

El SDK `google-genai` evoluciona rápido y los nombres de modelo cambian. Antes de escribir el cliente, confirmar ambas cosas:

Run: `python -c "from google import genai; c = genai.Client(api_key='TU_CLAVE'); print([m.name for m in c.models.list()][:20])"`
Expected: una lista de modelos disponibles. Anotar el nombre exacto del modelo *flash* más reciente y ponerlo en `.env` como `MODELO_LLM` si difiere de `gemini-2.5-flash`.

Run: `python -c "from google.genai import types; print(types.Tool, types.FunctionDeclaration, types.Schema, types.Part.from_function_response)"`
Expected: imprime las cuatro referencias sin error. Si alguna falla, consultar la documentación del SDK antes de continuar.

- [ ] **Step 6: Implementar `gemini.py`**

```python
# src/asistente/llm/gemini.py
from collections.abc import Iterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from asistente.llm.base import ClienteLLM, ErrorDeRed, acumular_frases
from asistente.llm.herramientas import ESQUEMA_CLIMA, ejecutar

INSTRUCCIONES = (
    "Eres un asistente de voz doméstico. Tus respuestas se convierten en voz "
    "y se escuchan en voz alta, así que:\n"
    "- Responde en dos o tres frases como mucho. Sé directo.\n"
    "- Escribe como se habla: sin listas, sin viñetas, sin markdown, sin "
    "emojis, sin paréntesis.\n"
    "- Escribe los números y las unidades como se pronuncian.\n"
    "- Si no sabes algo, dilo en una frase y no te disculpes de más.\n"
    "- Responde siempre en español."
)

MAX_TOKENS = 400
MAX_VUELTAS_HERRAMIENTAS = 3
TURNOS_DE_HISTORIAL = 6  # 3 intercambios; suficiente para dar contexto


def _construir_herramientas() -> types.Tool:
    """Traduce el esquema neutro de `herramientas.py` al formato de Gemini.

    Esta traducción vive aquí, en el cliente del proveedor, y no en el
    módulo de herramientas: así cambiar de proveedor no obliga a tocar la
    definición de las herramientas.
    """
    propiedades = {
        nombre: types.Schema(
            type=types.Type.NUMBER, description=definicion["descripcion"]
        )
        for nombre, definicion in ESQUEMA_CLIMA["parametros"].items()
    }
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=ESQUEMA_CLIMA["nombre"],
                description=ESQUEMA_CLIMA["descripcion"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=propiedades,
                    required=list(ESQUEMA_CLIMA["parametros"]),
                ),
            )
        ]
    )


class ClienteGemini(ClienteLLM):
    """Implementación del cerebro contra la API de Gemini.

    Se desactiva la llamada automática a funciones del SDK y se maneja el
    ciclo a mano: con streaming es la única forma de emitir el texto según
    llega, que es lo que permite empezar a hablar antes de que termine la
    respuesta.
    """

    def __init__(self, api_key: str, modelo: str) -> None:
        self._cliente = genai.Client(api_key=api_key)
        self._modelo = modelo
        self._config = types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES,
            tools=[_construir_herramientas()],
            max_output_tokens=MAX_TOKENS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        self._historial: list[types.Content] = []

    def reiniciar(self) -> None:
        self._historial = []

    def conversar(self, texto_usuario: str) -> Iterator[str]:
        yield from acumular_frases(self._tokens(texto_usuario))

    def _tokens(self, texto_usuario: str) -> Iterator[str]:
        turno_usuario = types.Content(
            role="user", parts=[types.Part(text=texto_usuario)]
        )
        contenidos = self._historial + [turno_usuario]
        texto_final = ""

        for _ in range(MAX_VUELTAS_HERRAMIENTAS):
            llamadas: list[types.FunctionCall] = []
            try:
                for fragmento in self._cliente.models.generate_content_stream(
                    model=self._modelo, contents=contenidos, config=self._config
                ):
                    for parte in self._partes(fragmento):
                        if parte.text:
                            texto_final += parte.text
                            yield parte.text
                        if parte.function_call is not None:
                            llamadas.append(parte.function_call)
            except (genai_errors.APIError, OSError) as exc:
                raise ErrorDeRed(str(exc)) from exc

            if not llamadas:
                self._recordar(turno_usuario, texto_final)
                return

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
                            response={
                                "resultado": ejecutar(ll.name, dict(ll.args or {}))
                            },
                        )
                        for ll in llamadas
                    ],
                ),
            ]

        self._recordar(turno_usuario, texto_final)

    @staticmethod
    def _partes(fragmento) -> list:
        """Extrae las partes de un fragmento del stream.

        Los fragmentos pueden llegar sin candidatos o sin contenido; hay que
        comprobarlo en cada nivel o el generador revienta a mitad de una
        respuesta perfectamente válida.
        """
        candidatos = getattr(fragmento, "candidates", None) or []
        if not candidatos:
            return []
        contenido = getattr(candidatos[0], "content", None)
        if contenido is None:
            return []
        return list(getattr(contenido, "parts", None) or [])

    def _recordar(self, turno_usuario: types.Content, respuesta: str) -> None:
        """Guarda solo el texto del intercambio, no las llamadas a
        herramientas: mantiene el historial corto y evita arrastrar
        estructuras que el proveedor podría dejar de aceptar."""
        if not respuesta.strip():
            return
        self._historial.append(turno_usuario)
        self._historial.append(
            types.Content(role="model", parts=[types.Part(text=respuesta)])
        )
        self._historial = self._historial[-TURNOS_DE_HISTORIAL:]
```

- [ ] **Step 7: Verificación manual contra la API real**

Crear `scripts/probar_llm.py`:

```python
# scripts/probar_llm.py
"""Conversa por teclado con el LLM, para validarlo sin audio de por medio."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.config import Config  # noqa: E402
from asistente.llm.base import ErrorDeRed  # noqa: E402
from asistente.llm.gemini import ClienteGemini  # noqa: E402


def main() -> int:
    cfg = Config.cargar()
    llm = ClienteGemini(cfg.gemini_api_key, cfg.modelo_llm)
    print("escribe una pregunta. Ctrl+C para salir.")
    try:
        while True:
            pregunta = input("\n> ")
            try:
                for frase in llm.conversar(pregunta):
                    print(f"  [frase] {frase}")
            except ErrorDeRed as exc:
                print(f"  [sin red] {exc}")
    except KeyboardInterrupt:
        print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `python scripts/probar_llm.py`

Comprobar:
- Una pregunta general se responde en 2-3 frases, sin markdown ni listas.
- Preguntar "¿qué tiempo hace en Madrid?" produce datos reales del clima.
- Cada frase se imprime por separado, no todo de golpe al final.
- Desconectar el wifi y preguntar produce `[sin red]`, no una traza de error.

- [ ] **Step 8: Commit**

```bash
git add src/asistente/llm/ tests/test_llm_base.py scripts/probar_llm.py
git commit -m "Interfaz del LLM y cliente de Gemini con uso de herramientas"
```

---

### Task 16: Interfaz de transcripción e implementación con Deepgram

**Files:**
- Create: `src/asistente/stt/base.py`, `src/asistente/stt/deepgram.py`
- Test: `tests/test_stt_base.py`

**Interfaces:**
- Consumes: `ErrorDeRed` (Task 15), `TASA_MUESTREO` (Task 9)
- Produces:
  - `ClienteSTT` — clase base abstracta con `transcribir(self, audio: numpy.ndarray) -> str`
  - `ClienteDeepgram(ClienteSTT)` — implementación
  - `STTFalso(ClienteSTT)` — doble para tests y para el orquestador, con `__init__(self, texto: str = "")`

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_stt_base.py
import numpy as np
import pytest

from asistente.stt.base import ClienteSTT, STTFalso


def test_el_doble_devuelve_lo_configurado():
    stt = STTFalso("hola qué tal")
    assert stt.transcribir(np.zeros(100, dtype=np.int16)) == "hola qué tal"


def test_el_doble_registra_las_llamadas():
    stt = STTFalso("x")
    stt.transcribir(np.zeros(10, dtype=np.int16))
    stt.transcribir(np.zeros(20, dtype=np.int16))
    assert len(stt.llamadas) == 2


def test_el_doble_puede_simular_un_fallo():
    from asistente.llm.base import ErrorDeRed

    stt = STTFalso("x", fallar=True)
    with pytest.raises(ErrorDeRed):
        stt.transcribir(np.zeros(10, dtype=np.int16))


def test_la_interfaz_es_abstracta():
    with pytest.raises(TypeError):
        ClienteSTT()
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_stt_base.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.stt.base'`

- [ ] **Step 3: Implementar `base.py`**

```python
# src/asistente/stt/base.py
from abc import ABC, abstractmethod

import numpy as np

from asistente.llm.base import ErrorDeRed


class ClienteSTT(ABC):
    """Interfaz de transcripción de voz a texto."""

    @abstractmethod
    def transcribir(self, audio: np.ndarray) -> str:
        """Devuelve el texto transcrito, o cadena vacía si no se entendió
        nada. Debe lanzar ErrorDeRed si no hay conectividad."""


class STTFalso(ClienteSTT):
    """Doble para tests y para probar el orquestador sin gastar cuota."""

    def __init__(self, texto: str = "", fallar: bool = False) -> None:
        self.texto = texto
        self.fallar = fallar
        self.llamadas: list[int] = []

    def transcribir(self, audio: np.ndarray) -> str:
        self.llamadas.append(len(audio))
        if self.fallar:
            raise ErrorDeRed("fallo simulado")
        return self.texto
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_stt_base.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Implementar `deepgram.py`**

```python
# src/asistente/stt/deepgram.py
import numpy as np
import httpx

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

    def __init__(self, api_key: str, idioma: str = "es") -> None:
        self._api_key = api_key
        self._idioma = idioma

    def transcribir(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        try:
            respuesta = httpx.post(
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
        except httpx.HTTPError as exc:
            raise ErrorDeRed(str(exc)) from exc

        try:
            alternativas = datos["results"]["channels"][0]["alternatives"]
        except (KeyError, IndexError, TypeError):
            return ""
        if not alternativas:
            return ""
        return alternativas[0].get("transcript", "").strip()
```

- [ ] **Step 6: Verificación manual contra la API real**

Crear `scripts/probar_stt.py`:

```python
# scripts/probar_stt.py
"""Graba 5 segundos del micrófono y los transcribe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from asistente.audio.captura import (  # noqa: E402
    TAMANO_BLOQUE,
    TASA_MUESTREO,
    Captura,
)
from asistente.config import Config  # noqa: E402
from asistente.stt.deepgram import ClienteDeepgram  # noqa: E402

SEGUNDOS = 5


def main() -> int:
    cfg = Config.cargar()
    bloques = []
    necesarios = int(SEGUNDOS * TASA_MUESTREO / TAMANO_BLOQUE)

    print(f"habla durante {SEGUNDOS} segundos...")
    with Captura(cfg.dispositivo_entrada) as captura:
        while len(bloques) < necesarios:
            bloque = captura.leer_bloque()
            if bloque is not None:
                bloques.append(bloque)

    print("transcribiendo...")
    stt = ClienteDeepgram(cfg.deepgram_api_key)
    print(f"-> {stt.transcribir(np.concatenate(bloques))!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `python scripts/probar_stt.py`
Expected: imprime lo que dijiste, con puntuación y en español.

- [ ] **Step 7: Commit**

```bash
git add src/asistente/stt/ tests/test_stt_base.py scripts/probar_stt.py
git commit -m "Interfaz de transcripción y cliente de Deepgram"
```

---

### Task 17: Orquestador

**Files:**
- Create: `src/asistente/orquestador.py`
- Test: `tests/test_orquestador.py`

**Interfaces:**
- Consumes: todo lo anterior, siempre a través de interfaces
- Produces: `Orquestador` — clase con `__init__(self, captura, detector, vad, stt, llm, tts, reproductor, cara)`, `un_ciclo(self) -> None`, `ejecutar(self) -> None`

**Esta es la tarea central.** El orquestador no importa `sounddevice`, `httpx`, `google-genai` ni `pygame`. Recibe todas sus dependencias construidas, lo que permite probarlo entero sin hardware ni red.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_orquestador.py
import numpy as np

from asistente.audio.captura import TAMANO_BLOQUE
from asistente.llm.base import ErrorDeRed
from asistente.orquestador import MENSAJE_NO_ENTENDIDO, MENSAJE_SIN_RED, Orquestador
from asistente.stt.base import STTFalso
from comun.estados import Estado


class CapturaFalsa:
    def __init__(self, bloques):
        self._bloques = list(bloques)

    def leer_bloque(self, timeout=1.0):
        if not self._bloques:
            return None
        return self._bloques.pop(0)

    def vaciar(self):
        pass


class DetectorFalso:
    def __init__(self, despertar_en=0):
        self._n = 0
        self._despertar_en = despertar_en
        self.reinicios = 0

    def procesar(self, bloque):
        self._n += 1
        return self._n > self._despertar_en

    def reiniciar(self):
        self.reinicios += 1


class VadFalso:
    def __init__(self, bloques_hasta_fin=2, hubo_voz=True):
        self._restantes = bloques_hasta_fin
        self.hubo_voz = hubo_voz

    def procesar(self, bloque):
        self._restantes -= 1
        return self._restantes <= 0

    def reiniciar(self):
        pass


class LlmFalso:
    def __init__(self, frases=("Hola.",), fallar=False):
        self.frases = list(frases)
        self.fallar = fallar
        self.preguntas = []

    def conversar(self, texto):
        self.preguntas.append(texto)
        if self.fallar:
            raise ErrorDeRed("sin red")
        yield from self.frases

    def reiniciar(self):
        pass


class TtsFalso:
    def __init__(self):
        self.textos = []
        self.tasa_muestreo = 16000

    def sintetizar(self, texto):
        self.textos.append(texto)
        yield np.zeros(320, dtype=np.int16).tobytes()


class ReproductorFalso:
    def __init__(self):
        self.reproducciones = 0

    def reproducir(self, chunks, al_rms):
        self.reproducciones += 1
        for _ in chunks:
            al_rms(0.5)
        al_rms(0.0)

    def detener(self):
        pass


class CaraFalsa:
    def __init__(self):
        self.estados = []

    def set_estado(self, estado, rms=0.0):
        if not self.estados or self.estados[-1] != estado:
            self.estados.append(estado)

    def cerrar(self):
        pass


def bloque():
    return np.zeros(TAMANO_BLOQUE, dtype=np.int16)


def construir(**cambios):
    piezas = {
        "captura": CapturaFalsa([bloque() for _ in range(20)]),
        "detector": DetectorFalso(),
        "vad": VadFalso(),
        "stt": STTFalso("qué tiempo hace"),
        "llm": LlmFalso(["Hace sol.", "Veinte grados."]),
        "tts": TtsFalso(),
        "reproductor": ReproductorFalso(),
        "cara": CaraFalsa(),
    }
    piezas.update(cambios)
    return Orquestador(**piezas), piezas


def test_un_ciclo_completo_recorre_todos_los_estados():
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["cara"].estados == [
        Estado.ESCUCHANDO,
        Estado.PENSANDO,
        Estado.HABLANDO,
        Estado.REPOSO,
    ]


def test_la_transcripcion_llega_al_llm():
    orq, piezas = construir(stt=STTFalso("qué tiempo hace"))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == ["qué tiempo hace"]


def test_cada_frase_se_sintetiza_por_separado():
    """Sintetizar frase a frase es lo que permite empezar a hablar antes de
    tener la respuesta completa."""
    orq, piezas = construir(llm=LlmFalso(["Uno.", "Dos.", "Tres."]))
    orq.un_ciclo()
    assert piezas["tts"].textos == ["Uno.", "Dos.", "Tres."]


def test_un_falso_positivo_no_produce_respuesta():
    orq, piezas = construir(vad=VadFalso(hubo_voz=False))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == []
    assert Estado.HABLANDO not in piezas["cara"].estados


def test_un_falso_positivo_vuelve_a_reposo():
    orq, piezas = construir(vad=VadFalso(hubo_voz=False))
    orq.un_ciclo()
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_transcripcion_vacia_avisa_y_no_llama_al_llm():
    orq, piezas = construir(stt=STTFalso(""))
    orq.un_ciclo()
    assert piezas["llm"].preguntas == []
    assert piezas["tts"].textos == [MENSAJE_NO_ENTENDIDO]


def test_sin_red_en_el_stt_avisa_por_voz():
    orq, piezas = construir(stt=STTFalso("x", fallar=True))
    orq.un_ciclo()
    assert piezas["tts"].textos == [MENSAJE_SIN_RED]
    assert Estado.ERROR in piezas["cara"].estados


def test_sin_red_en_el_llm_avisa_por_voz():
    orq, piezas = construir(llm=LlmFalso(fallar=True))
    orq.un_ciclo()
    assert piezas["tts"].textos == [MENSAJE_SIN_RED]
    assert Estado.ERROR in piezas["cara"].estados


def test_siempre_vuelve_a_reposo_tras_un_error():
    orq, piezas = construir(llm=LlmFalso(fallar=True))
    orq.un_ciclo()
    assert piezas["cara"].estados[-1] is Estado.REPOSO


def test_el_detector_se_reinicia_tras_despertar():
    """Sin esto, la misma palabra dispararía varias veces seguidas."""
    orq, piezas = construir()
    orq.un_ciclo()
    assert piezas["detector"].reinicios >= 1
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_orquestador.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente.orquestador'`

- [ ] **Step 3: Implementar `orquestador.py`**

```python
# src/asistente/orquestador.py
import numpy as np

from asistente.llm.base import ErrorDeRed
from comun.estados import Estado

MENSAJE_SIN_RED = "No puedo ayudarte con esto hasta que estés conectado a una red."
MENSAJE_NO_ENTENDIDO = "No te he entendido."


class Orquestador:
    """La máquina de estados del asistente.

    Recibe todas sus dependencias ya construidas y solo las usa a través de
    sus interfaces: no importa sounddevice, httpx, google-genai ni pygame. Eso
    es lo que permite ejercitar el ciclo completo, incluidos los caminos de
    error, sin micrófono ni conexión.
    """

    def __init__(self, captura, detector, vad, stt, llm, tts, reproductor, cara) -> None:
        self._captura = captura
        self._detector = detector
        self._vad = vad
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._reproductor = reproductor
        self._cara = cara

    def ejecutar(self) -> None:
        self._cara.set_estado(Estado.REPOSO)
        while True:
            self.un_ciclo()

    def un_ciclo(self) -> None:
        """Espera la palabra clave, atiende una petición, y vuelve a reposo."""
        if not self._esperar_palabra_clave():
            return

        self._detector.reiniciar()
        self._captura.vaciar()
        self._cara.set_estado(Estado.ESCUCHANDO)

        audio = self._grabar_intervencion()

        if not self._vad.hubo_voz:
            # Falso positivo del wake word: nadie dijo nada. Volver a reposo
            # en silencio; hablar aquí sería peor que no despertar.
            self._cara.set_estado(Estado.REPOSO)
            return

        self._cara.set_estado(Estado.PENSANDO)
        try:
            texto = self._stt.transcribir(audio)
        except ErrorDeRed:
            self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
            return

        if not texto.strip():
            self._avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)
            return

        try:
            self._responder(texto)
        except ErrorDeRed:
            self._avisar(MENSAJE_SIN_RED, Estado.ERROR)
            return

        self._cara.set_estado(Estado.REPOSO)

    def _esperar_palabra_clave(self) -> bool:
        bloque = self._captura.leer_bloque()
        if bloque is None:
            return False
        return self._detector.procesar(bloque)

    def _grabar_intervencion(self) -> np.ndarray:
        self._vad.reiniciar()
        bloques = []
        while True:
            bloque = self._captura.leer_bloque()
            if bloque is None:
                break
            bloques.append(bloque)
            if self._vad.procesar(bloque):
                break
        if not bloques:
            return np.array([], dtype=np.int16)
        return np.concatenate(bloques)

    def _responder(self, texto: str) -> None:
        """Sintetiza y reproduce frase a frase, según van llegando.

        No espera a tener la respuesta completa: en cuanto el LLM cierra la
        primera frase, esa frase ya se está oyendo mientras el modelo sigue
        generando el resto."""
        hablando = False
        for frase in self._llm.conversar(texto):
            if not hablando:
                self._cara.set_estado(Estado.HABLANDO)
                hablando = True
            self._decir(frase)
        if not hablando:
            self._avisar(MENSAJE_NO_ENTENDIDO, Estado.PENSANDO)

    def _decir(self, texto: str) -> None:
        self._reproductor.reproducir(
            self._tts.sintetizar(texto),
            al_rms=lambda rms: self._cara.set_estado(Estado.HABLANDO, rms=rms),
        )

    def _avisar(self, texto: str, estado: Estado) -> None:
        """Dice un mensaje del sistema y vuelve a reposo.

        Funciona sin internet porque el TTS es local: por eso el asistente
        puede avisar de que no hay red en vez de quedarse mudo."""
        self._cara.set_estado(estado)
        self._decir(texto)
        self._cara.set_estado(Estado.REPOSO)
```

- [ ] **Step 4: Ejecutar los tests**

Run: `pytest tests/test_orquestador.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Ejecutar toda la batería**

Run: `pytest -v`
Expected: todos PASSED

- [ ] **Step 6: Commit**

```bash
git add src/asistente/orquestador.py tests/test_orquestador.py
git commit -m "Orquestador: máquina de estados completa con manejo de errores"
```

---

### Task 18: Arranque del asistente y documentación

**Files:**
- Create: `src/asistente/__main__.py`, `README.md`
- Modify: `.env.example` (añadir `UMBRAL_WAKEWORD` y `MODELO_WAKEWORD`)
- Modify: `src/asistente/config.py` (campos nuevos)

**Interfaces:**
- Consumes: todo lo anterior
- Produces: el ejecutable `python -m asistente`

- [ ] **Step 1: Añadir la configuración del wake word**

En `.env.example`, añadir:

```
# Palabra de activación
MODELO_WAKEWORD=hey_jarvis
UMBRAL_WAKEWORD=0.5
```

En `src/asistente/config.py`, añadir a la dataclass (después de `ruta_voz`):

```python
    modelo_wakeword: str
    umbral_wakeword: float
```

Y en `cargar()`:

```python
            modelo_wakeword=os.getenv("MODELO_WAKEWORD", "hey_jarvis"),
            umbral_wakeword=float(os.getenv("UMBRAL_WAKEWORD", "0.5")),
```

- [ ] **Step 2: Verificar que los tests de configuración siguen pasando**

Run: `pytest tests/test_config.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Implementar `src/asistente/__main__.py`**

```python
# src/asistente/__main__.py
import sys

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


def main() -> int:
    cfg = Config.cargar()

    if not cfg.gemini_api_key or not cfg.deepgram_api_key:
        print("Faltan claves de API. Copia .env.example a .env y rellénalo.")
        return 1

    print("cargando modelos...")
    tts = Piper(cfg.ruta_voz)
    detector = Detector(cfg.modelo_wakeword, cfg.umbral_wakeword)

    captura = Captura(cfg.dispositivo_entrada)
    captura.iniciar()

    cara = CaraCliente(cfg.host_cara, cfg.puerto_cara)

    orquestador = Orquestador(
        captura=captura,
        detector=detector,
        vad=DetectorSilencio(),
        stt=ClienteDeepgram(cfg.deepgram_api_key),
        llm=ClienteGemini(cfg.gemini_api_key, cfg.modelo_llm),
        tts=tts,
        reproductor=Reproductor(cfg.dispositivo_salida, tts.tasa_muestreo),
        cara=cara,
    )

    print(f"listo. di '{cfg.modelo_wakeword.replace('_', ' ')}'. Ctrl+C para salir.")
    try:
        orquestador.ejecutar()
    except KeyboardInterrupt:
        print("\ncerrando...")
    finally:
        captura.detener()
        cara.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Escribir el `README.md`**

````markdown
# Asistente de voz con cara animada

Asistente tipo Alexa que despierta al oír su nombre, responde hablando, y
muestra una cara animada que reacciona a cada fase de la conversación.

Diseño completo en [`docs/superpowers/specs/`](docs/superpowers/specs/).

## Requisitos

- Python 3.11 o superior
- Un micrófono y un altavoz
- Claves de API de [Deepgram](https://console.deepgram.com) y de
  [Google AI Studio](https://aistudio.google.com/apikey)

> El plan gratuito de Gemini tiene límites de peticiones por minuto, y Google
> puede usar los datos enviados para mejorar sus productos. Tenlo en cuenta en
> un aparato que escucha en casa.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux

pip install -e ".[dev]"
python -c "import openwakeword.utils; openwakeword.utils.download_models()"
```

Descargar un modelo de voz de Piper en español a `modelos/`:
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
pytest
```

Los tests no necesitan micrófono, altavoz ni conexión: todas las dependencias
externas están detrás de interfaces y se sustituyen por dobles.

## Cambiar de proveedor

El STT y el LLM están aislados tras interfaces (`stt/base.py`, `llm/base.py`).
Cambiar de proveedor es escribir una subclase nueva y sustituir una línea en
`src/asistente/__main__.py`.

## Cambiar la palabra de activación

El Hito 1 usa el modelo pre-entrenado `hey_jarvis`. Para un nombre propio hay
que entrenar un modelo con openWakeWord y apuntar `MODELO_WAKEWORD` a él.
````

- [ ] **Step 5: Prueba de integración manual completa**

En una terminal: `python -m cara`
En otra: `python -m asistente`

Verificar los ocho criterios de aceptación del Hito 1:

1. Decir "hey jarvis" despierta al asistente; hablar normalmente, no.
2. Decir "hey jarvis" y luego callarse no produce ninguna respuesta hablada.
3. Decir "hey jarvis" y hacer una pregunta general produce respuesta hablada.
4. Preguntar por el tiempo en una ciudad devuelve datos reales.
5. Desconectar el wifi y preguntar produce el mensaje de red por voz.
6. La cara pasa por escuchando, pensando y hablando, con transiciones suaves.
7. La boca se mueve sincronizada con la voz.
8. La cara no se atasca en ningún momento, ni durante la espera de red.

- [ ] **Step 6: Ejecutar toda la batería una última vez**

Run: `pytest -v`
Expected: todos PASSED

- [ ] **Step 7: Commit**

```bash
git add src/asistente/__main__.py src/asistente/config.py .env.example README.md
git commit -m "Arranque del asistente y documentación de uso"
```

---

## Cierre del Hito 1

Al completar la Tarea 18 tienes un asistente de voz funcional en Windows, con
todos los criterios de aceptación del Hito 1 verificados.

**Lo que queda para hitos posteriores, deliberadamente fuera de este plan:**

| Trabajo | Hito |
|---|---|
| Entrenar la palabra de activación personalizada | Cualquiera, es independiente |
| Configurar el overlay I2S y validar el micrófono con `arecord` | Hito 2 |
| Ajustar dispositivos de audio en `.env` para la Pi | Hito 2 |
| Medir latencia real en la 3B y calibrar el umbral del wake word | Hito 2 |
| Arranque automático de ambos procesos como servicios systemd | Hito 3 |
| Pantalla completa en la DSI y ajuste de resolución | Hito 3 |
