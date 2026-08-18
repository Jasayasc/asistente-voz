from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

# El modelo no tiene reloj: sin esta herramienta se inventa la hora con toda
# naturalidad, que es peor que no contestar. La zona horaria la deduce él de
# la ciudad que diga el usuario, igual que las coordenadas del clima.
ESQUEMA_HORA = {
    "nombre": "consultar_hora",
    "descripcion": (
        "Consulta la fecha y la hora actuales en una zona horaria. Úsala "
        "siempre que el usuario pregunte qué hora es, qué día es, o cuánto "
        "falta para algo. Deduce tú la zona horaria de la ciudad o el país "
        "que mencione el usuario."
    ),
    "parametros": {
        "zona_horaria": {
            "tipo": "string",
            "descripcion": (
                "Zona horaria en formato IANA, por ejemplo 'America/Bogota', "
                "'Europe/Madrid' o 'America/Mexico_City'."
            ),
        },
    },
}

DIAS = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def consultar_hora(zona_horaria: str) -> str:
    """Devuelve la fecha y la hora en texto llano. Nunca lanza.

    Los nombres de día y mes se escriben aquí a mano en vez de usar
    `strftime`: el locale del sistema no está bajo nuestro control y en un
    equipo en inglés saldría "Monday", que el TTS pronunciaría en castellano.
    """
    try:
        zona = ZoneInfo(zona_horaria)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return f"No conozco la zona horaria '{zona_horaria}'."
    ahora = datetime.now(zona)
    return (
        f"Son las {ahora.hour} horas y {ahora.minute} minutos "
        f"del {DIAS[ahora.weekday()]} {ahora.day} "
        f"de {MESES[ahora.month - 1]} de {ahora.year}."
    )

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
    56: "con llovizna helada ligera",
    57: "con llovizna helada",
    61: "con lluvia ligera",
    63: "con lluvia",
    65: "con lluvia fuerte",
    66: "con lluvia helada ligera",
    67: "con lluvia helada",
    71: "con nieve ligera",
    73: "con nieve",
    75: "con nieve intensa",
    77: "con granos de nieve",
    80: "con chubascos",
    81: "con chubascos fuertes",
    82: "con chubascos muy fuertes",
    85: "con chubascos de nieve",
    86: "con chubascos de nieve fuertes",
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
        cielo = DESCRIPCIONES.get(int(actual.get("weather_code", -1)), "estado desconocido")
        return (
            f"Temperatura {actual['temperature_2m']} grados, "
            f"sensación térmica {actual['apparent_temperature']} grados, "
            f"humedad {actual['relative_humidity_2m']} por ciento, "
            f"viento {actual['wind_speed_10m']} kilómetros por hora, "
            f"cielo {cielo}."
        )
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
        return "No se ha podido consultar el clima ahora mismo."
    finally:
        if propio:
            cliente.close()


HERRAMIENTAS = [ESQUEMA_CLIMA, ESQUEMA_HORA]


def ejecutar(
    nombre: str, argumentos: dict, cliente_http: httpx.Client | None = None
) -> str:
    """Despacha una llamada de herramienta. Nunca lanza."""
    if nombre == "consultar_clima":
        try:
            return consultar_clima(
                float(argumentos["latitud"]),
                float(argumentos["longitud"]),
                cliente_http=cliente_http,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return "No se ha podido procesar la solicitud de clima."
    if nombre == "consultar_hora":
        try:
            return consultar_hora(str(argumentos["zona_horaria"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            return "No se ha podido procesar la solicitud de hora."
    return f"La herramienta '{nombre}' no existe."
