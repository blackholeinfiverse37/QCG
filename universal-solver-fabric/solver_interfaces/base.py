from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseSolverAdapter(ABC):
    """
    The BaseSolverAdapter defines the fundamental contract for how the 
    Universal Solver Fabric communicates with specific optimization engines.
    """
    
    @abstractmethod
    def bind_problem(self, problem: Dict[str, Any]) -> None:
        """
        Translates the fabric's agnostic problem definition into the solver's 
        native structure.
        """
        pass

    @abstractmethod
    def execute(self, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes the optimization process. Must return a standardized result 
        dictionary including solution, convergence status, confidence score, 
        and replay metadata.
        """
        pass

    @abstractmethod
    def get_health(self) -> str:
        """
        Returns the operational health of the solver engine.
        """
        pass
