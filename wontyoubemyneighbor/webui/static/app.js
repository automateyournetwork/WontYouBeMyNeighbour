/**
 * ASI Dashboard - JavaScript Application
 * Handles WebSocket connection, chat, and status updates
 */

class ASIDashboard {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;

        // DOM elements
        this.elements = {
            agentName: document.getElementById('agent-name'),
            containerName: document.getElementById('container-name'),
            routerId: document.getElementById('router-id'),
            connectionStatus: document.getElementById('connection-status'),
            providerBadge: document.getElementById('provider-badge'),
            chatMessages: document.getElementById('chat-messages'),
            chatInput: document.getElementById('chat-input'),
            sendBtn: document.getElementById('send-btn'),
            protocolCards: document.getElementById('protocol-cards'),
            interfacesBody: document.getElementById('interfaces-body'),
            neighborsBody: document.getElementById('neighbors-body'),
            mcpBody: document.getElementById('mcp-body'),
            mcpSection: document.getElementById('mcp-section'),
            routesContainer: document.getElementById('routes-container'),
            logsContainer: document.getElementById('logs-container')
        };

        // Logs pause state
        this.logsPaused = false;

        // Track configured protocols
        this.configuredProtocols = new Set();
        this.protocolCardsRendered = false;

        // Track intervals for cleanup
        this._routeUpdateInterval = null;

        this.init();
    }

    init() {
        // Setup event listeners
        this.elements.sendBtn.addEventListener('click', () => this.sendChat());
        this.elements.chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendChat();
        });

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Connect WebSocket
        this.connect();

        // Periodic route updates (with cleanup tracking)
        this._routeUpdateInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'get_routes' }));
            }
        }, 10000);

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => this.cleanup());
    }

    cleanup() {
        // Clear intervals to prevent memory leaks
        if (this._routeUpdateInterval) {
            clearInterval(this._routeUpdateInterval);
            this._routeUpdateInterval = null;
        }
        // Close WebSocket cleanly
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => this.onConnect();
            this.ws.onmessage = (e) => this.onMessage(e);
            this.ws.onclose = () => this.onDisconnect();
            this.ws.onerror = (e) => this.onError(e);
        } catch (err) {
            console.error('WebSocket connection failed:', err);
            this.scheduleReconnect();
        }
    }

    onConnect() {
        this.reconnectAttempts = 0;
        this.updateConnectionStatus('connected', 'Connected');
        console.log('WebSocket connected');

        // Request initial routes
        setTimeout(() => {
            this.ws.send(JSON.stringify({ type: 'get_routes' }));
        }, 500);
    }

    onDisconnect() {
        this.updateConnectionStatus('disconnected', 'Disconnected');
        console.log('WebSocket disconnected');
        this.scheduleReconnect();
    }

    onError(error) {
        console.error('WebSocket error:', error);
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
            this.updateConnectionStatus('', `Reconnecting (${this.reconnectAttempts})...`);
            setTimeout(() => this.connect(), delay);
        } else {
            this.updateConnectionStatus('disconnected', 'Connection Failed');
        }
    }

    onMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'status':
                    this.updateStatus(data.data);
                    break;
                case 'routes':
                    this.updateRoutes(data.data);
                    break;
                case 'log':
                    this.addLog(data.data);
                    break;
                case 'chat_response':
                    this.addChatMessage(data.data.response, 'asi');
                    this.elements.sendBtn.disabled = false;
                    this.elements.chatInput.disabled = false;
                    this.elements.chatInput.focus();
                    break;
            }
        } catch (err) {
            console.error('Error parsing message:', err);
        }
    }

    updateConnectionStatus(cls, text) {
        this.elements.connectionStatus.className = 'connection-status ' + cls;
        this.elements.connectionStatus.textContent = text;
    }

    updateStatus(status) {
        // Agent Name
        if (status.agent_name) {
            this.elements.agentName.textContent = status.agent_name;
            document.title = `${status.agent_name} - ASI Dashboard`;
        }

        // Container Name (shown separately for clarity)
        if (status.container_name && this.elements.containerName) {
            this.elements.containerName.textContent = `[${status.container_name}]`;

            // Update Agent Dashboard link with agent_id
            const agentDashboardLink = document.getElementById('nav-agent-dashboard');
            if (agentDashboardLink) {
                agentDashboardLink.href = `/agent-dashboard?agent_id=${encodeURIComponent(status.container_name)}`;
            }
        }

        // Router ID
        this.elements.routerId.textContent = status.router_id || '--';

        // Agentic provider
        if (status.agentic) {
            this.elements.providerBadge.textContent = status.agentic.provider || 'Unknown';
        }

        // Dynamically build protocol cards based on what's configured
        this.renderProtocolCards(status);

        // Update interfaces
        this.renderInterfaces(status.interfaces);

        // Update neighbors/peers
        this.renderNeighbors(status);

        // Update MCPs
        this.renderMCPs(status.mcps);
    }

    renderInterfaces(interfaces) {
        if (!interfaces || interfaces.length === 0) {
            this.elements.interfacesBody.innerHTML = '<p class="muted">No interfaces configured</p>';
            return;
        }

        let html = '<table class="routes-table" style="width: 100%;">';
        html += '<thead><tr><th>Name</th><th>Type</th><th>IP Address(es)</th><th>Status</th></tr></thead>';
        html += '<tbody>';

        for (const iface of interfaces) {
            const name = iface.name || iface.n || iface.id;
            const type = iface.type || iface.t || 'eth';
            const addresses = iface.addresses || iface.a || [];
            const status = iface.status || iface.s || 'up';

            const typeNames = {
                'eth': 'Ethernet',
                'lo': 'Loopback',
                'vlan': 'VLAN',
                'tun': 'Tunnel',
                'sub': 'Sub-Interface'
            };
            const typeDisplay = typeNames[type] || type;

            const statusClass = status === 'up' ? 'full' : 'other';
            const addrDisplay = addresses.length > 0 ? addresses.join(', ') : '-';

            html += `
                <tr>
                    <td><strong>${name}</strong></td>
                    <td>${typeDisplay}</td>
                    <td style="font-family: monospace;">${addrDisplay}</td>
                    <td><span class="state-badge ${statusClass}">${status}</span></td>
                </tr>
            `;
        }

        html += '</tbody></table>';
        this.elements.interfacesBody.innerHTML = html;
    }

    renderProtocolCards(status) {
        const container = this.elements.protocolCards;
        let cardsHtml = '';

        // OSPF Card
        if (status.ospf) {
            this.configuredProtocols.add('ospf');
            cardsHtml += `
                <div class="status-card" id="ospf-card">
                    <div class="card-header">
                        <h3>OSPFv2</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Area</span><span class="stat-value">${status.ospf.area}</span></div>
                        <div class="stat"><span class="stat-label">Interface</span><span class="stat-value">${status.ospf.interface}</span></div>
                        <div class="stat"><span class="stat-label">IP</span><span class="stat-value">${status.ospf.ip}</span></div>
                        <div class="stat"><span class="stat-label">Neighbors</span><span class="stat-value">${status.ospf.neighbors} (${status.ospf.full_neighbors} full)</span></div>
                        <div class="stat"><span class="stat-label">LSDB Size</span><span class="stat-value">${status.ospf.lsdb_size}</span></div>
                        <div class="stat"><span class="stat-label">Routes</span><span class="stat-value">${status.ospf.routes}</span></div>
                    </div>
                </div>
            `;
        }

        // OSPFv3 Card
        if (status.ospfv3) {
            this.configuredProtocols.add('ospfv3');
            cardsHtml += `
                <div class="status-card" id="ospfv3-card">
                    <div class="card-header">
                        <h3>OSPFv3 (IPv6)</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Router ID</span><span class="stat-value">${status.ospfv3.router_id}</span></div>
                        <div class="stat"><span class="stat-label">Areas</span><span class="stat-value">${status.ospfv3.areas?.join(', ') || '-'}</span></div>
                        <div class="stat"><span class="stat-label">Interfaces</span><span class="stat-value">${status.ospfv3.interfaces}</span></div>
                    </div>
                </div>
            `;
        }

        // BGP Card
        if (status.bgp && !status.bgp.error) {
            this.configuredProtocols.add('bgp');
            cardsHtml += `
                <div class="status-card" id="bgp-card">
                    <div class="card-header">
                        <h3>BGP</h3>
                        <span class="status-indicator ${status.bgp.established_peers > 0 ? 'active' : 'warning'}"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Local AS</span><span class="stat-value">${status.bgp.local_as}</span></div>
                        <div class="stat"><span class="stat-label">Router ID</span><span class="stat-value">${status.bgp.router_id}</span></div>
                        <div class="stat"><span class="stat-label">Peers</span><span class="stat-value">${status.bgp.total_peers} (${status.bgp.established_peers} established)</span></div>
                        <div class="stat"><span class="stat-label">Routes</span><span class="stat-value">${status.bgp.loc_rib_routes}</span></div>
                    </div>
                </div>
            `;
        }

        // IS-IS Card
        if (status.isis) {
            this.configuredProtocols.add('isis');
            cardsHtml += `
                <div class="status-card" id="isis-card">
                    <div class="card-header">
                        <h3>IS-IS</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">System ID</span><span class="stat-value">${status.isis.system_id}</span></div>
                        <div class="stat"><span class="stat-label">Area</span><span class="stat-value">${status.isis.area}</span></div>
                        <div class="stat"><span class="stat-label">Level</span><span class="stat-value">${status.isis.level}</span></div>
                        <div class="stat"><span class="stat-label">Adjacencies</span><span class="stat-value">${status.isis.adjacencies || 0}</span></div>
                    </div>
                </div>
            `;
        }

        // MPLS Card
        if (status.mpls) {
            this.configuredProtocols.add('mpls');
            cardsHtml += `
                <div class="status-card" id="mpls-card">
                    <div class="card-header">
                        <h3>MPLS/LDP</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Router ID</span><span class="stat-value">${status.mpls.router_id}</span></div>
                        <div class="stat"><span class="stat-label">LDP Sessions</span><span class="stat-value">${status.mpls.ldp_sessions || 0}</span></div>
                        <div class="stat"><span class="stat-label">Labels Allocated</span><span class="stat-value">${status.mpls.labels_allocated || 0}</span></div>
                    </div>
                </div>
            `;
        }

        // DHCP Card
        if (status.dhcp) {
            this.configuredProtocols.add('dhcp');
            cardsHtml += `
                <div class="status-card" id="dhcp-card">
                    <div class="card-header">
                        <h3>DHCP Server</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Pool</span><span class="stat-value">${status.dhcp.pool_name || 'default'}</span></div>
                        <div class="stat"><span class="stat-label">Active Leases</span><span class="stat-value">${status.dhcp.active_leases || 0}</span></div>
                        <div class="stat"><span class="stat-label">Available</span><span class="stat-value">${status.dhcp.available || 0}</span></div>
                    </div>
                </div>
            `;
        }

        // DNS Card
        if (status.dns) {
            this.configuredProtocols.add('dns');
            cardsHtml += `
                <div class="status-card" id="dns-card">
                    <div class="card-header">
                        <h3>DNS Server</h3>
                        <span class="status-indicator active"></span>
                    </div>
                    <div class="card-body">
                        <div class="stat"><span class="stat-label">Zone</span><span class="stat-value">${status.dns.zone || '-'}</span></div>
                        <div class="stat"><span class="stat-label">Records</span><span class="stat-value">${status.dns.record_count || 0}</span></div>
                        <div class="stat"><span class="stat-label">Queries</span><span class="stat-value">${status.dns.queries || 0}</span></div>
                    </div>
                </div>
            `;
        }

        // If no protocols configured, show message
        if (cardsHtml === '') {
            cardsHtml = `
                <div class="status-card">
                    <div class="card-body">
                        <p class="muted">No protocols configured for this agent</p>
                    </div>
                </div>
            `;
        }

        container.innerHTML = cardsHtml;
    }

    renderNeighbors(status) {
        const neighbors = [];

        // Collect OSPF neighbors
        if (status.ospf && status.ospf.neighbor_details) {
            for (const n of status.ospf.neighbor_details) {
                neighbors.push({
                    protocol: 'OSPF',
                    id: n.router_id,
                    ip: n.ip,
                    state: n.state,
                    isUp: n.is_full
                });
            }
        }

        // Collect BGP peers
        if (status.bgp && status.bgp.peer_details) {
            for (const p of status.bgp.peer_details) {
                neighbors.push({
                    protocol: p.peer_type || 'BGP',
                    id: `AS ${p.remote_as}`,
                    ip: p.ip,
                    state: p.state,
                    isUp: p.state === 'Established'
                });
            }
        }

        // Collect IS-IS adjacencies
        if (status.isis && status.isis.adjacencies_details) {
            for (const a of status.isis.adjacencies_details) {
                neighbors.push({
                    protocol: 'IS-IS',
                    id: a.system_id,
                    ip: a.ip,
                    state: a.state,
                    isUp: a.state === 'Up'
                });
            }
        }

        // Render neighbors
        if (neighbors.length === 0) {
            this.elements.neighborsBody.innerHTML = '<p class="muted">No neighbors or peers</p>';
            return;
        }

        let html = '<div class="neighbor-list">';
        for (const n of neighbors) {
            const stateClass = n.isUp ? 'full' : 'other';
            html += `
                <div class="neighbor-item">
                    <span class="state-badge ${stateClass}">${n.state}</span>
                    <div class="neighbor-info">
                        <div class="neighbor-id">${n.id}</div>
                        <div class="neighbor-ip">${n.ip} (${n.protocol})</div>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        this.elements.neighborsBody.innerHTML = html;
    }

    renderMCPs(mcps) {
        if (!mcps || mcps.length === 0) {
            this.elements.mcpSection.style.display = 'none';
            return;
        }

        this.elements.mcpSection.style.display = 'block';

        let html = '<div class="mcp-list" style="display: flex; flex-wrap: wrap; gap: 10px;">';
        for (const mcp of mcps) {
            const statusClass = mcp.enabled ? 'active' : 'inactive';
            html += `
                <div class="mcp-item" style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 6px; padding: 10px 15px; min-width: 150px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 5px;">
                        <span class="status-indicator ${statusClass}" style="width: 8px; height: 8px;"></span>
                        <strong style="color: var(--accent-cyan);">${mcp.name}</strong>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">${mcp.description || mcp.type}</div>
                </div>
            `;
        }
        html += '</div>';
        this.elements.mcpBody.innerHTML = html;
    }

    updateRoutes(routes) {
        const container = this.elements.routesContainer;
        let html = '';

        // OSPF routes (only if OSPF is configured)
        if (this.configuredProtocols.has('ospf') && routes.ospf) {
            html += `
                <div class="routes-section">
                    <h4>OSPF Routes</h4>
                    <table class="routes-table">
                        <thead>
                            <tr><th>Prefix</th><th>Next Hop</th><th>Interface</th><th>Cost</th></tr>
                        </thead>
                        <tbody>
            `;
            if (routes.ospf.length > 0) {
                for (const r of routes.ospf) {
                    html += `<tr><td>${r.prefix}</td><td>${r.next_hop || 'Direct'}</td><td>${r.interface || '-'}</td><td>${r.cost}</td></tr>`;
                }
            } else {
                html += '<tr><td colspan="4" class="muted">No OSPF routes</td></tr>';
            }
            html += '</tbody></table></div>';
        }

        // BGP routes (only if BGP is configured)
        if (this.configuredProtocols.has('bgp') && routes.bgp) {
            html += `
                <div class="routes-section">
                    <h4>BGP Routes</h4>
                    <table class="routes-table">
                        <thead>
                            <tr><th>Prefix</th><th>Next Hop</th><th>Interface</th><th>AS Path</th></tr>
                        </thead>
                        <tbody>
            `;
            if (routes.bgp.length > 0) {
                for (const r of routes.bgp) {
                    html += `<tr><td>${r.prefix}</td><td>${r.next_hop}</td><td>${r.interface || '-'}</td><td>${r.as_path || '-'}</td></tr>`;
                }
            } else {
                html += '<tr><td colspan="4" class="muted">No BGP routes</td></tr>';
            }
            html += '</tbody></table></div>';
        }

        // IS-IS routes (only if IS-IS is configured)
        if (this.configuredProtocols.has('isis') && routes.isis) {
            html += `
                <div class="routes-section">
                    <h4>IS-IS Routes</h4>
                    <table class="routes-table">
                        <thead>
                            <tr><th>Prefix</th><th>Next Hop</th><th>Metric</th></tr>
                        </thead>
                        <tbody>
            `;
            if (routes.isis.length > 0) {
                for (const r of routes.isis) {
                    html += `<tr><td>${r.prefix}</td><td>${r.next_hop || 'Direct'}</td><td>${r.metric}</td></tr>`;
                }
            } else {
                html += '<tr><td colspan="3" class="muted">No IS-IS routes</td></tr>';
            }
            html += '</tbody></table></div>';
        }

        // MPLS labels (only if MPLS is configured)
        if (this.configuredProtocols.has('mpls') && routes.mpls) {
            html += `
                <div class="routes-section">
                    <h4>MPLS Label Bindings</h4>
                    <table class="routes-table">
                        <thead>
                            <tr><th>FEC/Prefix</th><th>Local Label</th><th>Next Hop</th></tr>
                        </thead>
                        <tbody>
            `;
            if (routes.mpls.length > 0) {
                for (const r of routes.mpls) {
                    html += `<tr><td>${r.fec || r.prefix}</td><td>${r.local_label}</td><td>${r.next_hop || '-'}</td></tr>`;
                }
            } else {
                html += '<tr><td colspan="3" class="muted">No MPLS labels</td></tr>';
            }
            html += '</tbody></table></div>';
        }

        if (html === '') {
            html = '<p class="muted">No routes available</p>';
        }

        container.innerHTML = html;
    }

    addLog(logEntry) {
        // Skip if logs are paused
        if (this.logsPaused) {
            return;
        }

        const level = logEntry.level.toLowerCase();
        const time = new Date(logEntry.timestamp).toLocaleTimeString();

        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;
        entry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-level">${logEntry.level}</span>
            <span class="log-message">${this.escapeHtml(logEntry.message)}</span>
        `;

        this.elements.logsContainer.appendChild(entry);

        // Limit log entries
        while (this.elements.logsContainer.children.length > 500) {
            this.elements.logsContainer.removeChild(this.elements.logsContainer.firstChild);
        }

        // Auto-scroll if near bottom
        const container = this.elements.logsContainer;
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        if (isNearBottom) {
            container.scrollTop = container.scrollHeight;
        }
    }

    toggleLogsPause() {
        this.logsPaused = !this.logsPaused;
        const btn = document.getElementById('logs-pause-btn');
        const status = document.getElementById('logs-status');

        if (this.logsPaused) {
            btn.textContent = '▶ Resume';
            btn.style.background = 'var(--accent-green)';
            status.textContent = 'Paused';
            status.style.color = 'var(--accent-yellow)';
        } else {
            btn.textContent = '⏸ Pause';
            btn.style.background = 'var(--accent-yellow)';
            status.textContent = 'Live';
            status.style.color = 'var(--text-muted)';
        }
    }

    clearLogs() {
        this.elements.logsContainer.innerHTML = `
            <div class="log-entry info">
                <span class="log-time">${new Date().toLocaleTimeString()}</span>
                <span class="log-level">INFO</span>
                <span class="log-message">Logs cleared</span>
            </div>
        `;
    }

    sendChat() {
        const message = this.elements.chatInput.value.trim();
        if (!message) return;

        // Add user message to chat
        this.addChatMessage(message, 'user');

        // Disable input while waiting
        this.elements.sendBtn.disabled = true;
        this.elements.chatInput.disabled = true;
        this.elements.chatInput.value = '';

        // Send via WebSocket
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'chat',
                message: message
            }));
        } else {
            this.addChatMessage('Not connected to server. Please wait...', 'asi');
            this.elements.sendBtn.disabled = false;
            this.elements.chatInput.disabled = false;
        }
    }

    addChatMessage(text, sender) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}-message`;

        // Check if message contains code blocks
        if (text.includes('```')) {
            msgDiv.innerHTML = this.formatCodeBlocks(text);
        } else {
            msgDiv.innerHTML = `<p>${this.escapeHtml(text).replace(/\n/g, '<br>')}</p>`;
        }

        this.elements.chatMessages.appendChild(msgDiv);
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }

    formatCodeBlocks(text) {
        // Simple markdown code block formatting
        const parts = text.split('```');
        let html = '';
        for (let i = 0; i < parts.length; i++) {
            if (i % 2 === 0) {
                // Regular text
                html += `<p>${this.escapeHtml(parts[i]).replace(/\n/g, '<br>')}</p>`;
            } else {
                // Code block
                html += `<pre>${this.escapeHtml(parts[i])}</pre>`;
            }
        }
        return html;
    }

    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `tab-${tabName}`);
        });

        // Request data for specific tabs
        if (tabName === 'routes' && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'get_routes' }));
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new ASIDashboard();
});

// Toggle to Logs tab
function toggleLogs() {
    if (window.dashboard) {
        window.dashboard.switchTab('logs');
    }
}

// Toggle logs pause
function toggleLogsPause() {
    if (window.dashboard) {
        window.dashboard.toggleLogsPause();
    }
}

// Clear logs
function clearLogs() {
    if (window.dashboard) {
        window.dashboard.clearLogs();
    }
}
