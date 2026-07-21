# HANDOVER: Universal Solver Fabric

This document serves as the onboarding and handover guide for new engineers continuing work on the Universal Solver Fabric. It satisfies the Phase 6 (Documentation & Handover) requirements of the Master Directive.

## 1. Environment Setup

To begin development and testing, ensure the following prerequisites are met:
* **Python**: `python >= 3.9`
* **Dependencies**: `pip install jsonschema`
* **Runtime Verification**: Run `python runtime_validation.py` to ensure local execution adapter logic works and evidence is correctly generated.

## 2. Repository Map

* `solver_contract.schema.json`: The source of truth for solver capability declarations.
* `solver_registry.py` & `solver_selection_engine.py`: Registration and dynamic selection core.
* `execution_adapter.py`: Standardizes problem execution and generates deterministic trace evidence.
* `DEP/`: Engineering Operations compliance files (Governance, Master Directive Updates).
* `evidence_packet/`: Captured runtime logs and proof of execution integrity.
* `tests/`: Unit tests and local validation frameworks.

## 3. Known Limitations

* The current execution flow uses an in-memory solver selection engine which resets upon process restart.
* The local solver interfaces mock external APIs. Actual API integrations (e.g., to D-Wave or IBM Q) are pending.

## 4. Pending Integration Work

* Complete the downstream testing with TANTRA Product Layer requests.
* Integrate actual remote solver infrastructure adapters into `solver_interfaces/`.

## 5. Build History

* **v1.0.0**: Initial implementation of Universal Solver Fabric Phase V integration. Completed Registry, Selection Engine, and Execution Adapter with replay-safe evidence generation.
