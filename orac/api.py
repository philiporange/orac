"""
HTTP API server for Orac - exposes all orac functionality via REST endpoints.

Endpoints:
- GET /api/prompts - List all prompts
- GET /api/prompts/{name} - Get prompt details
- POST /api/prompts/{name}/run - Run a prompt with parameters
- GET /api/flows - List all flows
- GET /api/flows/{name} - Get flow details
- POST /api/flows/{name}/run - Run a flow with inputs
- GET /api/skills - List all skills
- GET /api/skills/{name} - Get skill details
- POST /api/skills/{name}/run - Run a skill
- GET /api/agents - List all agents
- GET /api/agents/{name} - Get agent details
- POST /api/agents/{name}/run - Run an agent
- GET /api/teams - List all teams
- POST /api/teams/{name}/run - Run a team
- POST /api/chat - Send a chat message
- GET /api/conversations - List conversations
- GET /api/conversations/{id} - Get conversation history
- GET /api/config - Get current configuration
- POST /api/create - Create new resources with AI
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Config, Provider, ConfigLoader
from .prompt import Prompt
from .flow import Flow, load_flow, list_flows, find_flow
from .skill import Skill, load_skill, list_skills, find_skill
from .agent import Agent, load_agent_spec, find_agent
from .team import Team, load_team_spec, find_team, list_teams
from .registry import ToolRegistry
from .providers import ProviderRegistry
from .auth import AuthManager
# ChatSession not used - we use Prompt directly for chat
from .conversation_db import ConversationDB
import orac


# Request/Response models
class PromptRunRequest(BaseModel):
    parameters: Dict[str, Any] = {}
    model_name: Optional[str] = None
    provider: Optional[str] = None


class FlowRunRequest(BaseModel):
    inputs: Dict[str, Any] = {}
    provider: Optional[str] = None


class SkillRunRequest(BaseModel):
    inputs: Dict[str, Any] = {}


class AgentRunRequest(BaseModel):
    inputs: Dict[str, Any] = {}
    provider: Optional[str] = None


class TeamRunRequest(BaseModel):
    inputs: Dict[str, Any] = {}
    provider: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None


class CreateResourceRequest(BaseModel):
    resource_type: str  # prompt, flow, agent, skill
    description: str
    name: Optional[str] = None
    project: bool = False


class RunResult(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None


class PromptInfo(BaseModel):
    name: str
    description: str
    parameters: List[Dict[str, Any]] = []
    model_name: Optional[str] = None
    provider: Optional[str] = None


class FlowInfo(BaseModel):
    name: str
    description: str
    inputs: List[Dict[str, Any]] = []
    steps: List[str] = []


class SkillInfo(BaseModel):
    name: str
    description: str
    inputs: List[Dict[str, Any]] = []


class AgentInfo(BaseModel):
    name: str
    description: str
    inputs: List[Dict[str, Any]] = []
    tools: List[str] = []
    model_name: Optional[str] = None


class TeamInfo(BaseModel):
    name: str
    description: str
    inputs: List[Dict[str, Any]] = []
    agents: List[str] = []


class ConversationInfo(BaseModel):
    id: str
    title: str
    created_at: str
    message_count: int


class ConfigInfo(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    prompts_dirs: List[str] = []
    flows_dirs: List[str] = []
    skills_dirs: List[str] = []
    agents_dirs: List[str] = []


# Global state
_client = None
_auth_manager = None


def get_client():
    """Get or initialize the orac client."""
    global _client, _auth_manager
    if _client is None:
        _auth_manager = AuthManager()
        if orac.is_initialized():
            _client = orac.get_client()
        else:
            # Try to initialize with consented providers
            consented = _auth_manager.get_consented_providers()
            if consented:
                _client = orac.init(default_provider=consented[0])
            else:
                # Initialize without providers - will fail on API calls
                _client = None
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize client on startup."""
    get_client()
    yield


# Create FastAPI app
app = FastAPI(
    title="Orac API",
    description="REST API for the Orac LLM framework",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================================
# Prompt endpoints
# ============================================================================

@app.get("/api/prompts", response_model=List[PromptInfo])
async def list_prompts():
    """List all available prompts."""
    import yaml

    prompts = []
    seen = set()

    for prompts_dir in Config.get_prompts_dirs():
        if not prompts_dir.exists():
            continue
        for yaml_file in list(prompts_dir.glob("*.yaml")) + list(prompts_dir.glob("*.yml")):
            name = yaml_file.stem
            if name in seen:
                continue
            seen.add(name)
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                prompts.append(PromptInfo(
                    name=name,
                    description=data.get("description", ""),
                    parameters=data.get("parameters", []),
                    model_name=data.get("model_name"),
                    provider=data.get("provider")
                ))
            except Exception:
                prompts.append(PromptInfo(name=name, description="(Error loading)"))

    return sorted(prompts, key=lambda p: p.name)


@app.get("/api/prompts/{name}", response_model=PromptInfo)
async def get_prompt(name: str):
    """Get details of a specific prompt."""
    import yaml

    try:
        path = Config.find_resource(name, 'prompts')
        if not path:
            raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        return PromptInfo(
            name=name,
            description=data.get("description", ""),
            parameters=data.get("parameters", []),
            model_name=data.get("model_name"),
            provider=data.get("provider")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prompts/{name}/run", response_model=RunResult)
async def run_prompt(name: str, request: PromptRunRequest):
    """Run a prompt with the given parameters."""
    try:
        prompt = Prompt(name)

        # Apply overrides
        if request.provider:
            prompt.provider = request.provider
        if request.model_name:
            prompt.model_name = request.model_name

        result = prompt.completion(**request.parameters)
        return RunResult(success=True, result=result)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Flow endpoints
# ============================================================================

@app.get("/api/flows", response_model=List[FlowInfo])
async def list_flows_endpoint():
    """List all available flows."""
    flows = []
    seen = set()

    for flows_dir in Config.get_flows_dirs():
        if not flows_dir.exists():
            continue
        for flow_data in list_flows(str(flows_dir)):
            name = flow_data['name']
            if name in seen:
                continue
            seen.add(name)
            flows.append(FlowInfo(
                name=name,
                description=flow_data.get('description', ''),
                inputs=flow_data.get('inputs', []),
                steps=[s.get('name', '') for s in flow_data.get('steps', [])]
            ))

    return sorted(flows, key=lambda f: f.name)


@app.get("/api/flows/{name}", response_model=FlowInfo)
async def get_flow(name: str):
    """Get details of a specific flow."""
    try:
        path = find_flow(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")
        spec = load_flow(path)
        return FlowInfo(
            name=spec.name,
            description=spec.description or "",
            inputs=[{"name": i.name, "type": i.type, "required": i.required, "default": i.default, "description": i.description} for i in spec.inputs],
            steps=[s.name for s in spec.steps]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/flows/{name}/run", response_model=RunResult)
async def run_flow(name: str, request: FlowRunRequest):
    """Run a flow with the given inputs."""
    try:
        path = find_flow(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")
        spec = load_flow(path)

        provider = Provider(request.provider) if request.provider else None
        flow = Flow(spec, provider=provider)
        result = flow.execute(request.inputs)
        return RunResult(success=True, result=str(result))
    except HTTPException:
        raise
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Skill endpoints
# ============================================================================

@app.get("/api/skills", response_model=List[SkillInfo])
async def list_skills_endpoint():
    """List all available skills."""
    skills = []
    seen = set()

    for skills_dir in Config.get_skills_dirs():
        if not skills_dir.exists():
            continue
        for skill_data in list_skills(str(skills_dir)):
            name = skill_data['name']
            if name in seen:
                continue
            seen.add(name)
            skills.append(SkillInfo(
                name=name,
                description=skill_data.get('description', ''),
                inputs=skill_data.get('inputs', [])
            ))

    return sorted(skills, key=lambda s: s.name)


@app.get("/api/skills/{name}", response_model=SkillInfo)
async def get_skill(name: str):
    """Get details of a specific skill."""
    try:
        path = find_skill(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        spec = load_skill(path)
        return SkillInfo(
            name=spec.name,
            description=spec.description or "",
            inputs=[{"name": i.name, "type": i.type, "required": i.required, "default": i.default, "description": i.description} for i in spec.inputs]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/{name}/run", response_model=RunResult)
async def run_skill(name: str, request: SkillRunRequest):
    """Run a skill with the given inputs."""
    try:
        path = find_skill(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        spec = load_skill(path)
        skill = Skill(spec)
        result = skill.execute(request.inputs)
        return RunResult(success=True, result=str(result))
    except HTTPException:
        raise
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Agent endpoints
# ============================================================================

@app.get("/api/agents", response_model=List[AgentInfo])
async def list_agents_endpoint():
    """List all available agents."""
    agents = []
    seen = set()

    for agents_dir in Config.get_agents_dirs():
        if not agents_dir.exists():
            continue
        for yaml_file in list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml")):
            name = yaml_file.stem
            if name in seen:
                continue
            seen.add(name)
            try:
                spec = load_agent_spec(yaml_file)
                agents.append(AgentInfo(
                    name=spec.name,
                    description=spec.description or "",
                    inputs=[{"name": i.get("name"), "type": i.get("type", "string"), "required": i.get("required", False), "default": i.get("default"), "description": i.get("description", "")} for i in spec.inputs],
                    tools=spec.tools,
                    model_name=spec.model_name
                ))
            except Exception:
                agents.append(AgentInfo(name=name, description="(Error loading)"))

    return sorted(agents, key=lambda a: a.name)


@app.get("/api/agents/{name}", response_model=AgentInfo)
async def get_agent(name: str):
    """Get details of a specific agent."""
    try:
        path = find_agent(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
        spec = load_agent_spec(path)
        return AgentInfo(
            name=spec.name,
            description=spec.description or "",
            inputs=[{"name": i.get("name"), "type": i.get("type", "string"), "required": i.get("required", False), "default": i.get("default"), "description": i.get("description", "")} for i in spec.inputs],
            tools=spec.tools,
            model_name=spec.model_name
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{name}/run", response_model=RunResult)
async def run_agent(name: str, request: AgentRunRequest):
    """Run an agent with the given inputs."""
    try:
        path = find_agent(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
        spec = load_agent_spec(path)

        # Get provider registry from client
        client = get_client()
        if not client:
            return RunResult(success=False, error="No providers configured. Run 'orac auth init' first.")

        provider = Provider(request.provider) if request.provider else client.default_provider
        registry = ToolRegistry(
            prompts_dir=str(Config.get_prompts_dir()),
            flows_dir=str(Config.get_flows_dir()),
            skills_dir=str(Config.get_skills_dir())
        )

        agent = Agent(spec, registry, client.provider_registry, provider=provider)
        result = agent.run(**request.inputs)
        return RunResult(success=True, result=result)
    except HTTPException:
        raise
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Team endpoints
# ============================================================================

@app.get("/api/teams", response_model=List[TeamInfo])
async def list_teams_endpoint():
    """List all available teams."""
    teams = []
    seen = set()

    for teams_dir in Config.get_teams_dirs():
        if not teams_dir.exists():
            continue
        for team_data in list_teams(str(teams_dir)):
            name = team_data['name']
            if name in seen:
                continue
            seen.add(name)
            teams.append(TeamInfo(
                name=name,
                description=team_data.get('description', ''),
                inputs=team_data.get('inputs', []),
                agents=[a.get('name', '') for a in team_data.get('agents', [])]
            ))

    return sorted(teams, key=lambda t: t.name)


@app.post("/api/teams/{name}/run", response_model=RunResult)
async def run_team(name: str, request: TeamRunRequest):
    """Run a team with the given inputs."""
    try:
        path = find_team(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"Team '{name}' not found")
        spec = load_team_spec(path)

        client = get_client()
        if not client:
            return RunResult(success=False, error="No providers configured. Run 'orac auth init' first.")

        registry = ToolRegistry(
            prompts_dir=str(Config.get_prompts_dir()),
            flows_dir=str(Config.get_flows_dir()),
            skills_dir=str(Config.get_skills_dir())
        )

        team = Team(spec, registry, agents_dir=str(Config.get_agents_dir()))
        result = team.run(**request.inputs)
        return RunResult(success=True, result=result)
    except HTTPException:
        raise
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Chat endpoints
# ============================================================================

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Send a chat message and get a response."""
    try:
        # Get or create conversation
        db = ConversationDB()

        if request.conversation_id:
            conversation = db.get_conversation(request.conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            history = db.get_messages(request.conversation_id)
        else:
            # Create new conversation
            conv_id = db.create_conversation(title=request.message[:50])
            history = []
            request.conversation_id = conv_id

        # Build message history for the prompt
        message_history = [{"role": m["role"], "text": m["content"]} for m in history]

        # Create a chat prompt instance
        try:
            chat_prompt = Prompt("chat")
        except FileNotFoundError:
            # If no chat prompt exists, use a simple inline prompt
            chat_prompt = Prompt.__new__(Prompt)
            chat_prompt.system_prompt = "You are a helpful assistant."
            chat_prompt.prompt_template = "${message}"
            chat_prompt.parameters = [{"name": "message", "type": "string", "required": True}]
            chat_prompt.model_name = request.model_name or Config.get_default_model_name()
            chat_prompt.provider = request.provider or (Config.get_provider_from_env().value if Config.get_provider_from_env() else "google")
            chat_prompt.generation_config = {"temperature": 0.7}
            chat_prompt.use_conversation = False

        # Override model and provider if specified
        if request.model_name:
            chat_prompt.model_name = request.model_name
        if request.provider:
            chat_prompt.provider = request.provider

        # Get response
        response = chat_prompt.completion(
            message_history=message_history,
            message=request.message
        )

        # Save messages
        db.add_message(request.conversation_id, "user", request.message)
        db.add_message(request.conversation_id, "model", response)

        return {
            "success": True,
            "response": response,
            "conversation_id": request.conversation_id
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/conversations", response_model=List[ConversationInfo])
async def list_conversations():
    """List all conversations."""
    db = ConversationDB()
    conversations = db.list_conversations()
    return [
        ConversationInfo(
            id=c["id"],
            title=c["title"],
            created_at=c["created_at"],
            message_count=c.get("message_count", 0)
        )
        for c in conversations
    ]


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get conversation history."""
    db = ConversationDB()
    conversation = db.get_conversation(conv_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.get_messages(conv_id)
    return {
        "id": conv_id,
        "title": conversation.get("title", ""),
        "messages": messages
    }


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation."""
    db = ConversationDB()
    db.delete_conversation(conv_id)
    return {"success": True}


# ============================================================================
# Config endpoints
# ============================================================================

@app.get("/api/config", response_model=ConfigInfo)
async def get_config():
    """Get current configuration."""
    loader = ConfigLoader()
    config = loader.get_merged_config()

    return ConfigInfo(
        provider=config.get("provider"),
        model=config.get("model"),
        prompts_dirs=[str(p) for p in Config.get_prompts_dirs()],
        flows_dirs=[str(p) for p in Config.get_flows_dirs()],
        skills_dirs=[str(p) for p in Config.get_skills_dirs()],
        agents_dirs=[str(p) for p in Config.get_agents_dirs()]
    )


@app.get("/api/providers")
async def list_providers():
    """List available providers and their status."""
    auth_manager = AuthManager()
    detected = auth_manager.detect_available_providers()

    providers = []
    for provider, info in detected.items():
        providers.append({
            "name": provider.value,
            "available": info["available"],
            "has_consent": info["has_consent"],
            "env_var": info["env_var"]
        })

    return providers


# ============================================================================
# Create endpoint
# ============================================================================

@app.post("/api/create", response_model=RunResult)
async def create_resource(request: CreateResourceRequest):
    """Create a new resource using AI."""
    try:
        from .cli.create import create_resource as do_create

        # This is a long-running operation, run synchronously for now
        # In production, this should be a background task
        do_create(
            resource_type=request.resource_type,
            description=request.description,
            name=request.name,
            project=request.project,
            dry_run=False
        )

        return RunResult(success=True, result=f"Created {request.resource_type}")
    except Exception as e:
        return RunResult(success=False, error=str(e))


# ============================================================================
# Frontend serving
# ============================================================================

@app.get("/")
async def serve_frontend():
    """Serve the frontend."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return {"message": "Orac API is running. Frontend not found at /static/index.html"}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
