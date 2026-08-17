# tests/test_config.py
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
    monkeypatch.delenv("RUTA_VOZ", raising=False)
    monkeypatch.delenv("MODELO_WAKEWORD", raising=False)
    monkeypatch.delenv("UMBRAL_WAKEWORD", raising=False)
    cfg = Config.cargar()
    assert cfg.puerto_cara == 8765
    assert cfg.dispositivo_entrada is None
    assert cfg.ruta_voz == "modelos/es_ES-davefx-medium.onnx"
    assert cfg.modelo_wakeword == "hey_jarvis"
    assert cfg.umbral_wakeword == 0.5


def test_cargar_usa_ruta_voz_del_entorno(monkeypatch):
    monkeypatch.setenv("RUTA_VOZ", "modelos/otra-voz.onnx")
    cfg = Config.cargar()
    assert cfg.ruta_voz == "modelos/otra-voz.onnx"


def test_dispositivo_vacio_se_convierte_en_none(monkeypatch):
    monkeypatch.setenv("DISPOSITIVO_ENTRADA", "")
    cfg = Config.cargar()
    assert cfg.dispositivo_entrada is None


def test_cargar_usa_wakeword_del_entorno(monkeypatch):
    monkeypatch.setenv("MODELO_WAKEWORD", "hey_mycroft")
    monkeypatch.setenv("UMBRAL_WAKEWORD", "0.7")
    cfg = Config.cargar()
    assert cfg.modelo_wakeword == "hey_mycroft"
    assert cfg.umbral_wakeword == 0.7
