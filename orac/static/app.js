/**
 * Orac Frontend Application
 * Vanilla JavaScript client for the Orac API
 */

const API_BASE = '/api';

// State
let currentSection = 'prompts';
let currentConversationId = null;
let runContext = null; // { type: 'prompt'|'flow'|'skill'|'agent'|'team', name: string, item: object }

// ============================================================================
// API Functions
// ============================================================================

async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: {
            'Content-Type': 'application/json',
        },
        ...options
    };

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || 'API error');
        }
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// ============================================================================
// Navigation
// ============================================================================

function showSection(section) {
    // Hide all sections
    document.querySelectorAll('.section').forEach(el => el.classList.add('hidden'));

    // Show selected section
    const sectionEl = document.getElementById(`section-${section}`);
    if (sectionEl) {
        sectionEl.classList.remove('hidden');
        sectionEl.classList.add('fade-in');
    }

    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('bg-gray-700', 'text-white');
        if (btn.dataset.section === section) {
            btn.classList.add('bg-gray-700', 'text-white');
        }
    });

    currentSection = section;

    // Load section data
    switch (section) {
        case 'prompts': refreshPrompts(); break;
        case 'flows': refreshFlows(); break;
        case 'skills': refreshSkills(); break;
        case 'agents': refreshAgents(); break;
        case 'teams': refreshTeams(); break;
        case 'chat': refreshConversations(); break;
        case 'config': refreshConfig(); break;
    }
}

// ============================================================================
// Prompts
// ============================================================================

async function refreshPrompts() {
    const container = document.getElementById('prompts-list');
    container.innerHTML = '<div class="loading text-gray-400">Loading prompts...</div>';

    try {
        const prompts = await api('/prompts');
        if (prompts.length === 0) {
            container.innerHTML = '<div class="text-gray-400">No prompts found</div>';
            return;
        }

        container.innerHTML = prompts.map(p => `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition cursor-pointer" onclick="openRunPanel('prompt', '${p.name}')">
                <h3 class="font-medium text-white mb-1">${p.name}</h3>
                <p class="text-gray-400 text-sm mb-2 line-clamp-2">${p.description || 'No description'}</p>
                <div class="flex items-center space-x-2 text-xs text-gray-500">
                    ${p.provider ? `<span class="px-2 py-0.5 bg-gray-700 rounded">${p.provider}</span>` : ''}
                    ${p.model_name ? `<span class="px-2 py-0.5 bg-gray-700 rounded">${p.model_name}</span>` : ''}
                    ${p.parameters?.length ? `<span>${p.parameters.length} params</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Flows
// ============================================================================

async function refreshFlows() {
    const container = document.getElementById('flows-list');
    container.innerHTML = '<div class="loading text-gray-400">Loading flows...</div>';

    try {
        const flows = await api('/flows');
        if (flows.length === 0) {
            container.innerHTML = '<div class="text-gray-400">No flows found</div>';
            return;
        }

        container.innerHTML = flows.map(f => `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition cursor-pointer" onclick="openRunPanel('flow', '${f.name}')">
                <h3 class="font-medium text-white mb-1">${f.name}</h3>
                <p class="text-gray-400 text-sm mb-2 line-clamp-2">${f.description || 'No description'}</p>
                <div class="flex items-center space-x-2 text-xs text-gray-500">
                    <span>${f.steps?.length || 0} steps</span>
                    ${f.inputs?.length ? `<span>${f.inputs.length} inputs</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Skills
// ============================================================================

async function refreshSkills() {
    const container = document.getElementById('skills-list');
    container.innerHTML = '<div class="loading text-gray-400">Loading skills...</div>';

    try {
        const skills = await api('/skills');
        if (skills.length === 0) {
            container.innerHTML = '<div class="text-gray-400">No skills found</div>';
            return;
        }

        container.innerHTML = skills.map(s => `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition cursor-pointer" onclick="openRunPanel('skill', '${s.name}')">
                <h3 class="font-medium text-white mb-1">${s.name}</h3>
                <p class="text-gray-400 text-sm mb-2 line-clamp-2">${s.description || 'No description'}</p>
                <div class="flex items-center space-x-2 text-xs text-gray-500">
                    ${s.inputs?.length ? `<span>${s.inputs.length} inputs</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Agents
// ============================================================================

async function refreshAgents() {
    const container = document.getElementById('agents-list');
    container.innerHTML = '<div class="loading text-gray-400">Loading agents...</div>';

    try {
        const agents = await api('/agents');
        if (agents.length === 0) {
            container.innerHTML = '<div class="text-gray-400">No agents found</div>';
            return;
        }

        container.innerHTML = agents.map(a => `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition cursor-pointer" onclick="openRunPanel('agent', '${a.name}')">
                <h3 class="font-medium text-white mb-1">${a.name}</h3>
                <p class="text-gray-400 text-sm mb-2 line-clamp-2">${a.description || 'No description'}</p>
                <div class="flex items-center space-x-2 text-xs text-gray-500">
                    ${a.model_name ? `<span class="px-2 py-0.5 bg-gray-700 rounded">${a.model_name}</span>` : ''}
                    <span>${a.tools?.length || 0} tools</span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Teams
// ============================================================================

async function refreshTeams() {
    const container = document.getElementById('teams-list');
    container.innerHTML = '<div class="loading text-gray-400">Loading teams...</div>';

    try {
        const teams = await api('/teams');
        if (teams.length === 0) {
            container.innerHTML = '<div class="text-gray-400">No teams found</div>';
            return;
        }

        container.innerHTML = teams.map(t => `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition cursor-pointer" onclick="openRunPanel('team', '${t.name}')">
                <h3 class="font-medium text-white mb-1">${t.name}</h3>
                <p class="text-gray-400 text-sm mb-2 line-clamp-2">${t.description || 'No description'}</p>
                <div class="flex items-center space-x-2 text-xs text-gray-500">
                    <span>${t.agents?.length || 0} agents</span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Chat
// ============================================================================

async function refreshConversations() {
    const select = document.getElementById('chat-conversation');

    try {
        const conversations = await api('/conversations');
        select.innerHTML = '<option value="">New Conversation</option>' +
            conversations.map(c => `<option value="${c.id}">${c.title}</option>`).join('');

        if (currentConversationId) {
            select.value = currentConversationId;
            await loadConversation(currentConversationId);
        }
    } catch (error) {
        console.error('Failed to load conversations:', error);
    }
}

async function loadConversation(convId) {
    if (!convId) {
        document.getElementById('chat-messages').innerHTML =
            '<div class="text-gray-400 text-center py-8">Start a conversation</div>';
        return;
    }

    try {
        const conversation = await api(`/conversations/${convId}`);
        currentConversationId = convId;

        const container = document.getElementById('chat-messages');
        if (conversation.messages.length === 0) {
            container.innerHTML = '<div class="text-gray-400 text-center py-8">No messages yet</div>';
            return;
        }

        container.innerHTML = conversation.messages.map(m => `
            <div class="flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}">
                <div class="max-w-[80%] rounded-lg px-4 py-2 ${m.role === 'user' ? 'bg-primary text-white' : 'bg-gray-700 text-gray-100'}">
                    <pre class="whitespace-pre-wrap text-sm">${escapeHtml(m.content)}</pre>
                </div>
            </div>
        `).join('');

        container.scrollTop = container.scrollHeight;
    } catch (error) {
        console.error('Failed to load conversation:', error);
    }
}

function newConversation() {
    currentConversationId = null;
    document.getElementById('chat-conversation').value = '';
    document.getElementById('chat-messages').innerHTML =
        '<div class="text-gray-400 text-center py-8">Start a conversation</div>';
}

async function sendMessage(message) {
    const container = document.getElementById('chat-messages');

    // Add user message immediately
    if (container.querySelector('.text-gray-400.text-center')) {
        container.innerHTML = '';
    }

    container.innerHTML += `
        <div class="flex justify-end fade-in">
            <div class="max-w-[80%] rounded-lg px-4 py-2 bg-primary text-white">
                <pre class="whitespace-pre-wrap text-sm">${escapeHtml(message)}</pre>
            </div>
        </div>
    `;
    container.scrollTop = container.scrollHeight;

    // Add loading indicator
    container.innerHTML += `
        <div class="flex justify-start" id="loading-message">
            <div class="max-w-[80%] rounded-lg px-4 py-2 bg-gray-700 text-gray-400">
                <span class="loading">Thinking...</span>
            </div>
        </div>
    `;
    container.scrollTop = container.scrollHeight;

    try {
        const response = await api('/chat', {
            method: 'POST',
            body: JSON.stringify({
                message,
                conversation_id: currentConversationId
            })
        });

        // Remove loading indicator
        document.getElementById('loading-message')?.remove();

        if (response.success) {
            currentConversationId = response.conversation_id;

            container.innerHTML += `
                <div class="flex justify-start fade-in">
                    <div class="max-w-[80%] rounded-lg px-4 py-2 bg-gray-700 text-gray-100">
                        <pre class="whitespace-pre-wrap text-sm">${escapeHtml(response.response)}</pre>
                    </div>
                </div>
            `;

            // Update conversation selector
            refreshConversations();
        } else {
            container.innerHTML += `
                <div class="flex justify-start fade-in">
                    <div class="max-w-[80%] rounded-lg px-4 py-2 bg-red-900 text-red-200">
                        Error: ${escapeHtml(response.error)}
                    </div>
                </div>
            `;
        }

        container.scrollTop = container.scrollHeight;
    } catch (error) {
        document.getElementById('loading-message')?.remove();
        container.innerHTML += `
            <div class="flex justify-start fade-in">
                <div class="max-w-[80%] rounded-lg px-4 py-2 bg-red-900 text-red-200">
                    Error: ${escapeHtml(error.message)}
                </div>
            </div>
        `;
        container.scrollTop = container.scrollHeight;
    }
}

// ============================================================================
// Config
// ============================================================================

async function refreshConfig() {
    const container = document.getElementById('config-content');
    container.innerHTML = '<div class="loading text-gray-400">Loading configuration...</div>';

    try {
        const [config, providers] = await Promise.all([
            api('/config'),
            api('/providers')
        ]);

        container.innerHTML = `
            <div class="bg-gray-800 rounded-lg p-4">
                <h3 class="font-medium mb-4">Current Settings</h3>
                <div class="space-y-2 text-sm">
                    <div class="flex justify-between">
                        <span class="text-gray-400">Provider:</span>
                        <span>${config.provider || 'Not set'}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-gray-400">Model:</span>
                        <span>${config.model || 'Not set'}</span>
                    </div>
                </div>
            </div>

            <div class="bg-gray-800 rounded-lg p-4">
                <h3 class="font-medium mb-4">Providers</h3>
                <div class="space-y-2">
                    ${providers.map(p => `
                        <div class="flex items-center justify-between text-sm">
                            <span>${p.name}</span>
                            <div class="flex items-center space-x-2">
                                <span class="px-2 py-0.5 rounded text-xs ${p.available ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}">
                                    ${p.available ? 'Available' : 'Not available'}
                                </span>
                                <span class="px-2 py-0.5 rounded text-xs ${p.has_consent ? 'bg-blue-900 text-blue-300' : 'bg-gray-700 text-gray-400'}">
                                    ${p.has_consent ? 'Consented' : 'No consent'}
                                </span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>

            <div class="bg-gray-800 rounded-lg p-4">
                <h3 class="font-medium mb-4">Resource Directories</h3>
                <div class="space-y-3 text-sm">
                    <div>
                        <span class="text-gray-400">Prompts:</span>
                        <ul class="mt-1 space-y-1 text-xs text-gray-300">
                            ${config.prompts_dirs.map(d => `<li class="font-mono">${d}</li>`).join('')}
                        </ul>
                    </div>
                    <div>
                        <span class="text-gray-400">Flows:</span>
                        <ul class="mt-1 space-y-1 text-xs text-gray-300">
                            ${config.flows_dirs.map(d => `<li class="font-mono">${d}</li>`).join('')}
                        </ul>
                    </div>
                    <div>
                        <span class="text-gray-400">Skills:</span>
                        <ul class="mt-1 space-y-1 text-xs text-gray-300">
                            ${config.skills_dirs.map(d => `<li class="font-mono">${d}</li>`).join('')}
                        </ul>
                    </div>
                    <div>
                        <span class="text-gray-400">Agents:</span>
                        <ul class="mt-1 space-y-1 text-xs text-gray-300">
                            ${config.agents_dirs.map(d => `<li class="font-mono">${d}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="text-red-400">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Run Panel
// ============================================================================

async function openRunPanel(type, name) {
    try {
        const item = await api(`/${type}s/${name}`);
        runContext = { type, name, item };

        document.getElementById('run-panel-title').textContent = `Run ${type}: ${name}`;
        document.getElementById('run-panel-result').classList.add('hidden');
        document.getElementById('run-panel-submit').disabled = false;
        document.getElementById('run-panel-submit').textContent = 'Run';

        // Build form based on parameters/inputs
        const params = item.parameters || item.inputs || [];
        const content = document.getElementById('run-panel-content');

        if (params.length === 0) {
            content.innerHTML = `
                <p class="text-gray-400 mb-4">${item.description || 'No description'}</p>
                <p class="text-sm text-gray-500">This ${type} has no parameters.</p>
            `;
        } else {
            content.innerHTML = `
                <p class="text-gray-400 mb-4">${item.description || 'No description'}</p>
                <form id="run-form" class="space-y-4">
                    ${params.map(p => `
                        <div>
                            <label class="block text-sm font-medium mb-1">
                                ${p.name}
                                ${p.required ? '<span class="text-red-400">*</span>' : ''}
                            </label>
                            ${p.description ? `<p class="text-xs text-gray-500 mb-1">${p.description}</p>` : ''}
                            ${p.type === 'text' || (p.type === 'string' && p.name.includes('text')) ? `
                                <textarea
                                    name="${p.name}"
                                    class="w-full bg-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    rows="4"
                                    ${p.required ? 'required' : ''}
                                >${p.default || ''}</textarea>
                            ` : `
                                <input
                                    type="${p.type === 'number' || p.type === 'integer' ? 'number' : 'text'}"
                                    name="${p.name}"
                                    value="${p.default || ''}"
                                    class="w-full bg-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    ${p.required ? 'required' : ''}
                                >
                            `}
                        </div>
                    `).join('')}
                </form>
            `;
        }

        document.getElementById('run-panel').classList.remove('hidden');
    } catch (error) {
        alert(`Error loading ${type}: ${error.message}`);
    }
}

function closeRunPanel() {
    document.getElementById('run-panel').classList.add('hidden');
    runContext = null;
}

async function executeRun() {
    if (!runContext) return;

    const { type, name } = runContext;
    const form = document.getElementById('run-form');
    const submitBtn = document.getElementById('run-panel-submit');
    const resultPanel = document.getElementById('run-panel-result');
    const resultText = document.getElementById('run-result-text');

    // Collect form data
    const params = {};
    if (form) {
        const formData = new FormData(form);
        for (const [key, value] of formData.entries()) {
            if (value) params[key] = value;
        }
    }

    // Show loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Running...';
    resultPanel.classList.remove('hidden');
    resultText.textContent = 'Processing...';
    resultText.className = 'text-sm text-gray-400 loading';

    try {
        let endpoint = `/${type}s/${name}/run`;
        let body = {};

        if (type === 'prompt') {
            body = { parameters: params };
        } else {
            body = { inputs: params };
        }

        const result = await api(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });

        resultText.className = 'text-sm';
        if (result.success) {
            resultText.classList.add('text-green-300');
            resultText.textContent = result.result || 'Success (no output)';
        } else {
            resultText.classList.add('text-red-300');
            resultText.textContent = `Error: ${result.error}`;
        }
    } catch (error) {
        resultText.className = 'text-sm text-red-300';
        resultText.textContent = `Error: ${error.message}`;
    }

    submitBtn.disabled = false;
    submitBtn.textContent = 'Run Again';
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize with prompts section
    showSection('prompts');

    // Chat form submission
    document.getElementById('chat-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (message) {
            input.value = '';
            await sendMessage(message);
        }
    });

    // Conversation selector
    document.getElementById('chat-conversation').addEventListener('change', (e) => {
        loadConversation(e.target.value);
    });

    // Close run panel on escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeRunPanel();
        }
    });

    // Close run panel on backdrop click
    document.getElementById('run-panel').addEventListener('click', (e) => {
        if (e.target.id === 'run-panel') {
            closeRunPanel();
        }
    });
});
