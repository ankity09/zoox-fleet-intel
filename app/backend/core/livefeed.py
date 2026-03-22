"""
Generic live feed simulation engine for real-time streaming demos.

Provides an async background task that periodically inserts synthetic data
into Delta Lake tables via the Statement Execution API. Domain-specific
value generators are injected by the demo's main.py — the engine itself
is completely domain-agnostic.

Architecture:
    LiveFeedEngine runs a single asyncio background task that ticks once
    per second. Each tick, it checks which streams are due (based on their
    cadence), generates rows for every configured entity, batches them into
    INSERT statements, and executes them via the injected run_query function.

    The engine tracks per-stream statistics (rows inserted, errors, last
    insert time) and exposes a status endpoint for the frontend to poll.

Usage in main.py:
    from backend.core.livefeed import LiveFeedEngine, StreamConfig, EntityConfig

    engine = LiveFeedEngine(
        run_query_fn=run_query,
        catalog="my_catalog",
        schema="my_schema",
    )

    # Define domain-specific generators
    def gps_generator(entity, progress, elapsed, scenario):
        lat, lon = geo_interpolate(entity.origin, entity.destination, progress)
        return {"vehicle_id": entity.entity_id, "latitude": lat, "longitude": lon, ...}

    engine.configure(
        streams=[
            StreamConfig(name="gps", table="fleet_gps_pings", cadence_seconds=10, generator=gps_generator),
            StreamConfig(name="telemetry", table="sensor_readings", cadence_seconds=30, generator=telemetry_gen),
        ],
        entities=[
            EntityConfig(entity_id="VEH-001", origin=(43.66, -116.69), destination=(45.52, -122.68), scenario="normal"),
            EntityConfig(entity_id="VEH-002", origin=(43.66, -116.69), destination=(41.88, -87.63), scenario="fault"),
        ],
    )

    # Mount the convenience router
    from backend.core.livefeed import create_streaming_router
    app.include_router(create_streaming_router(engine))

    # Or control manually
    await engine.start(duration=300)
    await engine.stop()
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter

log = logging.getLogger("livefeed")


# ─── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class StreamConfig:
    """Configuration for a single data stream (maps to one Delta table).

    Attributes:
        name:            Stream identifier used in stats and logs.
        table:           Delta table name (without catalog/schema prefix).
        cadence_seconds: How often to insert rows (10, 30, 60, etc.).
        generator:       Callable(entity, progress, elapsed, scenario) -> dict
                         of column_name: sql_literal_string. The engine wraps
                         values into an INSERT statement — the generator only
                         needs to return the column map.
        columns:         Ordered list of column names for the INSERT. If None,
                         the engine uses dict key order from the first generator
                         call (stable in Python 3.7+).
        batch_size:      Max entities per INSERT statement. Large entity lists
                         are chunked into multiple INSERTs of this size.
        enabled:         Set False to skip this stream without removing it.
    """

    name: str
    table: str
    cadence_seconds: int
    generator: Callable[["EntityConfig", float, float, str], Dict[str, str]]
    columns: Optional[List[str]] = None
    batch_size: int = 50
    enabled: bool = True


@dataclass
class EntityConfig:
    """Configuration for a single simulated entity (vehicle, sensor, asset, etc.).

    Attributes:
        entity_id:   Unique identifier (e.g. "VEH-001", "SENSOR-A1").
        origin:      Starting lat/lon for geo entities. None for non-geo.
        destination: Ending lat/lon for geo entities. None for non-geo.
        scenario:    Behavior profile: "normal", "fault", "warning", "deviation",
                     or any custom string the generator understands.
        metadata:    Arbitrary extra data the generator can read (e.g. carrier
                     name, is_refrigerated, route_id).
    """

    entity_id: str
    origin: Optional[Tuple[float, float]] = None
    destination: Optional[Tuple[float, float]] = None
    scenario: str = "normal"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Geo Helpers ─────────────────────────────────────────────────────────────


def geo_interpolate(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    progress: float,
    jitter: float = 0.002,
) -> Tuple[float, float]:
    """Linear lat/lon interpolation with small random jitter.

    Args:
        origin:      (lat, lon) start point.
        destination: (lat, lon) end point.
        progress:    0.0 to 1.0 fraction of the journey.
        jitter:      Max random offset in degrees (~220m at equator per 0.002).

    Returns:
        (lat, lon) tuple at the interpolated position.
    """
    p = max(0.0, min(1.0, progress))
    lat = origin[0] + (destination[0] - origin[0]) * p
    lon = origin[1] + (destination[1] - origin[1]) * p
    lat += random.uniform(-jitter, jitter)
    lon += random.uniform(-jitter, jitter)
    return (round(lat, 6), round(lon, 6))


def geo_heading(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> float:
    """Approximate compass heading from origin to destination (degrees 0-360).

    Uses simple atan2 on lat/lon deltas — accurate enough for demo purposes.
    """
    dlat = destination[0] - origin[0]
    dlon = destination[1] - origin[1]
    heading = math.degrees(math.atan2(dlon, dlat)) % 360
    return round(heading, 1)


# ─── Scenario Modifier ──────────────────────────────────────────────────────


def scenario_modifier(
    scenario: str,
    progress: float,
    base_value: float,
    value_range: Tuple[float, float] = (-2.0, 2.0),
    fault_spike: float = 3.0,
    deviation_step: float = 2.0,
    seed: Optional[int] = None,
) -> float:
    """Apply scenario-specific modification to a base sensor value.

    This is a convenience helper that generators can use to add realistic
    behavior profiles without writing custom math for each scenario.

    Args:
        scenario:       One of "normal", "fault", "warning", "deviation".
        progress:       0.0 to 1.0 journey/simulation progress.
        base_value:     The nominal/expected value.
        value_range:    (min_offset, max_offset) for normal random variation.
        fault_spike:    Multiplier for the spike amplitude in fault scenario.
        deviation_step: Multiplier for the step change in deviation scenario.
        seed:           Optional seed for deterministic deviation trigger point.

    Returns:
        Modified value as float.

    Scenarios:
        normal:    Small random variation within value_range.
        fault:     Gradual drift (0-60% progress), then sharp spike (>60%).
        warning:   Oscillation near the upper bound of value_range.
        deviation: Sudden step change at a pseudo-random progress point.
        (unknown): Falls back to normal behavior.
    """
    lo, hi = value_range

    if scenario == "fault":
        if progress < 0.6:
            # Gradual upward drift
            drift = (hi - lo) * 0.5 * (progress / 0.6)
            return base_value + drift + random.uniform(lo * 0.3, hi * 0.3)
        else:
            # Sharp spike
            spike_intensity = (progress - 0.6) / 0.4  # 0->1 over last 40%
            return base_value + hi * fault_spike * spike_intensity + random.uniform(-0.5, 0.5)

    if scenario == "warning":
        # Oscillation near the high end of the range
        wave = math.sin(progress * math.pi * 8) * (hi * 0.6)
        return base_value + hi * 0.7 + wave

    if scenario == "deviation":
        # Sudden step change at a deterministic point
        rng = random.Random(seed if seed is not None else hash(scenario))
        trigger = rng.uniform(0.25, 0.55)
        if progress > trigger:
            return base_value + hi * deviation_step + random.uniform(-0.3, 0.3)
        return base_value + random.uniform(lo * 0.3, hi * 0.3)

    # "normal" or any unrecognized scenario
    return base_value + random.uniform(lo, hi)


# ─── Live Feed Engine ────────────────────────────────────────────────────────


class LiveFeedEngine:
    """Async background engine that inserts synthetic data into Delta Lake tables.

    The engine is stateful but not started until ``start()`` is called.
    Only one feed can run at a time — calling ``start()`` while running
    returns immediately with an "already_running" status.

    Args:
        run_query_fn: Synchronous function(sql: str) -> Any. Typically
                      ``backend.core.lakehouse.run_query``.
        catalog:      Unity Catalog catalog name.
        schema:       Unity Catalog schema name.
    """

    def __init__(
        self,
        run_query_fn: Callable[[str], Any],
        catalog: str,
        schema: str,
    ) -> None:
        self._run_query = run_query_fn
        self._catalog = catalog
        self._schema = schema

        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._start_time: Optional[float] = None
        self._duration: int = 0
        self._tick: int = 0

        self._streams: List[StreamConfig] = []
        self._entities: List[EntityConfig] = []

        self._stats: Dict[str, Dict[str, Any]] = {}

    # ── Configuration ────────────────────────────────────────────────────

    def configure(
        self,
        streams: List[StreamConfig],
        entities: List[EntityConfig],
    ) -> None:
        """Set up streams and entities. Can be called while stopped to reconfigure.

        Raises RuntimeError if called while the feed is running.
        """
        if self._running:
            raise RuntimeError("Cannot reconfigure while feed is running. Stop first.")
        self._streams = list(streams)
        self._entities = list(entities)
        self._stats = {
            s.name: {"rows_inserted": 0, "errors": 0, "last_insert": None}
            for s in streams
        }
        log.info(
            "LiveFeedEngine configured: %d streams, %d entities",
            len(self._streams),
            len(self._entities),
        )

    # ── Control ──────────────────────────────────────────────────────────

    async def start(self, duration: int = 300) -> Dict[str, Any]:
        """Launch the background feed task.

        Args:
            duration: How many seconds to run before auto-stopping.

        Returns:
            Status dict: {"status": "started"|"already_running", ...}
        """
        if self._running:
            elapsed = time.time() - (self._start_time or time.time())
            return {
                "status": "already_running",
                "elapsed": round(elapsed, 1),
                "duration": self._duration,
            }

        if not self._streams:
            return {"status": "error", "message": "No streams configured. Call configure() first."}

        if not self._entities:
            return {"status": "error", "message": "No entities configured. Call configure() first."}

        self._duration = duration
        self._start_time = time.time()
        self._tick = 0
        # Reset stats
        for s in self._streams:
            self._stats[s.name] = {"rows_inserted": 0, "errors": 0, "last_insert": None}

        self._task = asyncio.create_task(self._run_feed(duration))
        return {"status": "started", "duration": duration, "streams": len(self._streams), "entities": len(self._entities)}

    async def stop(self) -> Dict[str, Any]:
        """Stop the feed gracefully.

        Returns:
            Status dict: {"status": "stopping"|"not_running"}
        """
        if not self._running:
            return {"status": "not_running"}
        self._running = False
        if self._task and not self._task.done():
            # Give the loop one tick to notice _running=False
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                log.warning("Live feed task did not stop within 5s; cancelled.")
        return {"status": "stopped", "stats": dict(self._stats)}

    def status(self) -> Dict[str, Any]:
        """Return current engine state (synchronous — safe to call from any context).

        Returns:
            Dict with running, elapsed_seconds, duration, progress, tick, stats.
        """
        if not self._running or self._start_time is None:
            return {
                "running": False,
                "elapsed_seconds": 0.0,
                "duration": self._duration,
                "progress": 0.0,
                "tick": 0,
                "stats": dict(self._stats),
            }
        elapsed = time.time() - self._start_time
        return {
            "running": True,
            "elapsed_seconds": round(elapsed, 1),
            "duration": self._duration,
            "progress": round(min(elapsed / self._duration, 1.0), 4) if self._duration > 0 else 0.0,
            "tick": self._tick,
            "stats": dict(self._stats),
        }

    # ── Main Loop ────────────────────────────────────────────────────────

    async def _run_feed(self, duration: int) -> None:
        """Main feed loop — runs as a background asyncio task.

        Ticks once per second. Each tick:
        1. Compute elapsed time and progress (0.0 -> 1.0).
        2. For each enabled stream whose cadence aligns with this tick:
           a. For each entity, call the stream's generator.
           b. Batch the results into INSERT statements.
           c. Execute via run_query (wrapped in asyncio.to_thread).
        3. Update per-stream stats.
        4. Stop when elapsed >= duration or _running is set to False.
        """
        self._running = True
        start = time.time()
        log.info("Live feed started — duration=%ds, streams=%d, entities=%d", duration, len(self._streams), len(self._entities))

        try:
            while self._running and (time.time() - start) < duration:
                elapsed = time.time() - start
                progress = min(elapsed / duration, 1.0) if duration > 0 else 0.0

                # Determine which streams fire this tick
                active_streams = [
                    s for s in self._streams
                    if s.enabled and self._tick % s.cadence_seconds == 0
                ]

                # Fire all active streams concurrently
                if active_streams:
                    coros = [
                        self._insert_stream(stream, progress, elapsed)
                        for stream in active_streams
                    ]
                    await asyncio.gather(*coros, return_exceptions=True)

                self._tick += 1
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            log.info("Live feed task cancelled.")
        except Exception as e:
            log.error("Live feed unexpected error: %s", e, exc_info=True)
        finally:
            self._running = False
            total_elapsed = time.time() - start
            total_rows = sum(s["rows_inserted"] for s in self._stats.values())
            total_errors = sum(s["errors"] for s in self._stats.values())
            log.info(
                "Live feed stopped after %.0fs — %d rows inserted, %d errors",
                total_elapsed,
                total_rows,
                total_errors,
            )

    async def _insert_stream(
        self,
        stream: StreamConfig,
        progress: float,
        elapsed: float,
    ) -> None:
        """Generate and insert rows for one stream across all entities.

        Batches entities into groups of stream.batch_size for efficient INSERTs.
        """
        values_list: List[str] = []
        columns: Optional[List[str]] = stream.columns

        for entity in self._entities:
            try:
                row = stream.generator(entity, progress, elapsed, entity.scenario)
                if row is None:
                    continue  # Generator can skip entities by returning None

                # Discover column order from first non-None row
                if columns is None:
                    columns = list(row.keys())

                # Build VALUES tuple — generator returns sql-literal strings
                vals = ", ".join(str(row.get(c, "NULL")) for c in columns)
                values_list.append(f"({vals})")

            except Exception as e:
                log.warning(
                    "Generator error: stream=%s entity=%s error=%s",
                    stream.name,
                    entity.entity_id,
                    e,
                )
                self._stats[stream.name]["errors"] += 1

        if not values_list or columns is None:
            return

        # Chunk into batches
        fqn = f"{self._catalog}.{self._schema}.{stream.table}"
        col_clause = ", ".join(columns)

        for i in range(0, len(values_list), stream.batch_size):
            batch = values_list[i : i + stream.batch_size]
            sql = f"INSERT INTO {fqn} ({col_clause}) VALUES {', '.join(batch)}"

            try:
                await asyncio.to_thread(self._run_query, sql)
                self._stats[stream.name]["rows_inserted"] += len(batch)
                self._stats[stream.name]["last_insert"] = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                log.warning("Insert error: stream=%s batch_size=%d error=%s", stream.name, len(batch), e)
                self._stats[stream.name]["errors"] += 1


# ─── FastAPI Router Factory ─────────────────────────────────────────────────


def create_streaming_router(
    engine: LiveFeedEngine,
    prefix: str = "/streaming",
    tags: Optional[List[str]] = None,
) -> APIRouter:
    """Create a FastAPI router with standard live feed control endpoints.

    Mounts four endpoints under the given prefix:
        POST {prefix}/start-live-feed  — Start the feed (body: {"duration": 300})
        POST {prefix}/stop-live-feed   — Stop the feed
        GET  {prefix}/live-feed-status — Current running state + progress
        GET  {prefix}/stats            — Per-stream insertion statistics

    Args:
        engine: The LiveFeedEngine instance to control.
        prefix: URL prefix for all endpoints (default "/streaming").
        tags:   OpenAPI tags (default ["streaming"]).

    Returns:
        FastAPI APIRouter ready to include in your app.

    Usage:
        from backend.core.livefeed import LiveFeedEngine, create_streaming_router

        engine = LiveFeedEngine(run_query_fn=run_query, catalog=CATALOG, schema=SCHEMA)
        engine.configure(streams=[...], entities=[...])
        app.include_router(create_streaming_router(engine, prefix="/api/fleet"))
    """
    router = APIRouter(prefix=prefix, tags=tags or ["streaming"])

    @router.post("/start-live-feed")
    async def start_feed(duration: int = 300):
        """Start the live feed simulation.

        Args:
            duration: Seconds to run before auto-stopping (default 300).
        """
        return await engine.start(duration=duration)

    @router.post("/stop-live-feed")
    async def stop_feed():
        """Stop the live feed simulation gracefully."""
        return await engine.stop()

    @router.get("/live-feed-status")
    async def feed_status():
        """Get current feed state: running, elapsed, progress, tick count."""
        return engine.status()

    @router.get("/stats")
    async def feed_stats():
        """Get per-stream statistics: rows inserted, errors, last insert time."""
        return {
            "running": engine._running,
            "streams": dict(engine._stats),
        }

    return router
