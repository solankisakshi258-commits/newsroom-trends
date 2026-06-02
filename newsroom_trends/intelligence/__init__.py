"""Modular, agent-based intelligence layer for the Newsroom AI Intelligence dashboard.

Each "agent" is a small, single-responsibility analyzer that reads the trend report
(the same `latest.json` the classic dashboard uses) and annotates it with a higher-order
signal — competitor gaps, forecasts, Discover potential, topic groupings, story angles.

The engine runs the agents in order and returns an enriched structure for rendering.
Nothing here mutates the pipeline or the existing dashboard; it's a pure read-layer.
"""

from .base import IntelligenceAgent, IntelligenceContext
from .engine import DEFAULT_AGENTS, analyze_report

__all__ = ["IntelligenceAgent", "IntelligenceContext", "analyze_report", "DEFAULT_AGENTS"]
