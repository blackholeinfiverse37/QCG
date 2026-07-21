# Universal Solver Fabric

The Universal Solver Fabric is the foundational optimization infrastructure of the BHIV Sovereign Optimization Capability. It allows classical, quantum, heuristic, and evolutionary optimization engines to participate through unified contracts.

## Components

1. **Solver Capability Contract** (`solver_contract.schema.json`): A JSON Schema that strictly enforces what capabilities and limits a solver must declare.
2. **Universal Solver Registry** (`solver_registry.py`): In-memory registry to validate, track, and lookup registered solvers.
3. **Solver Selection Engine** (`solver_selection_engine.py`): A deterministic engine recommending an ordered list of compatible solvers based on a problem's characteristics.
4. **Solver Interfaces** (`solver_interfaces/`): Attachment interfaces for bridging the gap between the Selection Engine and specific execution runtimes.

## Getting Started

### Prerequisites

Ensure you have python >= 3.9 and install required packages:
```bash
pip install jsonschema
```

### Registration Example

```python
from solver_registry import SolverRegistry
import json

registry = SolverRegistry("solver_contract.schema.json")

# Load examples
with open("solver_examples.json") as f:
    examples = json.load(f)

# Register a solver
for solver in examples:
    registry.register_solver(solver)

# Lookup capabilities
compatible = registry.compatibility_lookup(required_problem_type="QUBO")
print(compatible)
```

## Architecture & Integration

Please refer to `UNIVERSAL_SOLVER_FABRIC.md` for complete architecture diagrams, lifecycles, and failure modes.

### BCAB/BCAES Capability Integration

The Universal Solver Fabric is formally registered as a **Platform Service** capability within the Sovereign Optimization domain.
For canonical registry details, see `CAPABILITY_REGISTRY.md`.
For the platform service specification, see `PLATFORM_SERVICE_SPEC.md`.
For the runtime integration sequence, see `runtime_flow.md`.
