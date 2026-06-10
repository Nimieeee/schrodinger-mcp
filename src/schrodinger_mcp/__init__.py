"""Schrödinger Suites MCP server.

Exposes Schrödinger Suites 2026 computational-chemistry workflows (structure prep,
Glide docking, ADMET/site analysis, QM/MM-GBSA) as MCP tools so Claude can drive them.

Architecture: the server runs in its own venv and shells out to ``$SCHRODINGER/run``
for all chemistry. See ``schrodinger_mcp.runner`` for the subprocess boundary.
"""

__version__ = "0.1.0"
