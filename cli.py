"""Command line entry point.

    python cli.py "Samstag 19:00, 4 Pizzen, 65 %, Raum 22 °C"     # LLM mode
    python cli.py --offline --pizzas 4 --hydration 65 --room-temp 22 --target 2026-11-07T19:00
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Fermentation planner agent")
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--now", help="override current time (ISO 8601), for reproducible demos")
    parser.add_argument("--yes", action="store_true", help="skip calendar confirmation")
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
