import json
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class QuantumProvider(str, Enum):
    """
    Supported providers for Quantum Execution Context.
    No provider-specific assumptions may exist inside RuntimeCore.
    """
    IBM_QUANTUM = "IBM_QUANTUM"
    IONQ = "IONQ"
    QUANTINUUM = "QUANTINUUM"
    RIGETTI = "RIGETTI"
    NEUTRAL_ATOM_SYSTEMS = "NEUTRAL_ATOM_SYSTEMS"
    PHOTONIC_SYSTEMS = "PHOTONIC_SYSTEMS"
    FUTURE_INDIGENOUS = "FUTURE_INDIGENOUS"
    SIMULATED = "SIMULATED"


@dataclass(frozen=True)
class QuantumExecutionContext:
    """
    Phase 3: Provider-neutral execution metadata.
    This encapsulates execution metadata without any provider-specific logic.
    """
    provider: QuantumProvider
    solver_name: str
    shots: int
    noise_model: Optional[str]
    optimization_level: int
    backend_properties: Dict[str, Any] = field(default_factory=dict)
    seed_simulator: Optional[int] = None
    schema_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert the execution context to a deterministic dictionary."""
        return {
            "provider": self.provider.value,
            "solver_name": self.solver_name,
            "shots": self.shots,
            "noise_model": self.noise_model,
            "optimization_level": self.optimization_level,
            "backend_properties": self.backend_properties,
            "seed_simulator": self.seed_simulator,
            "schema_version": self.schema_version,
        }

    def compute_hash(self) -> str:
        """Computes a deterministic hash of the context metadata."""
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()
