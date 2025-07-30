from typing import Dict, Any

def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    This skill acts as a signal for the agent to finish its task.
    It simply returns the provided result.
    """
    return {"result": inputs.get("result", "No result provided.")}