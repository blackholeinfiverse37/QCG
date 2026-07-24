"""
platform_lifecycle_manager.py — Platform Service Lifecycle State Machine

Manages the lifecycle of Platform Services with replay-safe evidence
for every state transition.

Lifecycle States:
    DRAFT → ACTIVE → DEPRECATED → RETIRED

Overlay States (orthogonal):
    ENABLED / DISABLED  (only meaningful when status == ACTIVE)

Every transition generates:
    - Transition type, timestamp, before/after states
    - Actor identity and reason
    - SHA-256 hash chain linking to previous evidence

RESPONSIBILITY BOUNDARY
-----------------------
LifecycleManager OWNS:
    - State transition validation
    - Transition evidence generation
    - State machine enforcement

LifecycleManager does NOT OWN:
    - Service registration            → PlatformServiceRegistry
    - Capability publication          → PlatformServiceRegistry
    - Version negotiation             → VersionNegotiator
    - Execution logic                 → RuntimeCore
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Lifecycle constants
# ---------------------------------------------------------------------------

LIFECYCLE_STATES = {"DRAFT", "ACTIVE", "DEPRECATED", "RETIRED"}

# Valid state transitions
VALID_TRANSITIONS = {
    "DRAFT":      {"ACTIVE"},
    "ACTIVE":     {"DEPRECATED", "DRAFT"},       # DRAFT = disabled
    "DEPRECATED": {"RETIRED", "ACTIVE"},          # reactivation allowed
    "RETIRED":    set(),                           # terminal state
}

LIFECYCLE_ACTIONS = {
    "REGISTER":   "Initial registration",
    "UPDATE":     "Metadata update",
    "ENABLE":     "Activate service",
    "DISABLE":    "Deactivate service (move to DRAFT)",
    "DEPRECATE":  "Mark as deprecated",
    "RETIRE":     "Permanently retire service",
}


# ---------------------------------------------------------------------------
# Lifecycle event record
# ---------------------------------------------------------------------------

@dataclass
class LifecycleEvent:
    """A single lifecycle transition event with replay-safe evidence."""
    event_id: str
    service_id: str
    action: str
    previous_state: str
    new_state: str
    actor: str
    reason: str
    timestamp: str
    event_hash: str = ""
    previous_event_hash: str = ""
    replay_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Lifecycle Manager
# ---------------------------------------------------------------------------

class LifecycleManager:
    """
    Manages lifecycle transitions for Platform Services.

    Enforces valid state transitions and generates a deterministic,
    append-only evidence chain for every lifecycle action.
    """

    def __init__(self):
        self._service_states: Dict[str, str] = {}
        self._service_enabled: Dict[str, bool] = {}
        self._events: List[LifecycleEvent] = []
        self._lock = threading.Lock()
        self._head_hash = hashlib.sha256(b"LIFECYCLE_GENESIS").hexdigest()

    # -- State queries ------------------------------------------------------

    def get_state(self, service_id: str) -> Optional[str]:
        """Get the current lifecycle state of a service."""
        with self._lock:
            return self._service_states.get(service_id)

    def is_enabled(self, service_id: str) -> bool:
        """Check if a service is enabled (ACTIVE + enabled overlay)."""
        with self._lock:
            state = self._service_states.get(service_id)
            return state == "ACTIVE" and self._service_enabled.get(service_id, True)

    # -- Lifecycle actions --------------------------------------------------

    def register(
        self,
        service_id: str,
        initial_state: str = "ACTIVE",
        actor: str = "SYSTEM",
        reason: str = "Initial registration",
    ) -> LifecycleEvent:
        """Register a new service in the lifecycle manager."""
        with self._lock:
            if initial_state not in LIFECYCLE_STATES:
                raise ValueError(f"Invalid initial state: {initial_state}")

            self._service_states[service_id] = initial_state
            self._service_enabled[service_id] = (initial_state == "ACTIVE")

            return self._record_event(
                service_id=service_id,
                action="REGISTER",
                previous_state="NONE",
                new_state=initial_state,
                actor=actor,
                reason=reason,
            )

    def transition(
        self,
        service_id: str,
        target_state: str,
        actor: str = "SYSTEM",
        reason: str = "",
    ) -> LifecycleEvent:
        """
        Transition a service to a new lifecycle state.

        Validates the transition against the state machine and generates
        replay-safe evidence.

        Raises ValueError if the transition is not valid.
        """
        with self._lock:
            current = self._service_states.get(service_id)
            if current is None:
                raise ValueError(f"Service '{service_id}' is not registered in lifecycle manager.")

            if target_state not in LIFECYCLE_STATES:
                raise ValueError(f"Invalid target state: {target_state}")

            if target_state not in VALID_TRANSITIONS.get(current, set()):
                raise ValueError(
                    f"Invalid transition: {current} → {target_state}. "
                    f"Valid transitions from {current}: {VALID_TRANSITIONS.get(current, set())}"
                )

            self._service_states[service_id] = target_state
            self._service_enabled[service_id] = (target_state == "ACTIVE")

            return self._record_event(
                service_id=service_id,
                action=self._action_for_transition(current, target_state),
                previous_state=current,
                new_state=target_state,
                actor=actor,
                reason=reason,
            )

    def enable(self, service_id: str, actor: str = "SYSTEM") -> LifecycleEvent:
        """Enable a service (transition to ACTIVE if in DRAFT/DEPRECATED)."""
        current = self.get_state(service_id)
        if current == "ACTIVE":
            # Already active, just ensure enabled overlay
            with self._lock:
                self._service_enabled[service_id] = True
                return self._record_event(
                    service_id=service_id,
                    action="ENABLE",
                    previous_state="ACTIVE",
                    new_state="ACTIVE",
                    actor=actor,
                    reason="Re-enabled active service",
                )
        return self.transition(service_id, "ACTIVE", actor, "Enabled by operator")

    def disable(self, service_id: str, actor: str = "SYSTEM") -> LifecycleEvent:
        """Disable a service (transition to DRAFT)."""
        current = self.get_state(service_id)
        if current == "ACTIVE":
            return self.transition(service_id, "DRAFT", actor, "Disabled by operator")
        # If already in DRAFT, just record the event
        with self._lock:
            self._service_enabled[service_id] = False
            return self._record_event(
                service_id=service_id,
                action="DISABLE",
                previous_state=current or "UNKNOWN",
                new_state=current or "UNKNOWN",
                actor=actor,
                reason="Disable requested (already inactive)",
            )

    def deprecate(self, service_id: str, actor: str = "SYSTEM", reason: str = "") -> LifecycleEvent:
        """Deprecate a service."""
        return self.transition(
            service_id, "DEPRECATED", actor,
            reason or "Deprecated by operator"
        )

    def retire(self, service_id: str, actor: str = "SYSTEM", reason: str = "") -> LifecycleEvent:
        """Retire a service (terminal state)."""
        return self.transition(
            service_id, "RETIRED", actor,
            reason or "Retired by operator"
        )

    # -- Evidence -----------------------------------------------------------

    def get_events(self, service_id: str = None) -> List[Dict[str, Any]]:
        """Get lifecycle events, optionally filtered by service_id."""
        with self._lock:
            events = self._events
            if service_id:
                events = [e for e in events if e.service_id == service_id]
            return [e.to_dict() for e in events]

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Return all lifecycle events."""
        with self._lock:
            return [e.to_dict() for e in self._events]

    def verify_chain(self) -> bool:
        """Verify the integrity of the lifecycle event chain."""
        with self._lock:
            head = hashlib.sha256(b"LIFECYCLE_GENESIS").hexdigest()
            for event in self._events:
                if event.previous_event_hash != head:
                    return False
                # Recompute hash
                hash_seed = json.dumps({
                    "event_id": event.event_id,
                    "service_id": event.service_id,
                    "action": event.action,
                    "previous_state": event.previous_state,
                    "new_state": event.new_state,
                    "actor": event.actor,
                    "reason": event.reason,
                    "previous_hash": head,
                }, sort_keys=True)
                expected = hashlib.sha256(hash_seed.encode()).hexdigest()
                if event.event_hash != expected:
                    return False
                head = event.event_hash
            return head == self._head_hash

    # -- Internals ----------------------------------------------------------

    def _record_event(
        self,
        service_id: str,
        action: str,
        previous_state: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> LifecycleEvent:
        """Record a lifecycle event with hash chaining. Caller holds _lock."""
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        hash_seed = json.dumps({
            "event_id": event_id,
            "service_id": service_id,
            "action": action,
            "previous_state": previous_state,
            "new_state": new_state,
            "actor": actor,
            "reason": reason,
            "previous_hash": self._head_hash,
        }, sort_keys=True)
        event_hash = hashlib.sha256(hash_seed.encode()).hexdigest()

        event = LifecycleEvent(
            event_id=event_id,
            service_id=service_id,
            action=action,
            previous_state=previous_state,
            new_state=new_state,
            actor=actor,
            reason=reason,
            timestamp=timestamp,
            event_hash=event_hash,
            previous_event_hash=self._head_hash,
            replay_metadata={
                "chain_length": len(self._events) + 1,
                "head_hash_before": self._head_hash,
            },
        )

        self._events.append(event)
        self._head_hash = event_hash
        return event

    @staticmethod
    def _action_for_transition(from_state: str, to_state: str) -> str:
        """Map a state transition to a lifecycle action name."""
        mapping = {
            ("DRAFT", "ACTIVE"): "ENABLE",
            ("ACTIVE", "DRAFT"): "DISABLE",
            ("ACTIVE", "DEPRECATED"): "DEPRECATE",
            ("DEPRECATED", "ACTIVE"): "ENABLE",
            ("DEPRECATED", "RETIRED"): "RETIRE",
        }
        return mapping.get((from_state, to_state), "TRANSITION")
