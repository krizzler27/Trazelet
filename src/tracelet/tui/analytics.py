"""
PostgreSQL analytics layer for Tracelet.
Handles percentile calculations, health metrics, and time-window aggregations.
Uses cumulative bucket snapshots for O(1) query performance.
Pure SQLAlchemy ORM.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, and_
from tracelet.db.models import Buckets, Endpoints, Metrics, EndpointStatus

from tracelet.tui.caching import ttl_cache_decorator, lru_cache_decorator

logger = logging.getLogger("tracelet")


@dataclass(frozen=True)
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
        if self.threshold_ms < 0 and self.threshold_ms != float("inf"):
            raise ValueError(
                f"Latency threshold cannot be negative: {self.threshold_ms}"
            )


class AnalyticsEngine:
    """
    Optimized engine for API performance analytics.
    Uses SQLAlchemy Expression Language for type-safe queries.
    """

    def __init__(self, session: Any):
        self.session = session

    @ttl_cache_decorator(ttl=300)
    def fetch_data_time_range(
        self, cache_bypass: bool = False
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Finds the boundary timestamps for available telemetry data."""
        try:
            stmt = select(func.min(Buckets.captured_at), func.max(Buckets.captured_at))
            result = self.session.execute(stmt).fetchone()
            if result and result[0]:
                return result[0], result[1]
            return None, None
        except Exception as e:
            logger.error("Error fetching data range: %s", e, exc_info=True)
            return None, None

    @ttl_cache_decorator(ttl=300)
    def fetch_active_endpoints(self, cache_bypass: bool = False) -> List[Dict]:
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
                    "framework": ep.framework,
                }
                for ep in endpoints
            ]
        except Exception as e:
            logger.error("Error fetching active endpoints: %s", e, exc_info=True)
            return []

    def _get_snapshot_subquery(self, endpoint_id: int, target_time: datetime) -> Any:
        """Helper to find the closest bucket snapshot to a specific timestamp."""
        return (
            select(func.max(Buckets.captured_at)).where(
                and_(
                    Buckets.endpoint_id == endpoint_id,
                    Buckets.captured_at <= target_time,
                )
            )
        ).scalar_subquery()

    @ttl_cache_decorator(ttl=300)
    def fetch_batch_summary_stats(
        self,
        endpoint_ids: List[int],
        start: datetime,
        end: datetime,
        cache_bypass: bool = False,
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
                    func.count()
                    .filter(Metrics.response_status == EndpointStatus.FAILED)
                    .label("errors"),
                )
                .where(
                    and_(
                        Metrics.endpoint_id.in_(endpoint_ids),
                        Metrics.created_at.between(start, end),
                    )
                )
                .group_by(Metrics.endpoint_id)
            )

            results = self.session.execute(stmt).mappings().all()
            # Convert list of rows to a dictionary for fast lookup by ID
            return {row["endpoint_id"]: dict(row) for row in results}
        except Exception as e:
            logger.error("Error fetching batch summary stats: %s", e, exc_info=True)
            return {}

    def get_error_rate(self, endpoint_id: int, start: datetime, end: datetime) -> float:
        """Calculate error rate (%) for time window. Not used for actualy analyitcs.
        Can be used for individual calculations if needed."""
        try:
            stmt = select(
                func.count()
                .filter(Metrics.response_status == EndpointStatus.FAILED)
                .label("errors"),
                func.count(Metrics.metrics_id).label("total"),
            ).where(
                and_(
                    Metrics.endpoint_id == endpoint_id,
                    Metrics.created_at.between(start, end),
                )
            )
            result = self.session.execute(stmt).mappings().first()

            if not result or result["total"] == 0:
                return 0.0

            return round((result["errors"] / result["total"]) * 100, 2)
        except Exception as e:
            logger.error("Error calculating error rate: %s", e, exc_info=True)
            return 0.0

    def get_throughput_rps(
        self, endpoint_id: int, start: datetime, end: datetime
    ) -> float:
        """Calculate requests per second for time window. Not used for actualy analyitcs.
        Can be used for individual calculations if needed."""
        try:
            stmt = select(func.count(Metrics.metrics_id).label("total")).where(
                and_(
                    Metrics.endpoint_id == endpoint_id,
                    Metrics.created_at.between(start, end),
                )
            )
            result = self.session.execute(stmt).mappings().first()

            if not result or result["total"] == 0:
                return 0.0

            time_delta = (end - start).total_seconds()
            if time_delta <= 0:
                return 0.0

            return round(result["total"] / time_delta, 2)
        except Exception as e:
            logger.error("Error calculating throughput: %s", e, exc_info=True)
            return 0.0

    @ttl_cache_decorator(ttl=300)
    def fetch_batch_apdex_scores(
        self,
        endpoint_ids: List[int],
        start: datetime,
        end: datetime,
        target_latency_ms: float = 100.0,
        cache_bypass: bool = False,
    ) -> Dict[int, float]:
        """
        BATCH QUERY: Fetches Apdex scores for all provided endpoints in one trip.
        Returns a mapping of {endpoint_id: apdex_score}.
        """
        try:
            stmt = (
                select(
                    Metrics.endpoint_id,
                    func.count()
                    .filter(Metrics.latency_ms <= target_latency_ms)
                    .label("satisfactory"),
                    func.count()
                    .filter(
                        and_(
                            Metrics.latency_ms > target_latency_ms,
                            Metrics.latency_ms <= target_latency_ms * 4,
                        )
                    )
                    .label("tolerable"),
                    func.count(Metrics.metrics_id).label("total"),
                )
                .where(
                    and_(
                        Metrics.endpoint_id.in_(endpoint_ids),
                        Metrics.created_at.between(start, end),
                    )
                )
                .group_by(Metrics.endpoint_id)
            )

            results = self.session.execute(stmt).mappings().all()
            apdex_scores = {}
            for row in results:
                total = row["total"]
                if total == 0:
                    apdex_scores[row["endpoint_id"]] = 0.0
                    continue
                apdex = (row["satisfactory"] + row["tolerable"] / 2) / total
                apdex_scores[row["endpoint_id"]] = round(min(apdex, 1.0), 2)
            return apdex_scores
        except Exception as e:
            logger.error("Error fetching batch Apdex scores: %s", e, exc_info=True)
            return {endpoint_id: 0.0 for endpoint_id in endpoint_ids}

    @ttl_cache_decorator(ttl=300)
    def fetch_batch_window_metrics(
        self,
        endpoint_ids: List[int],
        start_at: datetime,
        end_at: datetime,
        cache_bypass: bool = False,
    ) -> Dict[int, List[HistogramSnapshot]]:
        """
        BATCH QUERY: Calculates deltas between two snapshots for multiple endpoints.
        Returns mapping of {endpoint_id: [HistogramSnapshot, ...]} with delta counts.

        Delta represents: How many NEW requests arrived in this time window?
        Example:
        Start snapshot le=100: count=500 (500 total requests ≤100ms)
        End snapshot le=100: count=650 (650 total requests ≤100ms)
        Delta: 650 - 500 = 150 (150 NEW requests ≤100ms in this window)
        """
        try:
            # 1. Find the latest snapshot at/before start_at for each endpoint
            start_ts_subquery = (
                select(
                    Buckets.endpoint_id,
                    func.max(Buckets.captured_at).label("max_captured_at"),
                )
                .where(
                    and_(
                        Buckets.endpoint_id.in_(endpoint_ids),
                        Buckets.captured_at <= start_at,
                    )
                )
                .group_by(Buckets.endpoint_id)
            ).cte("start_ts_subquery")

            # 2. Find the latest snapshot at/before end_at for each endpoint
            end_ts_subquery = (
                select(
                    Buckets.endpoint_id,
                    func.max(Buckets.captured_at).label("max_captured_at"),
                )
                .where(
                    and_(
                        Buckets.endpoint_id.in_(endpoint_ids),
                        Buckets.captured_at <= end_at,
                    )
                )
                .group_by(Buckets.endpoint_id)
            ).cte("end_ts_subquery")

            # 3. Fetch bucket counts from START snapshots
            start_buckets_stmt = (
                select(Buckets.endpoint_id, Buckets.le, Buckets.count)
                .join(
                    start_ts_subquery,
                    and_(
                        Buckets.endpoint_id == start_ts_subquery.c.endpoint_id,
                        Buckets.captured_at == start_ts_subquery.c.max_captured_at,
                    ),
                )
                .where(Buckets.endpoint_id.in_(endpoint_ids))
            )
            start_bucket_results = self.session.execute(start_buckets_stmt).all()

            # 4. Fetch bucket counts from END snapshots
            end_buckets_stmt = (
                select(Buckets.endpoint_id, Buckets.le, Buckets.count)
                .join(
                    end_ts_subquery,
                    and_(
                        Buckets.endpoint_id == end_ts_subquery.c.endpoint_id,
                        Buckets.captured_at == end_ts_subquery.c.max_captured_at,
                    ),
                )
                .where(Buckets.endpoint_id.in_(endpoint_ids))
            )
            end_bucket_results = self.session.execute(end_buckets_stmt).all()

            # 5. Convert to maps for easy lookup
            start_maps: Dict[int, Dict[float, int]] = {eid: {} for eid in endpoint_ids}
            end_maps: Dict[int, Dict[float, int]] = {eid: {} for eid in endpoint_ids}

            for eid, le, count in start_bucket_results:
                start_maps[eid][le] = count or 0

            for eid, le, count in end_bucket_results:
                end_maps[eid][le] = count or 0

            # 6. Calculate deltas (FULL OUTER JOIN approach - all buckets from both snapshots)
            # Missing buckets are treated as count=0 for proper delta calculation
            final_batch_buckets: Dict[int, List[HistogramSnapshot]] = {
                eid: [] for eid in endpoint_ids
            }

            for eid in endpoint_ids:
                start_map = start_maps[eid]
                end_map = end_maps[eid]

                # Use FULL OUTER JOIN logic: union of all buckets from both snapshots
                # Missing buckets are treated as 0
                all_les = set(start_map.keys()) | set(end_map.keys())

                for le in sorted(all_les):
                    # Treat missing buckets as 0 (FULL OUTER JOIN semantics)
                    start_count = start_map.get(le, 0)
                    end_count = end_map.get(le, 0)

                    # Calculate delta (change in this window)
                    # Handle edge case where cumulative count decreased (shouldn't happen, but handle gracefully)
                    if end_count < start_count:
                        delta = end_count
                        logger.warning(
                            f"Cumulative count decreased for endpoint {eid}, bucket {le}: "
                            f"start_count={start_count}, end_count={end_count}. "
                            f"Setting delta to end_count ({end_count}) as per SQL logic."
                        )
                    else:
                        delta = end_count - start_count

                    # Include ALL buckets (including zero deltas) for complete histogram representation
                    final_batch_buckets[eid].append(
                        HistogramSnapshot(threshold_ms=le, cumulative_count=delta)
                    )

                logger.debug(
                    f"Endpoint {eid}: {len(final_batch_buckets[eid])} buckets with deltas"
                )

            return final_batch_buckets

        except Exception as e:
            logger.error("Error fetching batch window metrics: %s", e, exc_info=True)
            return {eid: [] for eid in endpoint_ids}


@lru_cache_decorator(maxsize=128)
def estimate_percentile(
    snapshots: Tuple[HistogramSnapshot, ...],
    percentile: float,
    cache_bypass: bool = False,
) -> float:
    """
    Pure math function: Linear interpolation for percentile calculation.
    Separated from the DB logic for easier testing and reusability.

    Algorithm: Master Formula
    - Finds bucket containing target rank
    - Interpolates within bucket using linear approximation

    Args:
        snapshots: List of HistogramSnapshot objects (deltas)
        percentile: Target percentile (50, 95, 99, etc.)

    Returns:
        Estimated latency in milliseconds
    """

    if not snapshots:
        return 0.0

    # Snapshots are ALREADY cumulative deltas
    sorted_snapshots = sorted(snapshots, key=lambda s: s.threshold_ms)
    
    total_count = sorted_snapshots[-1].cumulative_count  # Already cumulative
    if total_count == 0:
        return 0.0

    target_rank = (percentile / 100) * total_count
    prev_ms = 0.0
    prev_count = 0

    for snapshot in sorted_snapshots:
        if snapshot.cumulative_count >= target_rank:
            if snapshot.threshold_ms == float("inf"):
                return prev_ms

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