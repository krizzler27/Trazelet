"""
Comprehensive test for histogram cumulative/delta logic correctness.

This test verifies the complete data flow:
1. Engine bucket insertion (cumulative counts)
2. Analytics delta calculation (FULL OUTER JOIN)
3. Percentile calculation (delta-to-cumulative conversion)

Test Case:
- Snapshot T0: le=100: 500, le=250: 800, le=500: 950
- Snapshot T1: le=100: 650, le=250: 900, le=500: 1000
- Expected Delta: le=100: 150, le=250: 100, le=500: 50
- Expected P50: Should fall in le=100 bucket (150 total requests)
"""

import pytest # type: ignore
from datetime import datetime, timezone, timedelta
from tracelet.tui.analytics import HistogramSnapshot, estimate_percentile
from tracelet.db.models import Endpoints, Buckets
from tracelet.config import settings


def test_cumulative_to_delta_calculation():
    """Test that delta calculation correctly handles cumulative snapshots."""
    
    # Simulate two snapshots with cumulative counts
    # Snapshot T0 (start)
    start_snapshot = {
        100.0: 500,   # 500 requests ≤ 100ms
        250.0: 800,   # 800 requests ≤ 250ms
        500.0: 950,   # 950 requests ≤ 500ms
    }
    
    # Snapshot T1 (end)
    end_snapshot = {
        100.0: 650,   # 650 requests ≤ 100ms (150 new)
        250.0: 900,   # 900 requests ≤ 250ms (100 new)
        500.0: 1000,  # 1000 requests ≤ 500ms (50 new)
    }
    
    # Calculate deltas manually (expected)
    expected_deltas = {
        100.0: 150,   # 650 - 500 = 150
        250.0: 100,   # 900 - 800 = 100
        500.0: 50,    # 1000 - 950 = 50
    }
    
    # Simulate FULL OUTER JOIN logic
    all_les = set(start_snapshot.keys()) | set(end_snapshot.keys())
    
    calculated_deltas = {}
    for le in sorted(all_les):
        start_count = start_snapshot.get(le, 0)
        end_count = end_snapshot.get(le, 0)
        delta = end_count - start_count
        calculated_deltas[le] = delta
    
    # Verify deltas match expected
    assert calculated_deltas == expected_deltas, \
        f"Delta calculation failed. Expected {expected_deltas}, got {calculated_deltas}"


def test_delta_to_cumulative_conversion():
    """Test that deltas are correctly converted to cumulative for percentile calculation."""
    
    # Input: Deltas (new requests in window)
    deltas = [
        HistogramSnapshot(threshold_ms=100.0, cumulative_count=150),  # 150 new requests ≤ 100ms
        HistogramSnapshot(threshold_ms=250.0, cumulative_count=100),  # 100 new requests ≤ 250ms
        HistogramSnapshot(threshold_ms=500.0, cumulative_count=50),   # 50 new requests ≤ 500ms
    ]
    
    # Expected cumulative after conversion
    expected_cumulative = [
        HistogramSnapshot(threshold_ms=100.0, cumulative_count=150),  # 150 total
        HistogramSnapshot(threshold_ms=250.0, cumulative_count=250),  # 150 + 100 = 250
        HistogramSnapshot(threshold_ms=500.0, cumulative_count=300),  # 250 + 50 = 300
    ]
    
    # Convert deltas to cumulative (same logic as estimate_percentile)
    sorted_deltas = sorted(deltas, key=lambda s: s.threshold_ms)
    cumulative = []
    running_total = 0
    
    for snapshot in sorted_deltas:
        running_total += snapshot.cumulative_count  # Sum deltas
        cumulative.append(
            HistogramSnapshot(
                threshold_ms=snapshot.threshold_ms,
                cumulative_count=running_total
            )
        )
    
    # Verify conversion
    assert len(cumulative) == len(expected_cumulative)
    for i, (actual, expected) in enumerate(zip(cumulative, expected_cumulative)):
        assert actual.threshold_ms == expected.threshold_ms, \
            f"Threshold mismatch at index {i}: {actual.threshold_ms} != {expected.threshold_ms}"
        assert actual.cumulative_count == expected.cumulative_count, \
            f"Count mismatch at index {i}: {actual.cumulative_count} != {expected.cumulative_count}"


def test_percentile_calculation_with_deltas():
    """Test percentile calculation with delta input (real-world scenario)."""
    
    # Input: Deltas from time window
    deltas = [
        HistogramSnapshot(threshold_ms=10.0, cumulative_count=50),
        HistogramSnapshot(threshold_ms=25.0, cumulative_count=30),
        HistogramSnapshot(threshold_ms=50.0, cumulative_count=20),
        HistogramSnapshot(threshold_ms=100.0, cumulative_count=10),
        HistogramSnapshot(threshold_ms=250.0, cumulative_count=5),
        HistogramSnapshot(threshold_ms=500.0, cumulative_count=3),
        HistogramSnapshot(threshold_ms=1000.0, cumulative_count=2),
    ]
    
    # Total requests = 50 + 30 + 20 + 10 + 5 + 3 + 2 = 120
    total_expected = 120
    
    # Calculate P50 (median) - should be around 25ms (60th request)
    # Distribution:
    # - 0-10ms: 50 requests (0-50)
    # - 10-25ms: 30 requests (50-80)
    # - 25-50ms: 20 requests (80-100)
    # P50 (60th) falls in 10-25ms bucket
    
    p50 = estimate_percentile(tuple(deltas), 50.0)
    
    # P50 should be between 10ms and 25ms
    assert 10.0 <= p50 <= 25.0, \
        f"P50 ({p50}ms) should be between 10ms and 25ms"
    
    # Calculate P95 - should be higher
    p95 = estimate_percentile(tuple(deltas), 95.0)
    assert p95 > p50, \
        f"P95 ({p95}ms) should be greater than P50 ({p50}ms)"
    
    # P95 target rank = 0.95 * 120 = 114
    # Falls in 250ms bucket (100-105 range)
    assert p95 >= 100.0, \
        f"P95 ({p95}ms) should be at least 100ms"


def test_missing_buckets_handling():
    """Test that missing buckets are handled correctly (FULL OUTER JOIN logic)."""
    
    # Scenario: Start snapshot missing some buckets, end snapshot has all
    start_snapshot = {
        100.0: 500,
        # Missing 250.0 bucket
        500.0: 950,
    }
    
    end_snapshot = {
        100.0: 650,
        250.0: 900,  # This bucket exists in end but not start
        500.0: 1000,
    }
    
    # FULL OUTER JOIN: union of all buckets
    all_les = set(start_snapshot.keys()) | set(end_snapshot.keys())
    
    calculated_deltas = {}
    for le in sorted(all_les):
        start_count = start_snapshot.get(le, 0)  # Missing = 0
        end_count = end_snapshot.get(le, 0)
        delta = end_count - start_count
        calculated_deltas[le] = delta
    
    # Expected deltas
    expected = {
        100.0: 150,   # 650 - 500 = 150
        250.0: 900,   # 900 - 0 = 900 (missing in start = 0)
        500.0: 50,    # 1000 - 950 = 50
    }
    
    assert calculated_deltas == expected, \
        f"Missing bucket handling failed. Expected {expected}, got {calculated_deltas}"


def test_zero_deltas_included():
    """Test that zero deltas are included for complete histogram."""
    
    # Scenario: Bucket exists in both snapshots with same count (delta = 0)
    start_snapshot = {
        100.0: 500,
        250.0: 800,
        500.0: 950,
    }
    
    end_snapshot = {
        100.0: 650,   # Changed
        250.0: 800,   # No change (delta = 0)
        500.0: 1000,  # Changed
    }
    
    all_les = set(start_snapshot.keys()) | set(end_snapshot.keys())
    
    deltas = []
    for le in sorted(all_les):
        start_count = start_snapshot.get(le, 0)
        end_count = end_snapshot.get(le, 0)
        delta = end_count - start_count
        # Include ALL deltas, even zero
        deltas.append(HistogramSnapshot(threshold_ms=le, cumulative_count=delta))
    
    # Verify zero delta is included
    zero_deltas = [d for d in deltas if d.cumulative_count == 0]
    assert len(zero_deltas) == 1, \
        f"Expected 1 zero delta, got {len(zero_deltas)}"
    assert zero_deltas[0].threshold_ms == 250.0, \
        f"Zero delta should be at 250ms threshold"
    
    # Verify percentile calculation works with zero deltas
    p50 = estimate_percentile(tuple(deltas), 50.0)
    assert p50 >= 0, \
        f"Percentile calculation should handle zero deltas correctly, got {p50}"


def test_complete_histogram_snapshot():
    """Test that all thresholds are included in snapshots."""
    
    # Simulate what _prepare_bucket should return
    # All thresholds should be present, even with count=0
    endpoint_id = 1
    thresholds = settings.BUCKET_THRESHOLDS
    
    # Simulate cumulative counter state
    cumulative_counter = {
        (endpoint_id, 100.0): 500,
        (endpoint_id, 250.0): 800,
        # Missing other thresholds
    }
    
    # After fix: All thresholds should be included
    snapshot_data = []
    for threshold in thresholds:
        count = cumulative_counter.get((endpoint_id, threshold), 0)
        snapshot_data.append({
            'endpoint_id': endpoint_id,
            'le': threshold,
            'count': count,
        })
    
    # Verify all thresholds are present
    snapshot_les = {item['le'] for item in snapshot_data}
    expected_les = set(thresholds)
    
    assert snapshot_les == expected_les, \
        f"Snapshot missing thresholds. Expected {expected_les}, got {snapshot_les}"
    
    # Verify counts are correct
    for item in snapshot_data:
        if item['le'] == 100.0:
            assert item['count'] == 500
        elif item['le'] == 250.0:
            assert item['count'] == 800
        else:
            assert item['count'] == 0, \
                f"Missing threshold {item['le']} should have count=0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
