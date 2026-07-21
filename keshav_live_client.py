"""
keshav_live_client.py — Live KESHAV Ecosystem Integration Client

Provides a production-grade HTTP client for the KESHAV API (TANTRA pipeline).
Handles contract analysis, health checks, and metrics retrieval with
structured logging, timeout handling, and graceful fallback.

KESHAV API: https://keshav-cia7.onrender.com
Endpoints:
  POST /analyze       — Root-cause analysis on TANTRA contracts
  GET  /health        — Liveness/readiness check
  GET  /metrics/json  — Prometheus-compatible metrics (JSON)
"""

import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import config

logger = logging.getLogger("qcg.keshav")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KESHAV_API_URL: str = config._str("QCG_KESHAV_API_URL", "https://keshav-cia7.onrender.com")
KESHAV_TIMEOUT: int = config._int("QCG_KESHAV_TIMEOUT_SECONDS", 15)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class KeshavAnalysisRequest:
    """Contract payload sent to KESHAV /analyze endpoint."""
    trace_id: str
    execution_id: str
    tasks: list = field(default_factory=list)
    constraint_results: list = field(default_factory=list)
    propagation_results: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KeshavAnalysisResponse:
    """Parsed response from KESHAV /analyze endpoint."""
    trace_id: str
    execution_id: str
    root_cause: Optional[str]
    resolution_signal: Optional[str]
    impact_score: int
    severity: str
    timestamp: str
    raw_response: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "KeshavAnalysisResponse":
        return cls(
            trace_id=data.get("trace_id", ""),
            execution_id=data.get("execution_id", ""),
            root_cause=data.get("root_cause"),
            resolution_signal=data.get("resolution_signal"),
            impact_score=data.get("impact_score", 0),
            severity=data.get("severity", "UNKNOWN"),
            timestamp=data.get("timestamp", ""),
            raw_response=data,
        )


@dataclass
class KeshavHealthResponse:
    """Parsed response from KESHAV /health endpoint."""
    status: str
    service: str
    raw_response: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "KeshavHealthResponse":
        return cls(
            status=data.get("status", "UNKNOWN"),
            service=data.get("service", "UNKNOWN"),
            raw_response=data,
        )


# ---------------------------------------------------------------------------
# Integration Log — captures all request/response pairs for evidence
# ---------------------------------------------------------------------------

class IntegrationLog:
    """Structured log of all KESHAV API interactions for evidence collection."""

    def __init__(self):
        self.entries: list = []

    def record(self, method: str, endpoint: str, request_body: Optional[dict],
               status_code: int, response_body: Optional[dict],
               latency_ms: float, error: Optional[str] = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "endpoint": endpoint,
            "url": f"{KESHAV_API_URL}{endpoint}",
            "request_body": request_body,
            "status_code": status_code,
            "response_body": response_body,
            "latency_ms": round(latency_ms, 2),
            "error": error,
            "success": error is None and 200 <= status_code < 300,
        }
        self.entries.append(entry)
        logger.info("KESHAV API call: %s %s -> %d (%.1fms)",
                     method, endpoint, status_code, latency_ms)
        return entry

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.entries, indent=indent, default=str)


# ---------------------------------------------------------------------------
# KESHAV Client
# ---------------------------------------------------------------------------

class KeshavClient:
    """
    Production-grade HTTP client for the live KESHAV API.

    Usage:
        client = KeshavClient()

        # Health check
        health = client.health()

        # Analyze a contract
        request = KeshavAnalysisRequest(
            trace_id="qcg-trace-001",
            execution_id="exec-001",
            tasks=[{"task_id": "T1", "depends_on": []}],
            constraint_results=[{"task_id": "T1", "is_valid": True, "unsatisfied_dependencies": []}],
            propagation_results=[{"task_id": "T1", "affected_tasks": [], "impact_score": 5}]
        )
        response = client.analyze(request)
    """

    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = (base_url or KESHAV_API_URL).rstrip("/")
        self.timeout = timeout or KESHAV_TIMEOUT
        self.log = IntegrationLog()
        self._available: Optional[bool] = None

    # -- Core HTTP helper -----------------------------------------------------

    def _request(self, method: str, endpoint: str,
                 body: Optional[dict] = None) -> Tuple[int, dict]:
        """
        Execute an HTTP request against KESHAV.
        Returns (status_code, response_body_dict).
        Raises no exceptions — errors are captured in the integration log.
        """
        url = f"{self.base_url}{endpoint}"
        start = time.monotonic()

        try:
            if method == "POST" and body is not None:
                data = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
            else:
                req = urllib.request.Request(url, method="GET")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                latency = (time.monotonic() - start) * 1000
                response_body = json.loads(resp.read().decode("utf-8"))
                self.log.record(method, endpoint, body, resp.status,
                                response_body, latency)
                return resp.status, response_body

        except urllib.error.HTTPError as e:
            latency = (time.monotonic() - start) * 1000
            try:
                error_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                error_body = {"raw_error": str(e)}
            self.log.record(method, endpoint, body, e.code,
                            error_body, latency, error=str(e))
            return e.code, error_body

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            self.log.record(method, endpoint, body, 0, None, latency,
                            error=str(e))
            return 0, {"error": str(e)}

    # -- Public API -----------------------------------------------------------

    def health(self) -> KeshavHealthResponse:
        """Check KESHAV service health. GET /health"""
        status, body = self._request("GET", "/health")
        if status == 200:
            self._available = True
            return KeshavHealthResponse.from_dict(body)
        self._available = False
        return KeshavHealthResponse(status="UNREACHABLE", service="KESHAV",
                                    raw_response=body)

    def metrics(self) -> dict:
        """Retrieve KESHAV metrics. GET /metrics/json"""
        status, body = self._request("GET", "/metrics/json")
        return body if status == 200 else {"error": "unavailable", "raw": body}

    def analyze(self, request: KeshavAnalysisRequest) -> KeshavAnalysisResponse:
        """
        Submit a contract for KESHAV root-cause analysis.
        POST /analyze
        """
        status, body = self._request("POST", "/analyze", request.to_dict())
        if status == 200:
            return KeshavAnalysisResponse.from_dict(body)
        return KeshavAnalysisResponse(
            trace_id=request.trace_id,
            execution_id=request.execution_id,
            root_cause=None,
            resolution_signal=None,
            impact_score=0,
            severity="ERROR",
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_response=body,
        )

    def is_available(self) -> bool:
        """Check if KESHAV is reachable (caches result of last health check)."""
        if self._available is None:
            self.health()
        return self._available is True

    def analyze_from_contract(self, trace_id: str, execution_id: str,
                              payload: dict) -> KeshavAnalysisResponse:
        """
        Convenience method: build a KeshavAnalysisRequest from QCG contract
        fields and call /analyze.

        Maps QCG contract fields to KESHAV's expected schema:
          - trace_id -> trace_id
          - execution_id -> execution_id (generated if absent)
          - payload tasks -> tasks
        """
        # Build task list from payload content
        tasks = payload.get("tasks", [{"task_id": "QCG_VERIFY", "depends_on": []}])
        constraint_results = payload.get("constraint_results", [
            {"task_id": "QCG_VERIFY", "is_valid": True, "unsatisfied_dependencies": []}
        ])
        propagation_results = payload.get("propagation_results", [
            {"task_id": "QCG_VERIFY", "affected_tasks": [], "impact_score": 0}
        ])

        request = KeshavAnalysisRequest(
            trace_id=trace_id,
            execution_id=execution_id or f"exec-{trace_id}",
            tasks=tasks,
            constraint_results=constraint_results,
            propagation_results=propagation_results,
        )
        return self.analyze(request)

    def get_evidence_log(self) -> str:
        """Return all API interactions as JSON for evidence collection."""
        return self.log.to_json()


# ---------------------------------------------------------------------------
# Module-level singleton for shared use
# ---------------------------------------------------------------------------

_default_client: Optional[KeshavClient] = None


def get_client() -> KeshavClient:
    """Get or create the default KESHAV client singleton."""
    global _default_client
    if _default_client is None:
        _default_client = KeshavClient()
    return _default_client


# ---------------------------------------------------------------------------
# Self-test / Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    client = KeshavClient()
    print("=" * 60)
    print("KESHAV Live Integration Test")
    print(f"Target: {client.base_url}")
    print("=" * 60)

    # 1. Health check
    print("\n--- Health Check ---")
    health = client.health()
    print(f"  Status:  {health.status}")
    print(f"  Service: {health.service}")
    print(f"  Available: {client.is_available()}")

    # 2. Metrics
    print("\n--- Metrics ---")
    metrics = client.metrics()
    print(f"  {json.dumps(metrics, indent=2)}")

    # 3. Analyze with valid contract
    print("\n--- Analyze (valid contract) ---")
    req = KeshavAnalysisRequest(
        trace_id="qcg-live-test-001",
        execution_id="exec-qcg-demo",
        tasks=[{"task_id": "QCG_VERIFY", "depends_on": []}],
        constraint_results=[
            {"task_id": "QCG_VERIFY", "is_valid": True, "unsatisfied_dependencies": []}
        ],
        propagation_results=[
            {"task_id": "QCG_VERIFY", "affected_tasks": [], "impact_score": 3}
        ],
    )
    resp = client.analyze(req)
    print(f"  Trace ID:          {resp.trace_id}")
    print(f"  Root Cause:        {resp.root_cause}")
    print(f"  Resolution Signal: {resp.resolution_signal}")
    print(f"  Impact Score:      {resp.impact_score}")
    print(f"  Severity:          {resp.severity}")
    print(f"  Timestamp:         {resp.timestamp}")

    # 4. Analyze with failure scenario
    print("\n--- Analyze (constraint failure) ---")
    req2 = KeshavAnalysisRequest(
        trace_id="qcg-live-test-002",
        execution_id="exec-qcg-fail",
        tasks=[
            {"task_id": "T1", "depends_on": []},
            {"task_id": "T2", "depends_on": ["T1"]},
        ],
        constraint_results=[
            {"task_id": "T1", "is_valid": False, "unsatisfied_dependencies": []},
            {"task_id": "T2", "is_valid": False, "unsatisfied_dependencies": ["T1"]},
        ],
        propagation_results=[
            {"task_id": "T1", "affected_tasks": ["T2"], "impact_score": 8},
            {"task_id": "T2", "affected_tasks": [], "impact_score": 3},
        ],
    )
    resp2 = client.analyze(req2)
    print(f"  Trace ID:          {resp2.trace_id}")
    print(f"  Root Cause:        {resp2.root_cause}")
    print(f"  Resolution Signal: {resp2.resolution_signal}")
    print(f"  Impact Score:      {resp2.impact_score}")
    print(f"  Severity:          {resp2.severity}")

    # 5. Print evidence log
    print("\n--- Integration Evidence Log ---")
    print(client.get_evidence_log())

    print("\n" + "=" * 60)
    print("KESHAV integration test complete.")
    print("=" * 60)
