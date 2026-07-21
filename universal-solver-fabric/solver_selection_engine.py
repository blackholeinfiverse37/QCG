from typing import Dict, Any, List
from solver_registry import SolverRegistry

class SolverSelectionEngine:
    def __init__(self, registry: SolverRegistry):
        self.registry = registry

        # Mappings for sorting (lower is better)
        self.cost_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "DYNAMIC": 4}
        self.runtime_rank = {"REALTIME": 1, "SECONDS": 2, "MINUTES": 3, "HOURS": 4, "DAYS": 5}
        self.confidence_rank = {"EXACT": 1, "HEURISTIC_BOUNDED": 2, "PROBABILISTIC": 3, "UNBOUNDED": 4}

    def _is_compatible(self, problem: Dict[str, Any], solver: Dict[str, Any]) -> bool:
        """Determines if a solver meets the hard requirements of the problem."""
        # 1. Problem type
        if problem.get("problem_type") not in solver.get("supported_problem_types", []):
            return False

        # 2. Constraints
        req_constraints = problem.get("required_constraints", [])
        sup_constraints = solver.get("supported_constraints", [])
        if not all(c in sup_constraints for c in req_constraints):
            return False

        # 3. Objective
        if problem.get("required_objective") and problem["required_objective"] not in solver.get("objective_support", []):
            return False

        # 4. Capability requirements
        if problem.get("require_deterministic") and not solver.get("deterministic_capability"):
            return False
        if problem.get("require_replay") and not solver.get("replay_capability"):
            return False
        if problem.get("require_explainability") and not solver.get("explainability_support"):
            return False

        # 5. Resource Availability
        req_resources = solver.get("resource_requirements", {})
        if problem.get("available_memory_mb", float('inf')) < req_resources.get("memory_mb_min", 0):
            return False
        if problem.get("available_cores", float('inf')) < req_resources.get("cores_min", 0):
            return False

        # 6. Authority Limits
        limits = solver.get("authority_limits", {})
        if problem.get("max_variables", 0) > limits.get("max_variables", float('inf')):
            return False
        if problem.get("max_constraints", 0) > limits.get("max_constraints", float('inf')):
            return False

        return True

    def _score_solver(self, solver: Dict[str, Any]) -> tuple:
        """
        Creates a deterministic sorting tuple for the solver.
        Lower values are ranked higher.
        Tuple order: (Cost, Runtime, Confidence, Solver ID (alphabetical))
        """
        cost = self.cost_rank.get(solver.get("estimated_cost", "DYNAMIC"), 99)
        runtime = self.runtime_rank.get(solver.get("estimated_runtime", "DAYS"), 99)
        confidence = self.confidence_rank.get(solver.get("confidence_model", "UNBOUNDED"), 99)
        solver_id = solver.get("solver_id", "")
        
        return (cost, runtime, confidence, solver_id)

    def select_solvers(self, problem: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Recommends an ordered list of compatible solvers.
        """
        compatible_solvers = []
        
        # Retrieve all active solvers
        all_solvers = self.registry.search_capabilities()
        
        for solver in all_solvers:
            if self._is_compatible(problem, solver):
                compatible_solvers.append(solver)
                
        # Sort deterministically based on scoring criteria
        compatible_solvers.sort(key=self._score_solver)
        
        return compatible_solvers

if __name__ == "__main__":
    # Selection Report Example
    import json
    registry = SolverRegistry("solver_contract.schema.json")
    
    try:
        with open("solver_examples.json") as f:
            examples = json.load(f)
            for ex in examples:
                registry.register_solver(ex)
    except FileNotFoundError:
        print("Example data not found for local testing.")
        
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
    
    print(f"Problem: {problem}")
    recommendations = engine.select_solvers(problem)
    print(f"Recommended Solvers:")
    for r in recommendations:
        print(f" - {r['solver_name']} (ID: {r['solver_id']})")
