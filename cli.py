"""Command line entry point.

    python cli.py "Samstag 19:00, vier Pizzen, 22 °C, von Hand"          # LLM mode
    python cli.py                                                         # LLM mode, asks for the request
    python cli.py --offline --pizzas 4 --room-temp 22 --mixing hand --target 2026-11-07T19:00
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fermentation_agent import config
from fermentation_agent.agent.loop import AgentResult
from fermentation_agent.agent.summary import ingredient_lines
from fermentation_agent.models import FlourType, Mixing, StepKind, YeastType

DEFAULT_MODEL = "gpt-4.1-mini"


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo(config.TIMEZONE))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan pizza dough backwards from the bake time and export it as an .ics calendar.")
    parser.add_argument("prompt", nargs="?", help="request in natural language (LLM mode)")
    parser.add_argument("--offline", action="store_true", help="no LLM: fixed tool order, values from flags")
    parser.add_argument("--now", type=parse_time, help="override the current time (ISO 8601), for reproducible demos")
    parser.add_argument("-y", "--yes", action="store_true", help="write the calendar file without asking")
    parser.add_argument("--trace", action="store_true", help="print every tool call and its result")
    parser.add_argument("-o", "--output", type=Path, default=Path("out/plan.ics"), help="calendar file (default: %(default)s)")
    parser.add_argument("--model", help=f"model name (default: $FERMENTATION_MODEL or {DEFAULT_MODEL})")
    parser.add_argument("--base-url", help="OpenAI-compatible server, e.g. http://localhost:11434/v1 for Ollama "
                                           "(default: $OPENAI_BASE_URL or the OpenAI API)")

    offline = parser.add_argument_group("offline mode")
    offline.add_argument("--pizzas", type=int)
    offline.add_argument("--target", type=parse_time, help="bake time, e.g. 2026-11-07T19:00")
    offline.add_argument("--room-temp", type=float)
    offline.add_argument("--mixing", choices=[m.value for m in Mixing])
    offline.add_argument("--ball-weight", type=float, default=250.0)
    offline.add_argument("--hydration", type=float, default=65.0)
    offline.add_argument("--salt", type=float, default=2.8)
    offline.add_argument("--flour", choices=[f.value for f in FlourType], default=FlourType.TIPO_00.value)
    offline.add_argument("--yeast", choices=[y.value for y in YeastType], default=YeastType.FRESH.value)
    offline.add_argument("--fridge-temp", type=float, default=4.0)
    return parser


def ask(question: str) -> str:
    try:
        return input(question)
    except EOFError:
        return ""


class Display:
    """Prints the plan exactly once – before the confirmation question if there is one."""

    def __init__(self, show_facts: bool) -> None:
        self.show_facts = show_facts  # False when the summary already is the verified template
        self.plan_shown = False

    def show_plan(self, result: AgentResult) -> None:
        if self.plan_shown:
            return
        self.plan_shown = True
        print("\n── Summary " + "─" * 56)
        print(result.message)
        if result.summary_replaced:
            print("\n(The LLM summary contained numbers that did not match the tools; template summary shown.)")
        elif self.show_facts:
            print_plan(result)


def make_confirm(always_yes: bool, display: Display):
    def confirm(result: AgentResult) -> bool:
        if always_yes:
            return True
        if not sys.stdin.isatty():
            return False
        display.show_plan(result)
        return ask("\nWrite the calendar file? [y/N] ").strip().lower() in {"y", "yes", "j", "ja"}
    return confirm


def print_plan(result: AgentResult) -> None:
    """Verified facts straight from the tool results, independent of the LLM text."""
    if result.ingredients is None or result.timeline is None:
        return

    class _View:  # ingredient_lines expects session-like attributes
        request, ingredients, yeast, water = result.request, result.ingredients, result.yeast, result.water

    print("\n── Verified plan (from tool results) " + "─" * 30)
    for line in ingredient_lines(_View):
        print(f"  {line}")
    print()
    for step in result.timeline.steps:
        marker = "●" if step.kind is StepKind.ACTIVE else "○"
        end = f"{step.end:%H:%M}" if step.end.date() == step.start.date() else f"{step.end:%a %H:%M}"
        print(f"  {marker} {step.start:%a %d.%m. %H:%M}–{end:<9} {step.name}")
    for warning in result.yeast.warnings + result.water.warnings:
        print(f"  ! {warning}")


def print_trace(result: AgentResult) -> None:
    print("\n── Tool calls " + "─" * 53)
    for entry in result.trace:
        if entry["ok"]:
            print(f"  ✓ {entry['tool']} ({entry['ms']} ms)")
        else:
            error = entry["result"]
            print(f"  ✗ {entry['tool']}: {error['error']} – {error['message']}")


def print_result(result: AgentResult, trace: bool, display: Display) -> None:
    if trace:
        print_trace(result)
    if result.status == "planned":
        display.show_plan(result)
        print(f"\nCalendar file: {result.ics_path}" if result.ics_path else "\nNo calendar file written.")
    else:
        print(f"\n{result.message}")


def run_offline(args, now: datetime, display: Display) -> AgentResult:
    from fermentation_agent.models import DoughRequest
    from fermentation_agent.pipeline import plan_offline

    missing = [flag for flag, value in (("--pizzas", args.pizzas), ("--target", args.target),
                                        ("--room-temp", args.room_temp), ("--mixing", args.mixing)) if value is None]
    if missing:
        sys.exit(f"Offline mode needs: {', '.join(missing)}")
    request = DoughRequest(
        pizza_count=args.pizzas, target_time=args.target, room_temp_c=args.room_temp, mixing=args.mixing,
        ball_weight_g=args.ball_weight, hydration_pct=args.hydration, salt_pct=args.salt,
        flour_type=args.flour, yeast_type=args.yeast, fridge_temp_c=args.fridge_temp,
    )
    return plan_offline(request, now, confirm=make_confirm(args.yes, display), output_path=args.output)


def run_llm(args, now: datetime, display: Display) -> AgentResult:
    from dotenv import load_dotenv

    from fermentation_agent.agent.loop import FermentationAgent
    from fermentation_agent.agent.openai_client import OPENAI_BASE_URL, create_openai_client
    from fermentation_agent.agent.prompts import build_instructions
    from fermentation_agent.agent.registry import tool_schemas

    load_dotenv()  # before reading any setting, so values from .env apply
    model = args.model or os.environ.get("FERMENTATION_MODEL", "").strip() or DEFAULT_MODEL
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL", "").strip() or OPENAI_BASE_URL
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        if base_url == OPENAI_BASE_URL:
            sys.exit("OPENAI_API_KEY is not set. Put it into .env (see .env.example), "
                     "set OPENAI_BASE_URL for a local server, or use --offline.")
        api_key = "local"  # local servers such as Ollama ignore the key, but the SDK needs one
    client = create_openai_client(api_key, model, build_instructions(now), tool_schemas(), base_url)
    agent = FermentationAgent(client, now, make_confirm(args.yes, display), args.output)

    text = args.prompt or ask("What do you want to bake? ")
    result = agent.send(text)
    # The agent may ask for missing details (e.g. mixing method); keep the conversation going.
    while result.status == "answered" and sys.stdin.isatty():
        reply = ask(f"\n{result.message}\n> ").strip()
        if not reply:
            break
        result = agent.send(reply)
    return result


def main() -> None:
    args = build_parser().parse_args()
    now = args.now or datetime.now(ZoneInfo(config.TIMEZONE))
    display = Display(show_facts=not args.offline)  # offline summary already is the verified template
    result = run_offline(args, now, display) if args.offline else run_llm(args, now, display)
    print_result(result, args.trace, display)
    sys.exit(0 if result.status in {"planned", "answered"} else 1)


if __name__ == "__main__":
    main()
