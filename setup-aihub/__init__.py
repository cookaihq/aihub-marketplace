"""Hermes native registration; all hosts consume the same complete Plugin source."""
from pathlib import Path


def register(ctx):
    # setup-api-key retains its existing three-host execution scope.
    ctx.register_skill("setup-agent-model", Path(__file__).parent / "skills/setup-agent-model/SKILL.md")
