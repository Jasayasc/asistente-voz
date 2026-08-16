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
