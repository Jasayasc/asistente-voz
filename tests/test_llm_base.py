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
