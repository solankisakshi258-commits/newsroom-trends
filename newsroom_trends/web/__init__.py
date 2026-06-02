"""Live web dashboard for the trend report."""

from .dashboard import make_server, render_html
from .intelligence import render_intelligence_html

__all__ = ["make_server", "render_html", "render_intelligence_html"]
