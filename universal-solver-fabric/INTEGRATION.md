# Universal Solver Fabric - Integration Mapping

This document classifies the Universal Solver Fabric within the TANTRA canonical ecosystem, defining its boundaries, dependencies, and runtime position.

## Classification

* **Primary Domain**: Sovereign Optimization
* **Capability**: Universal Solver Fabric
* **Platform Service**: `Optimization.SolverFabric.v1`
* **Runtime position**: Platform Service Layer / Agnostic Execution Layer

## Dependencies & Consumers

* **Allowed consumers**: TANTRA Product Layer, Platform Services
* **Upstream dependencies**: TANTRA Platform Service, Request Routing
* **Downstream dependencies**: Solver Adapters (e.g., Pyomo, Qiskit), Execution Infrastructure, Specific Execution Engines (e.g., classical, quantum, heuristic solvers)

## Authority Boundaries

* **Explicit authority boundaries**: 
  - Strictly decouples domain formulation from deterministic execution.
  - Acts solely as a participant and execution fabric, not an orchestrator.
  - Enforces governed capability contracts for solver registration and discovery.
* **Components explicitly NOT owned**: 
  - Optimization modeling, problem formulation, or business logic.
  - Orchestration of external workflows.
  - Master Directive definitions.
  - BCAB/BCAES architecture definitions.
