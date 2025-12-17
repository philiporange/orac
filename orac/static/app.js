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
        // Trigger reflow for animation if needed
    }

    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        // Reset state
        btn.classList.remove('bg-surfaceHover', 'text-white', 'shadow-lg');
        btn.classList.add('text-slate-400');
        
        // Active state
        if (btn.dataset.section === section) {
            btn.classList.add('bg-surfaceHover', 'text-white');
            btn.classList.remove('text-slate-400');
        }
    });
    
    // Update Page Title
    const titleMap = {
        'prompts': 'Prompts Library',
        'flows': 'Workflow Orchestration',
        'skills': 'Capabilities & Tools',
        'agents': 'AI Agents',
        'teams': 'Collaborative Teams',
        'chat': 'Interactive Chat',
        'config': 'System Configuration'
    };
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titleMap[section] || 'Overview';

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
    container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 loading-pulse">Loading prompts...</div>';

    try {
        const prompts = await api('/prompts');
        if (prompts.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 border-2 border-dashed border-slate-800 rounded-xl">No prompts found</div>';
            return;
        }

        container.innerHTML = prompts.map(p => `
            <div class="group relative bg-surface border border-slate-800 rounded p-6 hover:border-blue-500/50 hover:shadow-md hover:shadow-blue-500/10 transition-all duration-300 cursor-pointer overflow-hidden" onclick="openRunPanel('prompt', '${p.name}')">
                <div class="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="w-8 h-8 bg-blue-500/20 rounded flex items-center justify-center text-blue-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                </div>
                <h3 class="text-lg font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">${p.name}</h3>
                <p class="text-secondary text-sm mb-4 line-clamp-2 h-10 leading-relaxed">${p.description || 'No description provided.'}</p>
                <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500 font-mono">
                    ${p.provider ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700 text-blue-300">${p.provider}</span>` : ''}
                    ${p.model_name ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${p.model_name}</span>` : ''}
                    ${p.parameters?.length ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${p.parameters.length} params</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="col-span-full text-center py-12 text-red-400 bg-red-900/10 rounded-xl border border-red-900/50">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Flows
// ============================================================================

async function refreshFlows() {
    const container = document.getElementById('flows-list');
    container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 loading-pulse">Loading flows...</div>';

    try {
        const flows = await api('/flows');
        if (flows.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 border-2 border-dashed border-slate-800 rounded-xl">No flows found</div>';
            return;
        }

        container.innerHTML = flows.map(f => `
            <div class="group relative bg-surface border border-slate-800 rounded p-6 hover:border-blue-500/50 hover:shadow-md hover:shadow-blue-500/10 transition-all duration-300 cursor-pointer overflow-hidden" onclick="openRunPanel('flow', '${f.name}')">
                <div class="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="w-8 h-8 bg-blue-500/20 rounded flex items-center justify-center text-blue-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                </div>
                <h3 class="text-lg font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">${f.name}</h3>
                <p class="text-secondary text-sm mb-4 line-clamp-2 h-10 leading-relaxed">${f.description || 'No description provided.'}</p>
                <div class="flex items-center gap-2 text-xs text-slate-500 font-mono">
                    <span class="flex items-center"><svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg> ${f.steps?.length || 0} steps</span>
                    ${f.inputs?.length ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${f.inputs.length} inputs</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="col-span-full text-center py-12 text-red-400 bg-red-900/10 rounded-xl border border-red-900/50">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Skills
// ============================================================================

async function refreshSkills() {
    const container = document.getElementById('skills-list');
    container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 loading-pulse">Loading skills...</div>';

    try {
        const skills = await api('/skills');
        if (skills.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 border-2 border-dashed border-slate-800 rounded-xl">No skills found</div>';
            return;
        }

        container.innerHTML = skills.map(s => `
            <div class="group relative bg-surface border border-slate-800 rounded p-6 hover:border-blue-500/50 hover:shadow-md hover:shadow-blue-500/10 transition-all duration-300 cursor-pointer overflow-hidden" onclick="openRunPanel('skill', '${s.name}')">
                <div class="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="w-8 h-8 bg-blue-500/20 rounded flex items-center justify-center text-blue-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                </div>
                <h3 class="text-lg font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">${s.name}</h3>
                <p class="text-secondary text-sm mb-4 line-clamp-2 h-10 leading-relaxed">${s.description || 'No description provided.'}</p>
                <div class="flex items-center gap-2 text-xs text-slate-500 font-mono">
                    ${s.inputs?.length ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${s.inputs.length} inputs</span>` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="col-span-full text-center py-12 text-red-400 bg-red-900/10 rounded-xl border border-red-900/50">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Agents
// ============================================================================

async function refreshAgents() {
    const container = document.getElementById('agents-list');
    container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 loading-pulse">Loading agents...</div>';

    try {
        const agents = await api('/agents');
        if (agents.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 border-2 border-dashed border-slate-800 rounded-xl">No agents found</div>';
            return;
        }

        container.innerHTML = agents.map(a => `
            <div class="group relative bg-surface border border-slate-800 rounded p-6 hover:border-blue-500/50 hover:shadow-md hover:shadow-blue-500/10 transition-all duration-300 cursor-pointer overflow-hidden" onclick="openRunPanel('agent', '${a.name}')">
                <div class="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="w-8 h-8 bg-blue-500/20 rounded flex items-center justify-center text-blue-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                </div>
                <h3 class="text-lg font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">${a.name}</h3>
                <p class="text-secondary text-sm mb-4 line-clamp-2 h-10 leading-relaxed">${a.description || 'No description provided.'}</p>
                <div class="flex items-center gap-2 text-xs text-slate-500 font-mono">
                    ${a.model_name ? `<span class="px-2 py-1 bg-slate-900 rounded border border-slate-700 text-blue-300">${a.model_name}</span>` : ''}
                    <span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${a.tools?.length || 0} tools</span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="col-span-full text-center py-12 text-red-400 bg-red-900/10 rounded-xl border border-red-900/50">Error: ${error.message}</div>`;
    }
}

// ============================================================================
// Teams
// ============================================================================

async function refreshTeams() {
    const container = document.getElementById('teams-list');
    container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 loading-pulse">Loading teams...</div>';

    try {
        const teams = await api('/teams');
        if (teams.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-12 text-slate-500 border-2 border-dashed border-slate-800 rounded-xl">No teams found</div>';
            return;
        }

        container.innerHTML = teams.map(t => `
            <div class="group relative bg-surface border border-slate-800 rounded p-6 hover:border-blue-500/50 hover:shadow-md hover:shadow-blue-500/10 transition-all duration-300 cursor-pointer overflow-hidden" onclick="openRunPanel('team', '${t.name}')">
                <div class="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="w-8 h-8 bg-blue-500/20 rounded flex items-center justify-center text-blue-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                </div>
                <h3 class="text-lg font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">${t.name}</h3>
                <p class="text-secondary text-sm mb-4 line-clamp-2 h-10 leading-relaxed">${t.description || 'No description provided.'}</p>
                <div class="flex items-center gap-2 text-xs text-slate-500 font-mono">
                    <span class="px-2 py-1 bg-slate-900 rounded border border-slate-700">${t.agents?.length || 0} agents</span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="col-span-full text-center py-12 text-red-400 bg-red-900/10 rounded-xl border border-red-900/50">Error: ${error.message}</div>`;
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
            `<div class="flex flex-col items-center justify-center h-full text-slate-600 space-y-4">
                <div class="p-4 bg-slate-900/50 rounded-full">
                    <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                </div>
                <p>Start a new conversation to interact with Orac</p>
            </div>`;
        return;
    }

    try {
        const conversation = await api(`/conversations/${convId}`);
        currentConversationId = convId;

        const container = document.getElementById('chat-messages');
        if (conversation.messages.length === 0) {
            container.innerHTML = '<div class="text-slate-500 text-center py-8">No messages yet</div>';
            return;
        }

        container.innerHTML = conversation.messages.map(m => `
            <div class="flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn">
                <div class="max-w-[80%] lg:max-w-[70%] rounded px-6 py-4 shadow-sm ${
                    m.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-br-none' 
                    : 'bg-surface border border-slate-800 text-slate-200 rounded-bl-none'
                }">
                    <pre class="whitespace-pre-wrap text-sm font-sans leading-relaxed">${escapeHtml(m.content)}</pre>
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
        `<div class="flex flex-col items-center justify-center h-full text-slate-600 space-y-4">
            <div class="p-4 bg-slate-900/50 rounded-full">
                <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
            </div>
            <p>Start a new conversation to interact with Orac</p>
        </div>`;
}

async function sendMessage(message) {
    const container = document.getElementById('chat-messages');

    // Remove empty state if present
    const emptyState = container.querySelector('.text-slate-600');
    if (emptyState) {
        container.innerHTML = '';
    }

    // User Message
    container.innerHTML += `
        <div class="flex justify-end fade-in">
            <div class="max-w-[80%] lg:max-w-[70%] rounded px-6 py-4 bg-blue-600 text-white rounded-br-none shadow-sm shadow-blue-500/10">
                <pre class="whitespace-pre-wrap text-sm font-sans leading-relaxed">${escapeHtml(message)}</pre>
            </div>
        </div>
    `;
    container.scrollTop = container.scrollHeight;

    // Loading Indicator
    const loadingId = 'loading-' + Date.now();
    container.innerHTML += `
        <div id="${loadingId}" class="flex justify-start fade-in">
            <div class="max-w-[80%] rounded px-6 py-4 bg-surface border border-slate-800 rounded-bl-none">
                <div class="flex space-x-2 items-center h-5">
                    <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0s"></div>
                    <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                    <div class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                </div>
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

        // Remove loading
        document.getElementById(loadingId)?.remove();

        if (response.success) {
            currentConversationId = response.conversation_id;

            container.innerHTML += `
                <div class="flex justify-start fade-in">
                    <div class="max-w-[80%] lg:max-w-[70%] rounded px-6 py-4 bg-surface border border-slate-800 text-slate-200 rounded-bl-none shadow-sm">
                        <pre class="whitespace-pre-wrap text-sm font-sans leading-relaxed">${escapeHtml(response.response)}</pre>
                    </div>
                </div>
            `;

            refreshConversations();
        } else {
            container.innerHTML += `
                <div class="flex justify-start fade-in">
                    <div class="max-w-[80%] rounded px-6 py-4 bg-red-900/20 border border-red-500/50 text-red-200">
                        Error: ${escapeHtml(response.error)}
                    </div>
                </div>
            `;
        }

        container.scrollTop = container.scrollHeight;
    } catch (error) {
        document.getElementById(loadingId)?.remove();
        container.innerHTML += `
            <div class="flex justify-start fade-in">
                <div class="max-w-[80%] rounded-2xl px-6 py-4 bg-red-900/20 border border-red-500/50 text-red-200">
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
    container.innerHTML = '<div class="text-slate-500 loading-pulse">Loading configuration...</div>';

    try {
        const [config, providers] = await Promise.all([
            api('/config'),
            api('/providers')
        ]);

        container.innerHTML = `
            <div class="bg-surface border border-slate-800 rounded overflow-hidden">
                <div class="px-6 py-4 border-b border-slate-800 bg-slate-900/30">
                    <h3 class="font-medium text-white">Current Environment</h3>
                </div>
                <div class="p-6 space-y-4">
                    <div class="grid grid-cols-2 gap-4">
                        <div class="p-4 bg-slate-900/50 rounded">
                            <span class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Active Provider</span>
                            <span class="text-lg font-mono text-blue-400">${config.provider || 'Not set'}</span>
                        </div>
                        <div class="p-4 bg-slate-900/50 rounded">
                            <span class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Active Model</span>
                            <span class="text-lg font-mono text-blue-400">${config.model || 'Not set'}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-surface border border-slate-800 rounded overflow-hidden">
                <div class="px-6 py-4 border-b border-slate-800 bg-slate-900/30">
                    <h3 class="font-medium text-white">Available Providers</h3>
                </div>
                <div class="divide-y divide-slate-800">
                    ${providers.map(p => `
                        <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-800/50 transition-colors">
                            <span class="font-medium text-slate-300">${p.name}</span>
                            <div class="flex items-center space-x-3">
                                <span class="px-2 py-1 rounded text-xs font-medium border ${
                                    p.available 
                                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                                    : 'bg-slate-800 text-slate-500 border-slate-700'
                                }">
                                    ${p.available ? 'Available' : 'Unavailable'}
                                </span>
                                <span class="px-2 py-1 rounded text-xs font-medium border ${
                                    p.has_consent 
                                    ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' 
                                    : 'bg-slate-800 text-slate-500 border-slate-700'
                                }">
                                    ${p.has_consent ? 'Consented' : 'No Consent'}
                                </span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>

            <div class="bg-surface border border-slate-800 rounded overflow-hidden">
                <div class="px-6 py-4 border-b border-slate-800 bg-slate-900/30">
                    <h3 class="font-medium text-white">Resource Paths</h3>
                </div>
                <div class="p-6 grid gap-6 md:grid-cols-2">
                    ${['prompts', 'flows', 'skills', 'agents'].map(type => `
                        <div>
                            <span class="block text-xs text-slate-500 uppercase tracking-wider mb-2">${type} Directories</span>
                            <ul class="space-y-1">
                                ${config[`${type}_dirs`]?.map(d => `
                                    <li class="px-3 py-2 bg-slate-900/50 rounded text-xs font-mono text-slate-400 truncate border border-slate-800">
                                        ${d}
                                    </li>
                                `).join('') || '<li class="text-slate-600 italic">None configured</li>'}
                            </ul>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="p-4 bg-red-900/20 border border-red-900/50 text-red-200 rounded-xl">Error: ${error.message}</div>`;
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
        document.getElementById('run-panel-submit').textContent = 'Execute';
        document.getElementById('run-panel-submit').className = 'px-6 py-2 rounded text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 shadow-md shadow-blue-500/10 transition-all';

        // Build form based on parameters/inputs
        const params = item.parameters || item.inputs || [];
        const content = document.getElementById('run-panel-content');

        if (params.length === 0) {
            content.innerHTML = `
                <div class="text-center py-8">
                    <p class="text-slate-400 mb-2">${item.description || 'No description available.'}</p>
                    <p class="text-sm text-slate-600">This component takes no parameters.</p>
                </div>
            `;
        } else {
            content.innerHTML = `
                <p class="text-slate-400 mb-6 text-sm bg-slate-900/50 p-3 rounded border border-slate-800">${item.description || 'No description available.'}</p>
                <form id="run-form" class="space-y-5">
                    ${params.map(p => `
                        <div>
                            <label class="block text-sm font-medium text-slate-300 mb-2">
                                ${p.name}
                                ${p.required ? '<span class="text-red-400 ml-1">*</span>' : '<span class="text-slate-600 text-xs ml-2">(Optional)</span>'}
                            </label>
                            ${p.description ? `<p class="text-xs text-slate-500 mb-2">${p.description}</p>` : ''}
                            ${p.type === 'text' || (p.type === 'string' && p.name.includes('text')) ? `
                                <textarea
                                    name="${p.name}"
                                    class="w-full bg-slate-900/50 border border-slate-700 rounded px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all placeholder-slate-600"
                                    rows="4"
                                    placeholder="Enter ${p.name}..."
                                    ${p.required ? 'required' : ''}
                                >${p.default || ''}</textarea>
                            ` : `
                                <input
                                    type="${p.type === 'number' || p.type === 'integer' ? 'number' : 'text'}"
                                    name="${p.name}"
                                    value="${p.default || ''}"
                                    class="w-full bg-slate-900/50 border border-slate-700 rounded px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all placeholder-slate-600"
                                    placeholder="Enter ${p.name}..."
                                    ${p.required ? 'required' : ''}
                                >
                            `}
                        </div>
                    `).join('')}
                </form>
            `;
        }

        document.getElementById('run-panel').classList.remove('hidden');
        // Trigger animation
        if (window.openModalAnim) window.openModalAnim();

    } catch (error) {
        alert(`Error loading ${type}: ${error.message}`);
    }
}

function closeRunPanel() {
    // Simple hide for now, could add exit animation
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
    submitBtn.innerHTML = '<span class="animate-pulse">Running...</span>';
    submitBtn.classList.add('opacity-75', 'cursor-not-allowed');
    
    resultPanel.classList.remove('hidden');
    resultText.textContent = 'Processing...';
    resultText.className = 'text-sm font-mono text-slate-400 animate-pulse';

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

        resultText.classList.remove('animate-pulse');
        
        if (result.success) {
            resultText.className = 'text-sm font-mono text-emerald-400 whitespace-pre-wrap';
            resultText.textContent = result.result || 'Success (no output)';
        } else {
            resultText.className = 'text-sm font-mono text-red-400 whitespace-pre-wrap';
            resultText.textContent = `Error: ${result.error}`;
        }
    } catch (error) {
        resultText.className = 'text-sm font-mono text-red-400 whitespace-pre-wrap';
        resultText.textContent = `Error: ${error.message}`;
    }

    submitBtn.disabled = false;
    submitBtn.textContent = 'Execute Again';
    submitBtn.classList.remove('opacity-75', 'cursor-not-allowed');
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    if (typeof text !== 'string') return text;
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
        // e.target is the backdrop div itself if clicked outside the panel
        if (e.target.id === 'run-panel' || e.target.classList.contains('backdrop-blur-sm')) {
            closeRunPanel();
        }
    });
});