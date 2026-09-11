"""Professional reporting pipeline for VAPT platform.

Provides a clean separation between:
- ReportModel: canonical report content
- ReportBuilder: builds ReportModel from domain/persisted state
- Renderers: export ReportModel to JSON/HTML/Markdown/TXT

Architecture:
    DomainResult / PersistentRun
            ↓
    ReportBuilder
            ↓
    ReportModel
            ↓
    JSON / HTML / Markdown / TXT renderers
"""
from __future__ import annotations

from .models import ReportModel, EvidenceTier, ReportMetadata
from .builder import ReportBuilder
from .renderers import (
    JSONRenderer,
    HTMLRenderer,
    MarkdownRenderer,
    TXTRenderer,
    get_renderer,
)

__all__ = [
    "ReportModel",
    "EvidenceTier",
    "ReportMetadata",
    "ReportBuilder",
    "JSONRenderer",
    "HTMLRenderer",
    "MarkdownRenderer",
    "TXTRenderer",
    "get_renderer",
]
