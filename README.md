# Orac

![Orac Logo](assets/orac_logo.png)

**Orac** is a lightweight, YAML-driven framework for working with OpenAI-compatible LLM APIs. It provides clean abstractions, command-line integration, structured parameter handling, and support for both local and remote file attachments.

---

## Features

* **Prompt-as-config**: Define entire LLM tasks in YAML, including prompt text, parameters, default values, model settings, and file attachments.
* **Hierarchical configuration**: Three-layer config system (base → prompt → runtime) with deep merging for flexible overrides.
* **Templated inputs**: Use `${variable}` placeholders in prompt and system prompt fields.
* **File support**: Attach local or remote files (e.g., images, documents) via `files:` or `file_urls:` in YAML or CLI flags.
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

3.  **Runtime Overrides (CLI / Python API)**: Settings provided directly at runtime, such as using the `--model-name` flag in the CLI or passing the `generation_config` dictionary to the `LLMWrapper` constructor, will always take the highest precedence, overriding all other configurations.

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

### 1. Create a YAML prompt

Save the following to `prompts/capital.yaml`:

```yaml
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    description: Country name
    default: France
```

### 2. Run from Python

```python
from orac import LLMWrapper

llm = LLMWrapper("capital")
print(llm.completion())  # Defaults to France
print(llm.completion(country="Japan"))
```

### 3. Run from CLI

```bash
orac capital
orac capital --country Japan
orac capital --verbose
orac capital --info
```

### 4. Advanced examples

```bash
# Override model and config
orac capital --country "Canada" \
  --model-name "gemini-2.0-flash" \
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

## Development & Testing

To run the test suite:

```bash
python test.py
```
