"""
Tracelet CLI using Typer + Rich.
Modern, interactive analytics interface with real-time feedback.
"""

import json
import logging
from typing import Optional, Callable, TypeVar
import functools
from dataclasses import dataclass

import typer  # type: ignore
from rich.console import Console # type: ignore
from rich.table import Table # type: ignore
from rich.panel import Panel # type: ignore
from rich.text import Text # type: ignore
from rich.live import Live # type: ignore
from rich.spinner import Spinner # type: ignore
from rich import box # type: ignore

from tracelet.db.config import setup_db, DBSetup
from tracelet.tui.services import AnalyticsServiceContext

logger = logging.getLogger("tracelet")
console = Console()
# logger.setLevel("DEBUG")

app = typer.Typer(
    help="📊 Tracelet Analytics — Modern API Performance Insights",
    no_args_is_help=True,
    rich_markup_mode="rich"
)

@dataclass
class CliContext:
    settings: dict
    db_setup: DBSetup
    db_session: object # SQLAlchemy session

# Type variable for decorator
F = TypeVar("F", bound=Callable)

def cli_error_handler(f: F) -> F:
    """Decorator to handle common CLI exceptions."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except typer.Exit:
            raise  # Re-raise TyperExit to allow clean exits
        except Exception as e:
            logger.error("Error in CLI command %s: %s", f.__name__, e, exc_info=True)
            console.print(f"[red]✗ Error: {e}[/red]")
            raise typer.Exit(code=1)
    return wrapper


def load_settings() -> dict:
    """Load Tracelet settings from config file."""
    try:
        with open("settings.json", "r") as f:
            settings = json.load(f)
        logger.debug("Settings loaded from settings.json")
        return settings
    except FileNotFoundError:
        console.print("[red]✗ Error: settings.json not found[/red]")
        console.print("[yellow]Run [bold]tracelet init[/bold] first to configure[/yellow]")
        raise typer.Exit(code=1)
    except json.JSONDecodeError:
        console.print("[red]✗ Error: settings.json is invalid JSON[/red]")
        raise typer.Exit(code=1)

# ============================================================================
# Formatting & Styling Utilities
# ============================================================================

def _format_method_badge(method: str) -> str:
    """Format HTTP method with color."""
    method_colors = {
        "GET": "[cyan]GET[/cyan]",
        "POST": "[green]POST[/green]",
        "PUT": "[yellow]PUT[/yellow]",
        "DELETE": "[red]DELETE[/red]",
        "PATCH": "[magenta]PATCH[/magenta]",
        "HEAD": "[blue]HEAD[/blue]",
        "OPTIONS": "[white]OPTIONS[/white]",
    }
    return method_colors.get(method.upper(), f"[white]{method}[/white]")


def _get_grade_emoji(grade: str) -> str:
    """Get emoji for health grade."""
    return {
        "A": "🟢",
        "B": "🟡",
        "C": "🟠",
        "D": "🔴"
    }.get(grade, "⚪")


def _get_grade_style(grade: str) -> str:
    """Get Rich style for health grade."""
    return {
        "A": "bold green",
        "B": "bold yellow",
        "C": "bold orange1",
        "D": "bold red"
    }.get(grade, "white")


def _format_latency(ms: float) -> str:
    """Format latency with color coding."""
    if ms < 100:
        return f"[green]{ms:.0f}ms[/green]"
    elif ms < 300:
        return f"[yellow]{ms:.0f}ms[/yellow]"
    elif ms < 1000:
        return f"[orange1]{ms:.0f}ms[/orange1]"
    else:
        return f"[red]{ms:.0f}ms[/red]"


def _format_percentage(value: float) -> str:
    """Format percentage with color coding."""
    if value < 1:
        return f"[green]{value:.2f}%[/green]"
    elif value < 5:
        return f"[yellow]{value:.2f}%[/yellow]"
    elif value < 10:
        return f"[orange1]{value:.2f}%[/orange1]"
    else:
        return f"[red]{value:.2f}%[/red]"


def _format_score(value: float) -> str:
    """Format score (0-1) with color coding."""
    if value >= 0.95:
        return f"[green]{value:.2f}[/green]"
    elif value >= 0.85:
        return f"[yellow]{value:.2f}[/yellow]"
    elif value >= 0.70:
        return f"[orange1]{value:.2f}[/orange1]"
    else:
        return f"[red]{value:.2f}[/red]"


# ============================================================================
# Table Renderers
# ============================================================================

def _render_detailed_table(metrics: list, window) -> None:
    """Render detailed metrics table with all statistics."""
    table = Table(
        title=f"📊 Tracelet Analytics — {window.label}",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 1)
    )
    
    table.add_column("Grade", justify="center", width=6)
    table.add_column("Endpoint", style="cyan", no_wrap=False)
    table.add_column("P50", justify="right", width=10)
    table.add_column("P95", justify="right", width=10)
    table.add_column("P99", justify="right", width=10)
    table.add_column("Error", justify="right", width=9)
    table.add_column("RPS", justify="right", width=8)
    table.add_column("Apdex", justify="right", width=8)

    for m in metrics:
        grade_style = _get_grade_style(m.health_grade)
        grade_emoji = _get_grade_emoji(m.health_grade)
        endpoint_label = f"{_format_method_badge(m.method)} {m.path}"
        
        table.add_row(
            f"{grade_emoji} [{grade_style}]{m.health_grade}[/{grade_style}]",
            endpoint_label,
            _format_latency(m.p50_ms),
            _format_latency(m.p95_ms),
            _format_latency(m.p99_ms),
            _format_percentage(m.error_rate_percent),
            f"{m.throughput_rps:.1f}",
            _format_score(m.apdex_score)
        )
    
    console.print(table)
    
    # Summary line
    total_reqs = sum(m.request_count for m in metrics)
    console.print(
        f"\n[dim]├─ Endpoints: {len(metrics)} "
        f"├─ Total Requests: {total_reqs:,} "
        f"├─ Period: {window.duration_human()}[/dim]"
    )


def _render_compact_view(metrics: list, window) -> None:
    logger.debug("Rendering compact view with %d metrics for window %s", len(metrics), window.label)
    """Render compact, minimal view using Rich Table."""
    console.print(f"\n[bold blue]🎯 {window.label}[/bold blue]")
    console.print(
        f"[dim]{window.start.strftime('%Y-%m-%d %H:%M')} → "
        f"{window.end.strftime('%Y-%m-%d %H:%M')}[/dim]\n"
    )

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim cyan",
        box=box.MINIMAL,
        padding=(0, 1)
    )

    table.add_column("Endpoint", style="cyan", no_wrap=True)
    table.add_column("P99", justify="right", width=10)
    table.add_column("Err", justify="right", width=9)
    table.add_column("Grade", justify="center", width=8)

    for m in metrics:
        grade_emoji = _get_grade_emoji(m.health_grade)
        grade_style = _get_grade_style(m.health_grade)
        method_badge = Text.from_markup(_format_method_badge(m.method))
        
        table.add_row(
            Text.assemble(grade_emoji," ", method_badge, " ", m.path),
            _format_latency(m.p99_ms),
            _format_percentage(m.error_rate_percent),
            Text(m.health_grade, style=grade_style)
        )
    
    console.print(table)


def _render_json_output(metrics: list, window) -> None:
    logger.debug("Rendering JSON output with %d metrics for window %s", len(metrics), window.label)
    """Render metrics as JSON for integration."""
    data = {
        "window": {
            "label": window.label,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "duration_seconds": window.total_seconds()
        },
        "metrics": [
            {
                "endpoint_id": m.endpoint_id,
                "path": m.path,
                "method": m.method,
                "framework": m.framework,
                "percentiles": {
                    "p50_ms": m.p50_ms,
                    "p95_ms": m.p95_ms,
                    "p99_ms": m.p99_ms
                },
                "health": {
                    "error_rate_percent": m.error_rate_percent,
                    "throughput_rps": m.throughput_rps,
                    "apdex_score": m.apdex_score,
                    "grade": m.health_grade
                },
                "counts": {
                    "request_count": m.request_count,
                    "error_count": m.error_count
                }
            }
            for m in metrics
        ],
        "summary": {
            "total_endpoints": len(metrics),
            "total_requests": sum(m.request_count for m in metrics),
            "total_errors": sum(m.error_count for m in metrics)
        }
    }
    console.print_json(data=data)


# ============================================================================
# Commands
# ============================================================================

@app.command()
@cli_error_handler
def status(
    ctx: typer.Context,
    duration: str = typer.Option(
        "last_24h",
        "--duration",
        "-d",
        help="⏱️  Time window: 'last_24h', 'last_7d', '3 months', '1 year', etc."
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        "-nc",
        help="🗄️ Bypass cache for this report."
    )
):
    """
    ❤️  Operational Health Overview — Quick status check.
    
    Analyzes all endpoints and shows overall health.
    
    [bold]Examples:[/bold]
    \b
      tracelet status
      tracelet status -d last_24h
      tracelet status -d "7 days"
    """
    session = ctx.obj.db_session
    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Analyzing {duration}...[/cyan]"),
            border_style="cyan"
        ),
        console=console,
        refresh_per_second=1
    ) as live:
        with AnalyticsServiceContext(session) as service:
            report, window = service.generate_operational_report(duration, no_cache=no_cache)

    if not report or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Calculate grade distribution
    grades = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
    for m in report:
        grades[m.health_grade] = grades.get(m.health_grade, 0) + 1
    
    critical = grades['D']
    healthy = grades['A'] + grades['B']
    
    # Overall status
    if critical > 0:
        status_color = "red"
        status_emoji = "🚨"
    elif grades['C'] > 0:
        status_color = "yellow"
        status_emoji = "⚠️"
    else:
        status_color = "green"
        status_emoji = "✅"
    
    # Header panel
    console.print(
        Panel(
            Text(
                f"All Systems Operational\n"
                f"{healthy}/{len(report)} endpoints healthy",
                justify="center"
            ),
            title=f"{status_emoji} Health Report: {window.label}",
            border_style=status_color,
            expand=False
        )
    )
    
    # Detailed table
    _render_detailed_table(report, window)
    
    # Grade distribution bar
    console.print(f"\n[bold]Grade Distribution:[/bold]")
    for grade in ['A', 'B', 'C', 'D']:
        count = grades[grade]
        pct = (count / len(report) * 100) if report else 0
        bar = "█" * count + "░" * (len(report) - count)
        style = _get_grade_style(grade)
        emoji = _get_grade_emoji(grade)
        console.print(
            f"  {emoji} [{style}]{grade}[/{style}] {bar:50} {count} ({pct:.0f}%)"
        )


@app.command()
@cli_error_handler
def describe(
    ctx: typer.Context,
    duration: str = typer.Option(
        "last_7d",
        "--duration",
        "-d",
        help="⏱️  Time window"
    ),
    endpoint_path: Optional[str] = typer.Option(
        None,
        "--endpoint",
        "-e",
        help="🎯 Filter to specific endpoint by path"
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="📋 Output format: 'table', 'compact', 'json'"
    ),
    sort_by: str = typer.Option(
        "p99",
        "--sort",
        "-s",
        help="🔢 Sort by: 'p99', 'error', 'rps', 'apdex'"
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        "-nc",
        help="🗄️ Bypass cache for this report."
    )
):
    """
    📈 Detailed Analytics — Full performance breakdown.
    
    Shows percentiles, error rates, throughput, and health grades.
    
    [bold]Examples:[/bold]
    \b
      tracelet describe
      tracelet describe -d last_24h
      tracelet describe -d "3 months" -e 1
      tracelet describe --sort error -f compact
    """
    session = ctx.obj.db_session

    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Fetching metrics for {duration}...[/cyan]"),
            border_style="cyan"
        ),
        console=console,
        refresh_per_second=1
    ) as live:
        with AnalyticsServiceContext(session) as service:
            metrics, window = service.generate_operational_report(duration_str=duration, endpoint_path=endpoint_path, no_cache=no_cache)

    if not metrics or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Sorting logic
    sort_map = {
        'p99': lambda m: m.p99_ms,
        'error': lambda m: m.error_rate_percent,
        'rps': lambda m: m.throughput_rps,
        'apdex': lambda m: m.apdex_score
    }
    reverse = sort_by != 'apdex'
    metrics.sort(key=sort_map.get(sort_by, lambda m: m.p99_ms), reverse=reverse)

    # Render based on format
    if format == 'table':
        _render_detailed_table(metrics, window)
    elif format == 'compact':
        _render_compact_view(metrics, window)
    elif format == 'json':
        _render_json_output(metrics, window)
    else:
        console.print(f"[red]✗ Unknown format: {format}[/red]")


@app.command()
@cli_error_handler
def top(
    ctx: typer.Context,
    duration: str = typer.Option(
        "last_7d",
        "--duration",
        "-d",
        help="⏱️  Time window"
    ),
    metric: str = typer.Option(
        "p99",
        "--metric",
        "-m",
        help="🎯 Metric: 'p99', 'error', 'slowest'"
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-n",
        help="📊 Number of endpoints to show"
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        "-nc",
        help="🗄️ Bypass cache for this report."
    )
):
    """
    🔥 Anomalies — Top endpoints by metric.
    
    Find your slowest, most error-prone, or most critical endpoints.
    
    [bold]Examples:[/bold]
    \b
      tracelet top -m p99 -n 10
      tracelet top -m error -d last_24h
      tracelet top -m slowest
    """
    session = ctx.obj.db_session
    
    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Finding anomalies in {duration}...[/cyan]"),
            border_style="cyan"
        ),
        console=console,
        refresh_per_second=1
    ) as live:
        with AnalyticsServiceContext(session) as service:
            metrics, window = service.generate_operational_report(duration, no_cache=no_cache)

    if not metrics or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Sort by metric
    if metric == 'p99':
        metrics.sort(key=lambda m: m.p99_ms, reverse=True)
        title = "🐢 Slowest Endpoints (P99)"
    elif metric == 'error':
        metrics.sort(key=lambda m: m.error_rate_percent, reverse=True)
        title = "⚠️  Highest Error Rate"
    elif metric == 'slowest':
        metrics.sort(key=lambda m: m.p99_ms, reverse=True)
        title = "🐢 Slowest Endpoints"
    else:
        console.print(f"[red]✗ Unknown metric: {metric}[/red]")
        return

    metrics = metrics[:limit]
    
    console.print(f"\n[bold blue]{title} — {window.label}[/bold blue]\n")

    for i, m in enumerate(metrics, 1):
        grade_emoji = _get_grade_emoji(m.health_grade)
        grade_style = _get_grade_style(m.health_grade)
        method_badge = _format_method_badge(m.method)
        
        console.print(f"[bold]{i}.[/bold] {method_badge} {m.path}")
        console.print(
            f"    P99: {_format_latency(m.p99_ms):15} │ "
            f"Error: {_format_percentage(m.error_rate_percent):12} │ "
            f"Apdex: {_format_score(m.apdex_score):8} │ "
            f"Grade: [{grade_style}]{m.health_grade}[/{grade_style}] {grade_emoji}"
        )
        console.print()


@app.command()
@cli_error_handler
def list_endpoints(
    ctx: typer.Context,
    framework: Optional[str] = typer.Option(
        None,
        "--framework",
        "-f",
        help="🏗️  Filter by framework: fastapi, django, flask"
    ),
    method: Optional[str] = typer.Option(
        None,
        "--method",
        "-m",
        help="🔗 Filter by HTTP method: GET, POST, PUT, DELETE"
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        "-nc",
        help="🗄️ Bypass cache for this report."
    )
):
    """
    📋 Endpoints — List all monitored endpoints.
    
    [bold]Examples:[/bold]
    \b
      tracelet list
      tracelet list --framework fastapi
      tracelet list --method GET
    """
    session = ctx.obj.db_session
    
    with AnalyticsServiceContext(session) as service:
        endpoints = service.engine.fetch_active_endpoints(cache_bypass=no_cache)

    if not endpoints:
        console.print("[yellow]ℹ️  No endpoints found[/yellow]")
        return

    # Filter
    if framework:
        endpoints = [ep for ep in endpoints if ep['framework'].lower() == framework.lower()]
    if method:
        endpoints = [ep for ep in endpoints if ep['method'].upper() == method.upper()]

    if not endpoints:
        console.print("[yellow]ℹ️  No endpoints matching filters[/yellow]")
        return

    # Create table
    table = Table(
        title="📋 Monitored Endpoints",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        box=box.ROUNDED
    )
    table.add_column("ID", justify="right", style="cyan", width=6)
    table.add_column("Method", style="green", width=10)
    table.add_column("Path", style="magenta")
    table.add_column("Framework", style="yellow", width=12)

    for ep in endpoints:
        table.add_row(
            str(ep['id']),
            _format_method_badge(ep['method']),
            ep['path'],
            ep['framework']
        )

    console.print(table)
    console.print(f"\n[dim]├─ Total: {len(endpoints)} endpoint{'s' if len(endpoints) != 1 else ''}[/dim]")

@app.callback()
def main(ctx: typer.Context):
    """Tracelet CLI — Modern API Performance Analytics."""
    try:
        settings_data = load_settings()
        db_setup = setup_db(settings_data.get("db_config", {}))
        db_session = db_setup.SessionLocal()
        ctx.obj = CliContext(settings=settings_data, db_setup=db_setup, db_session=db_session)
    except typer.Exit:
        raise
    except Exception as e:
        logger.error("Error during CLI startup: %s", e, exc_info=True)
        console.print(f"[red]✗ Error during startup: {e}[/red]")
        raise typer.Exit(code=1)
    
    # Register cleanup on exit
    def _cleanup_session():
        if ctx.obj and ctx.obj.db_session:
            ctx.obj.db_session.close()
            logger.debug("Database session closed on CLI exit")
    ctx.call_on_close(_cleanup_session)


if __name__ == "__main__":
    app()