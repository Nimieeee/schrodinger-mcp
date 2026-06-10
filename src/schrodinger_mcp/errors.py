"""Error taxonomy. Every failure surfaces to MCP as a ``ToolError`` carrying an
actionable message rather than a raw stack trace.

The official MCP SDK raises tool errors when a tool function raises any exception;
we subclass a common ``SchrodingerMCPError`` so the message text is clean and the
``kind`` is machine-readable for callers that inspect it.
"""

from __future__ import annotations


class SchrodingerMCPError(Exception):
    """Base class for all server-raised errors. ``kind`` is a stable string tag."""

    kind = "error"

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:  # what MCP shows the model
        if self.context:
            extras = "; ".join(f"{k}={v}" for k, v in self.context.items() if v)
            return f"[{self.kind}] {self.message}" + (f" ({extras})" if extras else "")
        return f"[{self.kind}] {self.message}"


class InstallationNotFound(SchrodingerMCPError):
    """$SCHRODINGER could not be located or is not a valid install."""

    kind = "installation_not_found"


class LicenseError(SchrodingerMCPError):
    """A Schrödinger license could not be checked out for the requested product."""

    kind = "license_error"


class InvalidInput(SchrodingerMCPError):
    """User-supplied arguments failed validation (before any subprocess ran)."""

    kind = "invalid_input"


class WorkerError(SchrodingerMCPError):
    """A worker script (run under $SCHRODINGER/run) exited non-zero or returned ok=false."""

    kind = "worker_error"


class JobFailed(SchrodingerMCPError):
    """An async job finished in a failed/cancelled state."""

    kind = "job_failed"


class JobNotFound(SchrodingerMCPError):
    """No job with the given id exists in the registry."""

    kind = "job_not_found"


class Timeout(SchrodingerMCPError):
    """A synchronous operation exceeded its timeout; suggest async submission."""

    kind = "timeout"


# --- License-error detection ---------------------------------------------------

_LICENSE_MARKERS = (
    "no valid license",
    "license not available",
    "could not check out",
    "checkout failed",
    "no such feature exists",
    "licensing error",
    "maximum number of users",
    "all licenses in use",
)


def looks_like_license_error(text: str) -> bool:
    """Heuristic: does captured stderr/stdout indicate a license problem?"""
    low = (text or "").lower()
    return any(m in low for m in _LICENSE_MARKERS)
