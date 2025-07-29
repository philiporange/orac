# Orac

![Orac Logo](assets/orac_logo.png)

**Orac** is a lightweight, YAML-driven framework for working with OpenAI-compatible LLM APIs. It provides clean abstractions, command-line integration, structured parameter handling, and support for both local and remote file attachments.

---

## Features

* **Prompt-as-config**: Define entire LLM tasks in YAML, including prompt text, parameters, default values, model settings, and file attachments.
* **Workflow orchestration**: Chain multiple prompts together with data flow and dependency management. Perfect for complex multi-step AI workflows.
* **Hierarchical configuration**: Three-layer config system (base → prompt → runtime) with deep merging for flexible overrides.
* **Templated inputs**: Use `${variable}` placeholders in prompt and system prompt fields.
* **File support**: Attach local or remote files (e.g., images, documents) via `files:` or `file_urls:` in YAML or CLI flags.
* **Conversation mode**: Automatic context preservation with SQLite-based history. Enable with `conversation: true` in YAML for seamless multi-turn interactions.
* **Command-line and Python API**: Use either the CLI tool or the `LLMWrapper` class in code.
* **Runtime configuration overrides**: Override model settings, API keys, generation options, and safety filters from the CLI or programmatically.
* **Structured output support**: Request `application/json` responses or validate against a JSON Schema.
* **Parameter validation**: Automatically convert and validate inputs by type.
* **Logging**: Logs all operations to file and provides optional verbose console output.

---

## Installation

### Option 1: Using requirements.txt
```bash
pip install -r requirements.txt
```

### Option 2: Manual installation
```bash
pip install google-generativeai openai PyYAML python-dotenv loguru
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
python -m orac capital --country France

# Using OpenAI
export ORAC_LLM_PROVIDER=openai
export OPENAI_API_KEY=your_openai_api_key
python -m orac capital --country Spain

# Using OpenRouter (access to multiple models)
export ORAC_LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=your_openrouter_api_key
python -m orac capital --country Japan

# Using CLI flags instead of environment variables
python -m orac capital --provider google --api-key your_api_key --country Italy

# Using a custom endpoint
python -m orac capital --provider custom --base-url https://my-custom-api.com/v1/ --api-key your_key --country Germany
```

### Configurable Environment Variables

All default settings can be overridden with environment variables using the `ORAC_` prefix:

- `ORAC_LLM_PROVIDER` - **Required**: LLM provider selection (google|openai|anthropic|azure|openrouter|custom)
- `ORAC_DEFAULT_MODEL_NAME` - Default LLM model
- `ORAC_DEFAULT_PROMPTS_DIR` - Directory for prompt files
- `ORAC_DEFAULT_CONFIG_FILE` - Path to config YAML
- `ORAC_DOWNLOAD_DIR` - Temp directory for file downloads
- `ORAC_LOG_FILE` - Log file location

### Configuration Hierarchy

Orac uses a layered configuration system, allowing for flexible and powerful control over your prompts. Settings are resolved with the following order of precedence (where higher numbers override lower ones):

1.  **Base Configuration (`orac/config.yaml`)**: The default settings for the entire project. This file is included with the `orac` package and provides sensible defaults for `model_name`, `generation_config`, and `safety_settings`. You can edit it directly in your site-packages or provide your own via a custom script.

2.  **Prompt Configuration (`prompts/your_prompt.yaml`)**: Any setting defined in a specific prompt's YAML file will override the base configuration. This is the primary way to customize a single task. For example, you can set a lower `temperature` for a factual prompt or a different `model_name` for a complex one.

3.  **Runtime Overrides (CLI / Python API)**: Settings provided directly at runtime, such as using the `--model-name` flag in the CLI or passing the `generation_config` dictionary to the `Orac` constructor, will always take the highest precedence, overriding all other configurations.

#### Example Override

If `orac/config.yaml` has:

```yaml
# orac/config.yaml
generation_config:
  temperature: 0.7
```

And your prompt has:

```yaml
# prompts/recipe.yaml
prompt: "Give me a recipe for ${dish}"
generation_config:
  temperature: 0.2  # Override for more deterministic recipes
```

Running `orac recipe` will use a temperature of **0.2**.

Running `orac recipe --generation-config '{"temperature": 0.9}'` will use a temperature of **0.9**.

---

## Example Usage

### 1. Basic YAML prompt

Save the following to `prompts/capital.yaml`:

```yaml
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    description: Country name
    default: France
```

### 1b. Conversation-enabled prompt

Orac includes a built-in `chat.yaml` prompt for conversational interactions:

```bash
# These automatically maintain conversation context
orac chat --message "What is machine learning?"
orac chat --message "Give me a simple example"
orac chat --message "How do I get started?"
```

### 2. Run from Python

```python
from orac import Orac

# Basic text completion
llm = Orac("capital")
print(llm.completion())  # Defaults to France -> "Paris"
print(llm.completion(country="Japan"))  # -> "Tokyo"

# JSON-returning prompts with automatic detection
recipe_llm = Orac("recipe")
result = recipe_llm(dish="cookies")  # Automatically returns dict (JSON detected)

# Force JSON parsing (raises exception if not valid JSON)
json_result = recipe_llm(dish="pasta", force_json=True)  # Returns dict

# Explicit JSON parsing
json_data = recipe_llm.completion_as_json(dish="pizza")  # Returns dict

# Mixed usage - callable interface handles both text and JSON
capital_result = llm(country="Spain")  # Returns "Madrid" (string)
recipe_result = recipe_llm(dish="salad")  # Returns {...} (dict - auto-detected JSON)
```

### 3. Run from CLI

```bash
orac capital
orac capital --country Japan
orac capital --verbose
orac capital --info
orac ./a/b/ad_hoc_task.yaml --some-param foo
```

### 4. Advanced examples

```bash
# Override model and config
orac capital --country "Canada" \
  --model-name "gemini-2.5-flash" \
  --generation-config '{"temperature": 0.4}'

# Structured JSON response
orac recipe --json-output

# Schema validation
orac capital --country "Germany" \
  --response-schema schemas/capital.schema.json

# Attach local and remote files
orac paper2audio \
  --file reports/report.pdf \
  --file-url https://example.com/image.jpg
```

### 5. Conversation mode

Orac supports automatic conversation mode that maintains context between interactions. Prompts can enable this by default in their YAML configuration.

```bash
# With conversation-enabled prompts (like chat.yaml), context is automatic
orac chat --message "What is 10 times 4?"    # → "40"
orac chat --message "Divided by 8?"          # → "5" (remembers context!)

# Use specific conversation ID for multiple parallel conversations
orac chat --conversation-id work --message "Help me with coding"
orac chat --conversation-id personal --message "Plan my vacation"

# Reset conversation before starting
orac chat --reset-conversation --message "Let's start fresh"

# Conversation management commands
orac chat --list-conversations              # List all conversations
orac chat --show-conversation CONVERSATION_ID   # Show conversation history
orac chat --delete-conversation CONVERSATION_ID # Delete a conversation
```

### Python API with Conversations

```python
from orac import Orac

# Automatic conversation mode (if enabled in YAML)
chat = Orac("chat")  # chat.yaml has conversation: true
print(chat("Hello! What's 15 + 25?"))      # → "40"
print(chat("Times 3?"))                     # → "120" (maintains context)

# Manual conversation control
assistant = Orac("capital", use_conversation=True, conversation_id="geography")
print(assistant(country="France"))         # → "Paris"
print(assistant(country="Japan"))          # → "Tokyo" (with context)

# Review conversation history
history = chat.get_conversation_history()
for msg in history:
    print(f"{msg['role']}: {msg['content']}")

# Reset when done
chat.reset_conversation()

# Override conversation mode (even if YAML enables it)
single_shot = Orac("chat", use_conversation=False)
print(single_shot("One-time question"))    # No conversation context
```

### 6. Workflows

Orac supports **workflows** - chains of prompts that execute in sequence with data flowing between steps. This enables complex multi-step AI operations like research → analysis → report generation.

#### Basic Workflow Usage

```bash
# List available workflows
orac workflow list

# Show workflow details
orac workflow run research_assistant --info

# Execute a workflow
orac workflow run capital_recipe --country Italy

# Dry run (show execution plan without running)
orac workflow run research_assistant --topic "AI ethics" --dry-run
```

#### Creating Workflow YAML Files

Workflows are defined in YAML files in the `workflows/` directory:

```yaml
# workflows/capital_recipe.yaml
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

#### Workflow Features

- **Dependency Management**: Steps run in topological order based on `depends_on` or data flow
- **Template Variables**: Use `${inputs.param}` and `${step_name.output}` for dynamic values
- **Error Handling**: Comprehensive validation and error reporting
- **Dry Run Mode**: Preview execution plan without running prompts
- **JSON Output**: `--json-output` formats results as structured JSON

#### Complex Workflow Example

```yaml
# workflows/research_assistant.yaml
name: "Research Assistant"
description: "Multi-step research with analysis and summary"

inputs:
  - name: topic
    type: string
    required: true
  - name: focus_area
    type: string
    default: "general overview"

outputs:
  - name: research_summary
    source: final_report.result
  - name: key_insights
    source: analyze_findings.insights

steps:
  initial_research:
    prompt: chat
    inputs:
      message: "Research ${inputs.topic}, focusing on ${inputs.focus_area}"
    outputs: [result]

  analyze_findings:
    prompt: chat
    depends_on: [initial_research]
    inputs:
      message: "Analyze these findings: ${initial_research.result}"
    outputs: [insights, conclusions]

  final_report:
    prompt: chat
    depends_on: [analyze_findings]
    inputs:
      message: "Create a report on ${inputs.topic}: ${analyze_findings.insights}"
    outputs: [result]
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

### Additional Options

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
                                 # When true, prompt is automatically set to '${message}'
                                 # Optional 'prompt' field provides fallback for non-conversation usage
```

### Conversation Mode YAML

For conversation-enabled prompts, you can simply enable conversation mode:

```yaml
# chat.yaml - A conversation-enabled assistant
model_name: "gemini-2.5-flash"

# Enable conversation mode - prompt automatically becomes '${message}'
conversation: true

# Optional: fallback prompt for when conversation is explicitly disabled
prompt: "Please respond to this message: ${message}"

system_prompt: |
    You are a helpful AI assistant. You are operating in conversation mode
    where context from previous messages is available.

parameters:
    - name: message
      type: string
      required: true
      default: "Hi!"
      description: "Your message or question for the assistant"
```

### Supported Parameter Types

* `string`
* `int`
* `float`
* `bool`
* `list` (comma-separated values)

---

## CLI Options

```bash
orac <prompt_name> [--parameter-name VALUE ...] [options]
```

### Global Flags

* `--info`: Show parameter metadata
* `--verbose`, `-v`: Enable verbose logging
* `--prompts-dir DIR`: Use custom prompt directory
* `--model-name MODEL`
* `--api-key KEY`
* `--generation-config JSON`
* `--safety-settings JSON`
* `--file FILE`
* `--file-url URL`
* `--json-output`
* `--response-schema FILE`
* `--output FILE`, `-o`
* `--conversation-id ID`
* `--reset-conversation`
* `--no-save`

### Conversation Management
* `--list-conversations`
* `--show-conversation ID`
* `--delete-conversation ID`

---

## Logging

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
orac capital --country France

# Verbose mode - shows detailed logging
orac capital --country Spain --verbose

# Check recent logs
tail -f llm.log
```

To configure logging programmatically:

```python
from orac.logger import configure_console_logging
configure_console_logging(verbose=True)
```

---

## Conversation Settings

Conversations are automatically stored in a local SQLite database and can be enabled per-prompt via YAML configuration.

### Configuration Methods

1. **YAML-level** (recommended): Add `conversation: true` to your prompt YAML
2. **Runtime**: Use `--conversation` flag or `use_conversation=True` parameter
3. **Global default**: Set `ORAC_DEFAULT_CONVERSATION_MODE=true` environment variable

### Environment Variables

- `ORAC_CONVERSATION_DB` - Database file location (default: `~/.orac/conversations.db`)
- `ORAC_DEFAULT_CONVERSATION_MODE` - Enable conversations globally (default: `false`)
- `ORAC_MAX_CONVERSATION_HISTORY` - Maximum messages to load from history (default: `20`)

```bash
# Global conversation settings
export ORAC_DEFAULT_CONVERSATION_MODE=true
export ORAC_MAX_CONVERSATION_HISTORY=50
export ORAC_CONVERSATION_DB="/path/to/conversations.db"
```

### Key Behavior

- **YAML `conversation: true`**: Automatically enables conversation mode and sets prompt to `${message}`
- **Runtime override**: `use_conversation=False` or `--conversation` flag can override YAML settings
- **Auto-continuation**: When no `--conversation-id` is specified, continues the most recent conversation for that prompt
- **Multiple conversations**: Use `--conversation-id` to maintain parallel conversations

---

## Development & Testing

To run the test suite:

```bash
python test.py
```
