import importlib

import pytest

MODULES = [
    "fermentation_agent.config",
    "fermentation_agent.tools.bakers_math",
    "fermentation_agent.tools.yeast",
    "fermentation_agent.tools.water_temp",
    "fermentation_agent.tools.timeline",
    "fermentation_agent.tools.schedule_check",
    "fermentation_agent.tools.calendar_ics",
    "fermentation_agent.guardrails.input",
    "fermentation_agent.guardrails.schedule",
    "fermentation_agent.guardrails.output",
    "fermentation_agent.agent.loop",
    "fermentation_agent.agent.registry",
    "fermentation_agent.agent.openai_client",
    "fermentation_agent.pipeline",
    "cli",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)
