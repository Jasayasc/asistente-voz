# tests/test_config.py
from pathlib import Path

from asistente import config as modulo_config
from asistente.config import Config


def test_cargar_usa_valores_del_entorno(monkeypatch):
    monkeypatch.setenv("PUERTO_CARA", "9999")
    monkeypatch.setenv("MODELO_LLM", "gemini-2.5-pro")
    cfg = Config.cargar()
    assert cfg.puerto_cara == 9999
    assert cfg.modelo_llm == "gemini-2.5-pro"


def test_cargar_aplica_predeterminados(monkeypatch):
    # `load_dotenv` se anula a propósito. Sin esto, el test lee el `.env`
    # real de quien lo ejecuta —borrar la variable del entorno no basta,
    # porque `cargar()` la repone desde el archivo— y acaba comprobando la
    # configuración de esa máquina en vez de los valores por defecto del
    # código, que es lo único que este test debe fijar.
    monkeypatch.setattr(modulo_config, "load_dotenv", lambda *a, **k: False)
    for variable in (
        "PUERTO_CARA",
        "DISPOSITIVO_ENTRADA",
        "RUTA_VOZ",
        "MODELO_WAKEWORD",
        "UMBRAL_WAKEWORD",
    ):
        monkeypatch.delenv(variable, raising=False)
    cfg = Config.cargar()
    assert cfg.puerto_cara == 8765
    assert cfg.dispositivo_entrada is None
    assert cfg.ruta_voz == "modelos/es_ES-davefx-medium.onnx"
    assert cfg.modelo_wakeword == "hey_jarvis"
    assert cfg.umbral_wakeword == 0.3


def test_cargar_usa_ruta_voz_del_entorno(monkeypatch):
    monkeypatch.setenv("RUTA_VOZ", "modelos/otra-voz.onnx")
    cfg = Config.cargar()
    assert cfg.ruta_voz == "modelos/otra-voz.onnx"


def test_dispositivo_vacio_se_convierte_en_none(monkeypatch):
    monkeypatch.setenv("DISPOSITIVO_ENTRADA", "")
    cfg = Config.cargar()
    assert cfg.dispositivo_entrada is None


def test_cargar_lee_el_env_de_la_raiz_desde_otro_directorio(monkeypatch, tmp_path):
    """El `.env` se encuentra aunque el proceso arranque en otro sitio.

    Es lo que pasa al lanzar el asistente desde un acceso directo o un
    servicio: si la configuración dependiera del directorio de trabajo, se
    cargaría vacía y el asistente se comportaría de otra manera sin decir
    por qué."""
    monkeypatch.chdir(tmp_path)
    for variable in ("MODELO_WAKEWORD", "UMBRAL_WAKEWORD"):
        monkeypatch.delenv(variable, raising=False)

    cfg = Config.cargar()

    assert modulo_config.RUTA_ENV.name == ".env"
    assert modulo_config.RUTA_ENV.parent == Path(modulo_config.__file__).resolve().parents[2]
    if modulo_config.RUTA_ENV.is_file():
        # Hay `.env` en la raíz: sus valores mandan sobre los del código.
        contenido = modulo_config.RUTA_ENV.read_text(encoding="utf-8")
        if "UMBRAL_WAKEWORD" in contenido:
            esperado = next(
                linea.split("=", 1)[1].strip()
                for linea in contenido.splitlines()
                if linea.startswith("UMBRAL_WAKEWORD=")
            )
            assert cfg.umbral_wakeword == float(esperado)


def test_cargar_usa_wakeword_del_entorno(monkeypatch):
    monkeypatch.setenv("MODELO_WAKEWORD", "hey_mycroft")
    monkeypatch.setenv("UMBRAL_WAKEWORD", "0.7")
    cfg = Config.cargar()
    assert cfg.modelo_wakeword == "hey_mycroft"
    assert cfg.umbral_wakeword == 0.7
