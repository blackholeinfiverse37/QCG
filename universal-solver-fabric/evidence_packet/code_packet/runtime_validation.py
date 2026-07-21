import json
import os
import time
from typing import Dict, Any, Optional

from solver_registry import SolverRegistry
from solver_selection_engine import SolverSelectionEngine
from execution_adapter import ExecutionAdapter
from solver_interfaces.base import BaseSolverAdapter

# Create evidence packet directories if they don't exist
os.makedirs("evidence_packet/runtime_logs", exist_ok=True)
os.makedirs("evidence_packet/code_packet", exist_ok=True)
os.makedirs("evidence_packet/api_samples", exist_ok=True)

class ValidatingSolverAdapter(BaseSolverAdapter):
    """
    A concrete mock implementation of a solver for runtime validation.
    Supports injecting a simulated failure for testing failure handling.
    """
    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure
        self.problem = None

    def bind_problem(self, problem: Dict[str, Any]) -> None:
        self.problem = problem

    def execute(self, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        time.sleep(0.1) # simulate brief execution time
        if self.simulate_failure:
            raise RuntimeError("Simulated solver failure for validation purposes.")
            
        return {
            "objective_value": 1337.0,
            "decision_variables": {"x1": 42, "x2": 99},
            "solver_specific_metrics": {
                "nodes_explored": 1500,
                "gap": 0.0
            }
        }

    def get_health(self) -> str:
        return "HEALTHY"

def run_validation():
    print("=== Phase 5: Runtime Validation ===")
    
    # 1. Capability Discovery & Runtime Registration
    print("\n1. Capability Discovery & Registration...")
    registry = SolverRegistry("solver_contract.schema.json")
    
    with open("solver_examples.json") as f:
        examples = json.load(f)
        for ex in examples:
            registry.register_solver(ex)
            
    print(f"Registered {len(registry.search_capabilities())} solvers successfully.")

    # 2. Solver Selection
    print("\n2. Solver Selection...")
    engine = SolverSelectionEngine(registry)
    
    problem = {
        "problem_type": "MILP",
        "required_constraints": ["LINEAR"],
        "require_deterministic": True,
        "available_memory_mb": 4096,
        "available_cores": 4,
        "max_variables": 500,
        "max_constraints": 1000
    }
    
    recommendations = engine.select_solvers(problem)
    if not recommendations:
        print("ERROR: No compatible solvers found.")
        return
        
    selected_solver_meta = recommendations[0]
    print(f"Selected Solver: {selected_solver_meta['solver_name']} (ID: {selected_solver_meta['solver_id']})")

    # 3 & 4 & 5. Solver Execution, Evidence Generation, Replay & Observability
    print("\n3. Executing Successful Run & Generating Evidence...")
    adapter_success = ExecutionAdapter(ValidatingSolverAdapter(simulate_failure=False), selected_solver_meta)
    
    evidence_success = adapter_success.execute_with_evidence(problem)
    print(f"Success Trace ID: {evidence_success['trace_id']}")
    print(f"Replay ID: {evidence_success['replay_id']}")
    print(f"Execution Status: {evidence_success['status']}")

    # 6. Failure Handling
    print("\n4. Executing Failure Run & Generating Evidence...")
    adapter_failure = ExecutionAdapter(ValidatingSolverAdapter(simulate_failure=True), selected_solver_meta)
    
    evidence_failure = adapter_failure.execute_with_evidence(problem)
    print(f"Failure Trace ID: {evidence_failure['trace_id']}")
    print(f"Execution Status: {evidence_failure['status']}")
    print(f"Captured Error: {evidence_failure['result'].get('error')}")
    
    # 7. Deterministic Replay Check
    # To demonstrate deterministic replay, the evidence package must capture all state required to reproduce.
    # The 'deterministic_inputs' and 'provenance' metadata are critical here.
    print("\n5. Validating Deterministic Replay Compatibility...")
    has_deterministic_inputs = "deterministic_inputs" in evidence_success
    has_provenance = "provenance" in evidence_success
    print(f"Contains Deterministic Inputs: {has_deterministic_inputs}")
    print(f"Contains Provenance Metadata: {has_provenance}")

    # Save evidence packets to disk as proof
    evidence_path_success = "evidence_packet/runtime_logs/execution_evidence_success.json"
    evidence_path_failure = "evidence_packet/runtime_logs/execution_evidence_failure.json"
    
    with open(evidence_path_success, 'w') as f:
        json.dump(evidence_success, f, indent=2)
        
    with open(evidence_path_failure, 'w') as f:
        json.dump(evidence_failure, f, indent=2)
        
    print(f"\nEvidence packets saved to {evidence_path_success} and {evidence_path_failure}")
    print("Runtime Validation Complete.")

if __name__ == "__main__":
    run_validation()
