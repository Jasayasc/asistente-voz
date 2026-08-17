# scripts/probar_llm.py
"""Conversa por teclado con el LLM, para validarlo sin audio de por medio."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asistente.config import Config  # noqa: E402
from asistente.llm.base import ErrorDeRed  # noqa: E402
from asistente.llm.gemini import ClienteGemini  # noqa: E402


def main() -> int:
    cfg = Config.cargar()
    llm = ClienteGemini(cfg.gemini_api_key, cfg.modelo_llm)
    print("escribe una pregunta. Ctrl+C para salir.")
    try:
        while True:
            pregunta = input("\n> ")
            try:
                for frase in llm.conversar(pregunta):
                    print(f"  [frase] {frase}")
            except ErrorDeRed as exc:
                print(f"  [sin red] {exc}")
    except KeyboardInterrupt:
        print("\nfin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
