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
