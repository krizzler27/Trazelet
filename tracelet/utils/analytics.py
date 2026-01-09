# tracelet/utils/analytics.py
"""
PostgreSQL analytics layer for Tracelet.
Handles percentile calculations, health metrics, and time-window aggregations.
Uses cumulative bucket snapshots for O(1) query performance.
Pure SQLAlchemy ORM (no raw SQL).
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Dict

from sqlalchemy import select, func, and_
from tracelet.db.models import Buckets, Endpoints, Metrics, EndpointStatus

logger = logging.getLogger("tracelet")

BUCKET_THRESHOLDS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]


@dataclass
class HistogramSnapshot:
    """Clean container for bucket data to separate DB from Logic."""
    threshold_ms: float
    cumulative_count: int

    def __post_init__(self):
        """Validate bucket data at construction time."""
        # 1. Handle the 'None' Blind Spot
        if self.cumulative_count is None:
            self.cumulative_count = 0
        
        # 2. Handle Logical Validation
        if self.cumulative_count < 0:
            raise ValueError("Cumulative count cannot be negative.")
        if self.threshold_ms < 0 and self.threshold_ms != float('inf'):
            raise ValueError(f"Latency threshold cannot be negative: {self.threshold_ms}")


class AnalyticsEngine:
    """
    Optimized engine for API performance analytics.
    Uses SQLAlchemy Expression Language for type-safe queries.
    """

    def __init__(self, session):
        self.session = session

    def fetch_data_time_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Finds the boundary timestamps for available telemetry data."""
        try:
            stmt = select(
                func.min(Buckets.captured_at),
                func.max(Buckets.captured_at)
            )
            result = self.session.execute(stmt).fetchone()
            if result and result[0]:
                return result[0], result[1]
            return None, None
        except Exception as e:
            logger.error("Error fetching data range: %s", e, exc_info=True)
            return None, None

    def fetch_active_endpoints(self) -> List[Dict]:
        """Retrieves all endpoints that have recorded performance data."""
        try:
            stmt = (
                select(Endpoints)
                .join(Buckets, Endpoints.endpoint_id == Buckets.endpoint_id)
                .distinct()
                .order_by(Endpoints.path, Endpoints.method)
            )
            endpoints = self.session.scalars(stmt).all()
            return [
                {
                    "id": ep.endpoint_id,
                    "path": ep.path,
                    "method": ep.method,
                    "framework": ep.framework
                }
                for ep in endpoints
            ]
        except Exception as e:
            logger.error("Error fetching active endpoints: %s", e, exc_info=True)
            return []

    def _get_snapshot_subquery(self, endpoint_id: int, target_time: datetime):
        """Helper to find the closest bucket snapshot to a specific timestamp."""
        return (
            select(func.max(Buckets.captured_at))
            .where(
                and_(
                    Buckets.endpoint_id == endpoint_id,
                    Buckets.captured_at <= target_time
                )
            )
        ).scalar_subquery()

    def get_window_metrics(self, endpoint_id: int, start_at: datetime, end_at: datetime) -> Dict:
        """
        Calculates deltas between two snapshots to determine 
        performance within a specific time window.
        
        Returns:
            {
                "endpoint_id": int,
                "buckets": [HistogramSnapshot, ...],
                # "summary": {mean, max, total, errors}
            }
        """
        try:
            # 1. Identify the two snapshots to compare
            start_ts = self._get_snapshot_subquery(endpoint_id, start_at)
            end_ts = self._get_snapshot_subquery(endpoint_id, end_at)

            # 2. Fetch bucket counts at start snapshot
            start_buckets = self.session.execute(
                select(Buckets.le, Buckets.count)
                .where(and_(
                    Buckets.endpoint_id == endpoint_id,
                    Buckets.captured_at == start_ts
                ))
            ).all()
            
            # 3. Fetch bucket counts at end snapshot
            end_buckets = self.session.execute(
                select(Buckets.le, Buckets.count)
                .where(and_(
                    Buckets.endpoint_id == endpoint_id,
                    Buckets.captured_at == end_ts
                ))
            ).all()

            # Convert to dictionaries for delta calculation
            start_map = {b.le: (b.count or 0) for b in start_buckets}
            end_map = {b.le: (b.count or 0) for b in end_buckets}
            
            # 4. Calculate deltas and prepare HistogramSnapshot objects
            final_buckets = []
            all_les = set(start_map.keys()) | set(end_map.keys())
            
            for le in sorted(all_les):
                start_count = start_map.get(le, 0) or 0
                end_count = end_map.get(le, 0)
                delta = end_count if end_count < start_count else end_count - start_count
                
                if delta > 0:
                    final_buckets.append(HistogramSnapshot(threshold_ms=le, cumulative_count=delta))
                elif delta < 0:
                    logger.warning(
                        f"Negative delta for endpoint {endpoint_id}, bucket {le}: "
                        f"start={start_count}, end={end_count}. Skipping."
                    )

            # 5. Fetch summary stats (mean, max, error count)
            # summary = self._fetch_summary_stats(endpoint_id, start_at, end_at)
            
            # If no positive deltas, return empty
            if not final_buckets:
                logger.warning(f"No positive deltas for endpoint {endpoint_id} in window [{start_at}, {end_at}]")
                return {
                    "endpoint_id": endpoint_id,
                    "buckets": [],
                    # "summary": {"mean": 0, "max": 0, "total": 0, "errors": 0}
                }

            
            return {
                "endpoint_id": endpoint_id,
                "buckets": final_buckets,
                # "summary": summary
            }

        except Exception as e:
            logger.error("Error getting window metrics: %s", e, exc_info=True)
            return {
                "endpoint_id": endpoint_id,
                "buckets": [],
                # "summary": {"mean": 0, "max": 0, "total": 0, "errors": 0}
            }

    def _fetch_summary_stats(self, endpoint_id: int, start: datetime, end: datetime) -> Dict:
        """Fetch average, max, and error counts in one clean SQLAlchemy call."""
        try:
            stmt = (
                select(
                    func.avg(Metrics.latency_ms).label("mean"),
                    func.max(Metrics.latency_ms).label("max"),
                    func.count(Metrics.metrics_id).label("total"),
                    func.count().filter(Metrics.response_status == EndpointStatus.FAILED).label("errors")
                )
                .where(
                    and_(
                        Metrics.endpoint_id == endpoint_id,
                        Metrics.created_at.between(start, end)
                    )
                )
            )
            result = self.session.execute(stmt).mappings().first()
            return dict(result) if result else {"mean": 0, "max": 0, "total": 0, "errors": 0}
        except Exception as e:
            logger.error("Error fetching summary stats: %s", e, exc_info=True)
            return {"mean": 0, "max": 0, "total": 0, "errors": 0}
    
    def fetch_batch_summary_stats(
        self, 
        endpoint_ids: List[int], 
        start: datetime, 
        end: datetime
    ) -> Dict[int, dict]:
        """
        BATCH QUERY: Fetches stats for all provided endpoints in one trip.
        Returns a mapping of {endpoint_id: stats_dict}.
        
        Avoids N+1 query problem by batching all stats at once.
        """
        try:
            stmt = (
                select(
                    Metrics.endpoint_id,
                    func.avg(Metrics.latency_ms).label("mean"),
                    func.max(Metrics.latency_ms).label("max"),
                    func.count(Metrics.metrics_id).label("total"),
                    func.count().filter(Metrics.response_status == EndpointStatus.FAILED).label("errors")
                )
                .where(
                    and_(
                        Metrics.endpoint_id.in_(endpoint_ids),
                        Metrics.created_at.between(start, end)
                    )
                )
                .group_by(Metrics.endpoint_id)
            )
            
            results = self.session.execute(stmt).mappings().all()
            # Convert list of rows to a dictionary for fast lookup by ID
            return {row['endpoint_id']: dict(row) for row in results}
        except Exception as e:
            logger.error("Error fetching batch summary stats: %s", e, exc_info=True)
            return {}

    def get_error_rate(self, endpoint_id: int, start: datetime, end: datetime) -> float:
        """Calculate error rate (%) for time window."""
        try:
            stmt = (
                select(
                    func.count().filter(Metrics.response_status == EndpointStatus.FAILED).label("errors"),
                    func.count(Metrics.metrics_id).label("total")
                )
                .where(
                    and_(
                        Metrics.endpoint_id == endpoint_id,
                        Metrics.created_at.between(start, end)
                    )
                )
            )
            result = self.session.execute(stmt).mappings().first()
            
            if not result or result['total'] == 0:
                return 0.0
            
            return round((result['errors'] / result['total']) * 100, 2)
        except Exception as e:
            logger.error("Error calculating error rate: %s", e, exc_info=True)
            return 0.0

    def get_throughput_rps(self, endpoint_id: int, start: datetime, end: datetime) -> float:
        """Calculate requests per second for time window."""
        try:
            stmt = (
                select(func.count(Metrics.metrics_id).label("total"))
                .where(
                    and_(
                        Metrics.endpoint_id == endpoint_id,
                        Metrics.created_at.between(start, end)
                    )
                )
            )
            result = self.session.execute(stmt).mappings().first()
            
            if not result or result['total'] == 0:
                return 0.0
            
            time_delta = (end - start).total_seconds()
            if time_delta <= 0:
                return 0.0
            
            return round(result['total'] / time_delta, 2)
        except Exception as e:
            logger.error("Error calculating throughput: %s", e, exc_info=True)
            return 0.0

    def get_apdex_score(
        self,
        endpoint_id: int,
        start: datetime,
        end: datetime,
        target_latency_ms: float = 100.0
    ) -> float:
        """
        Calculate Apdex score (0-1).
        Satisfactory: latency <= target_latency_ms
        Tolerable: target_latency_ms < latency <= 4*target_latency_ms
        Apdex = (satisfactory + tolerable/2) / total
        """
        try:
            stmt = (
                select(
                    func.count().filter(Metrics.latency_ms <= target_latency_ms).label("satisfactory"),
                    func.count().filter(
                        and_(
                            Metrics.latency_ms > target_latency_ms,
                            Metrics.latency_ms <= target_latency_ms * 4
                        )
                    ).label("tolerable"),
                    func.count(Metrics.metrics_id).label("total")
                )
                .where(
                    and_(
                        Metrics.endpoint_id == endpoint_id,
                        Metrics.created_at.between(start, end)
                    )
                )
            )
            result = self.session.execute(stmt).mappings().first()
            
            if not result or result['total'] == 0:
                return 0.0
            
            apdex = (result['satisfactory'] + result['tolerable'] / 2) / result['total']
            return round(min(apdex, 1.0), 2)
        except Exception as e:
            logger.error("Error calculating Apdex: %s", e, exc_info=True)
            return 0.0


def estimate_percentile(snapshots: List[HistogramSnapshot], percentile: float) -> float:
    """
    Pure math function: Linear interpolation for percentile calculation.
    Separated from the DB logic for easier testing and reusability.
    
    Algorithm: Master Formula
    - Finds bucket containing target rank
    - Interpolates within bucket using linear approximation
    
    Args:
        snapshots: List of HistogramSnapshot objects (cumulative)
        percentile: Target percentile (50, 95, 99, etc.)
    
    Returns:
        Estimated latency in milliseconds
    """
    if not snapshots:
        return 0.0

    total_count = snapshots[-1].cumulative_count
    if total_count == 0:
        return 0.0

    target_rank = (percentile / 100) * total_count
    
    prev_ms = 0.0
    prev_count = 0
    
    for snapshot in snapshots:
        if snapshot.cumulative_count >= target_rank:
            # If we hit the infinity bucket, return previous threshold
            if snapshot.threshold_ms == float('inf'):
                return prev_ms
            
            # Master Formula: Linear interpolation within bucket
            count_in_bucket = snapshot.cumulative_count - prev_count
            rank_in_bucket = target_rank - prev_count
            bucket_width = snapshot.threshold_ms - prev_ms
            
            if count_in_bucket <= 0:
                return prev_ms
            
            interpolation = prev_ms + (rank_in_bucket / count_in_bucket) * bucket_width
            return round(interpolation, 2)
        
        prev_ms = snapshot.threshold_ms
        prev_count = snapshot.cumulative_count
        
    return prev_ms