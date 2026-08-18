# src/asistente/conversacion.py
"""Cuándo dar por terminada una conversación.

El asistente arranca con la palabra clave y, a partir de ahí, se queda
escuchando turno tras turno. Hace falta entonces algo que no hacía falta
cuando cada pregunta era un ciclo suelto: saber cuándo el usuario ha
terminado de hablar con él.

Se decide sobre el texto ya transcrito, no sobre el audio: el STT es el
único que sabe qué se dijo, y usar el detector de palabra clave para una
segunda palabra ("desactívate") obligaría a entrenar otro modelo.
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Frases que cierran la conversación. Se comparan ya normalizadas, así que
# aquí se pueden escribir con tildes y como se digan de verdad.
#
# La lista evita a propósito palabras sueltas que aparecen dentro de
# preguntas normales. "para" cerraría "¿para qué sirve esto?"; "gracias"
# cerraría "dime gracias en inglés"; "desactivar" cerraría "¿cómo puedo
# desactivar esto?". Las que quedan solo aparecen cuando alguien de verdad
# se está despidiendo.
FRASES_DE_DESPEDIDA = (
    "desactívate",
    "inactívate",
    "apágate",
    "adiós",
    "hasta luego",
    "hasta pronto",
    "hasta mañana",
    "duérmete",
    "vete a dormir",
    "me voy a dormir",
    "voy a dormir",
    "eso es todo",
    "nada más",
    "ya está bien",
    "déjalo ya",
    "olvídalo",
    "cambio y corto",
    "que descanses",
)

# Coletillas que se pueden quitar del final sin cambiar lo que se dijo.
# "Adiós, Jarvis", "me voy a dormir ya" y "hasta luego, gracias" son la
# misma despedida que sin ellas, y sin esta lista la regla de posición del
# paso 3 las dejaría fuera por una palabra.
PALABRAS_DE_RELLENO = frozenset(
    {"ya", "jarvis", "gracias", "porfa", "hombre", "anda", "eh", "vale", "va"}
)

# Una despedida es corta. El límite es lo que separa "vale, gracias, adiós"
# (3 palabras: se despide) de "¿cómo se dice adiós en francés?" (6 palabras
# ya normalizadas: es una pregunta que resulta que contiene la palabra).
# Sin este tope, cualquier pregunta *sobre* una despedida cerraría la
# conversación, que es de los fallos más molestos posibles: el usuario
# pregunta algo y el asistente se apaga.
MAX_PALABRAS_DESPEDIDA = 5

# Palabras que delatan una PETICIÓN o una continuación, no una despedida.
# Se buscan en cualquier posición ANTES de la despedida, no solo al
# principio: "oye, traduce adiós al ruso" empieza por una muletilla, y
# mirar solo la primera palabra dejaba pasar justo el caso que esta lista
# viene a cubrir.
#
# Es seguro incluir aquí palabras con las que también empieza alguna
# despedida ("que descanses"): esas entran por el paso 2, el de la frase
# dicha tal cual, que no consulta esta lista.
APERTURAS_DE_PETICION = frozenset(
    {
        # Verbos con los que se pide algo SOBRE una frase.
        "traduce",
        "traduceme",
        "traducir",
        "dime",
        "di",
        "define",
        "deletrea",
        "repite",
        "escribe",
        "explica",
        "significa",
        "busca",
        "reproduce",
        "pon",
        "ponme",
        "canta",
        "cuenta",
        "ayuda",
        "ayudame",
        "necesito",
        # Interrogativos.
        "como",
        "que",
        "cual",
        "cuando",
        "cuanto",
        "donde",
        "quien",
        # Conjunciones de continuación: "¿y hasta luego?" es una pregunta
        # de seguimiento sobre lo anterior, no una despedida.
        "y",
        "o",
        "pero",
        "tambien",
        "ademas",
    }
)

_SOLO_PALABRAS = re.compile(r"[a-z0-9]+")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con un solo espacio.

    Lo que llega del STT no viene normalizado: Deepgram puntúa, escribe
    mayúsculas y acentúa. Comparar contra eso a pelo fallaría con
    "Desactívate." tanto por el punto como por la tilde.

    La descomposición NFD convierte la eñe en "n" más una tilde suelta que
    luego se descarta, así que "añade" queda "anade". No pasa nada mientras
    las frases de la lista se normalicen con esta misma función, que es lo
    que hace `es_despedida`: las dos partes de la comparación sufren la
    misma transformación.
    """
    descompuesto = unicodedata.normalize("NFD", texto.casefold())
    sin_tildes = "".join(
        caracter
        for caracter in descompuesto
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(_SOLO_PALABRAS.findall(sin_tildes))


def _es_pregunta(texto: str) -> bool:
    """¿Lo transcrito viene con signos de interrogación?

    Deepgram puntúa según la entonación, y ese signo es el único dato que
    separa "eso es todo" (cierra) de "¿eso es todo?" (pide más detalle).
    Se mira sobre el texto crudo porque `normalizar` lo tira.
    """
    return "?" in texto or "¿" in texto


def _candidatos(palabras: list[str]) -> list[list[str]]:
    """La frase entera, y cada versión con una coletilla menos al final.

    Hacen falta todas las versiones intermedias, no solo los dos extremos.
    "Déjalo ya, Jarvis" tiene dos coletillas seguidas, pero la despedida de
    la lista es "déjalo ya": quitando las dos queda "déjalo", que no está,
    y sin quitar ninguna tampoco casa. La buena es la de en medio.
    """
    secuencias = [list(palabras)]
    actual = list(palabras)
    while len(actual) > 1 and actual[-1] in PALABRAS_DE_RELLENO:
        actual = actual[:-1]
        secuencias.append(list(actual))
    return secuencias


def es_despedida(texto: str, frases: tuple[str, ...] = FRASES_DE_DESPEDIDA) -> bool:
    """¿Con esto el usuario está cerrando la conversación?

    Los dos errores posibles no cuestan lo mismo. No reconocer una
    despedida son ocho segundos de silencio y se cierra sola. Confundir una
    pregunta con una despedida apaga el asistente justo cuando le están
    preguntando algo. Todas las reglas de aquí están inclinadas hacia el
    lado seguro, y por eso el caso dudoso siempre se resuelve como "no es
    una despedida".

    Se comprueba en cuatro pasos:

    1. Si lleva interrogación, es una pregunta. "¿Eso es todo?" pide más
       detalle; "eso es todo" cierra.
    2. Una frase larga nunca es una despedida. Quien se despide lo hace en
       pocas palabras; quien pregunta *por* una despedida se enrolla.
    3. La frase dicha tal cual —quitando coletillas del final— siempre
       cierra. Aquí no hay ambigüedad, y es lo que garantiza que las frases
       configuradas a mano funcionen aunque empiecen por una palabra de las
       que el paso 4 descarta.
    4. Si viene acompañada, tiene que ir **al final** y no llevar delante
       ninguna palabra de petición. Una despedida no lleva nada detrás:
       "vale, gracias, adiós" sí; "adiós en japonés" no. Y "oye, traduce
       adiós al ruso" queda descartada por las dos cosas a la vez.
    """
    if _es_pregunta(texto):
        return False

    palabras = normalizar(texto).split()
    if not palabras or len(palabras) > MAX_PALABRAS_DESPEDIDA:
        return False

    normalizadas = [
        normalizada
        for normalizada in (normalizar(frase) for frase in frases)
        if normalizada
    ]
    # Se prueba con la frase entera y con cada versión sin una coletilla
    # más al final. Las dos puntas hacen falta: "déjalo ya" es una
    # despedida de la lista que termina en coletilla, y quitársela la
    # dejaría irreconocible; "me voy a dormir ya" solo se reconoce
    # quitándosela.
    candidatos = _candidatos(palabras)

    if any(" ".join(secuencia) in normalizadas for secuencia in candidatos):
        return True

    for secuencia in candidatos:
        for normalizada in normalizadas:
            cola = normalizada.split()
            if len(cola) >= len(secuencia):
                # Igual de larga ya se habría resuelto arriba; más larga no
                # cabe.
                continue
            if secuencia[-len(cola) :] != cola:
                continue  # la despedida no cierra la frase
            if any(
                previa in APERTURAS_DE_PETICION
                for previa in secuencia[: -len(cola)]
            ):
                continue  # lo de delante la convierte en una petición
            return True
    return False


def frases_desde_configuracion(valor: str | None) -> tuple[str, ...]:
    """Lee la lista de frases del `.env`. Vacío o ausente = las de fábrica.

    Se acepta configurarlas porque "desactívate" es una palabra rara de
    decir en voz alta, y cada uno acaba usando la suya.

    Se descartan las que `es_despedida` no podría reconocer nunca por
    pasarse del tope de palabras. Sin este filtro, configurar "ya puedes
    dejar de escucharme por hoy" dejaba al asistente anunciando al arrancar
    una frase de cierre que, dicha en voz alta, no cerraba nada.
    """
    if valor is None or not valor.strip():
        return FRASES_DE_DESPEDIDA

    utiles = []
    for trozo in valor.split(","):
        frase = trozo.strip()
        normalizada = normalizar(frase)
        if not normalizada:
            continue
        if len(normalizada.split()) > MAX_PALABRAS_DESPEDIDA:
            logger.warning(
                "Frase de despedida ignorada por larga (más de %d palabras): %r",
                MAX_PALABRAS_DESPEDIDA,
                frase,
            )
            continue
        utiles.append(frase)

    return tuple(utiles) or FRASES_DE_DESPEDIDA
