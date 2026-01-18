"""
Tracelet CLI using Typer + Rich.
Modern, interactive analytics interface with real-time feedback.
"""

import json
import logging
import os
from typing import Optional, Callable, TypeVar
import functools
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich import box

from tracelet.db.config import setup_db, DBSetup
from tracelet.tui.services import AnalyticsServiceContext
from tracelet.config import settings

logger = logging.getLogger("tracelet")
console = Console()
# logger.setLevel("DEBUG")

app = typer.Typer(
    help="📊 Tracelet Analytics — Modern API Performance Insights",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@dataclass
class CliContext:
    db_setup: Optional[DBSetup] = None
    db_session: Optional[object] = None  # SQLAlchemy session


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


def load_db_env() -> Optional[str]:
    """Load the database environment variable name from config file, if it exists."""
    if not settings.CONFIG_FILE.exists():
        return None

    try:
        with open(settings.CONFIG_FILE, "r") as f:
            config = json.load(f)
        db_env_var_name = config.get("db_env_variable_name")
        if db_env_var_name:
            logger.debug(
                f"DB environment variable name '{db_env_var_name}' loaded from config.json"
            )
        return db_env_var_name

    except json.JSONDecodeError:
        logger.warning(
            "Config file is corrupted. Starting with no database environment variable set."
        )
        return None


def save_db_env(env_var_name: Optional[str]):
    """Save the database environment variable name to config.json."""
    settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current_config = {}
    if settings.CONFIG_FILE.exists():
        try:
            with open(settings.CONFIG_FILE, "r") as f:
                current_config = json.load(f)
        except json.JSONDecodeError:
            logger.warning(
                f"Config file {settings.CONFIG_FILE} is corrupted. Overwriting."
            )

    if env_var_name:
        current_config["db_env_variable_name"] = env_var_name
    else:
        current_config.pop("db_env_variable_name", None)

    with open(settings.CONFIG_FILE, "w") as f:
        json.dump(current_config, f, indent=2)
    logger.debug(f"DB environment variable name {env_var_name} stored in config.json")


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
    return {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⚪")


def _get_grade_style(grade: str) -> str:
    """Get Rich style for health grade."""
    return {
        "A": "bold green",
        "B": "bold yellow",
        "C": "bold orange1",
        "D": "bold red",
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
        padding=(0, 1),
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
            _format_score(m.apdex_score),
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
    logger.debug(
        "Rendering compact view with %d metrics for window %s",
        len(metrics),
        window.label,
    )
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
        padding=(0, 1),
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
            Text.assemble(grade_emoji, " ", method_badge, " ", m.path),
            _format_latency(m.p99_ms),
            _format_percentage(m.error_rate_percent),
            Text(m.health_grade, style=grade_style),
        )

    console.print(table)


def _render_json_output(metrics: list, window) -> None:
    logger.debug(
        "Rendering JSON output with %d metrics for window %s",
        len(metrics),
        window.label,
    )
    """Render metrics as JSON for integration."""
    data = {
        "window": {
            "label": window.label,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "duration_seconds": window.total_seconds(),
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
                    "p99_ms": m.p99_ms,
                },
                "health": {
                    "error_rate_percent": m.error_rate_percent,
                    "throughput_rps": m.throughput_rps,
                    "apdex_score": m.apdex_score,
                    "grade": m.health_grade,
                },
                "counts": {
                    "request_count": m.request_count,
                    "error_count": m.error_count,
                },
            }
            for m in metrics
        ],
        "summary": {
            "total_endpoints": len(metrics),
            "total_requests": sum(m.request_count for m in metrics),
            "total_errors": sum(m.error_count for m in metrics),
        },
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
        help="⏱️  Time window: 'last_24h', 'last_7d', '3 months', '1 year', etc.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", "-nc", help="🗄️ Bypass cache for this report."
    ),
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
    if not session:
        console.print(
            "[red]✗ Error: Database not configured. Run [bold]tracelet configure-db[/bold] first.[/red]"
        )
        raise typer.Exit(code=1)

    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Analyzing {duration}...[/cyan]"),
            border_style="cyan",
        ),
        console=console,
        refresh_per_second=1,
    ):
        with AnalyticsServiceContext(session) as service:
            report, window = service.generate_operational_report(
                duration, no_cache=no_cache
            )

    if not report or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Calculate grade distribution
    grades = {"A": 0, "B": 0, "C": 0, "D": 0}
    for m in report:
        grades[m.health_grade] = grades.get(m.health_grade, 0) + 1

    critical = grades["D"]
    healthy = grades["A"] + grades["B"]

    # Overall status
    if critical > 0:
        status_color = "red"
        status_emoji = "🚨"
    elif grades["C"] > 0:
        status_color = "yellow"
        status_emoji = "⚠️"
    else:
        status_color = "green"
        status_emoji = "✅"

    # Header panel
    console.print(
        Panel(
            Text(
                f"All Systems Operational\n{healthy}/{len(report)} endpoints healthy",
                justify="center",
            ),
            title=f"{status_emoji} Health Report: {window.label}",
            border_style=status_color,
            expand=False,
        )
    )

    # Detailed table
    _render_detailed_table(report, window)

    # Grade distribution bar
    console.print("\n[bold]Grade Distribution:[/bold]")
    for grade in ["A", "B", "C", "D"]:
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
    duration: str = typer.Option("last_7d", "--duration", "-d", help="⏱️  Time window"),
    endpoint_path: Optional[str] = typer.Option(
        None, "--endpoint", "-e", help="🎯 Filter to specific endpoint by path"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="📋 Output format: 'table', 'compact', 'json'"
    ),
    sort_by: str = typer.Option(
        "p99", "--sort", "-s", help="🔢 Sort by: 'p99', 'error', 'rps', 'apdex'"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", "-nc", help="🗄️ Bypass cache for this report."
    ),
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
    if not session:
        console.print(
            "[red]✗ Error: Database not configured. Run [bold]tracelet configure-db[/bold] first.[/red]"
        )
        raise typer.Exit(code=1)

    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Fetching metrics for {duration}...[/cyan]"),
            border_style="cyan",
        ),
        console=console,
        refresh_per_second=1,
    ):
        with AnalyticsServiceContext(session) as service:
            metrics, window = service.generate_operational_report(
                duration_str=duration, endpoint_path=endpoint_path, no_cache=no_cache
            )

    if not metrics or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Sorting logic
    sort_map = {
        "p99": lambda m: m.p99_ms,
        "error": lambda m: m.error_rate_percent,
        "rps": lambda m: m.throughput_rps,
        "apdex": lambda m: m.apdex_score,
    }
    reverse = sort_by != "apdex"
    metrics.sort(key=sort_map.get(sort_by, lambda m: m.p99_ms), reverse=reverse)

    # Render based on format
    if format == "table":
        _render_detailed_table(metrics, window)
    elif format == "compact":
        _render_compact_view(metrics, window)
    elif format == "json":
        _render_json_output(metrics, window)
    else:
        console.print(f"[red]✗ Unknown format: {format}[/red]")


@app.command()
@cli_error_handler
def top(
    ctx: typer.Context,
    duration: str = typer.Option("last_7d", "--duration", "-d", help="⏱️  Time window"),
    metric: str = typer.Option(
        "p99", "--metric", "-m", help="🎯 Metric: 'p99', 'error', 'slowest'"
    ),
    limit: int = typer.Option(
        5, "--limit", "-n", help="📊 Number of endpoints to show"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", "-nc", help="🗄️ Bypass cache for this report."
    ),
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
    if not session:
        console.print(
            "[red]✗ Error: Database not configured. Run [bold]tracelet configure-db[/bold] first.[/red]"
        )
        raise typer.Exit(code=1)

    with Live(
        Panel(
            Spinner("dots", text=f"[cyan]Finding anomalies in {duration}...[/cyan]"),
            border_style="cyan",
        ),
        console=console,
        refresh_per_second=1,
    ):
        with AnalyticsServiceContext(session) as service:
            metrics, window = service.generate_operational_report(
                duration, no_cache=no_cache
            )

    if not metrics or not window:
        console.print("[yellow]⚠️  No metrics data available[/yellow]")
        return

    # Sort by metric
    if metric == "p99":
        metrics.sort(key=lambda m: m.p99_ms, reverse=True)
        title = "🐢 Slowest Endpoints (P99)"
    elif metric == "error":
        metrics.sort(key=lambda m: m.error_rate_percent, reverse=True)
        title = "⚠️  Highest Error Rate"
    elif metric == "slowest":
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
        None, "--framework", "-f", help="🏗️  Filter by framework: fastapi, django, flask"
    ),
    method: Optional[str] = typer.Option(
        None, "--method", "-m", help="🔗 Filter by HTTP method: GET, POST, PUT, DELETE"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", "-nc", help="🗄️ Bypass cache for this report."
    ),
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
    if not session:
        console.print(
            "[red]✗ Error: Database not configured. Run [bold]tracelet configure-db[/bold] first.[/red]"
        )
        raise typer.Exit(code=1)

    with AnalyticsServiceContext(session) as service:
        endpoints = service.engine.fetch_active_endpoints(cache_bypass=no_cache)

    if not endpoints:
        console.print("[yellow]ℹ️  No endpoints found[/yellow]")
        return

    # Filter
    if framework:
        endpoints = [
            ep for ep in endpoints if ep["framework"].lower() == framework.lower()
        ]
    if method:
        endpoints = [ep for ep in endpoints if ep["method"].upper() == method.upper()]

    if not endpoints:
        console.print("[yellow]ℹ️  No endpoints matching filters[/yellow]")
        return

    # Create table
    table = Table(
        title="📋 Monitored Endpoints",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        box=box.ROUNDED,
    )
    table.add_column("ID", justify="right", style="cyan", width=6)
    table.add_column("Method", style="green", width=10)
    table.add_column("Path", style="magenta")
    table.add_column("Framework", style="yellow", width=12)

    for ep in endpoints:
        table.add_row(
            str(ep["id"]),
            _format_method_badge(ep["method"]),
            ep["path"],
            ep["framework"],
        )

    console.print(table)
    console.print(
        f"\n[dim]├─ Total: {len(endpoints)} endpoint{'s' if len(endpoints) != 1 else ''}[/dim]"
    )


@app.command()
@cli_error_handler
def configure_db(
    ctx: typer.Context,
    env_var: Optional[str] = typer.Option(
        None,
        "--env-var",
        "-ev",
        help="Provide a custom environment variable name for the DB URL. This will be persisted.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Clear any saved custom environment variable name from config.json.",
    ),
):
    """
    ⚙️ Configure Database — Set up your Tracelet database connection.

    This command guides you through configuring the database connection for Tracelet.
    The database URL is resolved from environment variables in a specific order.

    [bold]Resolution Precedence:[/bold]
    \b
    1.  `TRACELET_DB_URL` environment variable (highest priority, always used if present).
    2.  `DATABASE_URL` environment variable (if `TRACELET_DB_URL` is not set, user will be prompted for confirmation).
    3.  A custom environment variable name previously saved via `tracelet configure-db --env-var <NAME>`.
    4.  Default to an internal SQLite database (`sqlite:///tracelet.db`) if no other options are confirmed or available.

    [bold]Options:[/bold]
    \b
    *   `--env-var/-ev <NAME>`: Provide a custom environment variable name (e.g., `MY_APP_DB_URL`) to persist for Tracelet to use. This name will be saved in `~/.tracelet/config.json`. The actual database URL will be read from `os.environ[NAME]`.
    *   `--reset/-r`: Clear any custom environment variable name previously saved in `~/.tracelet/config.json`. After resetting, the command will proceed with the standard resolution precedence (checking `TRACELET_DB_URL`, then `DATABASE_URL`, then defaulting to SQLite if needed).

    [bold]Examples:[/bold]
    \b
      tracelet configure-db --env-var MY_DB_CONNECTION # Save and use MY_DB_CONNECTION
      tracelet configure-db --reset                    # Clear saved env var and starts re-configure
      tracelet configure-db                            # Use existing config or go through interactive setup
    """
    if env_var and reset:
        console.print(
            "[red]✗ Error: Cannot use both --env-var and --reset simultaneously.[/red]"
        )
        raise typer.Exit(code=1)

    db_setup = None
    db_session = None

    if reset:
        save_db_env(None)
        console.print(
            "[green]✓ Cleared any previously saved custom database environment variable name.[/green]"
        )
        # After reset, proceed to configure with the new interactive logic
        try:
            db_setup, db_session = _get_session()
        except Exception as e:
            console.print(f"[red]✗ Error configuring database after reset: {e}[/red]")
            raise typer.Exit(code=1)
    elif env_var:
        try:
            db_setup, db_session = _get_session(env_var)
            save_db_env(env_var)
        except Exception as e:
            console.print(
                f"[red]✗ Error configuring database from provided environment variable '{env_var}': {e}[/red]"
            )
            save_db_env(None)  # Clear config if initial setup fails
            raise typer.Exit(code=1)
    else:
        try:
            db_setup, db_session = _get_session()
        except Exception as e:
            console.print(
                f"[red]✗ Error during interactive database configuration: {e}[/red]"
            )
            raise typer.Exit(code=1)

    ctx.obj = CliContext(db_setup=db_setup, db_session=db_session)

    console.print("[green]✓ Database configured successfully![/green]")
    console.print(
        "[yellow]You can now run other commands like [bold]tracelet status[/bold].[/yellow]"
    )


_db_session_cache = None


def _get_session(env_var=None, skip_if_cached=False):
    """
    Resolve database URL and return configured session.
    Priority: env_var > TRACELET_DB_URL > saved config > DATABASE_URL > interactive

    Args:
        env_var: Optional explicit environment variable name
        skip_if_cached: If True, return cached session if available (skip setup)
    """

    global _db_session_cache

    # Return cached session if available and skip requested
    if skip_if_cached and _db_session_cache:
        return _db_session_cache

    database_url = None

    # Priority 1: Explicit env_var parameter
    if env_var:
        if not os.environ.get(env_var):
            raise ValueError(f"Environment variable '{env_var}' not set")
        database_url = os.environ.get(env_var)
        console.print(f"[green]✓ Using {env_var}[/green]")

    # Priority 2: TRACELET_DB_URL
    elif os.environ.get("TRACELET_DB_URL"):
        database_url = os.environ.get("TRACELET_DB_URL")
        console.print("[green]✓ Using TRACELET_DB_URL[/green]")

    # Priority 3: Saved config env var
    elif saved_env := load_db_env():
        if saved_env == "__SQLITE_DEFAULT__":
            database_url = "sqlite:///tracelet.db"
            console.print("[green]✓ Using saved config: SQLite default[/green]")
        elif os.environ.get(saved_env):
            database_url = os.environ.get(saved_env)
            console.print(f"[green]✓ Using saved config: {saved_env}[/green]")
        else:
            console.print(
                f"[yellow]Warning: Saved env '{saved_env}' not found[/yellow]"
            )
            save_db_env(None)  # Clear invalid config

    # Priority 4: DATABASE_URL (with y/n confirmation)
    if not database_url and os.environ.get("DATABASE_URL"):
        if typer.confirm("Found DATABASE_URL. Use for Tracelet? [y/n]", default=False):
            database_url = os.environ.get("DATABASE_URL")
            console.print("[green]✓ Using DATABASE_URL[/green]")
        else:
            console.print("[yellow]Ignored DATABASE_URL[/yellow]")

    # Priority 5: Interactive prompt
    if not database_url:
        console.print("\n[yellow]Database not configured[/yellow]")
        choice = typer.prompt(
            "Configure database:\n"
            "1) Enter environment variable name\n"
            "2) Use default SQLite\n"
            "Choice [1/2]",
            type=int,
            default=2,
        )

        if choice == 1:
            env_name = typer.prompt("Environment variable name")
            if not os.environ.get(env_name):
                raise ValueError(f"'{env_name}' not set in environment")
            database_url = os.environ.get(env_name)
            save_db_env(env_name)  # Persist choice
            console.print(f"[green]✓ Using {env_name}[/green]")
        elif choice == 2:
            database_url = "sqlite:///tracelet.db"
            save_db_env("__SQLITE_DEFAULT__")
            console.print("[green]✓ Using default SQLite: tracelet.db[/green]")
        else:
            console.print("[red]✗ Invalid Choice, Try Again!!![/red]")
            raise ValueError("Invalid Choice")

    db = setup_db({"db_url": database_url})
    _db_session_cache = (db, db.SessionLocal())

    return _db_session_cache


@app.callback()
def main(ctx: typer.Context):
    """Tracelet CLI - Modern API Performance Analytics."""
    # Initialize ctx.obj if it's not already set.
    if ctx.obj is None:
        db_setup = None
        db_session = None
        try:
            db_setup, db_session = _get_session(skip_if_cached=True)
        except Exception as e:
            console.print(
                f"[red]✗ Warning: Database initialization failed: {e}. Commands requiring a database may not work.[/red]"
            )

        ctx.obj = CliContext(db_setup=db_setup, db_session=db_session)

    # Register cleanup on exit
    def _cleanup_session():
        if ctx.obj and ctx.obj.db_session:
            ctx.obj.db_session.close()
            logger.debug("Database session closed on CLI exit")

    ctx.call_on_close(_cleanup_session)


if __name__ == "__main__":
    app()
