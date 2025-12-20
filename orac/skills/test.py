"""
Test execution skill using coding agents.

Runs a list of requirements as tests using a coding agent (Claude Code by default)
and returns structured PASS/FAIL results for each requirement.

The coding agent is prompted to:
1. Examine the codebase
2. Run appropriate tests or checks for each requirement
3. Return structured JSON results
"""

import json
import re
from typing import Dict, Any, List

from orac.skills.code import execute as code_execute


TEST_PROMPT_TEMPLATE = '''You are a testing agent. Verify each of the following requirements against the codebase.

For each requirement:
1. Examine the relevant code
2. Run tests, type checks, or other verification as appropriate
3. Determine if the requirement is satisfied

{context_section}

Requirements to verify:
{requirements_list}

Respond with ONLY a JSON array, one object per requirement, in this exact format:
```json
[
  {{"requirement": "requirement text", "status": "PASS"}},
  {{"requirement": "requirement text", "status": "FAIL", "info": "explanation of what failed"}}
]
```

Rules:
- status must be exactly "PASS" or "FAIL"
- info is required for FAIL, optional for PASS
- Verify requirements in order
- Be thorough but concise in failure explanations
'''


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute tests against a list of requirements.

    Args:
        inputs: Dictionary containing:
            - requirements (list): List of requirement strings to test
            - working_directory (str): Directory containing code to test
            - context (str, optional): Additional context
            - agent (str, optional): Coding agent to use
            - model (str, optional): Model to use
            - api_endpoint (str, optional): Custom API endpoint
            - api_key (str, optional): API key

    Returns:
        Dictionary containing:
            - results (list): Test results with status and optional info
            - summary (dict): Counts of passed/failed/total
            - all_passed (bool): Whether all tests passed
    """
    requirements = inputs['requirements']
    working_directory = inputs['working_directory']
    context = inputs.get('context')
    agent = inputs.get('agent', 'claude_code')
    model = inputs.get('model', 'sonnet')
    api_endpoint = inputs.get('api_endpoint')
    api_key = inputs.get('api_key')

    if not requirements:
        return {
            'results': [],
            'summary': {'passed': 0, 'failed': 0, 'total': 0},
            'all_passed': True
        }

    # Build the test prompt
    prompt = _build_prompt(requirements, context)

    # Execute via the code skill
    code_result = code_execute({
        'prompt': prompt,
        'working_directory': working_directory,
        'agent': agent,
        'model': model,
        'api_endpoint': api_endpoint,
        'api_key': api_key,
        'system_addendum': 'Always respond with valid JSON. No markdown formatting around the JSON.'
    })

    # Parse the results
    raw_output = code_result['result']
    results = _parse_results(raw_output, requirements)

    # Calculate summary
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')

    return {
        'results': results,
        'summary': {
            'passed': passed,
            'failed': failed,
            'total': len(results)
        },
        'all_passed': failed == 0
    }


def _build_prompt(requirements: List[str], context: str | None) -> str:
    """Build the test prompt."""
    # Format requirements as numbered list
    requirements_list = "\n".join(
        f"{i+1}. {req}" for i, req in enumerate(requirements)
    )

    # Add context section if provided
    context_section = ""
    if context:
        context_section = f"Context:\n{context}\n"

    return TEST_PROMPT_TEMPLATE.format(
        context_section=context_section,
        requirements_list=requirements_list
    )


def _parse_results(raw_output: str, requirements: List[str]) -> List[Dict[str, Any]]:
    """Parse the JSON results from the coding agent."""
    # Try to extract JSON from the output
    json_match = re.search(r'\[[\s\S]*\]', raw_output)

    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                return _normalize_results(parsed, requirements)
        except json.JSONDecodeError:
            pass

    # If parsing fails, create error results for all requirements
    return [
        {
            'requirement': req,
            'status': 'FAIL',
            'info': f'Failed to parse test results. Raw output: {raw_output[:200]}...'
        }
        for req in requirements
    ]


def _normalize_results(parsed: List[Dict], requirements: List[str]) -> List[Dict[str, Any]]:
    """Normalize parsed results to ensure consistent format."""
    results = []

    for i, req in enumerate(requirements):
        if i < len(parsed):
            item = parsed[i]
            status = item.get('status', 'FAIL').upper()
            if status not in ('PASS', 'FAIL'):
                status = 'FAIL'

            result = {
                'requirement': req,
                'status': status
            }

            # Add info if present or if failed
            if 'info' in item:
                result['info'] = item['info']
            elif status == 'FAIL' and 'info' not in item:
                result['info'] = 'No failure details provided'

            results.append(result)
        else:
            # Requirement not covered in results
            results.append({
                'requirement': req,
                'status': 'FAIL',
                'info': 'Requirement was not evaluated by the testing agent'
            })

    return results
