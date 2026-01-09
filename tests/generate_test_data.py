# scripts/generate_test_data.py (Fixed & Timezone-Safe)
"""
Tracelet Test Data Generator - FIXED & OPTIMIZED.
- Proper timezone-aware datetime handling
- Fixed database insertion errors
- Better error handling with logging
"""

import random
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import numpy as np # type: ignore

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from tracelet.db.models import Endpoints, Metrics, Buckets, EndpointStatus
from tracelet.db.config import setup_db

db = setup_db({"db_url": "postgresql+psycopg2://kriz:root@localhost:5432/tracelet", "echo": False})
SessionLocal = db.SessionLocal

# Set up logging to file AND console
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # logging.FileHandler('tracelet_generation.log'),
        logging.StreamHandler(sys.stdout),
    ],
    encoding='utf-8'
)
logger = logging.getLogger("test_data_generator")

# ============================================================================
# Configuration
# ============================================================================

BUCKET_THRESHOLDS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float('inf')]
SNAPSHOT_INTERVAL = timedelta(minutes=5)
DAYS_OF_DATA = 7  # Default: 7 days (configurable)
BATCH_SIZE = 30  # Metrics batch size
SNAPSHOT_BATCH_SIZE = 20  # Buckets batch size
METRICS_PER_SNAPSHOT = 10  # ~100 requests per 5-min interval

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
# Utility Functions
# ============================================================================

def generate_latency(mean: float, stdev: float, min_val: float = 1.0) -> float:
    """Generate latency using normal distribution."""
    latency = np.random.normal(mean, stdev)
    return max(min_val, min(10000, latency))


def get_traffic_multiplier(timestamp: datetime) -> float:
    """Simulate realistic traffic patterns."""
    hour = timestamp.hour
    if 9 <= hour < 17:
        return 1.0 + random.uniform(0, 0.5)
    elif 17 <= hour < 22:
        return 0.8 + random.uniform(0, 0.3)
    else:
        return 0.2 + random.uniform(0, 0.2)


# ============================================================================
# FIXED: Timezone-Aware DateTime Generation
# ============================================================================

def generate_request_times(
    base_timestamp: datetime,
    count: int
) -> List[tuple]:
    """
    Generate timezone-aware request/response times.
    
    Pattern:
    1. Start with epoch (float)
    2. Do random math on float
    3. Convert back to AWARE datetime
    4. Math with timedelta keeps it AWARE
    
    Returns: List of (request_time, response_time, latency_ms) tuples
    """
    if not base_timestamp.tzinfo or base_timestamp.tzinfo.utcoffset(base_timestamp) is None:
        raise ValueError("base_timestamp must be timezone-aware (UTC)")
    
    request_tuples = []
    base_epoch = base_timestamp.timestamp()
    
    for _ in range(count):
        # Step 1: Start with epoch (float)
        request_epoch = base_epoch + random.uniform(0, SNAPSHOT_INTERVAL.total_seconds())
        
        # Step 2: Convert to AWARE datetime immediately
        request_time = datetime.fromtimestamp(request_epoch, tz=timezone.utc)
        
        # Generate latency
        latency_ms = generate_latency(50, 30)  # Generic latency
        
        # Step 3: Math with timedelta keeps it AWARE
        response_time = request_time + timedelta(milliseconds=latency_ms)
        
        # Verify both are aware
        assert request_time.tzinfo is not None, "request_time lost timezone!"
        assert response_time.tzinfo is not None, "response_time lost timezone!"
        
        request_tuples.append((request_time, response_time, latency_ms))
    
    return request_tuples


def generate_metrics_batch(
    endpoint_id: int,
    config: Dict,
    base_timestamp: datetime,
    count: int
) -> List[Dict]:
    """
    Generate metrics batch with proper timezone handling.
    
    All timestamps are UTC-aware.
    """
    if not base_timestamp.tzinfo:
        raise ValueError("base_timestamp must be timezone-aware")
    
    metrics = []
    base_epoch = base_timestamp.timestamp()
    
    for i in range(count):
        try:
            # Step 1: Epoch math
            request_epoch = base_epoch + random.uniform(0, SNAPSHOT_INTERVAL.total_seconds())
            
            # Step 2: Convert immediately to AWARE datetime
            request_time = datetime.fromtimestamp(request_epoch, tz=timezone.utc)
            
            # Generate endpoint-specific latency
            latency_ms = generate_latency(
                config['latency_mean'],
                config['latency_stdev']
            )
            
            # Step 3: Use timedelta (keeps timezone awareness)
            response_time = request_time + timedelta(milliseconds=latency_ms)
            
            # Error chance
            is_error = random.random() < (config['error_rate'] / 100)
            status = EndpointStatus.FAILED if is_error else EndpointStatus.SUCCESS
            
            # All fields must be timezone-aware
            metric = {
                'endpoint_id': endpoint_id,
                'request_time': request_time,
                'response_time': response_time,
                'latency_ms': float(latency_ms),
                'response_status': status,
                'created_at': response_time,  # Use response_time (when we recorded it)
                'unique_id': f"{endpoint_id}_{base_epoch:.0f}_{i}_{random.random():.6f}",
            }
            
            metrics.append(metric)
            
        except Exception as e:
            logger.error(f"Error generating metric {i}: {e}")
            raise
    
    return metrics


def generate_bucket_snapshot(
    endpoint_id: int,
    metrics: List[Dict],
    captured_at: datetime
) -> List[Dict]:
    """
    Generate bucket snapshot from metrics.
    
    captured_at must be UTC-aware.
    """
    if not captured_at.tzinfo:
        raise ValueError("captured_at must be timezone-aware")
    
    buckets = []
    
    for threshold in BUCKET_THRESHOLDS:
        if threshold == float('inf'):
            count = len(metrics)
        else:
            count = sum(1 for m in metrics if m['latency_ms'] <= threshold)
        
        if count > 0:
            bucket = {
                'endpoint_id': endpoint_id,
                'le': float(threshold) if threshold != float('inf') else float('inf'),
                'count': int(count),
                'captured_at': captured_at,
            }
            buckets.append(bucket)
    
    return buckets


# ============================================================================
# Database Operations (FIXED Error Handling)
# ============================================================================

def batch_insert_metrics(
    session: Session,
    metrics_batch: List[Dict]
) -> bool:
    """Bulk insert metrics with error handling."""
    if not metrics_batch:
        return True
    
    try:
        session.bulk_insert_mappings(Metrics, metrics_batch)
        logger.debug(f"✓ Inserted {len(metrics_batch)} metrics")
        return True
    except SQLAlchemyError as e:
        logger.error(f"❌ Database error inserting metrics: {e}")
        logger.error(f"   First metric: {metrics_batch[0] if metrics_batch else 'None'}")
        session.rollback()
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error inserting metrics: {e}", exc_info=True)
        session.rollback()
        return False


def batch_insert_buckets(
    session: Session,
    buckets_batch: List[Dict]
) -> bool:
    """Bulk insert buckets with error handling."""
    if not buckets_batch:
        return True
    
    try:
        # Simple insert (upsert handled by app logic)
        session.bulk_insert_mappings(Buckets, buckets_batch)
        logger.debug(f"✓ Inserted {len(buckets_batch)} buckets")
        return True
    except SQLAlchemyError as e:
        logger.error(f"❌ Database error inserting buckets: {e}")
        logger.error(f"   First bucket: {buckets_batch[0] if buckets_batch else 'None'}")
        session.rollback()
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error inserting buckets: {e}", exc_info=True)
        session.rollback()
        return False


# ============================================================================
# Main Generation
# ============================================================================

def create_endpoints(session: Session) -> Dict[int, Dict]:
    """Create endpoints with error handling."""
    logger.info("Creating endpoints...")
    endpoint_map = {}
    
    try:
        for config in ENDPOINTS_CONFIG:
            existing = session.query(Endpoints).filter(
                Endpoints.path == config['path'],
                Endpoints.method == config['method'],
                Endpoints.framework == config['framework']
            ).first()
            
            if existing:
                endpoint_map[existing.endpoint_id] = config
                logger.info(f"  Found: {config['method']:6} {config['path']:30} (ID: {existing.endpoint_id})")
            else:
                endpoint = Endpoints(
                    path=config['path'],
                    method=config['method'],
                    framework=config['framework'],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(endpoint)
                session.flush()
                endpoint_map[endpoint.endpoint_id] = config
                logger.info(f"  Created: {config['method']:6} {config['path']:30} (ID: {endpoint.endpoint_id})")
        
        session.commit()
        logger.info(f"✓ Total endpoints: {len(endpoint_map)}\n")
        return endpoint_map
        
    except Exception as e:
        logger.error(f"❌ Error creating endpoints: {e}", exc_info=True)
        session.rollback()
        raise


def generate_historical_data(
    session: Session,
    endpoint_map: Dict[int, Dict],
    days: int = DAYS_OF_DATA
) -> bool:
    """Generate historical data with proper error handling."""
    logger.info(f"Generating {days} days of data...\n")
    
    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days)
        
        current_time = start_time
        total_metrics = 0
        total_buckets = 0
        day_count = 0
        
        metrics_buffer = []
        buckets_buffer = []
        
        while current_time < now:
            # For each endpoint in this time window
            for endpoint_id, config in endpoint_map.items():
                traffic_multiplier = get_traffic_multiplier(current_time)
                metrics_count = int(METRICS_PER_SNAPSHOT * traffic_multiplier)
                
                # Generate metrics for this endpoint
                try:
                    endpoint_metrics = generate_metrics_batch(
                        endpoint_id,
                        config,
                        current_time,
                        metrics_count
                    )
                    metrics_buffer.extend(endpoint_metrics)
                    total_metrics += len(endpoint_metrics)
                except Exception as e:
                    logger.error(f"Error generating metrics for endpoint {endpoint_id}: {e}")
                    raise
                
                # Generate bucket snapshot
                try:
                    endpoint_buckets = generate_bucket_snapshot(
                        endpoint_id,
                        endpoint_metrics,
                        current_time
                    )
                    buckets_buffer.extend(endpoint_buckets)
                    total_buckets += len(endpoint_buckets)
                except Exception as e:
                    logger.error(f"Error generating buckets for endpoint {endpoint_id}: {e}")
                    raise
            
            # Batch flush for metrics
            if len(metrics_buffer) >= BATCH_SIZE:
                if not batch_insert_metrics(session, metrics_buffer):
                    return False
                metrics_buffer = []
            
            # Batch flush for buckets
            if len(buckets_buffer) >= SNAPSHOT_BATCH_SIZE:
                if not batch_insert_buckets(session, buckets_buffer):
                    return False
                buckets_buffer = []
            
            # Commit every 24 snapshots (2 hours of 5-min intervals)
            snapshots_since_start = (current_time - start_time).total_seconds() / SNAPSHOT_INTERVAL.total_seconds()
            if int(snapshots_since_start) % 288 == 0 and snapshots_since_start > 0:
                try:
                    session.commit()
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    session.rollback()
                    return False
            
            current_time += SNAPSHOT_INTERVAL
            
            # Progress every day
            days_elapsed = (current_time - start_time).days
            if days_elapsed > day_count:
                day_count = days_elapsed
                logger.info(
                    f"  Day {day_count}/{days} | "
                    f"Metrics: {total_metrics:,} | Buckets: {total_buckets:,}"
                )
        
        # Flush remaining buffers
        if metrics_buffer:
            if not batch_insert_metrics(session, metrics_buffer):
                return False
        if buckets_buffer:
            if not batch_insert_buckets(session, buckets_buffer):
                return False
        
        session.commit()
        
        logger.info(
            f"\n✓ Data generation complete!\n"
            f"  Total metrics: {total_metrics:,}\n"
            f"  Total bucket snapshots: {total_buckets:,}\n"
        )
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in generate_historical_data: {e}", exc_info=True)
        session.rollback()
        return False


# ============================================================================
# Public API
# ============================================================================

def generate_test_data(clear_existing: bool = True, days: int = DAYS_OF_DATA) -> bool:
    """
    Generate complete test dataset.
    
    Args:
        clear_existing: Clear data before generating
        days: Number of days to generate
    
    Returns:
        True if successful, False otherwise
    """
    session = SessionLocal()
    
    try:
        # Clear existing data
        if clear_existing:
            logger.warning("Clearing existing data...")
            try:
                session.query(Buckets).delete()
                session.query(Metrics).delete()
                session.query(Endpoints).delete()
                session.commit()
                logger.info("✓ Data cleared\n")
            except Exception as e:
                logger.error(f"❌ Error clearing data: {e}")
                session.rollback()
                return False
        
        # Create endpoints
        endpoint_map = create_endpoints(session)
        if not endpoint_map:
            logger.error("❌ No endpoints created")
            return False
        
        # Generate historical data
        if not generate_historical_data(session, endpoint_map, days):
            logger.error("❌ Data generation failed")
            return False
        
        # Verify
        verify_test_data(session)
        
        logger.info("\n🎉 Test data generation successful!")
        logger.info("Ready for testing:")
        logger.info("  python scripts/test_analytics.py")
        logger.info("  tracelet status -d last_7d")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        return False
    finally:
        session.close()


def verify_test_data(session: Session) -> None:
    """Verify generated data integrity."""
    logger.info("\nVerifying data...")
    
    try:
        endpoint_count = session.query(Endpoints).count()
        metric_count = session.query(Metrics).count()
        bucket_count = session.query(Buckets).count()
        
        logger.info(f"  ✓ Endpoints: {endpoint_count}")
        logger.info(f"  ✓ Metrics: {metric_count:,}")
        logger.info(f"  ✓ Buckets: {bucket_count:,}")
        
        # Date range
        from sqlalchemy import func
        m_min = session.query(func.min(Metrics.created_at)).scalar()
        m_max = session.query(func.max(Metrics.created_at)).scalar()
        
        if m_min and m_max:
            days = (m_max - m_min).days
            logger.info(f"  ✓ Date range: {days} days")
            logger.info(f"  ✓ Earliest: {m_min}")
            logger.info(f"  ✓ Latest: {m_max}")
            
            # Check timezone awareness
            if m_min.tzinfo:
                logger.info(f"  ✓ Timezone: {m_min.tzinfo}")
            else:
                logger.warning(f"  ⚠️  No timezone info detected!")
        
    except Exception as e:
        logger.error(f"Error verifying data: {e}", exc_info=True)


def cleanup_test_data() -> bool:
    """Delete all test data."""
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
        logger.error(f"❌ Error deleting data: {e}", exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    import time
    
    parser = argparse.ArgumentParser(description="Tracelet Test Data Generator")
    parser.add_argument("--generate", action="store_true", default=True)
    parser.add_argument("--clear", action="store_true", help="Clear before generating")
    parser.add_argument("--cleanup", action="store_true", help="Delete all data")
    parser.add_argument("--verify", action="store_true", help="Verify data")
    parser.add_argument("--days", type=int, default=DAYS_OF_DATA, help="Days of data")
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Tracelet Test Data Generator")
    logger.info("=" * 70)
    
    start = time.time()
    success = False
    
    try:
        if args.cleanup:
            success = cleanup_test_data()
        elif args.verify:
            session = SessionLocal()
            verify_test_data(session)
            session.close()
            success = True
        else:
            success = generate_test_data(clear_existing=args.clear, days=args.days)
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Generation interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}", exc_info=True)
    
    elapsed = time.time() - start
    logger.info(f"\n⏱️  Total time: {elapsed:.1f}s")
    
    if success or args.verify:
        logger.info("✓ Done!")
        exit(0)
    else:
        logger.error("✗ Failed - check tracelet_generation.log for details")
        exit(1)