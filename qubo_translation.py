from typing import Dict, Any, Tuple
from quantum_problem_compiler import CompiledOptimizationProblem

class QUBOTranslator:
    """Translates a CompiledOptimizationProblem into a QUBO formulation."""
    
    def __init__(self, problem: CompiledOptimizationProblem):
        self.problem = problem
        self.qubo_matrix: Dict[Tuple[str, str], float] = {}
        self.offset = 0.0

    def translate(self, constraint_weight: float = 10.0) -> Dict[Tuple[str, str], float]:
        """
        Main translation routine: converts objective and constraints into a QUBO matrix.
        QUBO aims to minimize x^T * Q * x.
        """
        # Ensure all variables are binary
        for var in self.problem.variables.values():
            if var.var_type != "binary":
                raise ValueError("QUBO translation currently only supports binary variables.")

        # 1. Map Objective
        multiplier = 1.0 if self.problem.objective.sense == "minimize" else -1.0
        
        for var_name, coeff in self.problem.objective.linear_terms.items():
            self._add_qubo_term(var_name, var_name, coeff * multiplier)
            
        for (v1, v2), coeff in self.problem.objective.quadratic_terms.items():
            self._add_qubo_term(v1, v2, coeff * multiplier)

        # 2. Map Constraints (as Penalties)
        # For an equality constraint: sum(a_i * x_i) == b
        # Penalty = weight * (sum(a_i * x_i) - b)^2
        # Expanding: weight * [ sum(a_i^2 * x_i^2) + 2*sum(a_i * a_j * x_i * x_j) - 2*b*sum(a_i * x_i) + b^2 ]
        # Since x_i is binary, x_i^2 = x_i.
        
        for c_name, constraint in self.problem.constraints.items():
            if constraint.sense != "==":
                 # Inequality constraints require slack variables (omitted for basic implementation)
                 print(f"Warning: Constraint {c_name} has sense {constraint.sense}. Only '==' is fully supported without slack variables in this basic translator.")
                 continue

            b = constraint.rhs
            terms = constraint.linear_terms
            
            # Constant term: weight * b^2
            self.offset += constraint_weight * (b ** 2)
            
            # Linear terms: weight * (a_i^2 - 2 * b * a_i) * x_i
            for v1, a_i in terms.items():
                coeff = constraint_weight * ((a_i ** 2) - 2 * b * a_i)
                self._add_qubo_term(v1, v1, coeff)
                
            # Quadratic terms: weight * 2 * a_i * a_j * x_i * x_j
            var_names = list(terms.keys())
            for i in range(len(var_names)):
                for j in range(i + 1, len(var_names)):
                    v1 = var_names[i]
                    v2 = var_names[j]
                    a_i = terms[v1]
                    a_j = terms[v2]
                    coeff = constraint_weight * 2 * a_i * a_j
                    self._add_qubo_term(v1, v2, coeff)
                    
        # 3. Map Explicit Penalties
        for penalty in self.problem.penalties:
            weight = penalty.weight
            for term, coeff in penalty.terms.items():
                if isinstance(term, str) and term != "offset":
                    self._add_qubo_term(term, term, coeff * weight)
                elif isinstance(term, tuple) and len(term) == 2:
                    self._add_qubo_term(term[0], term[1], coeff * weight)
                elif term == "offset":
                    self.offset += coeff * weight

        return self.qubo_matrix

    def _add_qubo_term(self, v1: str, v2: str, coeff: float):
        if coeff == 0:
            return
        # Canonicalize to upper triangular or just sorted tuple
        term = tuple(sorted([v1, v2]))
        if term in self.qubo_matrix:
            self.qubo_matrix[term] += coeff
        else:
            self.qubo_matrix[term] = coeff

    def get_matrix(self) -> Dict[Tuple[str, str], float]:
        return self.qubo_matrix
