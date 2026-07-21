# Platform Service Specification: Optimization.SolverFabric.v1

## Overview
This specification defines the Platform Service exposing the Universal Solver Fabric. It operates purely as an agnostic capability layer. It does not embed business workflows, approve usage budgets, or perform problem formulation.

## Interface Contract

### 1. Base URL
`https://api.bhiv.internal/platform/v1/optimization/solver-fabric`

### 2. Supported Attachment Modes
The service supports the following execution attachment modes negotiated via the `X-Attachment-Mode` header:
- `local`: Direct process invocation (default for lightweight solvers).
- `remote`: Dispatch to a remote compute cluster (e.g., QPU execution).
- `hybrid`: Orchestrated split execution (e.g., QAOA with classical optimization loop).

### 3. Discovery Metadata
```json
{
  "service_id": "Optimization.SolverFabric.v1",
  "domain": "Sovereign Optimization",
  "classification": "Platform Service",
  "status": "Active",
  "supported_problem_types": ["MILP", "QUBO", "CP", "NLP"]
}
```

## Endpoints

### 1. `GET /capabilities`
Discovers available solvers matching query criteria.

**Response Schema (200 OK):**
```json
{
  "solvers": [
    {
      "solver_id": "ORTOOLS_CP_SAT_01",
      "version": "1.0.0",
      "supported_problem_types": ["MILP", "CP"],
      "deterministic_capability": true
    }
  ]
}
```

### 2. `POST /execute`
Submits an optimization problem for deterministic execution. The service will automatically rank and select the best solver unless a strict override is provided.

**Request Schema:**
```json
{
  "problem_schema": {
    "problem_type": "MILP",
    "required_constraints": ["LINEAR"],
    "require_deterministic": true
  },
  "payload": {
    "variables": [...],
    "constraints": [...],
    "objective": [...]
  },
  "execution_constraints": {
    "max_time_ms": 60000,
    "max_memory_mb": 4096
  }
}
```

**Response Schema (200 OK):**
```json
{
  "execution_id": "exec-9f8a8-4b72",
  "selected_solver": "ORTOOLS_CP_SAT_01",
  "status": "Optimal",
  "solution": {
    "objective_value": 42.5,
    "decision_variables": {"x1": 1, "x2": 0}
  },
  "telemetry": {
    "execution_time_ms": 1450,
    "peak_memory_mb": 256
  },
  "replay_metadata": {
    "deterministic_seed": 42,
    "fabric_version": "1.0.0",
    "solver_version": "1.0.0"
  },
  "confidence_score": 0.99
}
```

## Error Model

Standard HTTP status codes are mapped to specific capability violations.

| Code | Type | Description |
|---|---|---|
| 400 | `ValidationError` | The problem payload violates the requested problem type schema. |
| 422 | `CapabilityMismatch` | No registered solver can satisfy the required constraints or problem type. |
| 429 | `ResourceExhausted` | The consumer has exceeded fabric quotas. |
| 500 | `EngineCrash` | The underlying solver engine failed unexpectedly; caught and normalized by the adapter. |
| 504 | `Timeout` | The solver exceeded the `max_time_ms` constraint. |

## Versioning Strategy
- **Service API Versioning**: Handled via URL path (e.g., `/v1/`). Increment only on breaking changes to the request/response schema.
- **Solver Capability Versioning**: Handled within the payload `replay_metadata.solver_version`. Backward compatibility enforced by the JSON Schema contract.
