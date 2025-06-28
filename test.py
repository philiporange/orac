#!/usr/bin/env python3
"""
Comprehensive, no-mock test-suite for the **Orac** project.

Covered features
================
• CLI execution (default parameters, explicit parameters)
• `--info`, `--verbose`, output redirection (`--output`)
• Structured JSON output (`--json-output` + `--response-schema`)
• Parameter-type conversion helper (`convert_cli_value`)
• Local file attachments and `require_file: true` enforcement
• Basic error handling for unknown prompts

The script keeps the simple *“run-as-a-script”* style of the original
tests so that contributors can execute it with a single command:

    $ python test.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

# --------------------------------------------------------------------------- #
# Paths & helpers                                                             #
# --------------------------------------------------------------------------- #
CLI_PATH = Path(__file__).parent / "orac" / "cli.py"


def run_command(
    cmd: list[str], *, check_success: bool = True, env: dict = None
) -> subprocess.CompletedProcess:
    """Run *cmd* in a subprocess and return the CompletedProcess object."""
    print(f"\n$ {' '.join(cmd)}")
    # Use provided env or current environment
    if env is None:
        env = os.environ.copy()
    try:
        result = subprocess.run(
            cmd, text=True, capture_output=True, check=check_success, env=env
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"▼ STDOUT\n{e.stdout}\n▲ END STDOUT")
        print(f"▼ STDERR\n{e.stderr}\n▲ END STDERR")
        raise


# --------------------------------------------------------------------------- #
# CLI-level integration tests                                                 #
# --------------------------------------------------------------------------- #
def test_basic_recipe_prompt() -> None:
    """Default-parameter execution for a prompt with a default field."""
    out = run_command(["python", "-m", "orac.cli", str(CLI_PATH), "recipe"])
    assert out.returncode == 0
    assert out.stdout.strip(), "recipe prompt produced no output"
    assert "pancake" in out.stdout.lower(), "should mention default dish 'pancakes'"
    print("✓ basic recipe prompt")


def test_capital_with_parameter() -> None:
    """Explicit parameter passing (`--country`)."""
    out = run_command(
        ["python", "-m", "orac.cli", str(CLI_PATH), "capital", "--country", "Japan"]
    )
    assert out.returncode == 0
    assert out.stdout.strip(), "capital prompt produced no output"
    assert "tokyo" in out.stdout.lower(), "answer should mention Tokyo"
    print("✓ parameterised capital prompt")


def test_output_redirection() -> None:
    """`--output` flag should write to file and keep STDOUT empty."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
        target = tf.name
    try:
        out = run_command(
            [
                "python",
                "-m",
                "orac.cli",
                str(CLI_PATH),
                "recipe",
                "--dish",
                "cookies",
                "--output",
                target,
            ]
        )
        assert out.stdout.strip() == "", "stdout must be empty if --output is used"
        with open(target, encoding="utf-8") as fh:
            txt = fh.read()
        assert "cookie" in txt.lower(), "output file should mention cookies"
        print("✓ --output writes file correctly")
    finally:
        os.unlink(target)


def test_info_mode() -> None:
    """`--info` must print parameter metadata and exit without error."""
    out = run_command(["python", "-m", "orac.cli", str(CLI_PATH), "capital", "--info"])
    assert out.returncode == 0
    assert "Parameters" in out.stdout
    assert "country" in out.stdout
    print("✓ --info mode")


def test_verbose_mode() -> None:
    """CLI must still print the model answer in verbose mode."""
    out = run_command(
        ["python", "-m", "orac.cli", str(CLI_PATH), "recipe", "--verbose"]
    )
    assert out.returncode == 0
    assert out.stdout.strip(), "no LLM answer in verbose mode"
    print("✓ --verbose mode")


def test_json_and_schema_output() -> None:
    """`--json-output` and `--response-schema`."""
    # --json-output
    out = run_command(
        ["python", "-m", "orac.cli", str(CLI_PATH), "recipe", "--json-output"]
    )
    obj = json.loads(out.stdout)
    assert isinstance(obj, dict), "--json-output must return a JSON object"
    print("✓ basic --json-output")

    # --response-schema
    schema = {
        "type": "object",
        "properties": {"capital": {"type": "string"}},
        "required": ["capital"],
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as sf:
        json.dump(schema, sf)
        spath = sf.name
    try:
        out = run_command(
            [
                "python",
                "-m",
                "orac.cli",
                str(CLI_PATH),
                "capital",
                "--country",
                "Canada",
                "--response-schema",
                spath,
            ]
        )
        obj = json.loads(out.stdout)
        assert isinstance(obj, dict)
        print("✓ --response-schema JSON output")
    finally:
        os.unlink(spath)


def test_generation_config_and_model_override() -> None:
    """
    Pass a small generation_config override and alternate model – we don’t
    validate the model’s response, only that the CLI completes successfully.
    """
    override = '{"temperature": 0.1, "max_tokens": 20}'
    out = run_command(
        [
            "python",
            "-m",
            "orac.cli",
            str(CLI_PATH),
            "capital",
            "--country",
            "Brazil",
            "--model-name",
            "gemini-1.5-flash",
            "--generation-config",
            override,
        ]
    )
    assert out.returncode == 0
    assert out.stdout.strip()
    print("✓ generation_config / model override")


def test_local_file_attachment() -> None:
    """
    Send a local text file to the `file_test` prompt (which is designed
    for file input).  Successful completion + no traceback is enough.
    """
    # create a tiny file to attach
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as fh:
        fh.write("Sample attachment for Orac tests.")
        file_path = fh.name

    try:
        out = run_command(
            [
                "python",
                "-m",
                "orac.cli",
                str(CLI_PATH),
                "file_test",
                "--file",
                file_path,
            ]
        )
        assert out.returncode == 0
        assert out.stdout.strip(), "file_test returned no text"
        print("✓ local file attachment")
    finally:
        os.unlink(file_path)


def test_multiple_file_attachment() -> None:
    """
    Test that multiple files can be attached using multiple --file flags.
    """
    # create two temporary files
    files = []
    for i in range(2):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=f"_{i}.txt") as fh:
            fh.write(f"Content of test file {i}")
            files.append(fh.name)

    try:
        out = run_command(
            [
                "python",
                "-m",
                "orac.cli",
                str(CLI_PATH),
                "file_test",
                "--file",
                files[0],
                "--file",
                files[1],
            ]
        )
        assert out.returncode == 0
        assert out.stdout.strip(), "file_test with multiple files returned no text"
        print("✓ multiple file attachment")
    finally:
        for file_path in files:
            os.unlink(file_path)


def test_require_file_validation() -> None:
    """
    Create an *ad-hoc* prompt with `require_file: true` and confirm that
    invoking it **without** a `--file` or `--file-url` aborts with error.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="orac_prompts_"))
    yaml_path = tmp_dir / "needs_file.yaml"
    yaml_path.write_text(
        dedent(
            """
            prompt: "Describe the attached file."
            require_file: true
            """
        )
    )
    out = run_command(
        [
            "python",
            "-m",
            "orac.cli",
            str(CLI_PATH),
            "needs_file",
            "--prompts-dir",
            str(tmp_dir),
        ],
        check_success=False,
    )
    assert out.returncode != 0
    assert "Files are required" in out.stderr or "require_file" in out.stderr
    print("✓ require_file enforcement")


def test_unknown_prompt_error() -> None:
    """The CLI must exit non-zero and complain if the prompt is missing."""
    out = run_command(
        ["python", "-m", "orac.cli", str(CLI_PATH), "does_not_exist"],
        check_success=False,
    )
    assert out.returncode != 0
    assert "not found" in out.stderr.lower()
    print("✓ unknown-prompt error handling")


def test_provider_requirement() -> None:
    """The CLI must exit non-zero if no provider is specified."""
    # Create a clean environment without ORAC_LLM_PROVIDER
    clean_env = os.environ.copy()
    clean_env.pop("ORAC_LLM_PROVIDER", None)
    clean_env["ORAC_DISABLE_DOTENV"] = "1"  # Disable .env loading
    clean_env["PYTHONPATH"] = str(Path(__file__).parent)

    out = run_command(
        ["python", "-m", "orac.cli", "capital", "--country", "France"],
        check_success=False,
        env=clean_env,
    )

    assert out.returncode != 0
    assert "select an llm provider" in out.stderr.lower()
    print("✓ provider requirement enforcement")


# --------------------------------------------------------------------------- #
# Unit-level utility tests (no network, no subprocess)                        #
# --------------------------------------------------------------------------- #
def test_convert_cli_value_helper() -> None:
    """Direct checks on the type-conversion utility in `orac.cli`."""
    from orac.cli import convert_cli_value

    assert convert_cli_value("true", "bool", "flag") is True
    assert convert_cli_value("42", "int", "num") == 42
    assert abs(convert_cli_value("3.14", "float", "pi") - 3.14) < 1e-6
    assert convert_cli_value("a,b,c", "list", "lst") == ["a", "b", "c"]
    assert convert_cli_value("raw", "string", "s") == "raw"
    print("✓ convert_cli_value helper")


def test_parameter_coercion_internal() -> None:
    """Quick sanity check on `LLMWrapper._resolve_parameters()` using a temp prompt."""
    from orac.orac import Orac

    tmp_dir = Path(tempfile.mkdtemp(prefix="orac_params_"))
    yaml_path = tmp_dir / "types.yaml"
    yaml_path.write_text(
        dedent(
            """
            prompt: "Echo ${flag} ${count} ${ratio} ${items}"
            parameters:
              - name: flag
                type: bool
              - name: count
                type: int
              - name: ratio
                type: float
              - name: items
                type: list
            """
        )
    )
    wrapper = Orac("types", prompts_dir=str(tmp_dir))
    params = wrapper._resolve_parameters(
        flag="yes", count="7", ratio="2.5", items="x, y ,z "
    )
    assert params == {
        "flag": True,
        "count": 7,
        "ratio": 2.5,
        "items": ["x", "y", "z"],
    }
    print("✓ parameter coercion")


def test_files_parameter() -> None:
    """Test that Orac can be instantiated with files=[] parameter containing a list of file paths."""
    from orac.orac import Orac

    # Create temporary files
    files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=f"_test_{i}.txt") as fh:
            fh.write(f"Test file content {i}")
            files.append(fh.name)

    try:
        # Test instantiating Orac with files parameter
        orac = Orac("file_test", files=files)

        # Verify files are stored correctly
        assert orac.files == files
        assert len(orac.files) == 3

        # Verify files exist and can be read
        for file_path in orac.files:
            assert os.path.exists(file_path)
            with open(file_path, 'r') as f:
                content = f.read()
                assert "Test file content" in content

        print("✓ files parameter with list of paths")

    finally:
        # Clean up temporary files
        for file_path in files:
            if os.path.exists(file_path):
                os.unlink(file_path)


def test_config_override_hierarchy() -> None:
    """Verify the config precedence: runtime > prompt.yaml > base_config.yaml"""
    from orac.orac import Orac

    # 1. Create temporary config and prompt files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        # Base config: defines model and a temp setting
        base_config_path = tmp_path / "base.yaml"
        base_config_path.write_text(
            dedent(
                """
            model_name: model-from-base-config
            generation_config:
              temperature: 0.1
              max_tokens: 100
        """
            )
        )

        # Prompt 1 (override_prompt): overrides model and temperature
        prompt1_path = prompts_dir / "override_prompt.yaml"
        prompt1_path.write_text(
            dedent(
                """
            prompt: "Test prompt 1"
            model_name: model-from-prompt
            generation_config:
              temperature: 0.5
        """
            )
        )

        # Prompt 2 (simple_prompt): inherits everything
        prompt2_path = prompts_dir / "simple_prompt.yaml"
        prompt2_path.write_text('prompt: "Test prompt 2"')

        # --- TEST CASES ---

        # Case A: Prompt overrides base config
        wrapper_a = Orac(
            "override_prompt",
            prompts_dir=str(prompts_dir),
            base_config_file=str(base_config_path),
        )
        assert wrapper_a.client_kwargs["model_name"] == "model-from-prompt"
        assert wrapper_a.client_kwargs["generation_config"]["temperature"] == 0.5
        assert (
            wrapper_a.client_kwargs["generation_config"]["max_tokens"] == 100
        )  # Inherited

        # Case B: Runtime args override everything
        wrapper_b = Orac(
            "override_prompt",
            prompts_dir=str(prompts_dir),
            base_config_file=str(base_config_path),
            model_name="model-from-runtime",
            generation_config={"temperature": 0.9},
        )
        assert wrapper_b.client_kwargs["model_name"] == "model-from-runtime"
        assert wrapper_b.client_kwargs["generation_config"]["temperature"] == 0.9
        assert (
            wrapper_b.client_kwargs["generation_config"]["max_tokens"] == 100
        )  # Base config is merged

        # Case C: Simple prompt inherits fully from base config
        wrapper_c = Orac(
            "simple_prompt",
            prompts_dir=str(prompts_dir),
            base_config_file=str(base_config_path),
        )
        assert wrapper_c.client_kwargs["model_name"] == "model-from-base-config"
        assert wrapper_c.client_kwargs["generation_config"]["temperature"] == 0.1

    print("✓ config override hierarchy")

def test_direct_path_loading() -> None:
    """
    Pass an *absolute* YAML file path to Orac() and ensure the prompt is
    loaded without needing --prompts-dir or copying into prompts/.

    This stays fully offline – no LLM call – so we pass a dummy provider.
    """
    from orac.orac import Orac

    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "direct_prompt.yaml"
        yaml_path.write_text(
            dedent(
                """
                prompt: "Echo ${word}"
                parameters:
                  - name: word
                    default: test
                """
            )
        )

        wrapper = Orac(str(yaml_path), provider="google")  # provider required
        # core invariants
        assert wrapper.prompt_name == "direct_prompt"
        assert Path(wrapper.yaml_file_path) == yaml_path
        assert Path(wrapper.prompts_root_dir) == Path(tmpdir)
        # parameter resolution should pick up the default
        assert wrapper._resolve_parameters() == {"word": "test"}

    print("✓ direct YAML path loading")


def test_completion_as_json_method() -> None:
    """Test the completion_as_json method with recipe prompt (returns JSON)."""
    from orac.orac import Orac

    recipe = Orac("recipe", provider="google")
    result = recipe.completion_as_json(dish="cookies")

    # Should return a dict (parsed JSON)
    assert isinstance(result, dict)
    assert "title" in result
    assert "ingredients" in result
    assert "steps" in result
    assert isinstance(result["ingredients"], list)
    assert isinstance(result["steps"], list)

    print("✓ completion_as_json method")


def test_completion_as_json_with_text_prompt() -> None:
    """Test completion_as_json method fails with text-only prompt."""
    from orac.orac import Orac
    import json

    capital = Orac("capital", provider="google")

    # Should raise JSONDecodeError since capital returns plain text
    try:
        capital.completion_as_json(country="France")
        assert False, "Expected JSONDecodeError but method succeeded"
    except json.JSONDecodeError:
        # This is expected
        pass

    print("✓ completion_as_json error handling")


def test_callable_interface_auto_detection() -> None:
    """Test __call__ method with automatic JSON detection."""
    from orac.orac import Orac

    # Test with JSON-returning prompt
    recipe = Orac("recipe", provider="google")
    result = recipe(dish="pancakes")

    # Should auto-detect and return dict
    assert isinstance(result, dict)
    assert "title" in result

    # Test with text-returning prompt
    capital = Orac("capital", provider="google")
    result = capital(country="Japan")

    # Should return string
    assert isinstance(result, str)
    assert result.strip()  # Should have content

    print("✓ callable interface auto-detection")


def test_callable_interface_force_json() -> None:
    """Test __call__ method with force_json parameter."""
    from orac.orac import Orac

    # Test force_json=True with JSON prompt (should succeed)
    recipe = Orac("recipe", provider="google")
    result = recipe(dish="cookies", force_json=True)
    assert isinstance(result, dict)

    # Test force_json=True with text prompt (should fail)
    capital = Orac("capital", provider="google")
    try:
        capital(country="France", force_json=True)
        assert False, "Expected ValueError but method succeeded"
    except ValueError as e:
        assert "not valid JSON" in str(e)

    print("✓ callable interface force_json parameter")


def test_callable_interface_parameters() -> None:
    """Test that __call__ method accepts all completion parameters."""
    from orac.orac import Orac

    # Test with various parameters
    recipe = Orac("recipe", provider="google")
    result = recipe(
        dish="tacos",
        generation_config={"temperature": 0.1},
        model_name="gemini-2.0-flash-001"
    )

    assert isinstance(result, dict)
    assert "title" in result

    print("✓ callable interface parameter passing")


# --------------------------------------------------------------------------- #
# Conversation tests                                                          #
# --------------------------------------------------------------------------- #
def test_conversation_basic() -> None:
    """Test basic conversation functionality."""
    from orac.orac import Orac
    import uuid

    # Create unique conversation ID for this test
    conv_id = f"test_{uuid.uuid4()}"

    # First message
    chat = Orac("capital", use_conversation=True, conversation_id=conv_id)
    response1 = chat.completion(country="France")
    assert "paris" in response1.lower()

    # Second message should have context
    chat2 = Orac("capital", use_conversation=True, conversation_id=conv_id)
    history = chat2.get_conversation_history()
    assert len(history) == 2  # User + Assistant messages
    assert history[0]["role"] == "user"
    assert "France" in history[0]["content"]
    assert history[1]["role"] == "assistant"
    assert "Paris" in history[1]["content"]

    # Cleanup
    chat2.delete_conversation()

    print("✓ basic conversation functionality")


def test_conversation_reset() -> None:
    """Test conversation reset functionality."""
    from orac.orac import Orac
    import uuid

    conv_id = f"test_{uuid.uuid4()}"

    # Create conversation with messages
    chat = Orac("capital", use_conversation=True, conversation_id=conv_id)
    chat.completion(country="Japan")

    # Verify messages exist
    history = chat.get_conversation_history()
    assert len(history) > 0

    # Reset conversation
    chat.reset_conversation()

    # Verify messages are gone
    history = chat.get_conversation_history()
    assert len(history) == 0

    # Cleanup
    chat.delete_conversation()

    print("✓ conversation reset")


def test_conversation_cli() -> None:
    """Test conversation mode via CLI."""
    import uuid

    conv_id = f"test_cli_{uuid.uuid4()}"

    # First message
    out1 = run_command([
        "python", "-m", "orac.cli", "chat",
        "--conversation-id", conv_id,
        "--message", "What is the capital of Spain?",
    ])
    assert out1.returncode == 0
    assert "madrid" in out1.stdout.lower()

    # List conversations
    out2 = run_command([
        "python", "-m", "orac.cli", "chat",
        "--list-conversations"
    ])
    assert out2.returncode == 0
    assert conv_id in out2.stdout

    # Show conversation
    out3 = run_command([
        "python", "-m", "orac.cli", "chat",
        "--show-conversation", conv_id
    ])
    assert out3.returncode == 0
    assert "Madrid" in out3.stdout

    # Delete conversation
    out4 = run_command([
        "python", "-m", "orac.cli", "chat",
        "--delete-conversation", conv_id
    ])
    assert out4.returncode == 0
    assert f"Deleted conversation: {conv_id}" in out4.stdout

    print("✓ conversation CLI commands")


def test_conversation_auto_id() -> None:
    """Test automatic conversation ID generation."""
    from orac.orac import Orac

    # Create without specifying ID
    chat = Orac("capital", use_conversation=True)
    assert chat.conversation_id is not None
    assert len(chat.conversation_id) > 0

    # Use it
    response = chat.completion(country="Italy")
    assert "rome" in response.lower()

    # Verify it was saved
    history = chat.get_conversation_history()
    assert len(history) == 2

    # Cleanup
    chat.delete_conversation()

    print("✓ automatic conversation ID generation")


def test_conversation_disabled_by_default() -> None:
    """Test that conversations are disabled by default."""
    from orac.orac import Orac

    # Create without conversation flag
    llm = Orac("capital")
    assert llm.use_conversation is False

    # Should raise error when trying to use conversation methods
    try:
        llm.get_conversation_history()
        assert False, "Expected ValueError"
    except ValueError:
        pass

    print("✓ conversations disabled by default")

# --------------------------------------------------------------------------- #
# Main entry point                                                            #
# --------------------------------------------------------------------------- #
def main() -> None:
    print("🧪  Orac full-functionality tests")
    print("=" * 40)

    # Set up provider for testing
    os.environ["ORAC_LLM_PROVIDER"] = "google"
    if not os.environ.get("GOOGLE_API_KEY"):
        print("⚠️  Warning: GOOGLE_API_KEY not set - tests may fail")

    # Keep tests deterministic: change CWD to repo root
    os.chdir(Path(__file__).parent)

    try:
        # Run the provider requirement test first (without provider set)
        test_provider_requirement()

        # Then set up provider for remaining tests
        os.environ["ORAC_LLM_PROVIDER"] = "google"
        if not os.environ.get("GOOGLE_API_KEY"):
            print("⚠️  Warning: GOOGLE_API_KEY not set - tests may fail")

        # CLI-level (live LLM) tests
        test_basic_recipe_prompt()
        test_capital_with_parameter()
        test_output_redirection()
        test_info_mode()
        test_verbose_mode()
        test_json_and_schema_output()
        test_generation_config_and_model_override()
        test_local_file_attachment()
        test_multiple_file_attachment()
        test_require_file_validation()
        test_unknown_prompt_error()

        # Helper / internal tests
        test_convert_cli_value_helper()
        test_parameter_coercion_internal()
        test_files_parameter()
        test_config_override_hierarchy()
        test_direct_path_loading()

        # New method tests
        test_completion_as_json_method()
        test_completion_as_json_with_text_prompt()
        test_callable_interface_auto_detection()
        test_callable_interface_force_json()
        test_callable_interface_parameters()

        # Conversation tests
        test_conversation_basic()
        test_conversation_reset()
        test_conversation_cli()
        test_conversation_auto_id()
        test_conversation_disabled_by_default()

        print("\n🎉  All tests passed!")
    except AssertionError as e:
        print("\n❌  Test failed:", e)
        sys.exit(1)
    except Exception as e:
        print("\n⚠️   Unexpected error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
