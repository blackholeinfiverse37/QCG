# ARCHITECTURE: Universal Solver Fabric

This document details the architectural boundaries of the Universal Solver Fabric, deployed as a **Platform Service Capability** (`Optimization.SolverFabric.v1`) within the TANTRA canonical ecosystem.

## 1. Architectural Philosophy

The core architectural tenet of the Universal Solver Fabric is the **strict decoupling of domain formulation from deterministic execution**. 
It acts as a governed participant and execution fabric rather than an orchestrator. It does not dictate optimization modeling, nor does it contain business logic.

## 2. Component Breakdown

The architecture is built upon the following decoupled components:

1. **Solver Capability Contract** (`solver_contract.schema.json`): A schema-driven contract that governs what capabilities a solver must declare.
2. **Universal Solver Registry** (`solver_registry.py`): In-memory component to validate and track solver registration metadata.
3. **Solver Selection Engine** (`solver_selection_engine.py`): Recommends an ordered list of solvers based on problem characteristics.
4. **Execution Adapter** (`execution_adapter.py`): Translates standardized optimization requests into engine-specific formats, executes them deterministically, and collects cryptographically secure replay metadata.
5. **Solver Interfaces** (`solver_interfaces/`): The physical attachment points for different runtimes (classical, quantum, heuristic).

## 3. Position in the TANTRA Ecosystem

As defined by the BCAB/BCAES canonical model:

* **Primary Domain**: Sovereign Optimization
* **Layer**: Platform Service Layer / Agnostic Execution Layer
* **Allowed Consumers**: TANTRA Product Layer, Platform Services
* **Upstream Dependencies**: TANTRA Platform Service, Request Routing
* **Downstream Dependencies**: Execution Infrastructure, specific Execution Engines (e.g., OR-Tools, Qiskit)

## 4. References

For detailed lifecycle diagrams and failure modes, refer to [UNIVERSAL_SOLVER_FABRIC.md](UNIVERSAL_SOLVER_FABRIC.md).
For the canonical runtime execution path, refer to [runtime_flow.md](runtime_flow.md).
