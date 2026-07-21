# REVIEW: Internal Review Criteria

This document specifies the internal review process for modifying or adding capabilities to the Universal Solver Fabric.

## Pre-Requisites for Pull Requests
1. **Schema Validation**: Any changes to `solver_contract.schema.json` must remain backward compatible.
2. **Deterministic Evidence**: New solver adapters must implement and pass the `execution_adapter` tests, producing cryptographically verifiable traces.
3. **No Orchestration Drift**: Code changes must not introduce external orchestration workflows (e.g., calling external REST APIs outside of an execution context).
4. **Validation Test**: The `runtime_validation.py` script must pass with 0 errors.

All reviews must verify that the BCAB boundary classification of "Platform Service" remains strictly intact.
