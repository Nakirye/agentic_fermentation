# Fermentation Planner Agent

An LLM agent that plans Neapolitan pizza dough backwards from the bake time:
exact ingredient amounts, yeast for your temperatures, a step-by-step timeline,
and an `.ics` file for your calendar. Night-time steps are caught and fixed
automatically.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.12+
pip install -e ".[llm,dev]"
cp .env.example .env         # then set OPENAI_API_KEY=sk-...
```

The key is only needed for LLM mode. Offline mode works without it.

## Usage

**With the LLM:** describe what you want, in German or English:

```bash
python cli.py "Samstag 19:00 vier Pizzen, Raum 22 °C"
```

If something is missing (e.g. kneading by hand or with a stand mixer), the agent
asks and you type the answer. Before writing the calendar file, it shows the plan
and asks for confirmation. Run `python cli.py` without text to be prompted.

**With a local model (Ollama):** set the server address and a model that supports
tool calling. No API key needed:

```bash
OPENAI_BASE_URL=http://localhost:11434/v1 FERMENTATION_MODEL=qwen3:14b python cli.py "Samstag 19:00 vier Pizzen"
# or: python cli.py --base-url http://localhost:11434/v1 --model qwen3:14b "..."
```

Small models (under ~8B) often call the tools with wrong values and run out of retries.

**Without an LLM (offline):** pass the values as flags:

```bash
python cli.py --offline --pizzas 4 --target 2026-11-07T19:00 --room-temp 22 --mixing hand
```

Optional: `--hydration 65` · `--ball-weight 250` · `--salt 2.8` · `--fridge-temp 4` ·
`--flour tipo_00|type_550|manitoba|whole_wheat` · `--yeast fresh|active_dry|instant_dry`

### Options

| Option | Effect |
|---|---|
| `--trace` | Print every tool call and guardrail error |
| `-y`, `--yes` | Write the calendar file without asking |
| `-o FILE` | Calendar file path (default `out/plan.ics`) |
| `--now 2026-11-05T18:00` | Pretend it is a different time (reproducible demos) |
| `--model NAME` | OpenAI model (default `gpt-4.1-mini`, or `$FERMENTATION_MODEL`) |

Times without an offset are read as Europe/Vienna.

### Calendar

Import `out/plan.ics` into Google Calendar, Thunderbird, Apple Calendar or Outlook.
Steps where you have to do something get a reminder 10 minutes before. Resting
phases are shown as "free". Importing a plan for the same bake time again
updates the events instead of duplicating them.

## Tests

```bash
pytest
```

All tests run offline with a fake model. No API key needed.

## More

See [PLAN.md](PLAN.md) for the architecture, tools, guardrails and the yeast model.
