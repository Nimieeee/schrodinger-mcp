# schrodinger-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes **Schrödinger Suites 2026**
computational-chemistry / drug-discovery workflows to Claude (Claude Code and Claude
Desktop). Ask Claude to fetch a PDB, prep a protein and ligands, build a Glide grid, dock,
score, run ADMET, MM-GBSA, or QM — it drives Schrödinger for you and hands back ranked
tables plus files you can open in Maestro.

## How it works

The server runs in its **own virtualenv** (any Python ≥3.10) and shells out to
`$SCHRODINGER/run` for all chemistry. Its MCP dependencies therefore stay independent of
Schrödinger's bundled Python 3.11. Fast operations return inline; long jobs run under a
detached supervisor that survives server restarts, and you poll them with
`get_job_status` / `get_job_results`.

```
Claude ──tool call──▶ schrodinger-mcp (venv, FastMCP, stdio)
                         │  fast ops ─▶ $SCHRODINGER/run python3 <worker>  ─▶ JSON
                         └  long jobs ─▶ detached supervisor ─▶ $SCHRODINGER/<launcher> -WAIT
                                          └─ status.json (authoritative) ◀─ poll
```

Outputs are written under `~/.local/share/schrodinger-mcp/` (override with
`SCHRODINGER_MCP_HOME`) and every tool also returns a structured summary.

## Requirements

- macOS/Linux with **Schrödinger Suites 2026** installed and licensed
  (auto-detected at `/opt/schrodinger/suites*`, or set `SCHRODINGER`).
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`.

> This project contains **no Schrödinger software or data**. You must supply your
> own licensed installation of Schrödinger Suites; this server only invokes it
> through its documented `$SCHRODINGER/run` / CLI interfaces.

> **GPU note:** Desmond molecular dynamics and FEP+ require an NVIDIA/CUDA GPU and are
> intentionally **not** exposed — they are not practical on Apple Silicon / non-NVIDIA hosts.

## Install

```bash
cd "/Users/mac/schrodinger mcp"
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Sanity check:

```bash
python -c "from schrodinger_mcp.tools.foundation import detect_installation as d; print(d()['version'])"
```

## Register with Claude

**Claude Code** (the `--` separates the launch command; quote the spaced path):

```bash
claude mcp add schrodinger \
  --env SCHRODINGER=/opt/schrodinger/suites2026-1 \
  -- "/Users/mac/schrodinger mcp/.venv/bin/schrodinger-mcp"
```

**Claude Desktop** — add to
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "schrodinger": {
      "command": "/Users/mac/schrodinger mcp/.venv/bin/schrodinger-mcp",
      "args": [],
      "env": { "SCHRODINGER": "/opt/schrodinger/suites2026-1" }
    }
  }
}
```

Restart the client; the `schrodinger` tools and the `schrodinger://installation` resource
appear.

## Tools

**Foundation (synchronous)**

| Tool | What it does |
|---|---|
| `detect_installation` | Report root, version, installed workflows, hosts, GPU |
| `fetch_pdb` | Download a structure from RCSB by 4-char PDB ID |
| `convert_structure` | Convert between mae/maegz/sdf/pdb/mol2/smi/cif |
| `structure_info` | Counts, titles, charges, MW, chains, properties |
| `smiles_to_3d` | Quick single-conformer 3D from SMILES |
| `split_structures` / `merge_structures` | Split a multi-structure file / concatenate |

**Preparation (async)** — `ligprep`, `protein_prepwizard`, `epik`, `confgen`

**Glide docking** — `generate_glide_grid`, `glide_dock` (SP/XP), `summarize_docking` (sync)

**ADMET & site analysis** — `qikprop`, `compute_descriptors` (sync), `sitemap`, `shape_screen`

**QM & MM-GBSA** — `prime_mmgbsa`, `jaguar_qm`

**Async job control** — `get_job_status`, `get_job_results`, `cancel_job`, `list_jobs`

Async tools return a `job_id` immediately. Poll `get_job_status(job_id)` until
`state == "completed"`, then `get_job_results(job_id)` for the output files.

## Example: dock a ligand against a target

```
1. fetch_pdb("1HSG")                     → receptor.pdb
2. protein_prepwizard(receptor.pdb)      → job → prepared.maegz
3. ligprep("CC(=O)Oc1ccccc1C(=O)O")      → job → ligprep_out.maegz
4. generate_glide_grid(prepared, center=[x,y,z] or ligand_ref=...) → job → grid.zip
5. glide_dock(grid.zip, ligprep_out, precision="SP")  → job → dock_pv.maegz
6. summarize_docking(dock_pv.maegz)      → ranked GlideScore table
```

## Testing

```bash
pytest tests/test_unit.py -q            # fast unit tests, no Schrödinger needed
python tests/manual_docking_e2e.py      # real end-to-end docking (bundled fixture, ~3 min)
python tests/manual_wave5.py            # qikprop / MM-GBSA / sitemap / shape / jaguar
```

Inspect the live MCP server with the official inspector:

```bash
npx @modelcontextprotocol/inspector "/Users/mac/schrodinger mcp/.venv/bin/schrodinger-mcp"
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `SCHRODINGER` | autodetect | Install root |
| `SCHRODINGER_MCP_HOME` | `~/.local/share/schrodinger-mcp` | Job dirs, scratch, registry |
| `SCHRODINGER_MCP_MAX_JOBS` | `2` | Concurrent heavy-job advisory limit |
| `SCHRODINGER_MCP_SYNC_TIMEOUT` | `120` | Seconds before a sync op suggests going async |

## Disclaimer & trademarks

This is an **independent, unofficial** project. It includes no Schrödinger software,
source, or data, and requires a separately licensed Schrödinger Suites installation.

Schrödinger, Maestro, Glide, Desmond, Jaguar, Prime, QikProp, Epik, Phase, Canvas,
and SiteMap are trademarks of **Schrödinger, LLC**. This project is not affiliated
with, endorsed by, or sponsored by Schrödinger, LLC; product names are used only to
describe interoperability. Use of Schrödinger software is governed by your own license
agreement with Schrödinger — consult it before publishing benchmarks or results.

## License

[MIT](LICENSE) © 2026. Your use of the underlying Schrödinger Suites remains subject
to your Schrödinger license.
