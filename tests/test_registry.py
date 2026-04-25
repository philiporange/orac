"""Tests for layered ToolRegistry resource discovery."""

from orac.config import Config
from orac.registry import ToolRegistry


def _write_yaml(path, name, description):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"name: {name}\ndescription: {description}\n")


def test_registry_loads_project_user_and_package_dirs(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    user_dir = tmp_path / "user"
    package_dir = tmp_path / "package"

    for resource_type in ["prompts", "flows", "skills", "teams", "agents"]:
        (package_dir / resource_type).mkdir(parents=True)

    _write_yaml(project_dir / ".orac" / "skills" / "shared.yaml", "shared", "Project skill")
    _write_yaml(user_dir / "skills" / "shared.yaml", "shared", "User skill")
    _write_yaml(user_dir / "skills" / "user_only.yaml", "user_only", "User-only skill")
    _write_yaml(package_dir / "skills" / "package_only.yaml", "package_only", "Package-only skill")
    _write_yaml(project_dir / ".orac" / "agents" / "project_agent.yaml", "project_agent", "Project agent")
    _write_yaml(user_dir / "prompts" / "user_prompt.yaml", "user_prompt", "User prompt")

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(Config, "_USER_CONFIG_DIR", user_dir)
    monkeypatch.setenv("ORAC_DEFAULT_PROMPTS_DIR", str(package_dir / "prompts"))
    monkeypatch.setenv("ORAC_DEFAULT_FLOWS_DIR", str(package_dir / "flows"))
    monkeypatch.setenv("ORAC_DEFAULT_SKILLS_DIR", str(package_dir / "skills"))
    monkeypatch.setenv("ORAC_DEFAULT_TEAMS_DIR", str(package_dir / "teams"))
    monkeypatch.setenv("ORAC_DEFAULT_AGENTS_DIR", str(package_dir / "agents"))

    registry = ToolRegistry()

    assert registry.get_tool("tool:shared").description == "Project skill"
    assert registry.get_tool("tool:user_only").description == "User-only skill"
    assert registry.get_tool("tool:package_only").description == "Package-only skill"
    assert registry.get_tool("agent:project_agent").description == "Project agent"
    assert registry.get_tool("prompt:user_prompt").description == "User prompt"
    assert registry.tools_dirs == [
        project_dir / ".orac" / "skills",
        user_dir / "skills",
        package_dir / "skills",
    ]


def test_registry_supports_explicit_multiple_dirs(tmp_path):
    high_priority = tmp_path / "high"
    low_priority = tmp_path / "low"
    empty = tmp_path / "empty"
    empty.mkdir()

    _write_yaml(high_priority / "shared.yaml", "shared", "High priority")
    _write_yaml(low_priority / "shared.yaml", "shared", "Low priority")
    _write_yaml(low_priority / "other.yaml", "other", "Other")

    registry = ToolRegistry(
        prompts_dir=empty,
        flows_dir=empty,
        tools_dirs=[high_priority, low_priority],
        teams_dir=empty,
        agents_dir=empty,
    )

    assert registry.get_tool("tool:shared").description == "High priority"
    assert registry.get_tool("tool:other").description == "Other"
