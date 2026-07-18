# Mandatory Research References

This document maps the architectural concepts in the BHIV Quantum Optimization Compiler framework to established literature in quantum computing and operations research.

## 1. QUBO Formulations and Ising Models
*   **Glover, F., Kochenberger, G., & Du, Y. (2019).** *Quantum Bridge Analytics I: A Tutorial on Formulating and Using QUBO Models.* Annals of Operations Research, 314(1), 141-183.
    *   **Mapping:** Serves as the foundation for `qubo_translation.py`, demonstrating how to convert linear inequalities into unconstrained quadratic penalty functions.
*   **Lucas, A. (2014).** *Ising formulations of many NP problems.* Frontiers in Physics, 2, 5.
    *   **Mapping:** The definitive guide for translating NP-hard operational problems (like Traveling Salesperson and Graph Coloring) into the Ising models natively solved by quantum annealers.

## 2. Quantum Annealing
*   **McGeoch, C. C. (2014).** *Adiabatic Quantum Computation and Quantum Annealing: Theory and Practice.* Synthesis Lectures on Quantum Computing.
    *   **Mapping:** Informs the limitations and scaling considerations in `QUBO_REPORT.md`, specifically regarding graph embedding and analog precision limits on D-Wave hardware.
*   **Yarkoni, S., Raponi, E., Bäck, T., & Schmitt, S. (2022).** *Quantum Annealing for Industry Applications: Introduction and Review.* Reports on Progress in Physics.
    *   **Mapping:** Justifies the use cases in the `QUANTUM_SOLVER_EVALUATION.md` and provides the structural basis for comparing annealers against classical MIP solvers.

## 3. Gate-Based Optimization (QAOA)
*   **Farhi, E., Goldstone, J., & Gutmann, S. (2014).** *A Quantum Approximate Optimization Algorithm.* arXiv:1411.4028.
    *   **Mapping:** Contextualizes the gate-based solver evaluation (IBM, IonQ), establishing QAOA as the primary algorithm for running combinatorial optimization on universal NISQ devices.

## 4. Hybrid Quantum-Classical Optimization
*   **Bausch, J. (2020).** *Quantum algorithms for combinatorial optimization.* In Quantum Computing for Operations Research.
    *   **Mapping:** Provides the theoretical backing for the hybrid approach in the `BHIV_OPERATIONAL_INTELLIGENCE_CASE_STUDY.md`.
*   **Festa, P., & Resende, M. G. (2011).** *Hybrid Heuristics for Combinatorial Optimization.*
    *   **Mapping:** Influences the architectural design in `QUANTUM_RUNTIME_INTEGRATION.md`, emphasizing that quantum systems act best as co-processors handling the hardest computational sub-graphs while classical systems manage state, bounds, and heuristics.
