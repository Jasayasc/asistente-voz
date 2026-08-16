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
