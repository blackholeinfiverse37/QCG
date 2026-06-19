"""
canonical_replay_proof.py — Phase 6: Canonical Replay Authority Proof Suite

Proves all required properties of CanonicalReplayAuthority:
  1. Duplicate Detection
  2. Stale Detection
  3. Restart Persistence
  4. Sequence Monotonicity
  5. Concurrent Access
  6. Lineage Reconstruction
  7. Authority Exclusivity

Expected output: CANONICAL REPLAY PROOF — PASS
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from replay_registry import ReplayRegistry
from canonical_replay_authority import CanonicalReplayAuthority, ReplayLineageRecord


def _authority(ttl: float = 300.0) -> tuple[CanonicalReplayAuthority, Path]:
    path = Path(tempfile.mktemp(suffix=".json"))
    reg = ReplayRegistry(path=path, ttl_seconds=ttl)
    return CanonicalReplayAuthority(reg), path


def _cleanup(path: Path) -> None:
    if path.exists():
        path.unlink()
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()


# ---------------------------------------------------------------------------
# Proof 1 — Duplicate Detection
# ---------------------------------------------------------------------------

def proof_duplicate_detection() -> bool:
    auth, path = _authority()
    try:
        v1 = auth.submit("dup-proof-001")
        v2 = auth.submit("dup-proof-001")
        assert v1.status == "VALID",     f"expected VALID, got {v1.status}"
        assert v2.status == "DUPLICATE", f"expected DUPLICATE, got {v2.status}"
        assert v2.sequence_number == v1.sequence_number, "duplicate must return original sequence"
        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 2 — Stale Detection
# ---------------------------------------------------------------------------

def proof_stale_detection() -> bool:
    auth, path = _authority(ttl=5.0)
    try:
        old_issued_at = time.time() - 100.0  # well outside TTL
        v = auth.submit("stale-proof-001", issued_at=old_issued_at)
        assert v.status == "STALE", f"expected STALE, got {v.status}"
        assert v.sequence_number == 0, "stale must not assign sequence"
        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 3 — Restart Persistence
# ---------------------------------------------------------------------------

def proof_restart_persistence() -> bool:
    path = Path(tempfile.mktemp(suffix="_persist.json"))
    try:
        # Session 1: submit a valid message
        reg1 = ReplayRegistry(path=path, ttl_seconds=300.0)
        auth1 = CanonicalReplayAuthority(reg1)
        v1 = auth1.submit("persist-proof-001")
        assert v1.status == "VALID", f"session1: expected VALID, got {v1.status}"
        seq_before = v1.sequence_number

        # Session 2: new instance, same file — must detect duplicate
        reg2 = ReplayRegistry(path=path, ttl_seconds=300.0)
        auth2 = CanonicalReplayAuthority(reg2)
        v2 = auth2.submit("persist-proof-001")
        assert v2.status == "DUPLICATE", f"session2: expected DUPLICATE, got {v2.status}"

        # Session 2: new message must get next sequence
        v3 = auth2.submit("persist-proof-002")
        assert v3.status == "VALID", f"session2: expected VALID for new msg, got {v3.status}"
        assert v3.sequence_number == seq_before + 1, \
            f"sequence must continue from {seq_before + 1}, got {v3.sequence_number}"
        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 4 — Sequence Monotonicity
# ---------------------------------------------------------------------------

def proof_sequence_monotonicity() -> bool:
    auth, path = _authority()
    try:
        seqs = []
        for i in range(10):
            v = auth.submit(f"mono-proof-{i:03d}")
            assert v.status == "VALID"
            seqs.append(v.sequence_number)
        assert seqs == sorted(seqs),  f"sequences not monotonic: {seqs}"
        assert seqs == list(range(1, 11)), f"sequences not 1..10: {seqs}"
        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 5 — Concurrent Access
# ---------------------------------------------------------------------------

def proof_concurrent_access() -> bool:
    path = Path(tempfile.mktemp(suffix="_conc.json"))
    try:
        reg = ReplayRegistry(path=path, ttl_seconds=300.0)
        auth = CanonicalReplayAuthority(reg)
        results: list = []
        lock = threading.Lock()

        def submit(i: int) -> None:
            v = auth.submit(f"conc-proof-{i:04d}")
            with lock:
                results.append(v)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 30
        assert all(r.status == "VALID" for r in results), \
            f"not all VALID: {[r.status for r in results if r.status != 'VALID']}"
        seqs = sorted(r.sequence_number for r in results)
        assert seqs == list(range(1, 31)), f"sequences not 1..30: {seqs}"
        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 6 — Lineage Reconstruction
# ---------------------------------------------------------------------------

def proof_lineage_reconstruction() -> bool:
    auth, path = _authority()
    try:
        ids = [f"lineage-proof-{i:03d}" for i in range(5)]
        for mid in ids:
            auth.submit(mid)
        # submit a duplicate — must NOT appear in lineage
        auth.submit(ids[0])

        lineage = auth.lineage()
        assert len(lineage) == 5, f"expected 5 lineage records, got {len(lineage)}"

        # All required fields present on every record
        required = {
            "replay_id", "message_id", "sequence_number", "decision",
            "decision_timestamp", "origin_component", "schema_version",
            "trace_reference", "parent_reference", "verification_hash",
        }
        for rec in lineage:
            assert isinstance(rec, ReplayLineageRecord)
            d = rec.to_dict()
            missing = required - d.keys()
            assert not missing, f"missing fields: {missing}"
            assert rec.decision == "VALID"
            assert rec.origin_component == "CanonicalReplayAuthority"

        # Sequence order preserved
        seqs = [r.sequence_number for r in lineage]
        assert seqs == sorted(seqs), f"lineage not in sequence order: {seqs}"

        # Parent reference chain is correct
        for rec in lineage:
            if rec.sequence_number > 1:
                assert rec.parent_reference == str(rec.sequence_number - 1), \
                    f"bad parent_reference on seq {rec.sequence_number}"
            else:
                assert rec.parent_reference == "", "seq=1 must have empty parent_reference"

        # verification_hash is a 64-char hex string
        for rec in lineage:
            assert len(rec.verification_hash) == 64
            int(rec.verification_hash, 16)  # must be valid hex

        return True
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Proof 7 — Authority Exclusivity
# ---------------------------------------------------------------------------

def proof_authority_exclusivity() -> bool:
    """
    Structural proof: components that previously owned replay authority no
    longer contain independent replay-decision code.

    Uses raw source-file reads to avoid importing modules with heavy
    optional dependencies (e.g. qiskit).

    Checks:
    - RuntimeCore.execute() source has no _replay_registry, no HALT:REPLAY_DETECTED
    - Receiver.__init__ has no _seen dict
    - QuantumGateway.__init__ has no _replay_registry dict
    - execution_process.run() delegates to CanonicalReplayAuthority, not ReplayEnforcer
    """
    import ast
    import pathlib

    base = pathlib.Path(__file__).parent

    def _src(filename: str) -> str:
        return (base / filename).read_text(encoding="utf-8")

    def _method_src(filename: str, class_name: str, method_name: str) -> str:
        """Extract source of a specific method via AST without importing."""
        src = _src(filename)
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and item.name == method_name:
                        start = item.lineno - 1
                        end = item.end_lineno
                        return "\n".join(lines[start:end])
        raise ValueError(f"{class_name}.{method_name} not found in {filename}")

    # RuntimeCore.execute must not own replay state
    execute_src = _method_src("runtime_core.py", "RuntimeCore", "execute")
    assert "_replay_registry" not in execute_src, \
        "RuntimeCore.execute must not own _replay_registry"
    assert "HALT:REPLAY_DETECTED" not in execute_src, \
        "RuntimeCore.execute must not emit HALT:REPLAY_DETECTED"

    # Receiver.__init__ must not own a _seen set/dict
    receiver_init_src = _method_src("gateway.py", "Receiver", "__init__")
    assert "_seen" not in receiver_init_src, \
        "Receiver.__init__ must not own _seen state"

    # QuantumGateway.__init__ must not own _replay_registry
    gw_init_src = _method_src("hybrid_gateway.py", "QuantumGateway", "__init__")
    assert "_replay_registry" not in gw_init_src, \
        "QuantumGateway.__init__ must not own _replay_registry"

    # execution_process.run must delegate to CanonicalReplayAuthority
    run_src = _src("execution_process.py")
    assert "CanonicalReplayAuthority" in run_src, \
        "execution_process.run must use CanonicalReplayAuthority"
    assert "ReplayEnforcer" not in run_src, \
        "execution_process.run must not use deprecated ReplayEnforcer directly"

    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

PROOFS = [
    ("Duplicate Detection",    proof_duplicate_detection),
    ("Stale Detection",        proof_stale_detection),
    ("Restart Persistence",    proof_restart_persistence),
    ("Sequence Monotonicity",  proof_sequence_monotonicity),
    ("Concurrent Access",      proof_concurrent_access),
    ("Lineage Reconstruction", proof_lineage_reconstruction),
    ("Authority Exclusivity",  proof_authority_exclusivity),
]


def run_proof(verbose: bool = True) -> dict:
    cases: dict[str, bool] = {}
    for name, fn in PROOFS:
        try:
            result = fn()
            cases[name] = result
            if verbose:
                print(f"  [PASS] {name}")
        except Exception as exc:
            cases[name] = False
            if verbose:
                print(f"  [FAIL] {name}: {exc}")

    passed = all(cases.values())
    if verbose:
        print()
        status = "PASS" if passed else "FAIL"
        print(f"CANONICAL REPLAY PROOF — {status}")
    return {"passed": passed, "cases": cases}


if __name__ == "__main__":
    import sys
    result = run_proof(verbose=True)
    sys.exit(0 if result["passed"] else 1)
