"""
Tracelet Test Data Generator
Generates realistic historical latency data for testing analytics.
Uses Tracelet's capture() engine for proper bucket accumulation.
"""

import random
import logging
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
from sqlalchemy.orm import Session

from tracelet.db.models import Endpoints, Metrics, Buckets
from tracelet.config import settings

# ============================================================================
# Logging Configuration
# ============================================================================

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "tracelet_generation.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("test_data_generator")


# ============================================================================
# Configuration
# ============================================================================

SNAPSHOT_INTERVAL = timedelta(minutes=5)
DAYS_OF_DATA = 7
METRICS_PER_SNAPSHOT = 10  # Base request rate per 5-min window

ENDPOINTS_CONFIG = [
    {
        "path": "/api/users",
        "method": "GET",
        "framework": "fastapi",
        "latency_mean": 50,
        "latency_stdev": 20,
        "error_rate": 0.5,
    },
    {
        "path": "/api/users",
        "method": "POST",
        "framework": "fastapi",
        "latency_mean": 150,
        "latency_stdev": 50,
        "error_rate": 2.0,
    },
    {
        "path": "/api/users/<id>",
        "method": "GET",
        "framework": "fastapi",
        "latency_mean": 45,
        "latency_stdev": 15,
        "error_rate": 0.3,
    },
    {
        "path": "/api/users/<id>",
        "method": "PUT",
        "framework": "fastapi",
        "latency_mean": 200,
        "latency_stdev": 80,
        "error_rate": 3.0,
    },
    {
        "path": "/api/users/<id>",
        "method": "DELETE",
        "framework": "fastapi",
        "latency_mean": 80,
        "latency_stdev": 30,
        "error_rate": 1.5,
    },
    {
        "path": "/api/products",
        "method": "GET",
        "framework": "django",
        "latency_mean": 120,
        "latency_stdev": 50,
        "error_rate": 1.0,
    },
    {
        "path": "/api/products/<id>",
        "method": "GET",
        "framework": "django",
        "latency_mean": 100,
        "latency_stdev": 40,
        "error_rate": 0.8,
    },
    {
        "path": "/api/orders",
        "method": "POST",
        "framework": "flask",
        "latency_mean": 300,
        "latency_stdev": 100,
        "error_rate": 4.0,
    },
    {
        "path": "/api/orders",
        "method": "GET",
        "framework": "flask",
        "latency_mean": 250,
        "latency_stdev": 80,
        "error_rate": 2.5,
    },
    {
        "path": "/api/analytics/report",
        "method": "POST",
        "framework": "fastapi",
        "latency_mean": 2000,
        "latency_stdev": 500,
        "error_rate": 5.0,
    },
]

# ============================================================================
# Database & Engine Initialization
# ============================================================================


def init_tracelet() -> tuple:
    """
    Initialize Tracelet engine and database session.

    Returns:
        (engine, SessionLocal) tuple
    """
    import tracelet
    from tracelet.core.engine import get_engine

    db_config = {
        "db_url": "postgresql+psycopg2://kriz:root@localhost:5432/tracelet",
        "echo": False,
    }

    tracelet.init(db_config=db_config, batch_size=100, logger_level="INFO")
    engine = get_engine()
    session_factory = settings.SessionLocal

    logger.info("✓ Tracelet engine initialized")
    return engine, session_factory


def shutdown_tracelet(engine) -> None:
    """Shutdown engine and cleanup."""
    if engine:
        engine.shutdown()

    # Reset singleton
    from tracelet.core.engine import _shared_engine_instance

    if _shared_engine_instance:
        globals()["_shared_engine_instance"] = None

    logger.info("✓ Engine shutdown complete")


# ============================================================================
# Traffic Pattern Simulation
# ============================================================================


def get_traffic_multiplier(timestamp: datetime) -> float:
    """
    Simulate realistic daily and weekly traffic patterns.

    Weekdays (Mon-Fri):
      - Business hours (9-17): 1.0-1.5x
      - Evening (17-22): 0.8-1.1x
      - Night: 0.2-0.4x

    Weekends (Sat-Sun):
      - Late start, reduced overall traffic
      - Peak window shifted later
      - Overall scale: 40-60% of weekday load
    """
    hour = timestamp.hour
    weekday = timestamp.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 5

    # Base hourly multiplier
    if 9 <= hour < 17:
        base = 1.0 + random.uniform(0, 0.5)
    elif 17 <= hour < 22:
        base = 0.8 + random.uniform(0, 0.3)
    else:
        base = 0.2 + random.uniform(0, 0.2)

    if not is_weekend:
        return base

    # Weekend scaling
    weekend_scale = random.uniform(0.4, 0.6)

    # Shift activity later on weekends
    if hour < 11:
        return base * weekend_scale * 0.6
    elif hour < 18:
        return base * weekend_scale
    else:
        return base * weekend_scale * 0.8


# ============================================================================
# Latency Generation
# ============================================================================


def generate_latency(mean: float, stdev: float) -> float:
    """
    Generate realistic latency using a normal distribution.
    Clamped to [1ms, 10000ms].
    """
    latency = np.random.lognormal(mean=np.log(mean), sigma=0.5)
    return min(latency, 5000.0)


# ============================================================================
# Endpoint Creation
# ============================================================================


def create_endpoints(session: Session, default_dt: datetime) -> Dict[int, Dict]:
    """
    Create or retrieve endpoint definitions.

    Returns:
        Dict mapping endpoint_id -> config
    """
    logger.info("Creating endpoints...")
    endpoint_map = {}

    try:
        for config in ENDPOINTS_CONFIG:
            existing = (
                session.query(Endpoints)
                .filter(
                    Endpoints.path == config["path"],
                    Endpoints.method == config["method"],
                    Endpoints.framework == config["framework"],
                )
                .first()
            )

            if existing:
                endpoint_map[existing.endpoint_id] = config
                logger.info(
                    f"  Found: {config['method']:6} {config['path']:30} "
                    f"(ID: {existing.endpoint_id})"
                )
            else:
                endpoint = Endpoints(
                    path=config["path"],
                    method=config["method"],
                    framework=config["framework"],
                    created_at=default_dt,
                    updated_at=default_dt,
                )
                session.add(endpoint)
                session.flush()
                endpoint_map[endpoint.endpoint_id] = config
                logger.info(
                    f"  Created: {config['method']:6} {config['path']:30} "
                    f"(ID: {endpoint.endpoint_id})"
                )

        session.commit()
        logger.info(f"✓ Total endpoints: {len(endpoint_map)}\n")
        return endpoint_map

    except Exception as e:
        logger.error(f"Error creating endpoints: {e}", exc_info=True)
        session.rollback()
        raise


# ============================================================================
# Historical Data Generation
# ============================================================================


def generate_historical_data(
    engine, endpoint_map: Dict[int, Dict], days: int
) -> Tuple[bool, List[Tuple[datetime, datetime]]]:
    """
    Generate historical metrics using Tracelet's capture() engine.

    Returns:
        (success, snapshot_windows) where snapshot_windows = [(start, end), ...]
    """
    logger.info(f"Generating {days} days of data...\n")

    snapshot_windows = []

    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days)
        current_time = start_time

        total_metrics = 0
        day_count = 0

        while current_time < now:
            snapshot_start = current_time
            snapshot_end = current_time + SNAPSHOT_INTERVAL

            for endpoint_id, config in endpoint_map.items():
                traffic_multiplier = get_traffic_multiplier(current_time)
                metrics_count = int(METRICS_PER_SNAPSHOT * traffic_multiplier)

                for _ in range(metrics_count):
                    request_epoch = current_time.timestamp() + random.uniform(
                        0, SNAPSHOT_INTERVAL.total_seconds()
                    )
                    request_time = datetime.fromtimestamp(
                        request_epoch, tz=timezone.utc
                    )

                    latency_ms = generate_latency(
                        config["latency_mean"], config["latency_stdev"]
                    )
                    response_time = request_time + timedelta(milliseconds=latency_ms)

                    is_error = random.random() < (config["error_rate"] / 100)
                    status_code = 500 if is_error else 200

                    engine.capture(
                        {
                            "path": config["path"],
                            "method": config["method"],
                            "framework": config["framework"],
                            "start_dt": request_time,
                            "end_dt": response_time,
                            "elapsed": latency_ms / 1000.0,
                            "response_status": status_code,
                        }
                    )

                    total_metrics += 1

            # Track this snapshot window for backfill
            snapshot_windows.append((snapshot_start, snapshot_end))
            current_time += SNAPSHOT_INTERVAL

            days_elapsed = (current_time - start_time).days
            if days_elapsed > day_count:
                day_count = days_elapsed
                logger.info(f"  Day {day_count}/{days} | Metrics: {total_metrics:,}")

        logger.info(f"\n✓ Generated {total_metrics:,} metrics")
        logger.info(f"✓ Snapshot windows: {len(snapshot_windows)}\n")
        return True, snapshot_windows

    except Exception as e:
        logger.error(f"Error in data generation: {e}", exc_info=True)
        return False, []


# ============================================================================
# Timestamp Backfill
# ============================================================================


def backfill_timestamps(
    session: Session,
    snapshot_windows: List[Tuple[datetime, datetime]],
    generation_start: datetime,
) -> bool:
    """
    Backfill historical timestamps for metrics and buckets.

    Phase 1: Update tracelet_metrics.created_at based on latency window
    Phase 2: Update tracelet_latency_buckets.captured_at to snapshot boundaries

    Args:
        session: DB session
        snapshot_windows: List of (start, end) tuples for each 5-min window
        generation_start: When data generation began (metrics after this need backfill)
    """
    logger.info("Backfilling timestamps...")

    try:
        # Phase 1: Backfill metrics timestamps
        logger.info("  Phase 1: Updating tracelet_metrics.created_at...")

        # Get all metrics created during generation
        metrics = (
            session.query(Metrics)
            .filter(Metrics.created_at >= generation_start)
            .order_by(Metrics.created_at)
            .all()
        )

        if not metrics:
            logger.warning("  No metrics found to backfill")
            return False

        logger.info(f"  Found {len(metrics):,} metrics to backfill")

        # Distribute metrics across snapshot windows
        metrics_per_window = len(metrics) // len(snapshot_windows)
        window_idx = 0

        for i, metric in enumerate(metrics):
            # Move to next window when threshold reached
            if (
                i > 0
                and i % metrics_per_window == 0
                and window_idx < len(snapshot_windows) - 1
            ):
                window_idx += 1

            window_start, window_end = snapshot_windows[window_idx]

            # Random timestamp within this window
            random_offset = random.uniform(
                0, (window_end - window_start).total_seconds()
            )
            backfill_time = window_start + timedelta(seconds=random_offset)

            metric.created_at = backfill_time

        session.commit()
        logger.info(f"  ✓ Updated {len(metrics):,} metrics timestamps")

        # Phase 2: Backfill bucket snapshots
        logger.info("  Phase 2: Updating tracelet_latency_buckets.captured_at...")

        # Get all buckets created during generation
        buckets = (
            session.query(Buckets)
            .filter(Buckets.captured_at >= generation_start)
            .order_by(Buckets.endpoint_id, Buckets.captured_at, Buckets.le)
            .all()
        )

        if not buckets:
            logger.warning("  No buckets found to backfill")
            return True  # Metrics were updated, consider success

        logger.info(f"  Found {len(buckets):,} bucket records to backfill")

        # Group buckets by (endpoint_id, captured_at) to form complete snapshots
        # All buckets with same endpoint_id and captured_at form one snapshot
        from collections import defaultdict

        snapshot_groups = defaultdict(list)

        for bucket in buckets:
            snapshot_key = (bucket.endpoint_id, bucket.captured_at)
            snapshot_groups[snapshot_key].append(bucket)

        logger.info(f"  Found {len(snapshot_groups):,} distinct snapshots")

        # Group snapshots by endpoint_id for sequential assignment
        endpoint_snapshots = defaultdict(list)
        for (eid, _), snapshot_buckets in snapshot_groups.items():
            endpoint_snapshots[eid].append(
                (snapshot_buckets[0].captured_at, snapshot_buckets)
            )

        # Assign entire snapshots to sequential snapshot windows
        for endpoint_id, snapshots in endpoint_snapshots.items():
            # Sort snapshots by original captured_at to maintain chronological order
            snapshots.sort(key=lambda x: x[0])

            # Distribute snapshots across windows
            snapshots_per_window = len(snapshots) // len(snapshot_windows)
            if snapshots_per_window == 0:
                snapshots_per_window = 1

            window_idx = 0
            for i, (original_ts, snapshot_buckets) in enumerate(snapshots):
                # Move to next window when threshold reached
                if (
                    i > 0
                    and i % snapshots_per_window == 0
                    and window_idx < len(snapshot_windows) - 1
                ):
                    window_idx += 1

                # Assign entire snapshot to window boundary (end time)
                new_timestamp = snapshot_windows[window_idx][1]
                for bucket in snapshot_buckets:
                    bucket.captured_at = new_timestamp

        session.commit()
        logger.info(
            f"  ✓ Updated {len(buckets):,} bucket records across {len(snapshot_groups):,} snapshots"
        )
        logger.info("✓ Timestamp backfill complete\n")

        return True

    except Exception as e:
        logger.error(f"Error in timestamp backfill: {e}", exc_info=True)
        session.rollback()
        return False


# ============================================================================
# Main Pipeline
# ============================================================================


def generate_test_data(clear_existing: bool = True, days: int = DAYS_OF_DATA) -> bool:
    """
    Main data generation pipeline.
    1. Initialize Tracelet engine
    2. Clear existing data (optional)
    3. Create endpoints
    4. Generate historical metrics
    5. Backfill timestamps
    6. Verify data
    7. Shutdown
    """
    engine, SessionLocal = init_tracelet()
    session = SessionLocal()
    generation_start = datetime.now(timezone.utc)

    try:
        # Clear existing data
        if clear_existing:
            logger.warning("Clearing existing data...")
            session.query(Buckets).delete()
            session.query(Metrics).delete()
            session.query(Endpoints).delete()
            session.commit()
            logger.info("✓ Data cleared\n")

        # Create endpoints
        endpoint_map = create_endpoints(session, generation_start)
        if not endpoint_map:
            logger.error("No endpoints created")
            return False

        # Generate data
        success, snapshot_windows = generate_historical_data(engine, endpoint_map, days)
        if not success:
            logger.error("Data generation failed")
            return False

        # Backfill timestamps
        if not backfill_timestamps(session, snapshot_windows, generation_start):
            logger.warning("Timestamp backfill failed, but data exists")

        # Verify
        verify_data(session)

        logger.info("\n🎉 Test data generation successful!")
        logger.info("Ready for: tracelet describe -d last_7d")

        return True

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return False
    finally:
        shutdown_tracelet(engine)
        session.close()


# ============================================================================
# Data Verification
# ============================================================================


def verify_data(session: Session) -> None:
    """Verify generated data integrity."""
    from sqlalchemy import func

    logger.info("Verifying data...")

    endpoint_count = session.query(Endpoints).count()
    metric_count = session.query(Metrics).count()
    bucket_count = session.query(Buckets).count()

    logger.info(f"  ✓ Endpoints: {endpoint_count}")
    logger.info(f"  ✓ Metrics: {metric_count:,}")
    logger.info(f"  ✓ Buckets: {bucket_count:,}")

    m_min = session.query(func.min(Metrics.created_at)).scalar()
    m_max = session.query(func.max(Metrics.created_at)).scalar()

    b_min = session.query(func.min(Buckets.captured_at)).scalar()
    b_max = session.query(func.max(Buckets.captured_at)).scalar()

    if m_min and m_max:
        logger.info(f"  ✓ Metrics date range: {(m_max - m_min).days} days")
        logger.info(f"    Earliest: {m_min.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"    Latest: {m_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    if b_min and b_max:
        logger.info(f"  ✓ Buckets date range: {(b_max - b_min).days} days")
        logger.info(f"    Earliest: {b_min.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"    Latest: {b_max.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    if m_min:
        logger.info(f"  ✓ Timezone: {'UTC' if m_min.tzinfo else 'NONE (ERROR)'}")


def cleanup_data() -> bool:
    """Delete all test data."""
    _, SessionLocal = init_tracelet()
    session = SessionLocal()
    try:
        logger.warning("Deleting all test data...")
        session.query(Buckets).delete()
        session.query(Metrics).delete()
        session.query(Endpoints).delete()
        session.commit()
        logger.info("✓ Test data deleted")
        return True
    except Exception as e:
        logger.error(f"Error deleting data: {e}", exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tracelet Test Data Generator")

    parser.add_argument(
        "--generate",
        action="store_true",
        default=True,
        help="Generate test data",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear before generating",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete all data",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing data",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DAYS_OF_DATA,
        help="Days of data to generate",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Tracelet Test Data Generator")
    logger.info("=" * 70)

    start = time.time()
    success = False

    try:
        if args.cleanup:
            success = cleanup_data()

        elif args.verify:
            _, SessionLocal = init_tracelet()
            session = SessionLocal()
            verify_data(session)
            session.close()
            success = True

        else:
            success = generate_test_data(
                clear_existing=args.clear,
                days=args.days,
            )

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrupted by user")

    except Exception:
        logger.error("\n❌ Fatal error", exc_info=True)

    elapsed = time.time() - start
    logger.info(f"\n⏱️  Total time: {elapsed:.1f}s")

    if success or args.verify:
        logger.info("✓ Done!")
    exit(0)
