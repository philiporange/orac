The Orac project provides a Python API and a command-line interface (CLI) for interacting with OpenAI-compatible Large Language Models (LLMs). It focuses on defining LLM tasks using YAML configurations for prompts, multi-step flows, autonomous agents, and executable skills.

The core functionality revolves around the `Prompt` class for single interactions, the `Flow` class for orchestration, and the `Client` class for managing connections to various LLM providers.

### Initialization and Client Management

The project uses an explicit initialization pattern to manage LLM provider connections and user consent, ensuring secure access to API keys.

#### `orac.init()`

Initializes the global Orac client, handling provider configuration and interactive consent for accessing API keys stored in environment variables.

-   Initializes the global client instance.
-   Sets up the specified `default_provider` (defaults to OpenRouter).
-   Manages consent for accessing API keys from environment variables if `interactive` is True.

```python
import orac
from orac.config import Provider

# Initialize the client, typically handling consent interactively
# For demonstration, we use quick_init below, but this is the recommended way
# for applications that need to manage consent.

# client = orac.init(
#     interactive=True,
#     default_provider=Provider.OPENROUTER
# )
# print(f"Client initialized: {orac.is_initialized()}")
```

#### `orac.quick_init()`

Provides a non-interactive way to initialize the client using a direct API key, bypassing the consent mechanism.

-   Initializes the global client instance using a direct API key.
-   Sets the specified provider as the default.

```python
import orac
from orac.config import Provider

# Note: Replace "test-api-key" with a valid key for actual execution
client = orac.quick_init(Provider.OPENROUTER, api_key="test-api-key")

print(f"Client initialized: {orac.is_initialized()}")
```

#### `orac.get_client()`

Retrieves the globally initialized `Client` instance. Must be called after `orac.init()` or `orac.quick_init()`.

-   Returns the active global `Client` instance.
-   Raises a `RuntimeError` if the client has not been initialized.

```python
import orac

# Assuming client was initialized above
client = orac.get_client()

print(f"Client type: {type(client)}")
```

### Registering Custom Providers

Orac supports registering custom LLM providers programmatically, allowing you to connect to any OpenAI-compatible API endpoint. This is useful for self-hosted models, alternative providers, proxy servers, or development/testing environments.

#### Understanding Providers

Orac includes built-in support for several providers:
- `Provider.OPENAI` - OpenAI's API
- `Provider.GOOGLE` - Google's Gemini API
- `Provider.ANTHROPIC` - Anthropic's Claude API
- `Provider.OPENROUTER` - OpenRouter's unified API
- `Provider.AZURE` - Azure OpenAI Service
- `Provider.ZAI` - Z.ai API
- `Provider.CUSTOM` - For custom/self-hosted endpoints

Each provider has default base URLs and environment variable names. You can override these when registering.

#### `Client.add_provider(provider, ...)`

Registers a provider with the client, making it available for use with prompts, flows, and agents.

**Parameters:**
- `provider` - The provider to register (from `orac.Provider` enum)
- `api_key` - Direct API key (no consent or environment access needed)
- `api_key_env` - Environment variable name containing the API key
- `allow_env` - Allow reading from the provider's default environment variable
- `from_config` - Allow reading from stored configuration (requires consent)
- `base_url` - Custom base URL for the API endpoint
- `model_name` - Default model name for this provider
- `interactive` - Allow interactive consent prompting

```python
import orac
from orac.config import Provider

# Initialize client
client = orac.Client()

# Register OpenAI with direct API key
client.add_provider(
    Provider.OPENAI,
    api_key="sk-your-api-key-here"
)

print(f"Registered providers: {client.get_registered_providers()}")
```

#### Registering with Custom Base URL

You can register any OpenAI-compatible API by using `Provider.CUSTOM` with a custom `base_url`:

```python
import orac
from orac.config import Provider

client = orac.Client()

# Register a custom self-hosted LLM
client.add_provider(
    Provider.CUSTOM,
    api_key="your-custom-api-key",
    base_url="https://my-llm-server.company.com/v1/",
    model_name="my-custom-model"
)

# Set as default provider
client.set_default_provider(Provider.CUSTOM)

print(f"Default provider: {client.get_default_provider()}")
```

#### Using Environment Variables

You can register providers that read API keys from environment variables:

```python
import orac
from orac.config import Provider

client = orac.Client()

# Method 1: Use default environment variable (requires consent if interactive=True)
client.add_provider(
    Provider.OPENAI,
    allow_env=True,  # Reads from OPENAI_API_KEY by default
    interactive=False  # Skip interactive consent
)

# Method 2: Specify custom environment variable
client.add_provider(
    Provider.GOOGLE,
    api_key_env="MY_CUSTOM_GOOGLE_KEY"  # Reads from this env var
)

# Method 3: Custom provider with custom env var
client.add_provider(
    Provider.CUSTOM,
    api_key_env="MY_SELFHOSTED_API_KEY",
    base_url="http://localhost:8080/v1/",
    model_name="llama-3.1-8b"
)

print(f"Registered providers: {client.get_registered_providers()}")
```

#### Managing Multiple Providers

You can register multiple providers and switch between them:

```python
import orac
from orac.config import Provider

client = orac.Client()

# Register multiple providers
client.add_provider(
    Provider.OPENAI,
    api_key="sk-openai-key"
)

client.add_provider(
    Provider.GOOGLE,
    api_key="google-api-key"
)

client.add_provider(
    Provider.CUSTOM,
    api_key="custom-key",
    base_url="https://custom-api.example.com/v1/",
    model_name="custom-model"
)

# Set default provider
client.set_default_provider(Provider.OPENAI)

# List all registered providers
providers = client.get_registered_providers()
print(f"Available providers: {[p.value for p in providers]}")

# Get information about a specific provider
info = client.get_provider_registry().get_provider_info(Provider.CUSTOM)
print(f"Custom provider info: {info}")
```

#### Using Providers with Prompts

Once providers are registered, you can use them with prompts by specifying the provider parameter:

```python
import orac
from orac import Prompt
from orac.config import Provider
from pathlib import Path
import tempfile

# Register multiple providers
client = orac.Client()
client.add_provider(Provider.OPENAI, api_key="sk-openai-key")
client.add_provider(Provider.GOOGLE, api_key="google-key")

# Create a test prompt
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "test.yaml").write_text("""
prompt: "What is 2+2?"
""")

# Use with OpenAI
prompt = Prompt("test", prompts_dir=str(prompts_dir), client=client)
# Will use the default provider unless overridden

# Override provider at runtime
with orac.patch('orac.client.Client.chat', return_value="4"):
    result = prompt.completion(provider=Provider.GOOGLE)
    print(f"Result from Google: {result}")
```

#### Removing Providers

You can remove a provider from the client:

```python
import orac
from orac.config import Provider

client = orac.Client()

# Add providers
client.add_provider(Provider.OPENAI, api_key="sk-key")
client.add_provider(Provider.GOOGLE, api_key="google-key")

print(f"Before removal: {client.get_registered_providers()}")

# Remove a provider
removed = client.remove_provider(Provider.GOOGLE)
print(f"Removed: {removed}")
print(f"After removal: {client.get_registered_providers()}")
```

#### Common Use Cases

**Self-hosted Ollama:**
```python
import orac
from orac.config import Provider

client = orac.Client()
client.add_provider(
    Provider.CUSTOM,
    api_key="ollama",  # Ollama doesn't require a real API key
    base_url="http://localhost:11434/v1/",
    model_name="llama3.1:8b"
)
client.set_default_provider(Provider.CUSTOM)
```

**LM Studio:**
```python
import orac
from orac.config import Provider

client = orac.Client()
client.add_provider(
    Provider.CUSTOM,
    api_key="lm-studio",
    base_url="http://localhost:1234/v1/",
    model_name="local-model"
)
client.set_default_provider(Provider.CUSTOM)
```

**vLLM Server:**
```python
import orac
from orac.config import Provider

client = orac.Client()
client.add_provider(
    Provider.CUSTOM,
    api_key="vllm-server-key",
    base_url="http://your-vllm-server:8000/v1/",
    model_name="meta-llama/Llama-3.1-8B-Instruct"
)
client.set_default_provider(Provider.CUSTOM)
```

**Corporate Proxy:**
```python
import orac
from orac.config import Provider

client = orac.Client()
client.add_provider(
    Provider.OPENAI,
    api_key_env="CORP_OPENAI_KEY",
    base_url="https://llm-proxy.company.internal/openai/v1/"
)
client.set_default_provider(Provider.OPENAI)
```

**Multiple Accounts:**
```python
import orac
from orac.config import Provider

client = orac.Client()

# Personal account
client.add_provider(
    Provider.OPENAI,
    api_key="sk-personal-key",
    base_url="https://api.openai.com/v1/"
)

# Work account - would need a way to differentiate,
# but you could use different provider types
client.add_provider(
    Provider.CUSTOM,
    api_key="sk-work-key",
    base_url="https://api.openai.com/v1/",
    model_name="gpt-4"
)
```

#### Provider Status and Debugging

Get comprehensive information about registered providers:

```python
import orac
from orac.config import Provider

client = orac.Client()
client.add_provider(Provider.OPENAI, api_key="sk-key")

# Get client status including all providers
status = client.get_client_status()
print(f"Client initialized: {status['initialized']}")
print(f"Registry status: {status['registry_status']}")

# Get specific provider information
registry = client.get_provider_registry()
info = registry.get_provider_info(Provider.OPENAI)
print(f"OpenAI config: {info}")
```

### Prompt Execution

The `orac.Prompt` class is the primary interface for executing single LLM interactions defined in YAML files.

#### `orac.Prompt(prompt_name, ...)`

Loads a prompt specification from a YAML file, resolves configuration, and prepares for execution.

-   Loads the YAML file corresponding to `prompt_name` (e.g., `capital.yaml`).
-   Merges configuration from base settings, YAML file, and runtime arguments.
-   Sets up conversation management if enabled.

```python
import orac
from orac import Prompt
from pathlib import Path
import tempfile

# Create a temporary prompt file for demonstration
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "capital.yaml").write_text("""
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    type: string
    default: France
""")

# Initialize Prompt instance
capital_prompt = Prompt("capital", prompts_dir=str(prompts_dir))

print(f"Prompt name: {capital_prompt.prompt_name}")
print(f"Prompt template: {capital_prompt.prompt_template_str}")
```

#### `Prompt.completion(**kwargs_params)`

Executes the prompt, resolves template variables using `kwargs_params`, and returns the raw string response from the LLM.

-   Resolves input parameters, applying type conversion and defaults.
-   Formats the prompt and system prompt templates.
-   Handles file attachments (local and remote).
-   Calls the underlying `Client.chat()` method.

```python
import orac
from orac import Prompt
from orac.config import Provider
import tempfile
from pathlib import Path

# Assuming client is initialized globally
# Create a temporary prompt file for demonstration
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "capital.yaml").write_text("""
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    type: string
    default: France
""")

# Mock the API call for demonstration purposes
with orac.patch('orac.client.Client.chat', return_value="Tokyo"):
    capital_prompt = Prompt("capital", prompts_dir=str(prompts_dir))
    
    # Execute the prompt with a specific country
    result = capital_prompt.completion(country="Japan")

    print(f"Result: {result}")
```

#### `Prompt.completion_as_json(**kwargs_params)`

Executes the prompt and attempts to parse the response as JSON, returning a Python dictionary.

-   Calls `Prompt.completion()`.
-   Raises `json.JSONDecodeError` if the response is not valid JSON.

```python
import orac
from orac import Prompt
import json
import tempfile
from pathlib import Path

# Create a temporary JSON-returning prompt
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "recipe.yaml").write_text("""
prompt: "Give me a recipe for ${dish} in JSON format."
parameters:
  - name: dish
    type: string
response_mime_type: application/json
""")

mock_json_response = '{"title": "Cookies", "ingredients": ["flour", "sugar"]}'

# Mock the API call to return JSON
with orac.patch('orac.client.Client.chat', return_value=mock_json_response):
    recipe_prompt = Prompt("recipe", prompts_dir=str(prompts_dir))
    
    # Execute and parse as JSON
    result = recipe_prompt.completion_as_json(dish="cookies")

    print(f"Result type: {type(result)}")
    print(f"Title: {result['title']}")
```

#### `Prompt.__call__(**kwargs_params)`

The callable interface for `Prompt`, which automatically detects and parses JSON responses if possible.

-   If the response is valid JSON, returns a dictionary.
-   Otherwise, returns the raw string response.
-   If `force_json=True` is passed, raises a `ValueError` if the response is not JSON.

```python
import orac
from orac import Prompt
import tempfile
from pathlib import Path

# Create a temporary JSON-returning prompt
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "recipe.yaml").write_text("""
prompt: "Give me a recipe for ${dish} in JSON format."
parameters:
  - name: dish
    type: string
response_mime_type: application/json
""")

mock_json_response = '{"title": "Tacos", "steps": 3}'

# Mock the API call to return JSON
with orac.patch('orac.client.Client.chat', return_value=mock_json_response):
    recipe_prompt = Prompt("recipe", prompts_dir=str(prompts_dir))
    
    # Use callable interface
    result = recipe_prompt(dish="tacos")

    print(f"Result type: {type(result)}")
    print(f"Steps: {result['steps']}")
```

### Conversation Management

The `Prompt` class integrates with `ConversationDB` to manage multi-turn interactions.

#### `Prompt.get_conversation_history()`

Retrieves the list of messages stored for the current conversation ID.

-   Requires `use_conversation` to be enabled for the `Prompt` instance.
-   Returns a list of dictionaries containing message history.

```python
import orac
from orac import Prompt
import tempfile
from pathlib import Path

# Create a temporary chat prompt
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "chat.yaml").write_text("""
prompt: "${message}"
parameters:
  - name: message
    type: string
conversation: true
""")

# Mock the API call to simulate a conversation
with orac.patch('orac.client.Client.chat', side_effect=["Hello Alice", "Your name is Alice"]):
    # Initialize in conversation mode
    chat_prompt = Prompt("chat", prompts_dir=str(prompts_dir), use_conversation=True)
    
    # First interaction
    response1 = chat_prompt(message="Hi, my name is Alice")
    print(f"Response 1: {response1}")
    
    # Second interaction - context is preserved
    response2 = chat_prompt(message="What's my name?")
    print(f"Response 2: {response2}")
    
    # Get the conversation history
    history = chat_prompt.get_conversation_history()
    print(f"History length: {len(history)}")
```

### Custom API Endpoints and Authentication

Orac supports specifying custom API endpoint URLs and API keys via the `base_url` and `api_key` fields in YAML configuration files. This allows you to use self-hosted models, proxy servers, or alternative API providers that are OpenAI-compatible.

#### Using `base_url` and `api_key` in Prompt YAML

You can specify a custom base URL and API key directly in your prompt YAML file:

```python
import orac
from orac import Prompt
from pathlib import Path
import tempfile

# Create a temporary prompt file with custom base_url and api_key
temp_dir = Path(tempfile.mkdtemp())
prompts_dir = temp_dir / "prompts"
prompts_dir.mkdir()

(prompts_dir / "custom_endpoint.yaml").write_text("""
prompt: "What is the capital of ${country}?"
provider: openai
base_url: https://my-custom-api.example.com/v1/
api_key: ${CUSTOM_API_KEY}  # Can use env vars or literal string
model_name: gpt-4o-mini
parameters:
  - name: country
    type: string
    default: France
""")

# When you use this prompt, it will automatically use the custom configuration
custom_prompt = Prompt("custom_endpoint", prompts_dir=str(prompts_dir))

# The base_url and api_key are accessible as attributes
print(f"Using base URL: {custom_prompt.base_url}")
print(f"Using API key: {custom_prompt.api_key[:10]}..." if custom_prompt.api_key else "No API key")
```

#### Using `base_url` and `api_key` in Agent YAML

Agents can also specify custom base URLs and API keys:

```yaml
# agents/custom_agent.yaml
name: custom_agent
description: Agent using a custom API endpoint
provider: openai
base_url: https://my-custom-api.example.com/v1/
api_key: ${CUSTOM_API_KEY}  # Can use env vars or literal string
model_name: gpt-4o-mini
system_prompt: |
  You are a helpful agent using a custom API endpoint.
tools:
  - "tool:finish"
inputs:
  - name: query
    type: string
    required: true
```

#### Configuration Precedence

Both `base_url` and `api_key` are resolved in the following order (highest to lowest priority):
1. **CLI flags/Programmatic parameters**: `--base-url`, `--api-key` (if provided)
2. **YAML file**: `base_url` and `api_key` fields in prompt/agent YAML
3. **Provider defaults/Environment**: Standard endpoint and environment variable-based API keys

This means you can override YAML configuration at runtime using CLI flags or when calling methods programmatically.

#### Supported Use Cases

- **Self-hosted models**: Point to your own OpenAI-compatible API with custom credentials
- **Proxy servers**: Route requests through a proxy or gateway
- **Alternative providers**: Use services with OpenAI-compatible APIs
- **Development/testing**: Point to local or staging endpoints with test API keys
- **Multiple accounts**: Use different API keys for different prompts/agents
- **Environment-specific keys**: Use `${VAR}` syntax to reference environment variables

Example with various configurations:

```yaml
# Use OpenAI's API with custom base URL and API key from environment
provider: openai
base_url: https://api.openai.com/v1/
api_key: ${OPENAI_API_KEY}

# Use a custom self-hosted endpoint with literal API key
provider: custom
base_url: https://my-llm-server.local:8080/v1/
api_key: my-custom-api-key-123

# Use a proxy or gateway with specific credentials
provider: openai
base_url: https://api-proxy.company.com/openai/v1/
api_key: ${PROXY_API_KEY}

# Development/testing with local endpoint
provider: custom
base_url: http://localhost:8000/v1/
api_key: test-key
```
