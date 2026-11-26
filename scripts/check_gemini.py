"""Developer tool: test which Gemini models work for your key, one at a time.

    python -m scripts.check_gemini                  # the configured fail-over chain
    python -m scripts.check_gemini model-a model-b  # specific models
"""
import logging
import sys
import time

from app.ai import Assistant
from app.config import Settings
from app.gemini import GeminiClient, GeminiError
from app.models import Timing


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.WARNING, format="LOG: %(message)s")
    settings = Settings.from_env()
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set in this terminal.")
        return 1
    models = argv or list(settings.gemini_models)
    print("Each model on its own:")
    working = []
    for model in models:
        started = time.perf_counter()
        try:
            GeminiClient(settings.gemini_api_key, [model]).generate(system="Reply briefly.", prompt="Say hello.")
            working.append(model)
            print(f"  OK      {model:28} {time.perf_counter() - started:4.1f}s")
        except GeminiError as err:
            print(f"  FAILED  {model:28} {time.perf_counter() - started:4.1f}s  {str(err)[:110]}")
    print("\nThe real plan reader (uses the configured chain):")
    started = time.perf_counter()
    result = Assistant(GeminiClient(settings.gemini_api_key, settings.gemini_models)).parse_plan(
        "going to college at 12 noon, 5 km away", Timing.FIXED
    )
    plan = result.plan and (result.plan.kind.value, result.plan.distance_km)
    print(f"  {result.status} {plan or result.question or ''} ({time.perf_counter() - started:.1f}s)")
    if working:
        print("\nWorking models:", ",".join(working))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
