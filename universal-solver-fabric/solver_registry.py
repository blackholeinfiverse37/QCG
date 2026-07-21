import json
import os
import jsonschema
from jsonschema import validate
from typing import Dict, List, Optional, Any

class RegistryError(Exception):
    pass

class SolverRegistry:
    def __init__(self, schema_path: str):
        self._solvers: Dict[str, Dict[str, Any]] = {}
        self._disabled_solvers: set = set()
        
        try:
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        except Exception as e:
            raise RegistryError(f"Failed to load schema from {schema_path}: {e}")

    def register_solver(self, solver_metadata: Dict[str, Any]) -> str:
        """Registers a new solver capability, validating against the JSON schema."""
        try:
            validate(instance=solver_metadata, schema=self.schema)
        except jsonschema.exceptions.ValidationError as e:
            raise RegistryError(f"Solver metadata is invalid: {e.message}")

        solver_id = solver_metadata.get("solver_id")
        if solver_id in self._solvers:
            # Check version conflicts - simple approach: do not allow same ID without unregistering
            if self._solvers[solver_id]["version"] == solver_metadata["version"]:
                raise RegistryError(f"Solver {solver_id} version {solver_metadata['version']} is already registered.")
            
        self._solvers[solver_id] = solver_metadata
        # By default, a newly registered solver is enabled
        self._disabled_solvers.discard(solver_id)
        
        return solver_id

    def remove_solver(self, solver_id: str) -> None:
        """Removes a solver from the registry."""
        if solver_id in self._solvers:
            del self._solvers[solver_id]
            self._disabled_solvers.discard(solver_id)
        else:
            raise RegistryError(f"Solver {solver_id} not found.")

    def enable_solver(self, solver_id: str) -> None:
        """Enables a solver."""
        if solver_id not in self._solvers:
            raise RegistryError(f"Solver {solver_id} not found.")
        self._disabled_solvers.discard(solver_id)

    def disable_solver(self, solver_id: str) -> None:
        """Disables a solver so it won't be returned in lookups."""
        if solver_id not in self._solvers:
            raise RegistryError(f"Solver {solver_id} not found.")
        self._disabled_solvers.add(solver_id)

    def get_health_status(self, solver_id: str) -> str:
        """Returns the health status of a solver (ENABLED, DISABLED, or UNKNOWN)."""
        if solver_id not in self._solvers:
            return "UNKNOWN"
        return "DISABLED" if solver_id in self._disabled_solvers else "ENABLED"

    def get_solver_metadata(self, solver_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves full metadata for a specific solver."""
        return self._solvers.get(solver_id)

    def search_capabilities(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for solvers matching specific criteria.
        Example: registry.search_capabilities(solver_type="CP", deterministic_capability=True)
        """
        results = []
        for solver_id, meta in self._solvers.items():
            if solver_id in self._disabled_solvers:
                continue
                
            match = True
            for k, v in kwargs.items():
                if k not in meta or meta[k] != v:
                    match = False
                    break
            if match:
                results.append(meta)
                
        return results

    def compatibility_lookup(self, required_problem_type: str, required_constraint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lookup solvers compatible with a specific problem type and optional constraint.
        """
        results = []
        for solver_id, meta in self._solvers.items():
            if solver_id in self._disabled_solvers:
                continue
            
            # Check problem type support
            if required_problem_type not in meta.get("supported_problem_types", []):
                continue
                
            # Check constraint support if provided
            if required_constraint and required_constraint not in meta.get("supported_constraints", []):
                continue
                
            results.append(meta)
            
        return results
