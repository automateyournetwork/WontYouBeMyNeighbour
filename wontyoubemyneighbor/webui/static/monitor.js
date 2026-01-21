/**
 * ASI Network Monitor
 *
 * JavaScript for monitoring deployed multi-agent networks
 */

// State
let deployedNetworks = [];
let savedNetworks = [];
let refreshInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    refreshNetworks();
    loadSavedNetworks();

    // Auto-refresh every 10 seconds
    refreshInterval = setInterval(refreshNetworks, 10000);
});

// Load deployed networks
async function refreshNetworks() {
    const indicator = document.getElementById('refresh-indicator');
    indicator.classList.add('loading');

    try {
        const response = await fetch('/api/wizard/networks');
        deployedNetworks = await response.json();
        renderNetworks();
        updateSummary();

        document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
    } catch (error) {
        console.error('Failed to load networks:', error);
    } finally {
        indicator.classList.remove('loading');
    }
}

// Load saved networks from persistence
// TODO: Feature not yet implemented - disabled until save/load ASI is built
async function loadSavedNetworks() {
    // Disabled - saved networks feature not yet implemented
    return;
    /*
    try {
        const response = await fetch('/api/wizard/libraries/networks');
        savedNetworks = await response.json();
        renderSavedNetworks();
    } catch (error) {
        console.error('Failed to load saved networks:', error);
    }
    */
}

// Render deployed networks
function renderNetworks() {
    const container = document.getElementById('networks-container');

    if (deployedNetworks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>No Networks Deployed</h3>
                <p>Use the Network Builder to create and deploy a multi-agent network.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="network-grid">
            ${deployedNetworks.map(network => renderNetworkCard(network)).join('')}
        </div>
    `;

    // Auto-load agent details for each network
    deployedNetworks.forEach(network => {
        viewNetworkDetails(network.network_id);
    });
}

// Render a single network card
function renderNetworkCard(network) {
    const agentCount = network.agent_count || 0;

    return `
        <div class="network-card" data-network-id="${network.network_id}">
            <div class="network-header">
                <span class="network-name">${network.name || network.network_id}</span>
                <span class="network-status ${network.status}">${network.status}</span>
            </div>
            <div class="network-body">
                <div class="network-info">
                    <div class="info-item">
                        <span class="label">Docker Network:</span>
                        <span class="value">${network.docker_network || 'N/A'}</span>
                    </div>
                    <div class="info-item">
                        <span class="label">Agents:</span>
                        <span class="value">${agentCount}</span>
                    </div>
                    <div class="info-item">
                        <span class="label">Started:</span>
                        <span class="value">${formatTime(network.started_at)}</span>
                    </div>
                    <div class="info-item">
                        <span class="label">Status:</span>
                        <span class="value">${network.status}</span>
                    </div>
                </div>

                <div class="agent-list" id="agents-${network.network_id}">
                    <h4>Agents</h4>
                    <div class="loading">Loading agents...</div>
                </div>
            </div>
            <div class="network-actions">
                <button class="btn btn-secondary" onclick="viewNetworkDetails('${network.network_id}')">
                    Details
                </button>
                <button class="btn btn-secondary" onclick="healthCheck('${network.network_id}')">
                    Health Check
                </button>
                ${network.status === 'running' ? `
                    <button class="btn btn-danger" onclick="stopNetwork('${network.network_id}')">
                        Stop Network
                    </button>
                ` : ''}
            </div>
        </div>
    `;
}

// View network details (loads agent info)
async function viewNetworkDetails(networkId) {
    try {
        const response = await fetch(`/api/wizard/networks/${networkId}/status`);
        const details = await response.json();

        const agentContainer = document.getElementById(`agents-${networkId}`);
        if (!agentContainer) return;

        if (!details.agents || Object.keys(details.agents).length === 0) {
            agentContainer.innerHTML = '<h4>Agents</h4><p class="muted">No agents</p>';
            return;
        }

        agentContainer.innerHTML = `
            <h4>Agents (${Object.keys(details.agents).length})</h4>
            ${Object.entries(details.agents).map(([agentId, agent]) => `
                <div class="agent-item">
                    <div class="agent-info">
                        <div class="agent-status-dot ${agent.status}"></div>
                        <div>
                            <div class="agent-name">${agentId}</div>
                            <div class="agent-ip">${agent.ip_address || 'No IP'} ${agent.webui_port ? `| Port: ${agent.webui_port}` : ''}</div>
                        </div>
                    </div>
                    <div class="agent-actions">
                        <button onclick="viewLogs('${networkId}', '${agentId}')" class="btn btn-secondary">
                            Logs
                        </button>
                        ${agent.webui_port ? `
                            <a href="http://localhost:${agent.webui_port}/dashboard" target="_blank" class="btn btn-primary" style="background: #4ade80;">
                                Open Dashboard
                            </a>
                        ` : `
                            <span style="color: #888; font-size: 0.8rem;">No WebUI port</span>
                        `}
                    </div>
                </div>
            `).join('')}
        `;

    } catch (error) {
        console.error('Failed to load network details:', error);
    }
}

// Health check
async function healthCheck(networkId) {
    try {
        const response = await fetch(`/api/wizard/networks/${networkId}/health`);
        const health = await response.json();

        const card = document.querySelector(`[data-network-id="${networkId}"]`);
        const body = card.querySelector('.network-body');

        // Find or create health display
        let healthDiv = body.querySelector('.health-display');
        if (!healthDiv) {
            healthDiv = document.createElement('div');
            healthDiv.className = 'health-display';
            body.appendChild(healthDiv);
        }

        healthDiv.innerHTML = `
            <h4 style="margin-top: 15px; color: #888; font-size: 0.8rem; text-transform: uppercase;">
                Health Status: ${health.healthy ? '✓ Healthy' : '✗ Issues Detected'}
            </h4>
            <div class="health-grid">
                ${Object.entries(health.agents || {}).map(([agentId, agent]) => `
                    <div class="health-item ${agent.healthy ? 'healthy' : 'unhealthy'}">
                        <span>${agentId}</span>
                        <span style="font-size: 0.7rem; color: #888;">${agent.status}</span>
                    </div>
                `).join('')}
            </div>
        `;

    } catch (error) {
        console.error('Failed to perform health check:', error);
        alert('Health check failed: ' + error.message);
    }
}

// Stop network
async function stopNetwork(networkId) {
    if (!confirm(`Are you sure you want to stop network "${networkId}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/wizard/networks/${networkId}/stop?save_state=true`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        alert('Network stopped successfully');
        refreshNetworks();

    } catch (error) {
        console.error('Failed to stop network:', error);
        alert('Failed to stop network: ' + error.message);
    }
}

// View agent logs
async function viewLogs(networkId, agentId) {
    const modal = document.getElementById('logs-modal');
    const output = document.getElementById('log-output');
    const agentName = document.getElementById('logs-agent-name');

    agentName.textContent = agentId;
    output.textContent = 'Loading logs...';
    modal.classList.add('active');

    try {
        const response = await fetch(`/api/wizard/networks/${networkId}/agents/${agentId}/logs?tail=200`);
        const data = await response.json();

        if (data.logs) {
            output.textContent = data.logs;
        } else {
            output.textContent = 'No logs available';
        }

    } catch (error) {
        output.textContent = 'Error loading logs: ' + error.message;
    }
}

function closeLogsModal() {
    document.getElementById('logs-modal').classList.remove('active');
}

// Render saved networks
function renderSavedNetworks() {
    const container = document.getElementById('saved-networks-container');

    if (savedNetworks.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No saved networks found.</p></div>';
        return;
    }

    container.innerHTML = `
        <div class="network-grid">
            ${savedNetworks.map(network => `
                <div class="network-card">
                    <div class="network-header">
                        <span class="network-name">${network.n || network.id}</span>
                        <span class="network-status stopped">Saved</span>
                    </div>
                    <div class="network-body">
                        <div class="network-info">
                            <div class="info-item">
                                <span class="label">ID:</span>
                                <span class="value">${network.id}</span>
                            </div>
                            <div class="info-item">
                                <span class="label">Agents:</span>
                                <span class="value">${network.agents?.length || 0}</span>
                            </div>
                        </div>
                    </div>
                    <div class="network-actions">
                        <button class="btn btn-primary" onclick="launchSavedNetwork('${network.id}')">
                            Launch
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Launch saved network
async function launchSavedNetwork(networkId) {
    const apiKey = prompt('Enter your LLM API key (or leave blank to skip):');

    try {
        // This would need a dedicated endpoint to launch from saved
        alert('Launch from saved network not yet implemented. Use the Network Builder wizard.');
    } catch (error) {
        console.error('Failed to launch network:', error);
    }
}

// Update summary cards
function updateSummary() {
    let runningCount = 0;
    let totalAgents = 0;
    let healthyAgents = 0;
    let errorCount = 0;

    deployedNetworks.forEach(network => {
        if (network.status === 'running') {
            runningCount++;
        }
        if (network.status === 'error') {
            errorCount++;
        }
        totalAgents += network.agent_count || 0;
    });

    document.getElementById('running-count').textContent = runningCount;
    document.getElementById('agent-count').textContent = totalAgents;
    document.getElementById('healthy-count').textContent = totalAgents; // Approximate
    document.getElementById('error-count').textContent = errorCount;
}

// Format time
function formatTime(isoString) {
    if (!isoString) return 'N/A';
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch {
        return isoString;
    }
}

// Close modal on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeLogsModal();
    }
});

// Close modal on outside click
document.getElementById('logs-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        closeLogsModal();
    }
});
