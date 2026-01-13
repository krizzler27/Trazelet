"""
Analytics service layer.
Orchestrates AnalyticsEngine, handles time windows, computes health metrics.
Separates business logic from database queries.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Any, Literal
from sqlalchemy.orm import session

from tracelet.tui.analytics import AnalyticsEngine, estimate_percentile
from tracelet.tui.caching import lru_cache_decorator

logger = logging.getLogger("tracelet")

@dataclass
class EndpointHealthMetrics:
    """Operational health snapshot for an endpoint."""
    endpoint_id: int
    path: str
    method: str
    framework: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate_percent: float
    throughput_rps: float
    apdex_score: float
    request_count: int
    error_count: int
    health_grade: str
    data_start: datetime = field(default_factory=datetime.now)
    data_end: datetime = field(default_factory=datetime.now)


@dataclass
class TimeWindow:
    """Represents a time window for analytics queries."""
    start: datetime
    end: datetime
    label: str

    def duration_human(self) -> str:
        """Human-readable duration."""
        delta = self.end - self.start
        days = delta.days
        hours = delta.seconds // 3600

        if days > 365:
            return f"{days // 365} year{'s' if days // 365 > 1 else ''}"
        elif days > 30:
            return f"{days // 30} month{'s' if days // 30 > 1 else ''}"
        elif days > 7:
            return f"{days // 7} week{'s' if days // 7 > 1 else ''}"
        elif days > 0:
            return f"{days} day{'s' if days > 1 else ''}"
        else:
            return f"{hours} hour{'s' if hours > 1 else ''}"

    def total_seconds(self) -> float:
        """Get total time window in seconds."""
        return (self.end - self.start).total_seconds()


class AnalyticsService:
    """
    The Project Strategy Orchestrator.
    Translates raw Engine data into meaningful Business Grades.
    Handles time window parsing, batch queries, and health metric computation.
    """

    def __init__(self, session: Any):
        """Initialize with database session."""
        self.session = session
        self.engine = AnalyticsEngine(session)

    def generate_operational_report(
        self,
        duration_str: str,
        endpoint_path: Optional[int] = None,
        no_cache: bool = False
    ) -> Tuple[List[EndpointHealthMetrics], Optional[TimeWindow]]:
        """
        Primary analytics query. Generate complete health report for endpoints.
        
        Args:
            duration_str: Time window string (e.g., 'last_7d', '3 months')
            endpoint_id: Optional filter to single endpoint
        
        Returns:
            (List of EndpointHealthMetrics, TimeWindow) or ([], None) if error
        """
        try:
            # 1. Parse time window
            window = self._parse_window(duration_str, cache_bypass=no_cache)
            if not window:
                logger.warning("Failed to parse duration: %s", duration_str)
                return [], None
            
            # 2. Fetch available endpoints
            all_endpoints = self.engine.fetch_active_endpoints(cache_bypass=no_cache)
            if not all_endpoints:
                logger.warning("No active endpoints found")
                return [], window
            
            # Filter by endpoint_id if provided
            if endpoint_path:
                endpoints = [ep for ep in all_endpoints if ep['path'] == endpoint_path]
                if not endpoints:
                    logger.warning("Endpoint %d not found", endpoint_path)
                    return [], window
            else:
                endpoints = all_endpoints
            
            endpoint_ids = [ep['id'] for ep in endpoints]
            
            # 3. BATCH FETCH: Get all summaries and apdex scores in one network call (avoid N+1)
            all_summaries = self.engine.fetch_batch_summary_stats(
                tuple(endpoint_ids), window.start, window.end, cache_bypass=no_cache
            )
            all_apdex_scores = self.engine.fetch_batch_apdex_scores(
                tuple(endpoint_ids), window.start, window.end, cache_bypass=no_cache
            )
            all_window_metrics = self.engine.fetch_batch_window_metrics(
                tuple(endpoint_ids), window.start, window.end, cache_bypass=no_cache
            )

            # 4. Build report for each endpoint
            report_data = []
            
            for ep in endpoints:
                eid = ep['id']
                
                # Get summary stats from Step: 3
                summary = all_summaries.get(eid, {"mean": 0, "max": 0, "total": 0, "errors": 0})
                apdex = all_apdex_scores.get(eid, 0.0)
                
                # Get window metrics from Step: 3
                buckets = all_window_metrics.get(eid, [])
                
                if not buckets:
                    logger.debug("No bucket data for endpoint %d in window", eid)
                    continue
                
                # Calculate percentiles
                # Convert buckets to a tuple for hashability with lru_cache
                p50 = estimate_percentile(tuple(buckets), 50.0, cache_bypass=no_cache)
                p95 = estimate_percentile(tuple(buckets), 95.0, cache_bypass=no_cache)
                p99 = estimate_percentile(tuple(buckets), 99.0, cache_bypass=no_cache)
                
                # Calculate operational metrics
                error_rate = self._calculate_error_percent(summary.get('total', 0), summary.get('errors', 0))
                throughput = self._calculate_throughput(summary.get('total', 0), window.total_seconds())
                
                # Assign health grade
                health_grade = self._assign_health_grade(p99, error_rate, apdex)
                
                # Build metrics object
                metrics = EndpointHealthMetrics(
                    endpoint_id=eid,
                    path=ep['path'],
                    method=ep['method'],
                    framework=ep['framework'],
                    p50_ms=p50,
                    p95_ms=p95,
                    p99_ms=p99,
                    error_rate_percent=error_rate,
                    throughput_rps=throughput,
                    apdex_score=apdex,
                    request_count=summary.get('total', 0),
                    error_count=summary.get('errors', 0),
                    health_grade=health_grade,
                    data_start=window.start,
                    data_end=window.end
                )
                report_data.append(metrics)
            
            return report_data, window

        except Exception as e:
            logger.error("Error generating operational report: %s", e, exc_info=True)
            return [], None

    @lru_cache_decorator(maxsize=128)
    def _parse_window(self, duration_str: str, cache_bypass: bool = False) -> Optional[TimeWindow]:
        """
        Parse duration string and return TimeWindow.
        
        Supports:
            - Presets: 'last_24h', 'last_7d', 'last_30d', 'last_90d', 'last_1y'
            - Custom: '7 days', '2 weeks', '3 months', '1 year'
        
        Auto-adjusts if window exceeds available data.
        """
        try:
            duration_str = duration_str.lower().strip()
            end_time = datetime.now(timezone.utc)
            start_time = end_time
            label = ""

            # Preset formats
            presets = {
                'last_24h': (timedelta(hours=24), "Last 24 Hours"),
                'last_7d': (timedelta(days=7), "Last 7 Days"),
                'last_30d': (timedelta(days=30), "Last 30 Days"),
                'last_90d': (timedelta(days=90), "Last 90 Days"),
                'last_1y': (timedelta(days=365), "Last 1 Year"),
            }

            if duration_str in presets:
                delta, label = presets[duration_str]
                start_time = end_time - delta
            else:
                # Parse custom format: "7 days", "2 weeks", etc.
                parts = duration_str.split()
                if len(parts) != 2:
                    raise ValueError(
                        "Invalid format. Use: '7 days', '2 weeks', '3 months', '1 year' "
                        "or presets: 'last_24h', 'last_7d', etc."
                    )
                
                try:
                    count = int(parts[0])
                except ValueError:
                    raise ValueError(f"First part must be a number, got: {parts[0]}")
                
                unit = parts[1]
                if unit.startswith('day'):
                    start_time = end_time - timedelta(days=count)
                    label = f"Last {count} Day{'s' if count > 1 else ''}"
                elif unit.startswith('week'):
                    start_time = end_time - timedelta(weeks=count)
                    label = f"Last {count} Week{'s' if count > 1 else ''}"
                elif unit.startswith('month'):
                    start_time = end_time - timedelta(days=count * 30)
                    label = f"Last {count} Month{'s' if count > 1 else ''}"
                elif unit.startswith('year'):
                    start_time = end_time - timedelta(days=count * 365)
                    label = f"Last {count} Year{'s' if count > 1 else ''}"
                else:
                    raise ValueError(f"Unknown unit: {unit}. Use: days, weeks, months, years")
            
            # Adjust if window exceeds available data
            earliest, latest = self.engine.fetch_data_time_range(cache_bypass=cache_bypass)
            
            if earliest is None or latest is None: # Handle case where no data is available
                logger.warning("No historical data available to determine time range. Cannot adjust window.")
                return TimeWindow(start=start_time, end=end_time, label=label) # Return window without adjustment

            earliest = earliest.replace(tzinfo=timezone.utc)
            latest = latest.replace(tzinfo=timezone.utc)
            if earliest and start_time < earliest:
                logger.info(
                    "Data only available from %s; adjusting window from %s",
                    earliest.strftime('%Y-%m-%d %H:%M'),
                    start_time.strftime('%Y-%m-%d %H:%M')
                )
                start_time = earliest
            
            return TimeWindow(start=start_time, end=end_time, label=label)
        
        except ValueError as e:
            logger.error("Time window parse error: %s", e)
            return None

    def _assign_health_grade(self, p99_ms: float, error_rate: float, apdex: float) -> str:
        """
        Assign A/B/C/D health grade based on composite metrics.
        
        Grading Logic:
            A: P99 < 200ms AND Error% < 1% AND Apdex >= 0.95
            B: P99 < 500ms AND Error% < 5% AND Apdex >= 0.85
            C: P99 < 1000ms AND Error% < 10% AND Apdex >= 0.70
            D: Everything else (poor performance)
        """
        if p99_ms <= 200 and error_rate <= 1 and apdex >= 0.95:
            return "A"
        elif p99_ms <= 1000 and error_rate <= 5 and apdex >= 0.85:
            return "B"
        elif p99_ms <= 3000 and error_rate <= 10 and apdex >= 0.70:
            return "C"
        else:
            return "D"

    def _calculate_error_percent(self, total: int, errors: int) -> float:
        """Calculate error rate percentage."""
        if total == 0:
            return 0.0
        return round((errors / total) * 100, 2)

    def _calculate_throughput(self, total_requests: int, time_seconds: float) -> float:
        """Calculate requests per second."""
        if time_seconds <= 0:
            return 0.0
        return round(total_requests / time_seconds, 2)

    def close(self) -> None:
        """Clean up database connections."""
        if self.session:
            self.session.close()
            logger.debug("Analytics service session closed")


# ============================================================================
# Context Manager Support for Automatic Cleanup
# ============================================================================

class AnalyticsServiceContext:
    """
    Context manager for AnalyticsService to ensure proper cleanup.
    
    Usage:
        with AnalyticsServiceContext(session) as service:
            report, window = service.generate_operational_report("last_7d")
    """
    
    def __init__(self, session: session):
        self.session = session
        self.service = None
    
    def __enter__(self) -> AnalyticsService:
        self.service = AnalyticsService(self.session)
        return self.service
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        if self.service:
            self.service.close()
        return False