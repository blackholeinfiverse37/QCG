"""
audit_trail.py -- Merkle Audit Trail

A tamper-evident, append-only event log backed by an incremental Merkle tree.
Any insertion, deletion, or reordering of events is cryptographically detectable.

This is the "air traffic control logbook" of the trust layer: once an event
is recorded, its position in the tree is permanently anchored by the root hash.

Design Notes
------------
- Each AuditEntry has a deterministic sequence number assigned at append time.
- The Merkle tree is rebuilt incrementally on each append (acceptable for
  simulation-scale volumes; a production system would use a persistent tree).
- verify_inclusion() uses an O(log N) Merkle proof path.
- verify_integrity() performs a full chain walk to detect any gap or mutation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Merkle helpers
# ---------------------------------------------------------------------------

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _merkle_parent(left: str, right: str) -> str:
    """Deterministic parent hash from two children."""
    return _sha256(left + right)


def _build_merkle_tree(leaves: list[str]) -> list[list[str]]:
    """
    Build a full Merkle tree from leaf hashes.
    Returns list-of-levels where [0] = leaves, [-1] = [root].
    Empty leaves → empty tree.
    """
    if not leaves:
        return []

    # Duplicate last leaf if odd count (standard Merkle padding)
    working = list(leaves)
    levels = [working]

    while len(working) > 1:
        if len(working) % 2 == 1:
            working.append(working[-1])
        next_level = []
        for i in range(0, len(working), 2):
            next_level.append(_merkle_parent(working[i], working[i + 1]))
        working = next_level
        levels.append(working)

    return levels


def _merkle_proof(tree: list[list[str]], leaf_index: int) -> list[tuple[str, str]]:
    """
    Generate a Merkle inclusion proof for the leaf at `leaf_index`.
    Returns list of (sibling_hash, side) where side is 'L' or 'R'.
    """
    if not tree or leaf_index < 0 or leaf_index >= len(tree[0]):
        return []

    proof = []
    idx = leaf_index
    for level in tree[:-1]:  # skip root level
        # Pad level if odd
        padded = list(level)
        if len(padded) % 2 == 1:
            padded.append(padded[-1])

        if idx % 2 == 0:
            sibling_idx = idx + 1
            side = "R"  # sibling is on the right
        else:
            sibling_idx = idx - 1
            side = "L"  # sibling is on the left

        proof.append((padded[sibling_idx], side))
        idx = idx // 2

    return proof


def _verify_merkle_proof(
    leaf_hash: str,
    proof: list[tuple[str, str]],
    expected_root: str,
) -> bool:
    """Verify a Merkle inclusion proof against an expected root."""
    current = leaf_hash
    for sibling_hash, side in proof:
        if side == "R":
            current = _merkle_parent(current, sibling_hash)
        else:
            current = _merkle_parent(sibling_hash, current)
    return current == expected_root


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEntry:
    """A single event in the append-only audit trail."""
    sequence: int
    event_type: str           # e.g. "CONTRACT_SIGNED", "CONSENSUS_REACHED"
    event_hash: str           # SHA-256 of the canonical event data
    node_id: str              # which node produced this event
    event_data: dict          # the raw event payload (for reconstruction)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def leaf_hash(self) -> str:
        """Deterministic leaf hash for Merkle tree insertion."""
        canonical = json.dumps({
            "sequence": self.sequence,
            "event_type": self.event_type,
            "event_hash": self.event_hash,
            "node_id": self.node_id,
        }, sort_keys=True)
        return _sha256(canonical)


# ---------------------------------------------------------------------------
# MerkleAuditTrail
# ---------------------------------------------------------------------------

class MerkleAuditTrail:
    """
    Append-only audit log backed by a Merkle tree.

    Once an event is appended, its position is anchored by the root hash.
    Any future tampering (edit, delete, reorder) changes the root.
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []
        self._tree: list[list[str]] = []

    def append(self, event_type: str, event_data: dict, node_id: str) -> AuditEntry:
        """Append an event and rebuild the Merkle tree."""
        event_hash = _sha256(json.dumps(event_data, sort_keys=True, default=str))
        entry = AuditEntry(
            sequence=len(self._entries),
            event_type=event_type,
            event_hash=event_hash,
            node_id=node_id,
            event_data=event_data,
        )
        self._entries.append(entry)
        self._rebuild_tree()
        return entry

    def root_hash(self) -> str:
        """Current Merkle root. Empty string if no entries."""
        if not self._tree:
            return ""
        return self._tree[-1][0]

    def verify_inclusion(self, entry: AuditEntry) -> bool:
        """Prove that a specific entry is in the audit trail."""
        if entry.sequence < 0 or entry.sequence >= len(self._entries):
            return False

        # Check the entry matches what we have stored
        stored = self._entries[entry.sequence]
        if stored.leaf_hash != entry.leaf_hash:
            return False

        proof = _merkle_proof(self._tree, entry.sequence)
        return _verify_merkle_proof(entry.leaf_hash, proof, self.root_hash())

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """
        Full chain walk. Verify:
        1. Sequence numbers are contiguous (0..N-1).
        2. Rebuilding the tree from stored entries yields the same root.
        3. No duplicate sequence numbers.

        Returns (passed, list_of_errors).
        """
        errors = []

        if not self._entries:
            return True, []

        # Check contiguous sequence
        for i, entry in enumerate(self._entries):
            if entry.sequence != i:
                errors.append(f"Gap at index {i}: expected seq={i}, got seq={entry.sequence}")

        # Check for duplicates
        seqs = [e.sequence for e in self._entries]
        if len(seqs) != len(set(seqs)):
            errors.append("Duplicate sequence numbers detected")

        # Rebuild tree and compare root
        leaves = [e.leaf_hash for e in self._entries]
        rebuilt = _build_merkle_tree(leaves)
        if rebuilt:
            rebuilt_root = rebuilt[-1][0]
            if rebuilt_root != self.root_hash():
                errors.append(
                    f"Root mismatch: stored={self.root_hash()[:16]}... "
                    f"rebuilt={rebuilt_root[:16]}..."
                )

        return len(errors) == 0, errors

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # -- internal -----------------------------------------------------------

    def _rebuild_tree(self):
        # O(log N) incremental Merkle tree update
        if not self._tree:
            self._tree = [[self._entries[-1].leaf_hash]]
            return

        leaf_hash = self._entries[-1].leaf_hash
        old_count = len(self._entries) - 1
        
        # Remove padding from each level to prepare for append
        count = old_count
        for level in self._tree:
            if count % 2 == 1 and len(level) > count:
                level.pop()
            count = (count + 1) // 2
            
        # Append the new leaf
        self._tree[0].append(leaf_hash)
        
        # Update path to root
        for i in range(len(self._tree) - 1):
            level = self._tree[i]
            if len(level) % 2 == 1:
                level.append(level[-1])
            
            parent_idx = len(level) // 2 - 1
            new_parent = _merkle_parent(level[-2], level[-1])
            
            next_level = self._tree[i+1]
            if parent_idx < len(next_level):
                next_level[parent_idx] = new_parent
            else:
                next_level.append(new_parent)
                
        # Add new root levels if necessary
        top_level = self._tree[-1]
        while len(top_level) > 1:
            if len(top_level) % 2 == 1:
                top_level.append(top_level[-1])
            new_root = _merkle_parent(top_level[-2], top_level[-1])
            self._tree.append([new_root])
            top_level = self._tree[-1]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== MERKLE AUDIT TRAIL DEMO ===\n")

    trail = MerkleAuditTrail()

    # 1. Append 10 events
    print("[1] Appending 10 events...")
    entries = []
    for i in range(10):
        e = trail.append(
            event_type="CONTRACT_EXECUTED",
            event_data={"trace_id": f"tr-{i:03d}", "ack": "ACK:OK"},
            node_id=f"NODE_{i % 3}",
        )
        entries.append(e)
    print(f"    Root hash: {trail.root_hash()[:32]}...")
    print(f"    Entries  : {len(trail)}")

    # 2. Verify inclusion of entry #5
    print(f"\n[2] Verify inclusion of entry #5...")
    ok = trail.verify_inclusion(entries[5])
    print(f"    Result: {'INCLUDED' if ok else 'NOT FOUND'}")

    # 3. Verify inclusion of a fabricated entry
    print(f"\n[3] Verify fabricated entry...")
    fake = AuditEntry(
        sequence=5,
        event_type="FAKE_EVENT",
        event_hash="0" * 64,
        node_id="ATTACKER",
        event_data={},
    )
    ok_fake = trail.verify_inclusion(fake)
    print(f"    Result: {'INCLUDED' if ok_fake else 'REJECTED'}")

    # 4. Full integrity check
    print(f"\n[4] Full integrity check...")
    passed, errs = trail.verify_integrity()
    print(f"    Passed: {passed}")

    # 5. Tamper and detect
    print(f"\n[5] Tampering with internal entry (mutating sequence)...")
    # Direct mutation of internal state to simulate tampering
    original = trail._entries[3]
    tampered = AuditEntry(
        sequence=3,
        event_type="TAMPERED_EVENT",
        event_hash="bad" * 21 + "b",
        node_id="ATTACKER",
        event_data={"malicious": True},
    )
    trail._entries[3] = tampered
    passed_t, errs_t = trail.verify_integrity()
    print(f"    Integrity after tamper: {passed_t}")
    if errs_t:
        for err in errs_t:
            print(f"    Error: {err}")
    # Restore
    trail._entries[3] = original

    print("\n[DONE] Merkle Audit Trail demo complete.")
