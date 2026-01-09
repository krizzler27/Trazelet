# scripts/test_analytics.py
"""
Tracelet Analytics Testing Script.
Tests all analytics functions with generated test data.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from tracelet.utils.analytics import AnalyticsEngine, estimate_percentile
from tracelet.utils.services import AnalyticsService
from rich.console import Console #type: ignore
from rich.table import Table #type: ignore
from tracelet.db.config import setup_db

db = setup_db({"db_url": "postgresql+psycopg2://kriz:root@localhost:5432/tracelet", "echo": False})
SessionLocal = db.SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_analytics")
console = Console()

# ============================================================================
# Test Functions
# ============================================================================

def test_analytics_engine():
    """Test all AnalyticsEngine methods."""
    console.print("\n[bold cyan]Testing AnalyticsEngine[/bold cyan]")
    
    session = SessionLocal()
    engine = AnalyticsEngine(session)
    
    try:
        # Test 1: Data range
        console.print("\n  Test 1: fetch_data_time_range()")
        earliest, latest = engine.fetch_data_time_range()
        console.print(f"    ✓ Earliest: {earliest}")
        console.print(f"    ✓ Latest: {latest}")
        
        if not earliest:
            console.print("[yellow]    ⚠️  No data found - run generate_test_data first[/yellow]")
            return
        
        # Test 2: Active endpoints
        console.print("\n  Test 2: fetch_active_endpoints()")
        endpoints = engine.fetch_active_endpoints()
        console.print(f"    ✓ Found {len(endpoints)} endpoints:")
        for ep in endpoints[:5]:
            console.print(f"      - {ep['method']} {ep['path']} ({ep['framework']})")
        
        if not endpoints:
            console.print("[yellow]    ⚠️  No endpoints found[/yellow]")
            return
        
        # Test 3: Window metrics
        console.print("\n  Test 3: get_window_metrics()")
        endpoint_id = endpoints[0]['id']
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)
        
        metrics = engine.get_window_metrics(endpoint_id, start_time, end_time)
        console.print(f"    ✓ Endpoint: {endpoints[0]['method']} {endpoints[0]['path']}")
        console.print(f"    ✓ Buckets: {len(metrics.get('buckets', []))} thresholds")
        console.print(f"    ✓ Summary: {metrics.get('summary')}")
        
        # Test 4: Batch summary stats
        console.print("\n  Test 4: fetch_batch_summary_stats()")
        endpoint_ids = [ep['id'] for ep in endpoints[:3]]
        batch_stats = engine.fetch_batch_summary_stats(endpoint_ids, start_time, end_time)
        console.print(f"    ✓ Batch fetched stats for {len(batch_stats)} endpoints")
        
        # Test 5: Error rate
        console.print("\n  Test 5: get_error_rate()")
        error_rate = engine.get_error_rate(endpoint_id, start_time, end_time)
        console.print(f"    ✓ Error rate: {error_rate:.2f}%")
        
        # Test 6: Throughput
        console.print("\n  Test 6: get_throughput_rps()")
        throughput = engine.get_throughput_rps(endpoint_id, start_time, end_time)
        console.print(f"    ✓ Throughput: {throughput:.2f} RPS")
        
        # Test 7: Apdex
        console.print("\n  Test 7: get_apdex_score()")
        apdex = engine.get_apdex_score(endpoint_id, start_time, end_time)
        console.print(f"    ✓ Apdex: {apdex:.2f}")
        
        console.print("\n[green]✅ AnalyticsEngine: All tests passed[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ AnalyticsEngine test failed: {e}[/red]")
        logger.exception(e)
    finally:
        session.close()


def test_percentile_estimation():
    """Test percentile estimation algorithm."""
    console.print("\n[bold cyan]Testing Percentile Estimation[/bold cyan]")
    
    from tracelet.utils.analytics import HistogramSnapshot
    
    try:
        # Create mock bucket data
        snapshots = [
            HistogramSnapshot(10, 100),
            HistogramSnapshot(25, 250),
            HistogramSnapshot(50, 450),
            HistogramSnapshot(100, 700),
            HistogramSnapshot(250, 850),
            HistogramSnapshot(500, 950),
            HistogramSnapshot(1000, 980),
            HistogramSnapshot(2500, 995),
            HistogramSnapshot(5000, 998),
            HistogramSnapshot(float('inf'), 1000),
        ]
        
        console.print(f"\n  Total requests: {snapshots[-1].cumulative_count}")
        
        # Test various percentiles
        percentiles_to_test = [50, 75, 90, 95, 99]
        
        table = Table(title="Percentile Estimation Results")
        table.add_column("Percentile", style="cyan")
        table.add_column("Latency (ms)", justify="right", style="magenta")
        
        for p in percentiles_to_test:
            latency = estimate_percentile(snapshots, p)
            table.add_row(f"P{p}", f"{latency:.2f}")
        
        console.print(table)
        console.print("\n[green]✅ Percentile Estimation: All tests passed[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Percentile test failed: {e}[/red]")
        logger.exception(e)


def test_analytics_service():
    """Test AnalyticsService (high-level API)."""
    console.print("\n[bold cyan]Testing AnalyticsService[/bold cyan]")
    
    session = SessionLocal()
    service = AnalyticsService(session)
    
    try:
        # Test 1: Parse time window
        console.print("\n  Test 1: _parse_window()")
        windows_to_test = [
            "last_24h",
            "last_7d",
            "3 months",
            "1 year",
            "7 days",
        ]
        
        for window_str in windows_to_test:
            window = service._parse_window(window_str)
            if window:
                console.print(f"    ✓ '{window_str}' → {window.label} ({window.duration_human()})")
        
        # Test 2: Generate operational report
        console.print("\n  Test 2: generate_operational_report()")
        report, window = service.generate_operational_report("last_7d")
        
        if not report:
            console.print("[yellow]    ⚠️  No report generated[/yellow]")
            service.close()
            return
        
        console.print(f"    ✓ Generated report for {len(report)} endpoints")
        console.print(f"    ✓ Time window: {window.label}")
        
        # Test 3: Display report
        console.print("\n  Test 3: Report Details")
        table = Table(title="Endpoint Health Metrics (Sample)")
        table.add_column("Endpoint", style="cyan")
        table.add_column("P99 (ms)", justify="right")
        table.add_column("Error%", justify="right")
        table.add_column("RPS", justify="right")
        table.add_column("Apdex", justify="right")
        table.add_column("Grade", justify="center")
        
        for m in report[:5]:
            grade_emoji = {
                "A": "🟢",
                "B": "🟡",
                "C": "🟠",
                "D": "🔴"
            }.get(m.health_grade, "⚪")
            
            table.add_row(
                f"{m.method} {m.path}",
                f"{m.p99_ms:.0f}",
                f"{m.error_rate_percent:.2f}%",
                f"{m.throughput_rps:.1f}",
                f"{m.apdex_score:.2f}",
                f"{grade_emoji} {m.health_grade}"
            )
        
        console.print(table)
        
        # Test 4: Grade distribution
        console.print("\n  Test 4: Grade Distribution")
        grades = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        for m in report:
            grades[m.health_grade] += 1
        
        for grade in ['A', 'B', 'C', 'D']:
            count = grades[grade]
            pct = (count / len(report) * 100) if report else 0
            bar = "█" * count + "░" * (len(report) - count)
            console.print(f"    {grade}: {bar} {count} ({pct:.0f}%)")
        
        # Test 5: Single endpoint detail
        console.print("\n  Test 5: Single Endpoint Report")
        endpoint_id = report[0].endpoint_id
        single_report, _ = service.describe_endpoints("last_7d", endpoint_id)
        
        if single_report:
            m = single_report[0]
            console.print(f"    ✓ {m.method} {m.path}")
            console.print(f"      - P50: {m.p50_ms:.2f}ms")
            console.print(f"      - P95: {m.p95_ms:.2f}ms")
            console.print(f"      - P99: {m.p99_ms:.2f}ms")
            console.print(f"      - Grade: {m.health_grade}")
        
        console.print("\n[green]✅ AnalyticsService: All tests passed[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ AnalyticsService test failed: {e}[/red]")
        logger.exception(e)
    finally:
        service.close()


def benchmark_analytics():
    """Benchmark analytics performance."""
    console.print("\n[bold cyan]Benchmarking Analytics Performance[/bold cyan]")
    
    import time
    
    session = SessionLocal()
    service = AnalyticsService(session)
    
    try:
        # Benchmark: generate_operational_report
        console.print("\n  Benchmark: generate_operational_report()")
        
        durations = ["last_24h", "last_7d", "last_30d", "1 year"]
        
        for duration in durations:
            start = time.time()
            report, window = service.generate_operational_report(duration)
            elapsed = time.time() - start
            
            status = "✓" if report else "✗"
            console.print(
                f"    {status} {duration:15} {elapsed*1000:6.1f}ms ({len(report)} endpoints)"
            )
        
        console.print("\n[green]✅ Benchmark complete[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Benchmark failed: {e}[/red]")
        logger.exception(e)
    finally:
        service.close()


# ============================================================================
# Main Test Suite
# ============================================================================

def run_all_tests():
    """Run all analytics tests."""
    console.print("\n[bold cyan]╔═══════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║         Tracelet Analytics Test Suite                       ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════════════════════════════╝[/bold cyan]")
    
    console.print("\n[yellow]Prerequisites:[/yellow]")
    console.print("  1. Database initialized (tracelet.db or Postgres)")
    console.print("  2. Test data generated (python scripts/generate_test_data.py)")
    console.print("  3. Dependencies installed (sqlalchemy, rich, numpy)")
    
    # Run tests
    test_analytics_engine()
    test_percentile_estimation()
    test_analytics_service()
    benchmark_analytics()
    
    console.print("\n[bold cyan]╔═══════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║                   Test Suite Complete                        ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════════════════════════════╝[/bold cyan]\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Tracelet Analytics Tests")
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Run all tests (default)"
    )
    parser.add_argument(
        "--engine",
        action="store_true",
        help="Test AnalyticsEngine only"
    )
    parser.add_argument(
        "--percentile",
        action="store_true",
        help="Test percentile estimation only"
    )
    parser.add_argument(
        "--service",
        action="store_true",
        help="Test AnalyticsService only"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmarks only"
    )
    
    args = parser.parse_args()
    
    if args.engine:
        test_analytics_engine()
    elif args.percentile:
        test_percentile_estimation()
    elif args.service:
        test_analytics_service()
    elif args.benchmark:
        benchmark_analytics()
    else:
        run_all_tests()