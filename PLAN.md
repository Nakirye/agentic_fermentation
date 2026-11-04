# Implementation Plan – Fermentation Planner Agent

Goal: an LLM agent that turns *"Samstag 19:00, vier Neapolitanische Pizzen, 65 %, Raum 22 °C"*
into exact ingredient amounts, a backwards-scheduled timeline and an `.ics` calendar file,
protected by rule-based guardrails.

Scope: Neapolitan-style pizza with commercial yeast. Sourdough is listed as future work.

## Architecture

```text
User text ─► LLM (extract params, orchestrate) ─► allowlisted dispatcher ─► Python tools
                ▲                                        │  (Pydantic-validated args)
                └──── results / GuardrailError + hint ◄──┘
                │
                ├─ validate_schedule fails → LLM adjusts phases/temps (max 3 retries)
                ▼
     Plan shown to user ─► confirm? ─► create_calendar_events (.ics)  ◄─ app code, not LLM
                ▼
     LLM summary ─► output guardrail (numbers must match tool facts) ─► print + trace
```

The LLM never computes numbers or times. Its "knobs" are the **phase list** (durations,
fridge vs. room) and the **target dough temperature**. Everything else is derived.

## Module map (already scaffolded)

| Module | Responsibility |
|---|---|
| `models.py` | Pydantic schemas (done) |
| `config.py` | All limits and constants, one place |
| `errors.py` | `GuardrailError(rule, message, hint)` (done) |
| `tools/bakers_math.py` | grams from percentages |
| `tools/yeast.py` | multi-phase fermentation model |
| `tools/water_temp.py` | water temperature for target dough temp |
| `tools/timeline.py` | backwards scheduling |
| `tools/schedule_check.py` | LLM-callable wrapper around schedule guardrails |
| `tools/calendar_ics.py` | `.ics` export |
| `guardrails/input.py` · `schedule.py` · `output.py` | rule checks |
| `agent/model.py` | `ModelClient` protocol + `FakeModelClient` (done) |
| `agent/openai_client.py` | real LLM adapter |
| `agent/registry.py` | tool allowlist, JSON schemas, dispatcher |
| `agent/loop.py` | bounded agent loop + trace |
| `pipeline.py` | offline mode: same tools, fixed order, no LLM |
| `cli.py` | entry point |

## Phases

Each phase ends with passing tests. Phases 1–3 need no LLM and no API key.

### Phase 1 – Calculation tools

1. **`calculate_bakers_math`**
   `total = count · ball_weight · (1 + waste)`; `flour = total / (1 + h + s + y)`;
   water/salt/yeast = flour × percentage. Round to 1 g (yeast to 0.1 g).
   *Tests:* 4 × 250 g @ 65 % / 2.8 % → known reference values; sum of parts == total.
2. **`calculate_yeast_percentage`** – see *Yeast model* below.
   *Tests:* each calibration point within ±25 %; more time → less yeast (monotonic);
   colder → less effective time; clamping sets `clamped=True`.
3. **`calculate_water_temperature`**
   `water = 3·target − room − flour − friction`.
   *Tests:* textbook example; warnings at < 2 °C and > 35 °C.

### Phase 2 – Timeline + calendar

4. **`build_timeline`**: walk backwards from `target_time`:
   bake (15 min, active) ← preheat (45 min, overlaps final proof) ← final proof phase(s)
   (passive) ← balling (15 min, active) ← bulk phases (passive, the first one contains
   the stretch & folds as active 5-min steps) ← knead (active) ← autolyse (passive) ← mix (active).
   Use aware datetimes in `Europe/Vienna`. DST: compute in UTC and convert, test across
   the last-Sunday-of-October switch.
   *As built:* `target_time` = bake **starts**. Balling defaults to before the last phase
   (`ball_before_phase` moves it, e.g. before the cold retard). "Put in / take out of
   fridge" are active steps at the start/end of each cold stretch, so balling is always at
   room temperature. Invalid plans (< 2 phases, folds not fitting) raise `GuardrailError`
   with a hint for the LLM. Step names are unique (needed for UIDs).
5. **`create_calendar_events`**: hand-written RFC 5545 (no dependency): `VCALENDAR` +
   one `VEVENT` per step, `UID = sha1(target_time + step name)@fermentation-agent`,
   `VALARM` 10 min before active steps. Line folding at 75 octets.
   *As built:* times in UTC (`…Z`) instead of `TZID`, so no `VTIMEZONE` block is needed.
   Passive steps are `TRANSP:TRANSPARENT` (don't block the calendar). Optional `notes`
   (ingredients) go into the first event. Verified with the `icalendar` library.
   *Open:* manual import into Google Calendar / Thunderbird, screenshot for README.

### Phase 3 – Guardrails

6. **Input** (`validate_request`): ranges from `config.py`; hydration limit per flour type;
   target in the future. Raises `GuardrailError` with a `hint` the LLM can act on.
7. **Schedule**: `check_sleep_window` (only **active** steps, window 23:00–07:00, also
   catches steps that *span* the window); `check_feasibility` (first step ≥ now + 15 min;
   if impossible even with the shortest allowed plan → tell user, propose new time).
8. **Output** (`check_summary_numbers`): regex out numbers followed by g/%/°C/time; each
   must match a fact from the tool results. On mismatch: one regeneration, then fall back
   to a template summary. Numbers are additionally printed in a table from the tool data,
   so the user sees verified facts regardless.
9. **Loop limits**: `MAX_AGENT_TURNS = 12`, `MAX_SCHEDULE_RETRIES = 3`, unknown tool name
   → error result, invalid JSON args → error result (never crash).
10. **Side-effect gate**: calendar export is not in the tool registry; `run_agent` calls
    it only if `confirm(timeline)` returns True.
11. **Scope / injection**: system prompt restricts to dough planning; off-topic → refusal
    without tool calls. User text is passed as data; tool results are JSON, never
    concatenated into instructions.

*Tests:* one test per rule, including the *03:30 stretch & fold* case from the proposal.

*As built (6–8):*
- `validate_request` collects **all** problems into one `GuardrailError` (rule
  `invalid_input` if several), so the LLM can fix everything in one step. Also rejects
  bake times more than 14 days ahead. `check_user_text` strips control characters and
  rejects empty or > 2000-character input.
- Sleep violations tell the LLM how far the step would have to move ("4 h 35 min
  earlier or 3 h 30 min later"). Steps ending at or after the bake time (preheat, bake)
  are exempt: a late pizza night is the user's choice. `too_soon` proposes the earliest
  possible bake time (rounded up to the quarter hour).
- Output: `collect_facts(values)` walks all tool args/results (numbers, clock times, step
  durations, total plan length); `check_summary_numbers(summary, facts)` accepts a number
  only if it is a correct rounding at its written precision ("2 g" ok for 1.9 g, "600 g"
  not for 610 g). Handles German formats (1,9 g · 1.025 g · 19.00 Uhr) and kg/h/min
  conversions. Bare numbers without a unit are ignored.
- Items 9–11 (loop limits, calendar gate, scope prompt) live in the agent loop and the
  registry, so they are implemented and tested in phase 4.

### Phase 4 – Agent

12. **`offline pipeline`** (`plan_offline`): fixed order with a simple retry strategy
    (lengthen/shorten the cold phase in 2 h steps until the sleep check passes). This is
    the baseline and proves the tools work without an LLM.
13. **Registry**: Pydantic arg models → `model_json_schema()` → tool schemas. Registered:
    `calculate_bakers_math`, `calculate_yeast_percentage`, `calculate_water_temperature`,
    `build_timeline`, `validate_schedule`.
14. **System prompt**: role; current date/time and timezone injected; defaults (250 g balls,
    2.8 % salt, fridge 4 °C, Tipo 00, fresh yeast) and that it must *state* used defaults;
    ask a clarifying question if pizza count, target time or **mixing method (hand / stand
    mixer)** is missing – mixing is always asked, never assumed; required tool order;
    "never compute numbers yourself"; on `sleep_window` violation adjust phases, not the
    target time; final answer in the user's language, motivating tone, short.
15. **`run_agent`**: loop with trace (tool name, args, result, duration); after the final
    answer → output guardrail → confirmation → `.ics`.
16. **LLM adapter**: implement `OpenAIModelClient.respond` (Responses API, function calls,
    history replay — same pattern as the crimson project).
    *Tests:* `FakeModelClient` scripts for: happy path; sleep violation → retry → success;
    retries exhausted → clean failure; hallucinated number in summary → caught;
    off-topic prompt → no tool calls.

### Phase 5 – CLI, docs, submission

17. **CLI**: LLM mode (prompt string), `--offline` with flags, `--now` for reproducible
    demos, `--yes`, `--trace` to print the tool-call log, `-o out/plan.ics`.
18. **README** (German or English, see open decisions): process description, why an agent,
    tool list, guardrail table, setup, example run with trace, limitations.
19. **Evaluation**: 3–5 live scenarios with the real LLM, logged (prompt, trace, result),
    incl. one that triggers the sleep guardrail and one that triggers the hydration guardrail.
20. `git init`, push to GitHub/Gitea.

## Yeast model

Model (implemented in `tools/yeast.py`): convert every phase to *equivalent hours at 24 °C*,
then a power law gives the fresh yeast amount.

```
rate(T) = 2^((T − 24)/10)                         for T ≥ 15 °C
        = rate(15) · Q10_COLD^((T − 15)/10)       below 15 °C (fridge)
eq_h    = Σ hours_i · rate(T_i)
pct     = K · eq_h^(−a)          (fresh yeast, clamped to 0.02–3 %)
dry     = pct · conversion       (instant 0.33, active dry 0.4)
```

Why two regimes: with a single Q10 = 2, cold-retarded doughs came out about 3× too low,
because yeast activity collapses in the fridge.

Fitted by `scripts/calibrate_yeast.py` (grid search, squared log error) against
`data/yeast_reference.json`: `Q10_COLD = 6.75`, `K = 41.0`, `a = 2.55`. All six reference
doughs are within ±16 %. Extrapolation checked: 3 h @ 24 °C → ~2.5 %, 5 days fridge → ~0.07 %.

**Open:** the reference values are typical figures, not yet cited. Replace each `source`
field with a real reference and rerun the script before submission. The README must say
this is a heuristic (target ±25 %), not a lab model.

## Definition of done

- `pytest` green offline (no key needed), covering every tool and every guardrail
- `python cli.py --offline ...` and `python cli.py "<German prompt>"` both produce
  ingredients, timeline and a valid `.ics`
- Demo shows at least one guardrail-driven self-correction in the trace
- README explains process, tools, guardrails, limitations

## Decisions

1. **LLM provider** – OpenAI (`gpt-4.1-mini`), Responses API.
2. **Calendar** – `.ics` export only, no calendar API.
3. **Docs language** – README in English.
4. **Mixing method** – the agent must ask (hand vs. stand mixer). `DoughRequest.mixing` has
   no default, so a request without it fails validation.

## Status

- [x] Scaffold
- [x] Phase 1 – baker's math, yeast model (calibrated), water temperature + tests
- [x] Phase 2 – timeline + `.ics`
- [x] Phase 3 – guardrails (input, schedule, output; loop-level ones in phase 4)
- [ ] Phase 4 – agent
- [ ] Phase 5 – CLI, README, evaluation, submission
