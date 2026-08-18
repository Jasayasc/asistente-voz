# tests/test_conversacion.py
"""Pruebas del cierre de conversación.

Los dos fallos que importan aquí no son simétricos. Que una despedida no
se reconozca es una molestia: el asistente sigue escuchando ocho segundos
de más y se cierra solo. Que una pregunta se confunda con una despedida es
mucho peor: el usuario pregunta algo y el aparato se apaga sin contestar.
Por eso hay más tests de lo segundo que de lo primero.
"""
import pytest

from asistente.conversacion import (
    FRASES_DE_DESPEDIDA,
    MAX_PALABRAS_DESPEDIDA,
    es_despedida,
    frases_desde_configuracion,
    normalizar,
)


# --- Normalización --------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Desactívate.", "desactivate"),
        ("¡ADIÓS!", "adios"),
        ("  hasta   luego  ", "hasta luego"),
        ("Hasta luego, Jarvis.", "hasta luego jarvis"),
        ("", ""),
        ("...", ""),
        ("Son las 16:30", "son las 16 30"),
    ],
)
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_normalizar_quita_las_tildes_de_forma_consistente():
    """La eñe acaba como "n". Da igual mientras las dos partes de la
    comparación pasen por aquí, que es lo que garantiza `es_despedida`."""
    assert normalizar("añade") == normalizar("anade")


# --- Lo que sí cierra la conversación -------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "desactívate",
        "Desactívate.",
        "DESACTÍVATE",
        "inactívate",
        "apágate",
        "adiós",
        "vale, adiós",
        "gracias, hasta luego",
        "hasta luego",
        "duérmete",
        "vete a dormir",
        "eso es todo",
        "nada más",
        "olvídalo",
        "cambio y corto",
    ],
)
def test_estas_cierran(texto):
    assert es_despedida(texto)


# --- Lo que NO debe cerrarla ----------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        # El caso que importa: preguntas *sobre* una despedida. Estas caen
        # por longitud.
        "cómo se dice adiós en francés",
        "escribe una carta de despedida para mi jefe",
        "qué significa hasta luego en inglés",
        "por qué se dice adiós y no adiós con acento",
        # Y estas caben de sobra en el tope de palabras y contienen una
        # despedida entera: las descarta el verbo de petición de delante.
        # Salieron probando frases reales, no de imaginarlas.
        "traduce hasta luego al alemán",
        "di adiós en italiano",
        "deletrea adiós",
        "repite hasta luego",
        "qué significa adiós",
        "cómo se escribe adiós",
        # Palabras que estuvieron a punto de entrar en la lista y habrían
        # cerrado preguntas normalísimas.
        "para qué sirve esto",
        "dime gracias en inglés",
        "cómo puedo desactivar el wifi",
        "cuánto tiempo hay que dormir",
        "pon música para dormir",
        # Una muletilla delante desactivaba el filtro entero cuando solo
        # se miraba la primera palabra. El fallo era además irreproducible
        # escribiendo tests: la misma frase sin el "oye" funcionaba bien.
        "oye, traduce adiós al ruso",
        "pues dime adiós en italiano",
        # "a dormir" casaba dentro de peticiones normalísimas, y encima
        # sobre el tema del que más se pregunta de noche.
        "ayúdame a dormir",
        "la manzanilla ayuda a dormir",
        "pon música para dormir",
        # Signos de interrogación: son el único dato que separa pedir más
        # detalle de despedirse.
        "¿eso es todo?",
        "¿nada más?",
        "¿ya está bien así?",
        # Seguimiento elíptico dentro de una conversación.
        "y hasta luego",
        "¿y hasta luego?",
        # Formas verbales corrientes que estuvieron en la lista.
        "olvídalo, mejor otra cosa",
        "el corazón descansa alguna vez",
        # Preguntas corrientes.
        "qué tiempo hace",
        "qué hora es",
        "",
        "   ",
    ],
)
def test_estas_no_cierran(texto):
    assert not es_despedida(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "adiós, jarvis",
        "hasta luego, gracias",
        "hasta luego, jarvis, gracias",
        "me voy a dormir ya",
        "por hoy nada más",
        "vale, gracias, adiós",
        # Dos coletillas seguidas sobre una despedida que además TERMINA en
        # coletilla: la buena no es la frase entera ni la pelada del todo,
        # sino la de en medio.
        "déjalo ya, jarvis",
    ],
)
def test_las_coletillas_del_final_no_estorban(texto):
    """La regla de posición del paso 4 exige que la despedida cierre la
    frase, y sin quitar las coletillas se caían despedidas evidentes por
    una palabra de más."""
    assert es_despedida(texto)


def test_una_frase_larga_nunca_es_una_despedida():
    """El tope de palabras es lo que separa despedirse de preguntar por una
    despedida. Sin él, cualquier frase que contenga "adiós" apagaría el
    asistente."""
    larga = " ".join(["adiós"] * (MAX_PALABRAS_DESPEDIDA + 1))
    assert not es_despedida(larga)
    corta = " ".join(["adiós"] * MAX_PALABRAS_DESPEDIDA)
    assert es_despedida(corta)


def test_no_casa_a_mitad_de_palabra():
    """"a dormir" no debe casar dentro de "para dormir": si casara, "pon
    música para dormir" apagaría el asistente."""
    assert not es_despedida("música para dormir")


# --- Frases configurables -------------------------------------------------


def test_una_despedida_dicha_tal_cual_siempre_cierra():
    """El paso 2: sin nada alrededor no hay ambigüedad, ni siquiera si la
    frase empieza por una palabra de las que descartan una petición."""
    assert es_despedida("que descanses", ("que descanses",))
    assert es_despedida("pon fin a esto", ("pon fin a esto",))


def test_acompanada_de_un_verbo_de_peticion_no_cierra():
    """El paso 3, que es el que salva "traduce hasta luego al alemán"."""
    assert es_despedida("vale gracias adiós")  # nada sospechoso delante
    assert not es_despedida("traduce adiós al alemán")


def test_se_pueden_poner_frases_propias():
    """"Desactívate" es incómodo de decir en voz alta; cada uno acaba
    usando la suya."""
    propias = ("chao pescao",)
    assert es_despedida("chao pescao", propias)
    assert not es_despedida("adiós", propias)


def test_las_frases_propias_tambien_se_normalizan():
    assert es_despedida("Buenas noches.", ("buenas noches",))


@pytest.mark.parametrize("valor", [None, "", "   ", ",", " , , "])
def test_una_configuracion_vacia_deja_las_de_fabrica(valor):
    assert frases_desde_configuracion(valor) == FRASES_DE_DESPEDIDA


def test_una_configuracion_con_comas_se_reparte():
    assert frases_desde_configuracion(" chao , buenas noches ") == (
        "chao",
        "buenas noches",
    )
