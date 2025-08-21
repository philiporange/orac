# examples.py
#!/usr/bin/env python3
"""
Comprehensive examples demonstrating Orac's full functionality.

This file showcases:
- Basic prompt execution
- Parameter handling with type conversion
- File attachments (local and remote)
- JSON responses and schema validation
- Conversation management
- Multi-step flows
- Skills execution
- Autonomous agents
- Progress tracking
- Multiple LLM providers
- Error handling
- Advanced features
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, List

# Import Orac components
from orac import Prompt, Flow, Skill, Agent
from orac.flow import load_flow, FlowSpec
from orac.skill import load_skill
from orac.agent import load_agent_spec
from orac.registry import ToolRegistry
from orac.config import Config, Provider
from orac.progress import ProgressTracker, create_simple_callback
from orac.conversation_db import ConversationDB


# ============================================================================
# BASIC PROMPT EXECUTION
# ============================================================================

def example_basic_prompt():
    """Basic prompt execution with default parameters."""
    print("\n=== Basic Prompt Execution ===")
    
    # Simple prompt with default parameter
    capital = Prompt("capital")
    result = capital.completion()  # Uses default country: France
    print(f"Default result: {result}")
    
    # With explicit parameter
    result = capital.completion(country="Japan")
    print(f"Japan's capital: {result}")
    
    # Using the callable interface
    result = capital(country="Brazil")
    print(f"Brazil's capital: {result}")


def example_parameter_types():
    """Demonstrate parameter type conversion."""
    print("\n=== Parameter Type Conversion ===")
    
    # Create a test prompt YAML with different parameter types
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        # Create prompt with various parameter types
        (prompts_dir / "type_test.yaml").write_text("""
prompt: |
  Number: ${number}
  Flag: ${flag}
  Ratio: ${ratio}
  Items: ${items}
  
  Process this data accordingly.
parameters:
  - name: number
    type: int
    default: 42
  - name: flag
    type: bool
    default: false
  - name: ratio
    type: float
    default: 0.5
  - name: items
    type: list
    default: "apple,banana,cherry"
""")
        
        # Test with default values
        prompt = Prompt("type_test", prompts_dir=str(prompts_dir))
        result = prompt()
        print("With defaults:", result)
        
        # Test with explicit values (strings that need conversion)
        result = prompt(
            number="100",
            flag="true",
            ratio="0.75",
            items="x,y,z"
        )
        print("With conversions:", result)


# ============================================================================
# FILE ATTACHMENTS
# ============================================================================

def example_file_attachments():
    """Demonstrate file attachment capabilities."""
    print("\n=== File Attachments ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        test_file = Path(tmpdir) / "data.txt"
        test_file.write_text("This is sample data for analysis.")
        
        csv_file = Path(tmpdir) / "data.csv"
        csv_file.write_text("name,value\nAlpha,10\nBeta,20\nGamma,30")
        
        # Create a file analysis prompt
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "analyze_files.yaml").write_text("""
prompt: |
  Analyze the attached files and provide a summary.
  ${instructions}
parameters:
  - name: instructions
    type: string
    default: "Focus on key patterns and insights."
files:
  - "*.txt"
  - "*.csv"
""")
        
        # Attach files via constructor
        analyzer = Prompt(
            "analyze_files",
            prompts_dir=str(prompts_dir),
            files=[str(test_file), str(csv_file)]
        )
        
        result = analyzer(instructions="List all data points found.")
        print(f"File analysis result: {result[:200]}...")
        
        # Test with remote file URLs
        (prompts_dir / "web_content.yaml").write_text("""
prompt: "Summarize the content from the provided URL."
file_urls:
  - https://example.com/sample.txt
""")
        
        # Note: This would download and analyze the remote file
        # web_prompt = Prompt("web_content", prompts_dir=str(prompts_dir))
        # result = web_prompt()


# ============================================================================
# JSON RESPONSES AND VALIDATION
# ============================================================================

def example_json_responses():
    """Demonstrate JSON response handling and schema validation."""
    print("\n=== JSON Responses ===")
    
    # Recipe prompt returns JSON by default
    recipe = Prompt("recipe")
    
    # Method 1: Using completion_as_json
    result = recipe.completion_as_json(dish="pasta")
    print(f"Recipe JSON keys: {list(result.keys())}")
    print(f"Number of ingredients: {len(result.get('ingredients', []))}")
    
    # Method 2: Using callable interface with auto-detection
    result = recipe(dish="tacos")
    print(f"Auto-detected as dict: {isinstance(result, dict)}")
    
    # Method 3: Force JSON parsing
    result = recipe(dish="salad", force_json=True)
    print(f"Forced JSON result type: {type(result)}")
    
    # Schema validation example
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "structured_output.yaml").write_text("""
prompt: "Generate a user profile for ${name}"
parameters:
  - name: name
    type: string
    required: true
response_mime_type: "application/json"
response_schema:
  type: object
  properties:
    name:
      type: string
    age:
      type: integer
    email:
      type: string
      format: email
  required: ["name", "age", "email"]
""")
        
        structured = Prompt("structured_output", prompts_dir=str(prompts_dir))
        profile = structured(name="Alice", force_json=True)
        print(f"Validated profile: {profile}")


# ============================================================================
# CONVERSATION MANAGEMENT
# ============================================================================

def example_conversations():
    """Demonstrate conversation mode with context preservation."""
    print("\n=== Conversation Management ===")
    
    # Create a conversational prompt
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up temporary conversation DB
        db_path = Path(tmpdir) / "conversations.db"
        
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "chat.yaml").write_text("""
prompt: "${message}"
parameters:
  - name: message
    type: string
    required: true
conversation: true
""")
        
        # Start a conversation
        chat = Prompt(
            "chat",
            prompts_dir=str(prompts_dir),
            use_conversation=True,
            conversation_id="example_conv_123"
        )
        
        # First message
        response1 = chat(message="Hi! My name is Alice and I love coding.")
        print(f"Bot: {response1}")
        
        # Follow-up maintains context
        response2 = chat(message="What's my name?")
        print(f"Bot: {response2}")  # Should remember "Alice"
        
        # Check conversation history
        history = chat.get_conversation_history()
        print(f"Conversation has {len(history)} messages")
        
        # List all conversations
        conversations = chat.list_conversations()
        print(f"Total conversations: {len(conversations)}")
        
        # Clean up
        chat.delete_conversation()


# ============================================================================
# MULTI-STEP FLOWS
# ============================================================================

def example_flows():
    """Demonstrate multi-step flow execution."""
    print("\n=== Multi-Step Flows ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir) / "flows"
        flows_dir.mkdir()
        
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        # Create prompts for the flow
        (prompts_dir / "research.yaml").write_text("""
prompt: "Research the topic: ${topic}. Provide 3 key facts."
parameters:
  - name: topic
    type: string
response_mime_type: "application/json"
""")
        
        (prompts_dir / "summarize.yaml").write_text("""
prompt: |
  Based on this research: ${research}
  Create a one-paragraph summary about ${topic}.
parameters:
  - name: research
    type: string
  - name: topic
    type: string
""")
        
        (prompts_dir / "generate_quiz.yaml").write_text("""
prompt: |
  Based on this summary: ${summary}
  Generate 3 quiz questions with answers.
parameters:
  - name: summary
    type: string
response_mime_type: "application/json"
""")
        
        # Create a research flow
        (flows_dir / "research_flow.yaml").write_text("""
name: "Research and Quiz Flow"
description: "Research a topic, summarize it, and create quiz questions"

inputs:
  - name: topic
    type: string
    description: "Topic to research"
    required: true

outputs:
  - name: research_data
    source: research_step.result
    description: "Raw research data"
  - name: summary
    source: summarize_step.result
    description: "Summary paragraph"
  - name: quiz
    source: quiz_step.result
    description: "Quiz questions"

steps:
  research_step:
    prompt: research
    inputs:
      topic: ${inputs.topic}
    outputs:
      - result

  summarize_step:
    prompt: summarize
    depends_on: [research_step]
    inputs:
      research: ${research_step.result}
      topic: ${inputs.topic}
    outputs:
      - result

  quiz_step:
    prompt: generate_quiz
    depends_on: [summarize_step]
    inputs:
      summary: ${summarize_step.result}
    outputs:
      - result
""")
        
        # Load and execute the flow
        flow_spec = load_flow(flows_dir / "research_flow.yaml")
        
        # Add progress tracking
        tracker = ProgressTracker()
        flow_engine = Flow(
            flow_spec,
            prompts_dir=str(prompts_dir),
            progress_callback=tracker.track
        )
        
        # Execute with progress tracking
        results = flow_engine.execute({"topic": "quantum computing"})
        
        print(f"Research data type: {type(results['research_data'])}")
        print(f"Summary length: {len(results['summary'])} chars")
        print(f"Quiz questions: {len(results.get('quiz', {}).get('questions', []))}")
        
        # Show progress summary
        summary = tracker.to_summary()
        print(f"Flow completed in {summary['duration_seconds']:.2f} seconds")


# ============================================================================
# SKILLS EXECUTION
# ============================================================================

def example_skills():
    """Demonstrate skill execution."""
    print("\n=== Skills Execution ===")
    
    # Use the built-in calculator skill
    calc_spec = load_skill(Config.DEFAULT_SKILLS_DIR / "calculator.yaml")
    calculator = Skill(calc_spec)
    
    # Simple calculation
    result = calculator.execute({"expression": "2 + 2"})
    print(f"2 + 2 = {result['result']}")
    
    # Complex calculation
    result = calculator.execute({
        "expression": "sqrt(16) + 3^2 - sin(0)",
        "precision": 4
    })
    print(f"Complex calculation: {result['result']}")
    print(f"Expression tree: {result['expression_tree']}")
    
    # Create a custom skill
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        
        # Skill specification
        (skills_dir / "text_stats.yaml").write_text("""
name: text_stats
description: Calculate statistics about text
version: 1.0.0
inputs:
  - name: text
    type: string
    description: Text to analyze
    required: true
  - name: include_words
    type: bool
    description: Include word list
    default: false
outputs:
  - name: char_count
    type: int
    description: Number of characters
  - name: word_count
    type: int
    description: Number of words
  - name: words
    type: list
    description: List of words (if requested)
""")
        
        # Skill implementation
        (skills_dir / "text_stats.py").write_text("""
def execute(inputs):
    text = inputs['text']
    include_words = inputs.get('include_words', False)
    
    words = text.split()
    
    result = {
        'char_count': len(text),
        'word_count': len(words)
    }
    
    if include_words:
        result['words'] = words
    
    return result
""")
        
        # Execute custom skill
        stats_spec = load_skill(skills_dir / "text_stats.yaml")
        text_stats = Skill(stats_spec, skills_dir=str(skills_dir))
        
        result = text_stats.execute({
            "text": "The quick brown fox jumps over the lazy dog",
            "include_words": True
        })
        
        print(f"Text stats: {result}")


# ============================================================================
# AUTONOMOUS AGENTS
# ============================================================================

def example_agents():
    """Demonstrate autonomous agent execution."""
    print("\n=== Autonomous Agents ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up directories
        agents_dir = Path(tmpdir) / "agents"
        agents_dir.mkdir()
        
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        
        # Create tools for the agent
        (prompts_dir / "weather.yaml").write_text("""
prompt: "What's the weather like in ${city}?"
parameters:
  - name: city
    type: string
""")
        
        (prompts_dir / "news.yaml").write_text("""
prompt: "What are the top news headlines about ${topic}?"
parameters:
  - name: topic
    type: string
""")
        
        # Copy finish skill
        (skills_dir / "finish.yaml").write_text("""
name: finish
description: Signal completion with final answer
inputs:
  - name: result
    type: string
    required: true
outputs:
  - name: result
    type: string
""")
        
        (skills_dir / "finish.py").write_text("""
def execute(inputs):
    return {"result": inputs["result"]}
""")
        
        # Create a travel planning agent
        (agents_dir / "travel_agent.yaml").write_text("""
name: travel_agent
description: An agent that helps plan trips
inputs:
  - name: destination
    type: string
    required: true
    description: Travel destination
  - name: interests
    type: string
    required: true
    description: Traveler's interests
tools:
  - "prompt:weather"
  - "prompt:news"
  - "tool:finish"
model_name: gemini-2.0-flash
generation_config:
  temperature: 0.7
  response_mime_type: application/json
max_iterations: 5
system_prompt: |
  You are a travel planning agent. Your goal is to help plan a trip to ${destination} 
  for someone interested in ${interests}.
  
  You have access to these tools:
  ${tool_list}
  
  Research the destination by:
  1. Checking the weather
  2. Finding relevant news or events
  3. Providing personalized recommendations
  
  Respond with JSON:
  {
    "thought": "your reasoning",
    "tool": "tool_type:tool_name",
    "inputs": {"param": "value"}
  }
  
  When done, use tool:finish with a comprehensive travel plan.
""")
        
        # Set up and run the agent
        agent_spec = load_agent_spec(agents_dir / "travel_agent.yaml")
        registry = ToolRegistry(
            prompts_dir=str(prompts_dir),
            tools_dir=str(skills_dir)
        )
        
        # Assuming provider is set
        provider = Provider(os.getenv("ORAC_LLM_PROVIDER", "google"))
        
        agent = Agent(agent_spec, registry, provider)
        
        # Run agent (would make actual API calls)
        # result = agent.run(
        #     destination="Tokyo",
        #     interests="technology and cuisine"
        # )
        # print(f"Travel plan: {result}")
        
        print("Agent created successfully (execution skipped to avoid API calls)")


# ============================================================================
# PROGRESS TRACKING
# ============================================================================

def example_progress_tracking():
    """Demonstrate progress tracking capabilities."""
    print("\n=== Progress Tracking ===")
    
    # Create a simple progress callback
    def custom_progress_callback(event):
        """Custom progress handler that formats output nicely."""
        emoji_map = {
            "prompt_start": "🚀",
            "prompt_complete": "✅",
            "flow_start": "🔄",
            "flow_step_start": "📝",
            "flow_complete": "🎉",
            "error": "❌"
        }
        
        emoji = emoji_map.get(event.type.value, "▶")
        timestamp = event.timestamp.strftime("%H:%M:%S")
        
        if event.progress_percentage:
            print(f"{emoji} [{timestamp}] {event.message} ({event.progress_percentage:.0f}%)")
        else:
            print(f"{emoji} [{timestamp}] {event.message}")
    
    # Use progress tracking with a prompt
    capital = Prompt("capital", progress_callback=custom_progress_callback)
    result = capital(country="France")
    
    # Progress tracking with ProgressTracker
    tracker = ProgressTracker()
    
    recipe = Prompt("recipe", progress_callback=tracker.track)
    result = recipe(dish="pizza")
    
    # Analyze tracked events
    print(f"\nTracked {len(tracker.events)} events")
    print(f"Total duration: {tracker.duration:.2f}s")
    
    # Get specific event types
    starts = tracker.get_events_by_type(ProgressType.PROMPT_START)
    print(f"Number of prompt starts: {len(starts)}")


# ============================================================================
# PROVIDER SWITCHING
# ============================================================================

def example_provider_switching():
    """Demonstrate using different LLM providers."""
    print("\n=== Provider Switching ===")
    
    # Example with different providers (requires API keys)
    providers_config = {
        Provider.GOOGLE: {
            "api_key": os.getenv("GOOGLE_API_KEY"),
            "model": "gemini-2.0-flash"
        },
        Provider.OPENAI: {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "model": "gpt-4-turbo"
        },
        Provider.ANTHROPIC: {
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "model": "claude-3-sonnet"
        }
    }
    
    # Test with each provider
    for provider, config in providers_config.items():
        if config["api_key"]:
            print(f"\nTesting with {provider.value}:")
            
            prompt = Prompt(
                "capital",
                provider=provider,
                api_key=config["api_key"],
                model_name=config["model"]
            )
            
            # result = prompt(country="Spain")
            # print(f"{provider.value} says: {result}")
            
            print(f"✓ {provider.value} configured successfully")
        else:
            print(f"✗ {provider.value} - No API key found")


# ============================================================================
# ERROR HANDLING
# ============================================================================

def example_error_handling():
    """Demonstrate error handling patterns."""
    print("\n=== Error Handling ===")
    
    # Missing required parameter
    try:
        capital = Prompt("capital")
        # This would fail if 'country' was required without default
        result = capital()
    except ValueError as e:
        print(f"Parameter error handled: {e}")
    
    # Invalid JSON response
    try:
        capital = Prompt("capital")
        result = capital.completion_as_json(country="France")
    except json.JSONDecodeError:
        print("JSON decode error handled - capital returns plain text")
    
    # File not found
    try:
        prompt = Prompt("nonexistent_prompt")
    except FileNotFoundError as e:
        print(f"File not found error handled: {e}")
    
    # Flow validation error
    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir) / "flows"
        flows_dir.mkdir()
        
        # Create flow with circular dependency
        (flows_dir / "circular.yaml").write_text("""
name: "Circular Flow"
steps:
  step1:
    prompt: test
    depends_on: [step2]
  step2:
    prompt: test
    depends_on: [step1]
""")
        
        try:
            flow_spec = load_flow(flows_dir / "circular.yaml")
            flow = Flow(flow_spec)
        except Exception as e:
            print(f"Flow validation error handled: {e}")


# ============================================================================
# ADVANCED FEATURES
# ============================================================================

def example_advanced_features():
    """Demonstrate advanced Orac features."""
    print("\n=== Advanced Features ===")
    
    # 1. Direct YAML file loading
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode='w', delete=False) as f:
        f.write("""
prompt: "Translate '${text}' to ${language}"
parameters:
  - name: text
    type: string
    required: true
  - name: language
    type: string
    default: Spanish
""")
        yaml_path = f.name
    
    # Load prompt directly from path
    translator = Prompt(yaml_path)
    result = translator(text="Hello world", language="French")
    print(f"Translation: {result}")
    os.unlink(yaml_path)
    
    # 2. Complex generation config
    recipe = Prompt(
        "recipe",
        generation_config={
            "temperature": 0.8,
            "max_tokens": 500,
            "top_p": 0.95,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5
        }
    )
    result = recipe(dish="creative fusion cuisine")
    print(f"Creative recipe generated with custom params")
    
    # 3. Flow with conditional steps (future feature demo)
    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir) / "flows"
        flows_dir.mkdir()
        
        (flows_dir / "conditional.yaml").write_text("""
name: "Conditional Flow"
description: "Flow with conditional execution"

inputs:
  - name: analyze_deeply
    type: bool
    default: false

outputs:
  - name: result
    source: final_step.result

steps:
  initial_step:
    prompt: capital
    inputs:
      country: France
    outputs:
      - result

  deep_analysis:
    prompt: capital
    inputs:
      country: Germany
    depends_on: [initial_step]
    when: ${inputs.analyze_deeply}
    outputs:
      - result

  final_step:
    prompt: capital
    inputs:
      country: Italy
    depends_on: [initial_step]
    outputs:
      - result
""")
        
        # Note: 'when' conditions are marked as future feature
        print("Conditional flow example created (execution depends on feature support)")
    
    # 4. Parallel API calls with progress
    class ParallelProgressReporter:
        """Custom progress reporter for parallel operations."""
        def __init__(self):
            self.active_operations = {}
        
        def report(self, event):
            if event.type.value.endswith("_start"):
                self.active_operations[event.step_name] = event.timestamp
                print(f"⚡ Started: {event.step_name}")
            elif event.type.value.endswith("_complete"):
                if event.step_name in self.active_operations:
                    duration = (event.timestamp - self.active_operations[event.step_name]).total_seconds()
                    print(f"✓ Completed: {event.step_name} ({duration:.2f}s)")
    
    # Use custom reporter
    reporter = ParallelProgressReporter()
    capital = Prompt("capital", progress_callback=reporter.report)
    # Would show parallel execution if used in a flow


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run all examples."""
    print("=" * 60)
    print("ORAC COMPREHENSIVE EXAMPLES")
    print("=" * 60)
    
    # Check if provider is set
    if not os.getenv("ORAC_LLM_PROVIDER"):
        print("\n⚠️  Warning: ORAC_LLM_PROVIDER not set")
        print("Set it with: export ORAC_LLM_PROVIDER=google")
        print("Also ensure you have the appropriate API key set")
        return
    
    examples = [
        ("Basic Prompt Execution", example_basic_prompt),
        ("Parameter Types", example_parameter_types),
        ("File Attachments", example_file_attachments),
        ("JSON Responses", example_json_responses),
        ("Conversations", example_conversations),
        ("Multi-step Flows", example_flows),
        ("Skills", example_skills),
        ("Autonomous Agents", example_agents),
        ("Progress Tracking", example_progress_tracking),
        ("Provider Switching", example_provider_switching),
        ("Error Handling", example_error_handling),
        ("Advanced Features", example_advanced_features),
    ]
    
    # Run examples
    for name, func in examples:
        try:
            print(f"\n{'=' * 60}")
            print(f"Running: {name}")
            print('=' * 60)
            func()
        except Exception as e:
            print(f"❌ Example failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Ensure we're in the project directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Run examples
    main()
