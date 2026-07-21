# Universal Solver Fabric - Review Packet

## 1. What Changed
The Universal Solver Fabric (USF) has been implemented to serve as the unified optimization layer for BHIV under TANTRA Phase V. This establishes a clean separation between problem formulation and solver execution, moving away from a monolithic compiler approach.

New capabilities introduced:
- Deterministic Solver Registration and Validation (JSON Schema)
- Configurable Solver Capability Contracts
- Deterministic Solver Selection Engine
- Extensible Attachment Interfaces for Classical, Quantum, CP, MIP, Evolutionary, Metaheuristics, and RL engines.
- Comprehensive Unit Test Suite enforcing constraints.

## 2. Entry Point
The primary entry points are the `SolverRegistry` (for registering optimization capabilities) and the `SolverSelectionEngine` (for selecting the most suitable solver for a given problem configuration).
- **Registry Entry:** `solver_registry.py` -> `SolverRegistry`
- **Selection Entry:** `solver_selection_engine.py` -> `SolverSelectionEngine`

## 3. Core Execution Flow
1. An optimization engine initializes its specific `BaseSolverAdapter` implementation.
2. The engine calls `SolverRegistry.register_solver()` with its declared capabilities.
3. An incoming optimization problem is mapped into a standard request dictionary.
4. `SolverSelectionEngine.select_solvers()` determines the ranked list of compatible engines.
5. The application invokes the top-ranked engine's adapter: `adapter.bind_problem(problem)` followed by `adapter.execute()`.
6. The adapter returns deterministic results with provenance and replay metadata.

## 4. Solver Registration Flow
The `SolverRegistry` uses `jsonschema` to strictly validate each solver's capabilities against `solver_contract.schema.json`.
- A solver submits its payload.
- The registry checks version conflicts and schema conformance.
- Valid solvers are added to the active pool.
- Health endpoints allow solvers to be temporarily disabled if they crash.

## 5. Selection Flow
The `SolverSelectionEngine` utilizes deterministic filtering and ranking:
1. **Filtering:** Enforces hard constraints like `problem_type`, `required_constraints`, `require_deterministic`, and memory/core limits.
2. **Ranking:** Sorts by `estimated_cost` (ascending), `estimated_runtime` (ascending), and `confidence_model` (descending certainty).
3. **Tie-breaking:** Alphabetical sort by `solver_id`.

## 6. Sample Request/Response
**Request to Selection Engine:**
```json
{
    "problem_type": "MILP",
    "required_constraints": ["LINEAR"],
    "require_deterministic": true,
    "available_memory_mb": 4096,
    "available_cores": 4,
    "max_variables": 500,
    "max_constraints": 1000
}
```
**Selection Response (Ordered List):**
```json
[
  {
    "solver_id": "ORTOOLS_CP_SAT_01",
    "solver_name": "Google OR-Tools CP-SAT",
    "solver_type": "CP",
    "estimated_cost": "LOW",
    "confidence_model": "EXACT",
    ...
  }
]
```

## 7. Failure Cases Handled
- **Invalid Contracts:** A solver missing mandatory fields or specifying unknown constraint types is rejected instantly with `RegistryError`.
- **Duplicate Registration:** Prevents silent overwriting if a solver with the exact same ID and version tries to register twice.
- **Problem Unsupported:** If an application requests an NLP problem and only MIP solvers are available, the selection engine returns an empty list, gracefully falling back.
- **Solver Degradation:** A solver can be temporarily deactivated via `disable_solver()`, routing all new requests to the next best alternative deterministically.

## 8. Test Evidence
Unit testing framework: `pytest`
- Execution: `python -m pytest tests/test_fabric.py -v`
- Results: 7/7 tests passed successfully (100% coverage on tested behaviors).
- Provenance constraints, version conflicts, deterministic sorting, unsupported problem fallbacks, and schema validation all tested.

## 9. Runtime Participation Plan
To fully integrate the fabric into the TANTRA Phase V execution runtime:
1. **Pritesh / Harsha:** Hook the Selection Engine into the active runtime orchestrator, redirecting standard execution requests to the Fabric.
2. **Kanishk:** Seed the `SolverRegistry` with the current library of operational solvers (Google OR-Tools, Qiskit QAOA).
3. **MDU:** Officially own and lock down updates to `solver_contract.schema.json`.
4. **InsightFlow:** Wrap the `.execute()` command in a telemetry hook for real-time operational dashboarding.

## 10. BCAB/BCAES Canonical Integration Deliverables
As part of the canonical integration into the ecosystem, the following artifacts have been created:
- `CAPABILITY_REGISTRY.md`: Registers the Fabric as a core capability.
- `PLATFORM_SERVICE_SPEC.md`: Defines the Platform Service API boundary (`Optimization.SolverFabric.v1`).
- `runtime_flow.md`: Sequence diagram of the execution cycle.
- `review_packets/`: Contains runtime execution logs and evidence of registration and test execution.


## 11. Execution Validation (Phase 5)
- The solver successfully executed the request and produced deterministic Replay IDs.
- **Trace ID**: 26d61a0c-22ca-4be4-ba48-71150102d318
- **Replay ID**: c120e074-0118-4933-8187-a6b8b2176f6d
- Execution logs and proofs have been generated and packaged in the evidence_packet directory.
