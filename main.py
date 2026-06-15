"""
Wholesale Agency CLI — entry point for running the pipeline.

Usage examples:
  python main.py ingest --source tax_delinquent_csv --file leads.csv
  python main.py pipeline --source tax_delinquent_csv --file leads.csv
  python main.py audit-log
  python main.py score-leads --file leads.csv
  python main.py draft-sms --lead-id <uuid>
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from config.settings import settings
from orchestrator import MasterOrchestrator
from schemas.property import DataSource
from tools.crm import CRMStore
from tools.data_providers import DataProviderFactory

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/agency.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    name="wholesale-agency",
    help="AI-Native Texas Wholesale Agency — Claude Code Orchestration System",
    no_args_is_help=True,
)

# Global orchestrator (lazy init to avoid loading API keys at import)
_orchestrator: Optional[MasterOrchestrator] = None
_crm: Optional[CRMStore] = None


def get_orchestrator() -> MasterOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MasterOrchestrator()
    return _orchestrator


def get_crm() -> CRMStore:
    global _crm
    if _crm is None:
        _crm = CRMStore()
    return _crm


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command()
def ingest(
    source: Annotated[str, typer.Option(help="Data source name")] = "manual",
    file: Annotated[Optional[str], typer.Option(help="CSV file path")] = None,
    dry_run: Annotated[bool, typer.Option(help="Parse only, don't save")] = False,
) -> None:
    """Ingest and normalize property leads from a data source."""
    async def _run():
        orch = get_orchestrator()
        crm = get_crm()

        provider = DataProviderFactory.get(source)
        source_enum = _source_enum(source)

        if file:
            raw_records = provider.fetch(file_path=file)
        else:
            console.print("[red]Error: --file is required for CSV sources[/red]")
            raise typer.Exit(1)

        console.print(f"[blue]Ingesting {len(raw_records)} records from {source}...[/blue]")
        leads = orch.ingest_leads(raw_records, source_enum)

        new_count = 0
        dup_count = 0
        if not dry_run:
            for lead in leads:
                if crm.save_lead(lead, dedup=True):
                    new_count += 1
                else:
                    dup_count += 1

        _print_leads_table(leads)
        if dry_run:
            console.print(f"\n[green]✓ {len(leads)} leads parsed (dry run)[/green]")
        else:
            console.print(
                f"\n[green]✓ {new_count} new leads ingested"
                f"{f', {dup_count} duplicates updated' if dup_count else ''}[/green]"
            )
    
    asyncio.run(_run())


@app.command()
def pipeline(
    source: Annotated[str, typer.Option(help="Data source")] = "manual",
    file: Annotated[Optional[str], typer.Option(help="CSV file")] = None,
    json_records: Annotated[Optional[str], typer.Option(help="Inline JSON records")] = None,
) -> None:
    """Run the full pipeline: ingest → score → underwrite → outreach drafts."""
    async def _run():
        orch = get_orchestrator()
        crm = get_crm()

        if file:
            provider = DataProviderFactory.get(source)
            raw_records = provider.fetch(file_path=file)
        elif json_records:
            raw_records = json.loads(json_records)
        else:
            console.print("[red]Error: provide --file or --json-records[/red]")
            raise typer.Exit(1)

        source_enum = _source_enum(source)
        console.print(f"[blue]Running full pipeline on {len(raw_records)} records...[/blue]")

        state = await orch.run_full_pipeline(raw_records, source_enum)

        # Persist everything to CRM (dedup leads by address)
        for lead in state.raw_leads:
            crm.save_lead(lead, dedup=True)
        for deal in state.active_deals:
            crm.save_deal(deal)
        for entry in orch.export_audit_log():
            from schemas.compliance import AuditLogEntry
            crm.save_audit_entry(AuditLogEntry(**entry))

        # Print summary
        console.print(f"\n[bold green]Pipeline Summary[/bold green]")
        console.print(f"  Leads ingested:     {len(state.raw_leads)}")
        console.print(f"  Passed distress:    {len(state.scored_leads)}")
        console.print(f"  Viable deals:       {len(state.underwriting_reports)}")
        console.print(f"  Outreach drafted:   {len(state.outreach_messages)}")
        console.print(f"  Dispo matches:      {len(state.dispo_results)}")

        if state.dispo_results:
            console.print("\n[bold]Top Dispo Matches:[/bold]")
            for result in state.dispo_results:
                console.print(f"  Deal: {result.lead_address}")
                if result.top_matches:
                    winner = next((m for m in result.top_matches if m.recommended), None)
                    if winner:
                        console.print(f"    → Winner: {winner.buyer_name} (score={winner.combined_score:.0f})")

    asyncio.run(_run())


@app.command()
def audit_log(
    agent: Annotated[Optional[str], typer.Option(help="Filter by agent name")] = None,
    limit: Annotated[int, typer.Option(help="Max entries")] = 50,
) -> None:
    """Print the audit log."""
    crm = get_crm()
    entries = crm.get_audit_log(agent=agent, limit=limit)

    table = Table(title="Audit Log", show_lines=True)
    table.add_column("Timestamp", style="dim")
    table.add_column("Agent")
    table.add_column("Action")
    table.add_column("Entity")
    table.add_column("Status")
    table.add_column("Output")

    for e in entries:
        table.add_row(
            str(e["timestamp"])[:19],
            e["agent"],
            e["action"],
            f"{e['entity_type']}:{e['entity_id'] or '—'}"[:30],
            e["status"],
            (e["output_summary"] or "")[:40],
        )

    console.print(table)


@app.command()
def show_deals() -> None:
    """List all active deals."""
    crm = get_crm()
    deals = crm.get_active_deals()

    if not deals:
        console.print("[yellow]No active deals found[/yellow]")
        return

    table = Table(title="Active Deals", show_lines=True)
    table.add_column("Deal ID")
    table.add_column("Lead ID")
    table.add_column("Status")
    table.add_column("Contract Price")
    table.add_column("Created")

    for d in deals:
        table.add_row(
            d["id"][:8] + "...",
            d["lead_id"][:8] + "...",
            d["status"],
            f"${d['contract_price']:,.0f}" if d.get("contract_price") else "—",
            str(d["created_at"])[:10],
        )

    console.print(table)


@app.command()
def show_buyers() -> None:
    """List all active qualified buyers."""
    crm = get_crm()
    buyers = crm.get_active_buyers()

    if not buyers:
        console.print("[yellow]No buyers found. Run buyer sourcing first.[/yellow]")
        return

    table = Table(title="Active Buyers", show_lines=True)
    table.add_column("Name")
    table.add_column("Company")
    table.add_column("Source")
    table.add_column("Reliability")
    table.add_column("Added")

    for b in buyers:
        table.add_row(
            b["name"],
            b.get("company", "—"),
            b["source"],
            f"{b['reliability_score']:.0f}/100",
            str(b["created_at"])[:10],
        )

    console.print(table)


@app.command()
def show_leads() -> None:
    """List all leads in the CRM."""
    crm = get_crm()
    leads = crm.get_all_leads()

    if not leads:
        console.print("[yellow]No leads found[/yellow]")
        return

    table = Table(title="Leads", show_lines=True)
    table.add_column("ID")
    table.add_column("Address")
    table.add_column("Owner")
    table.add_column("Source")
    table.add_column("Distress Score")
    table.add_column("Flagged")

    for lead in leads:
        table.add_row(
            lead["id"][:8] + "...",
            (lead.get("address_full") or "")[:35],
            (lead.get("owner_name") or "")[:20],
            lead.get("source", ""),
            str(lead.get("distress_score") or "—"),
            "⚑" if lead.get("flagged") else "",
        )

    console.print(table)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _source_enum(source: str) -> DataSource:
    mapping = {
        "tax_delinquent_csv": DataSource.TAX_DELINQUENT,
        "tax_delinquent": DataSource.TAX_DELINQUENT,
        "probate_csv": DataSource.PROBATE,
        "probate": DataSource.PROBATE,
        "propstream": DataSource.PROPSTREAM,
        "batchleads": DataSource.BATCHLEADS,
        "manual": DataSource.MANUAL,
    }
    return mapping.get(source, DataSource.MANUAL)


def _print_leads_table(leads) -> None:
    table = Table(show_lines=True)
    table.add_column("Owner")
    table.add_column("Address")
    table.add_column("Source")
    table.add_column("Confidence")
    table.add_column("Flagged")

    for lead in leads:
        table.add_row(
            lead.owner_name[:25],
            lead.address.full[:40],
            lead.source.value,
            f"{lead.source_confidence:.2f}",
            "⚑" if lead.flagged else "",
        )
    console.print(table)


@app.command()
def migrate() -> None:
    """Run database migrations."""
    from tools.run_migrations import run_migrations
    console.print("[blue]Running database migrations...[/blue]")
    run_migrations()
    console.print("[green]✓ Migrations complete[/green]")


if __name__ == "__main__":
    app()
