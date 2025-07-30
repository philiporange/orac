# Orac

![Orac Logo](assets/orac_logo.png)

**Orac** is a lightweight, YAML-driven framework for working with OpenAI-compatible LLM APIs. It provides clean abstractions, intuitive command-line interface, structured parameter handling, and support for both local and remote file attachments.

---

## Features

* **Prompt-as-config**: Define entire LLM tasks in YAML, including prompt text, parameters, default values, model settings, and file attachments.
* **Flow orchestration**: Chain multiple prompts together with data flow and dependency management. Perfect for complex multi-step AI workflows.
* **Hierarchical configuration**: Three-layer config system (base → prompt → runtime) with deep merging for flexible overrides.
* **Templated inputs**: Use `${variable}` placeholders in prompt and system prompt fields.
* **File support**: Attach local or remote files (e.g., images, documents) via `files:` or `file_urls:` in YAML or CLI flags.
* **Conversation mode**: Automatic context preservation with SQLite-based history. Enable with `conversation: true` in YAML for seamless multi-turn interactions.
* **Intuitive CLI**: Modern resource-action command structure with excellent discoverability and help system.
* **Python API**: Full programmatic access via the `Orac` class for integration into applications.
* **Runtime configuration overrides**: Override model settings, API keys, generation options, and safety filters from the CLI or programmatically.
* **Structured output support**: Request `application/json` responses or validate against a JSON Schema.
* **Parameter validation**: Automatically convert and validate inputs by type.
* **Comprehensive logging**: Logs all operations to file and provides optional verbose console output.

---

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Setup

1. **Set your LLM provider and API key**:
   ```bash
   export ORAC_LLM_PROVIDER=google
   export GOOGLE_API_KEY=your_api_key_here
   ```

2. **Run your first prompt**:
   ```bash
   orac prompt run capital --country France
   # Output: Paris
   ```

3. **Discover what's available**:
   ```bash
   orac prompt list        # List all available prompts
   orac flow list          # List all available flows
   orac --help             # Show all commands
   ```

---

## Command Structure

Orac uses an intuitive **resource-action** pattern that makes commands predictable and discoverable:

```bash
orac <resource> <action> [arguments] [flags]
```

### Core Resources

#### **Prompts** - Single AI interactions
```bash
# Execute prompts
orac prompt run capital --country France
orac prompt run recipe --dish cookies --json-output

# Discover and explore prompts  
orac prompt list                        # List all available prompts
orac prompt show capital                # Show prompt details & parameters
orac prompt validate capital            # Validate prompt YAML
```

#### **Flows** - Multi-step AI workflows
```bash
# Execute flows (formerly called workflows)
orac flow run research_assistant --topic "AI ethics"
orac flow run capital_recipe --country Italy

# Discover and explore flows
orac flow list                          # List all flows
orac flow show research_assistant       # Show flow structure
orac flow graph research_assistant      # Show dependency graph
orac flow test research_assistant       # Dry-run validation
```

#### **Chat** - Interactive conversations
```bash
# Interactive conversations
orac chat send "What is machine learning?"
orac chat send "Give me an example" --conversation-id work

# Interactive curses-based chat interface
orac chat interactive                   # Start interactive chat with curses UI
orac chat interactive --conversation-id work  # Continue specific conversation

# Conversation management
orac chat list                          # List all conversations
orac chat show work                     # Show conversation history
orac chat delete work                   # Delete conversation
```

#### **Agents** - Autonomous agents for complex tasks
```bash
# Execute an agent
orac agent run research_agent --topic "quantum computing"
orac agent run geo_cuisine_agent --country "Japan"

# Discover and explore agents
orac agent list                         # List all agents
orac agent show research_agent          # Show agent details
```

#### **Configuration** - System management
```bash
# Configuration
orac config show                        # Show current configuration
orac config set provider google         # Set default provider
orac config set model gemini-2.0-flash  # Set default model

# Authentication
orac auth login google                  # Set up Google API key
orac auth status                        # Show auth status
```

#### **Global Discovery**
```bash
# Discover everything
orac list                              # List all prompts and flows
orac search "image"                    # Search by keyword
orac --help                            # Show all available commands
```

### Command Shortcuts

For frequently used operations, Orac provides convenient shortcuts:

```bash
# Shortcut aliases (optional, for power users)
orac run capital --country France      # → orac prompt run capital --country France
orac flow research --topic AI          # → orac flow run research --topic AI
orac ask "hello"                       # → orac chat send "hello"
orac interactive                       # → orac chat interactive

# Ultra-short aliases for power users
orac r capital --country France        # → orac prompt run capital --country France
orac f research --topic AI             # → orac flow run research --topic AI
orac c "hello"                         # → orac chat send "hello"
orac i                                 # → orac chat interactive
```

---

## Configuration

### Environment Variables

Orac supports configuration through environment variables. You can either set them directly or use a `.env` file:

1. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your settings**:
   ```bash
   # API Keys
   GOOGLE_API_KEY=your_google_api_key_here
   OPENAI_API_KEY=your_openai_api_key_here

   # Configuration overrides (optional)
   ORAC_DEFAULT_MODEL_NAME=gemini-2.0-flash
   ORAC_LOG_FILE=./llm.log
   ```

3. **Or set environment variables directly**:
   ```bash
   export ORAC_LLM_PROVIDER="google"
   export GOOGLE_API_KEY="your_api_key_here"
   export ORAC_DEFAULT_MODEL_NAME="gemini-2.0-flash"
   ```

### Choosing an LLM Provider

**Orac requires explicit provider selection**. You must specify which LLM provider to use either via environment variable or CLI flag:

| Provider      | `ORAC_LLM_PROVIDER` | API Key Environment Variable | Default Base URL                           |
| ------------- | ------------------- | --------------------------- | ------------------------------------------ |
| Google Gemini | `google`            | `GOOGLE_API_KEY`            | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| OpenAI        | `openai`            | `OPENAI_API_KEY`            | `https://api.openai.com/v1/`               |
| Anthropic     | `anthropic`         | `ANTHROPIC_API_KEY`         | `https://api.anthropic.com/v1/`            |
| Azure OpenAI  | `azure`             | `AZURE_OPENAI_KEY`          | `${AZURE_OPENAI_BASE}` (user-set)         |
| OpenRouter    | `openrouter`        | `OPENROUTER_API_KEY`        | `https://openrouter.ai/api/v1/`            |
| Custom        | `custom`            | *user picks*                | *user sets via `--base-url`*              |

**Examples:**

```bash
# Using Google Gemini
export ORAC_LLM_PROVIDER=google
export GOOGLE_API_KEY=your_google_api_key
orac prompt run capital --country France

# Using OpenAI
export ORAC_LLM_PROVIDER=openai
export OPENAI_API_KEY=your_openai_api_key
orac prompt run capital --country Spain

# Using CLI flags instead of environment variables
orac prompt run capital --provider google --api-key your_api_key --country Italy

# Using a custom endpoint
orac prompt run capital --provider custom --base-url https://my-custom-api.com/v1/ --api-key your_key --country Germany
```

---

## Example Usage

### 1. Basic Prompt Execution

Save the following to `prompts/capital.yaml`:

```yaml
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    description: Country name
    default: France
```

Then run:

```bash
orac prompt run capital                    # Uses default: France → "Paris"
orac prompt run capital --country Japan    # → "Tokyo"
orac prompt show capital                   # Show prompt details
```

### 2. Interactive Conversations

Orac includes built-in conversation support:

```bash
# These automatically maintain conversation context
orac chat send "What is machine learning?"
orac chat send "Give me a simple example"
orac chat send "How do I get started?"

# Use specific conversation IDs for multiple parallel conversations
orac chat send "Help me code" --conversation-id work
orac chat send "Plan vacation" --conversation-id personal
```

### 3. Multi-step Flows

Create flows that chain multiple prompts together:

```bash
# List available flows
orac flow list

# Execute a flow
orac flow run capital_recipe --country Italy

# Show flow structure before running
orac flow show research_assistant
orac flow run research_assistant --topic "AI ethics"
```

### 4. Advanced Usage

```bash
# Override model and configuration
orac prompt run capital --country "Canada" \
  --model-name "gemini-2.5-flash" \
  --generation-config '{"temperature": 0.4}'

# Structured JSON responses
orac prompt run recipe --json-output

# Schema validation
orac prompt run capital --country "Germany" \
  --response-schema schemas/capital.schema.json

# Attach local and remote files
orac prompt run paper2audio \
  --file reports/report.pdf \
  --file-url https://example.com/image.jpg
```

### 5. Discovery and Help

```bash
# Discover available prompts and flows
orac list                              # Show everything
orac prompt list                       # Show only prompts
orac flow list                         # Show only flows

# Get detailed help
orac prompt show capital               # Show prompt parameters
orac flow show research_assistant      # Show flow structure
orac --help                           # Show all available commands

# Search by keyword
orac search "translate"               # Find translation-related prompts/flows
```

### 6. Autonomous Agents

Create agents that can reason and use tools to accomplish complex goals.

**File:** `orac/agents/geo_cuisine_agent.yaml`
```yaml
name: geo_cuisine_agent
description: An agent that finds the capital of a country and a traditional recipe.
inputs:
  - name: country
    type: string
    required: true
tools:
  - "prompt:capital"
  - "prompt:recipe"
  - "tool:finish"
system_prompt: |
  You are Geo-Cuisine Agent... (and so on)
```

Then, run the agent from the command line:

```bash
orac agent run geo_cuisine_agent --country "Thailand"
```

The agent will show its thought process and tool usage, ultimately producing a result like:
*The capital of Thailand is Bangkok. A traditional recipe you can try is Pad Thai...*

---

## Python API

While the CLI provides an excellent user experience, you can also use Orac programmatically:

```python
from orac import Orac

# Basic text completion
llm = Orac("capital")
print(llm.completion())  # Defaults to France → "Paris"
print(llm.completion(country="Japan"))  # → "Tokyo"

# JSON-returning prompts with automatic detection
recipe_llm = Orac("recipe")
result = recipe_llm(dish="cookies")  # Automatically returns dict (JSON detected)

# Force JSON parsing (raises exception if not valid JSON)
json_result = recipe_llm(dish="pasta", force_json=True)  # Returns dict

# Explicit JSON parsing
json_data = recipe_llm.completion_as_json(dish="pizza")  # Returns dict

# Conversation mode
chat = Orac("chat", use_conversation=True)
print(chat("Hello! What's 15 + 25?"))      # → "40"
print(chat("Times 3?"))                     # → "120" (maintains context)
```

---

## YAML Prompt Reference

### Basic YAML

```yaml
prompt: "Translate the following text: ${text}"
parameters:
  - name: text
    type: string
    required: true
```

### Advanced YAML Features

```yaml
model_name: gemini-2.0-flash
api_key: ${OPENAI_API_KEY}

generation_config:
  temperature: 0.5
  max_tokens: 300

safety_settings:
  - category: HARM_CATEGORY_HARASSMENT
    threshold: BLOCK_NONE

response_mime_type: application/json
response_schema:
  type: object
  properties:
    translation: { type: string }

files:
  - data/*.pdf
file_urls:
  - https://example.com/image.jpg

require_file: true

# Conversation mode settings
conversation: true                # Enable conversation mode by default
```

### Flow YAML Structure

Flows (formerly workflows) chain multiple prompts together:

```yaml
# flows/capital_recipe.yaml
name: "Capital City Recipe"
description: "Get capital city and suggest a traditional recipe"

inputs:
  - name: country
    type: string
    description: "Name of the country"
    required: true

outputs:
  - name: capital_city
    source: get_capital.result
  - name: traditional_dish
    source: suggest_recipe.result

steps:
  get_capital:
    prompt: capital
    inputs:
      country: ${inputs.country}
    outputs:
      - result

  suggest_recipe:
    prompt: recipe
    depends_on: [get_capital]
    inputs:
      dish: "traditional ${inputs.country} cuisine"
    outputs:
      - result
```

---

## CLI Reference

### Global Flags

All commands support these global flags:

* `--verbose`, `-v`: Enable verbose logging
* `--quiet`, `-q`: Suppress progress output (only show errors)
* `--help`, `-h`: Show help for any command
* `--provider PROVIDER`: Override LLM provider
* `--api-key KEY`: Override API key
* `--model-name MODEL`: Override model name
* `--output FILE`, `-o`: Write output to file

### Resource-Specific Flags

#### Prompt Commands
* `--json-output`: Format response as JSON
* `--response-schema FILE`: Validate against JSON schema
* `--file FILE`: Attach local file
* `--file-url URL`: Attach remote file
* `--generation-config JSON`: Override generation settings

#### Flow Commands
* `--dry-run`: Show execution plan without running
* `--json-output`: Format final output as JSON

#### Chat Commands
* `--conversation-id ID`: Use specific conversation
* `--reset-conversation`: Reset conversation before sending
* `--no-save`: Don't save message to conversation history

---

## Migration Guide

### From Old CLI Structure

If you're upgrading from the old CLI structure, here's how commands map:

| Old Command | New Command |
|-------------|-------------|
| `orac capital --country France` | `orac prompt run capital --country France` |
| `orac workflow run research_assistant` | `orac flow run research_assistant` |
| `orac chat --message "hello"` | `orac chat send "hello"` |

**Quick migration**: Use the shortcut aliases during transition:
- `orac run` → `orac prompt run`
- `orac flow` → `orac flow run` (only the `run` is implicit now)
- `orac ask` → `orac chat send`

---

## Logging and Debugging

Orac provides comprehensive logging with two output modes:

### Default Mode (Quiet)
- Only shows LLM responses and critical errors
- All detailed logging goes to file only
- Perfect for clean integration and scripting

### Verbose Mode
- Shows detailed operation logs on console
- Includes timestamps, function names, and colorized output
- Enable with `--verbose` or `-v` flag

### Log Configuration
- **File logging**: All activity logged to `llm.log` (configurable via `ORAC_LOG_FILE`)
- **Rotation**: 10 MB max file size, 7 days retention
- **Levels**: DEBUG level in files, INFO+ in console (verbose mode)

### Usage Examples
```bash
# Quiet mode (default) - only shows LLM response
orac prompt run capital --country France

# Verbose mode - shows detailed logging
orac prompt run capital --country Spain --verbose

# Check recent logs
tail -f llm.log
```

---

## Development & Testing

To run the test suite:

```bash
python test.py
```

For enhanced testing with options:

```bash
python run_tests.py --coverage        # Run with coverage
python run_tests.py --verbose         # Verbose output
python run_tests.py tests.test_orac   # Run specific module
```

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

---

## License

[License information here]