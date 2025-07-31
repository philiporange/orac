import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import yaml
import json

# Adjust path to import from the project root
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orac.agent import AgentSpec, Agent, load_agent_spec
from orac.registry import ToolRegistry
from orac.config import Provider

class TestAgent(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for agent specs and tools
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create dummy prompt and tool for the registry
        (self.temp_path / "prompts").mkdir()
        (self.temp_path / "skills").mkdir()
        
        with open(self.temp_path / "prompts" / "dummy_prompt.yaml", "w") as f:
            yaml.dump({
                "name": "dummy_prompt",
                "description": "A dummy prompt.",
                "prompt": "Say ${word}",
                "parameters": [{"name": "word", "type": "string"}]
            }, f)
            
        with open(self.temp_path / "skills" / "finish.yaml", "w") as f:
             yaml.dump({"name": "finish", "description": "Finish tool"}, f)

        # Create a dummy agent spec
        self.agent_spec_data = {
            "name": "Test Agent",
            "description": "An agent for testing.",
            "system_prompt": "Your goal is ${goal}. Tools: ${tool_list}",
            "inputs": [{"name": "goal", "type": "string", "required": True}],
            "tools": ["prompt:dummy_prompt", "tool:finish"],
            "max_iterations": 2,
            "model_name": "test-model",
            "generation_config": {"response_mime_type": "application/json"}
        }
        self.agent_spec = AgentSpec(**self.agent_spec_data)
        
        # Setup registry and engine
        self.registry = ToolRegistry(
            prompts_dir=str(self.temp_path / "prompts"),
            tools_dir=str(self.temp_path / "skills")
        )
        self.engine = Agent(self.agent_spec, self.registry, Provider.CUSTOM)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('orac.agent.call_api')
    @patch('orac.agent.Prompt')
    def test_run_loop_and_tool_execution(self, MockPrompt, mock_call_api):
        # Mock the LLM to return a specific action
        mock_call_api.return_value = json.dumps({
            "thought": "I should use the dummy prompt.",
            "tool": "prompt:dummy_prompt",
            "inputs": {"word": "hello"}
        })
        
        # Mock the Prompt instance that gets created for the prompt
        mock_prompt_instance = MockPrompt.return_value
        mock_prompt_instance.completion.return_value = "The prompt said hello."
        
        # Mock a second LLM call that decides to finish
        final_answer = "I have the answer."
        mock_call_api.side_effect = [
            json.dumps({
                "thought": "I should use the dummy prompt.",
                "tool": "prompt:dummy_prompt",
                "inputs": {"word": "hello"}
            }),
            json.dumps({
                "thought": "I am done.",
                "tool": "tool:finish",
                "inputs": {"result": final_answer}
            })
        ]

        # Run the agent
        result = self.engine.run(goal="Test the loop")
        
        # Assertions
        self.assertEqual(result, final_answer)
        
        # Check that the Prompt (prompt) tool was called correctly
        MockPrompt.assert_called_once_with(
            'dummy_prompt', 
            prompts_dir=self.registry.prompts_dir, 
            provider=Provider.CUSTOM.value,
            api_key=None
        )
        mock_prompt_instance.completion.assert_called_with(word="hello")
        
        # Check that an observation was added to the history
        # The history should contain: model response, user observation, model response (finish)
        # So the observation should be at index -2
        if len(self.engine.message_history) >= 2:
            observation_message = self.engine.message_history[-2]
            self.assertEqual(observation_message['role'], 'user')
            self.assertIn("The prompt said hello.", observation_message['text'])


if __name__ == '__main__':
    unittest.main()