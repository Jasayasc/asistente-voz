from enum import Enum


class Estado(str, Enum):
    """Estados del asistente. Heredar de str hace que el enum sea
    serializable a JSON directamente."""

    REPOSO = "reposo"
    ESCUCHANDO = "escuchando"
    PENSANDO = "pensando"
    HABLANDO = "hablando"
    ERROR = "error"
