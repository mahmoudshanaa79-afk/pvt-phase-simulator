"""Public API for OpenPhase validation evidence reports.

Plotly is imported only when figures or HTML are actually rendered.
"""

from .evidence import (
    REPORT_FORMAT,
    REPORT_SCHEMA_VERSION,
    UnsupportedDataClassError,
    ValidationEvidence,
    build_validation_evidence,
)
from .exports import (
    ArtifactFile,
    ReportArtifacts,
    export_case_ledger_csv,
    export_comparisons_csv,
    export_json,
    write_validation_report,
)
from .html import render_html
from .membership import EvidenceInconsistencyError

__all__ = [
    "REPORT_FORMAT",
    "REPORT_SCHEMA_VERSION",
    "ArtifactFile",
    "EvidenceInconsistencyError",
    "ReportArtifacts",
    "UnsupportedDataClassError",
    "ValidationEvidence",
    "build_validation_evidence",
    "export_case_ledger_csv",
    "export_comparisons_csv",
    "export_json",
    "render_html",
    "write_validation_report",
]
