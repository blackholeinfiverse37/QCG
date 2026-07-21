import pytest
import json
import os
from solver_registry import SolverRegistry, RegistryError
from solver_selection_engine import SolverSelectionEngine

SCHEMA_PATH = "solver_contract.schema.json"
EXAMPLES_PATH = "solver_examples.json"

@pytest.fixture
def base_registry():
    return SolverRegistry(SCHEMA_PATH)

@pytest.fixture
def valid_solver_cp():
    return {
        "solver_id": "TEST_CP_01",
        "solver_name": "Test CP Solver",
        "solver_type": "CP",
        "version": "1.0.0",
        "supported_problem_types": ["CP", "MILP"],
        "supported_constraints": ["LINEAR", "LOGICAL"],
        "objective_support": ["SINGLE"],
        "optimization_direction": ["MINIMIZE"],
        "deterministic_capability": True,
        "replay_capability": True,
        "explainability_support": True,
        "execution_requirements": {"hardware": "CPU", "distributed": False},
        "resource_requirements": {"memory_mb_min": 512, "cores_min": 1},
        "estimated_cost": "LOW",
        "estimated_runtime": "SECONDS",
        "confidence_model": "EXACT",
        "authority_limits": {"max_variables": 1000, "max_constraints": 1000},
        "attachment_mode": "LOCAL",
        "schema_version": "1.0.0"
    }

@pytest.fixture
def valid_solver_q():
    return {
        "solver_id": "TEST_Q_01",
        "solver_name": "Test Quantum Solver",
        "solver_type": "QUANTUM",
        "version": "1.0.0",
        "supported_problem_types": ["QUBO"],
        "supported_constraints": ["QUADRATIC"],
        "objective_support": ["QUADRATIC"],
        "optimization_direction": ["MINIMIZE"],
        "deterministic_capability": False,
        "replay_capability": True,
        "explainability_support": False,
        "execution_requirements": {"hardware": "QPU", "distributed": False},
        "resource_requirements": {"memory_mb_min": 2048, "cores_min": 4},
        "estimated_cost": "HIGH",
        "estimated_runtime": "SECONDS",
        "confidence_model": "PROBABILISTIC",
        "authority_limits": {"max_variables": 100, "max_constraints": 100},
        "attachment_mode": "REMOTE",
        "schema_version": "1.0.0"
    }

def test_successful_registration(base_registry, valid_solver_cp):
    solver_id = base_registry.register_solver(valid_solver_cp)
    assert solver_id == "TEST_CP_01"
    assert base_registry.get_health_status(solver_id) == "ENABLED"

def test_invalid_contract(base_registry, valid_solver_cp):
    invalid_solver = valid_solver_cp.copy()
    del invalid_solver["solver_type"] # Missing required field
    with pytest.raises(RegistryError):
        base_registry.register_solver(invalid_solver)

def test_duplicate_solver_id_version_conflict(base_registry, valid_solver_cp):
    base_registry.register_solver(valid_solver_cp)
    # Registering exact same version should fail
    with pytest.raises(RegistryError, match="is already registered"):
        base_registry.register_solver(valid_solver_cp)

def test_capability_lookup(base_registry, valid_solver_cp, valid_solver_q):
    base_registry.register_solver(valid_solver_cp)
    base_registry.register_solver(valid_solver_q)
    
    results = base_registry.compatibility_lookup(required_problem_type="QUBO")
    assert len(results) == 1
    assert results[0]["solver_id"] == "TEST_Q_01"

def test_failure_handling_and_disabling(base_registry, valid_solver_cp):
    base_registry.register_solver(valid_solver_cp)
    base_registry.disable_solver("TEST_CP_01")
    assert base_registry.get_health_status("TEST_CP_01") == "DISABLED"
    
    # Disabled solver should not be returned in searches
    results = base_registry.compatibility_lookup("CP")
    assert len(results) == 0
    
    base_registry.enable_solver("TEST_CP_01")
    assert base_registry.get_health_status("TEST_CP_01") == "ENABLED"
    results = base_registry.compatibility_lookup("CP")
    assert len(results) == 1

def test_unsupported_problems(base_registry, valid_solver_cp):
    base_registry.register_solver(valid_solver_cp)
    engine = SolverSelectionEngine(base_registry)
    problem = {"problem_type": "NLP"} # Unsupported
    assert len(engine.select_solvers(problem)) == 0

def test_ranking_correctness_and_deterministic_ordering(base_registry, valid_solver_cp, valid_solver_q):
    base_registry.register_solver(valid_solver_cp)
    base_registry.register_solver(valid_solver_q)
    
    # Let's add a slightly worse CP solver (higher cost)
    worse_cp = valid_solver_cp.copy()
    worse_cp["solver_id"] = "TEST_CP_02"
    worse_cp["estimated_cost"] = "MEDIUM"
    base_registry.register_solver(worse_cp)

    # Add a CP solver with same cost but different ID to test deterministic tie-breaking
    same_cp = valid_solver_cp.copy()
    same_cp["solver_id"] = "TEST_CP_03"
    base_registry.register_solver(same_cp)

    engine = SolverSelectionEngine(base_registry)
    problem = {
        "problem_type": "CP",
        "required_constraints": ["LINEAR"],
    }
    
    selected = engine.select_solvers(problem)
    assert len(selected) == 3
    
    # Check deterministic ordering: Cost (LOW before MEDIUM), then tie-break by solver_id alphabetically
    assert selected[0]["solver_id"] == "TEST_CP_01"
    assert selected[1]["solver_id"] == "TEST_CP_03"
    assert selected[2]["solver_id"] == "TEST_CP_02"
