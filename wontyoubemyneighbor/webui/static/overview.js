/**
 * Network Overview Dashboard
 *
 * Provides a comprehensive view of all deployed networks and their status
 */

class OverviewDashboard {
    constructor() {
        this.networks = [];
        this.agents = [];
        this.topology = { nodes: [], links: [] };
        this.events = [];
        this.refreshInterval = null;
        this.selectedNetwork = null;

        this.init();
    }

    init() {
        this.loadData();

        // Auto-refresh every 10 seconds
        this.refreshInterval = setInterval(() => this.loadData(), 10000);

        // Setup event listeners
        this.setupEventListeners();
    }

    async loadData() {
        try {
            // Load networks
            const networksResp = await fetch('/api/wizard/networks');
            if (networksResp.ok) {
                this.networks = await networksResp.json();
            }

            // Load detailed status for each network
            for (const network of this.networks) {
                try {
                    const statusResp = await fetch(`/api/wizard/networks/${network.network_id}/status`);
                    if (statusResp.ok) {
                        const status = await statusResp.json();
                        network.agents = status.agents || {};
                        network.detailed = true;
                    }
                } catch (e) {
                    console.error(`Failed to load status for ${network.network_id}:`, e);
                }
            }

            this.updateUI();
        } catch (error) {
            console.error('Failed to load data:', error);
        }
    }

    updateUI() {
        this.updateGlobalStats();
        this.updateNetworkList();
        this.updateAgentSummary();
        this.updateProtocolDistribution();
        this.updateTopology();
        this.updateHealth();
    }

    updateGlobalStats() {
        let totalAgents = 0;
        let totalOspf = 0;
        let totalBgp = 0;
        let totalRoutes = 0;
        let runningNetworks = 0;

        for (const network of this.networks) {
            if (network.status === 'running') {
                runningNetworks++;
            }
            totalAgents += network.agent_count || Object.keys(network.agents || {}).length;

            // Count protocol instances
            for (const agent of Object.values(network.agents || {})) {
                if (agent.ospf) {
                    totalOspf += agent.ospf.neighbors || 0;
                    totalRoutes += agent.ospf.routes || 0;
                }
                if (agent.bgp) {
                    totalBgp += agent.bgp.established || 0;
                    totalRoutes += agent.bgp.routes || 0;
                }
            }
        }

        document.getElementById('total-networks').textContent = runningNetworks;
        document.getElementById('total-agents').textContent = totalAgents;
        document.getElementById('total-ospf').textContent = totalOspf;
        document.getElementById('total-bgp').textContent = totalBgp;
        document.getElementById('total-routes').textContent = totalRoutes;

        // Health score (simplified)
        const healthScore = runningNetworks > 0 ? Math.round((totalAgents / (runningNetworks * 5)) * 100) : 100;
        document.getElementById('health-score').textContent = Math.min(healthScore, 100) + '%';
    }

    updateNetworkList() {
        const container = document.getElementById('network-list');
        if (!container) return;

        if (this.networks.length === 0) {
            container.innerHTML = '<div class="empty-state">No networks deployed. <a href="/">Create one</a></div>';
            return;
        }

        let html = '';
        for (const network of this.networks) {
            const agentCount = network.agent_count || Object.keys(network.agents || {}).length;
            const selected = this.selectedNetwork === network.network_id ? 'selected' : '';

            html += `
                <div class="network-item ${selected}" data-network="${network.network_id}">
                    <div class="network-item-header">
                        <span class="network-item-name">${network.name || network.network_id}</span>
                        <span class="network-item-status ${network.status}">${network.status}</span>
                    </div>
                    <div class="network-item-stats">
                        <div class="network-item-stat">
                            <span>${agentCount}</span> agents
                        </div>
                        <div class="network-item-stat">
                            <span>${network.docker_network || '-'}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;

        // Add click handlers
        container.querySelectorAll('.network-item').forEach(item => {
            item.addEventListener('click', () => {
                this.selectNetwork(item.dataset.network);
            });
        });
    }

    selectNetwork(networkId) {
        this.selectedNetwork = networkId;

        // Update selection state
        document.querySelectorAll('.network-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.network === networkId);
        });

        // Update topology to highlight selected network
        this.updateTopology();
    }

    updateAgentSummary() {
        const container = document.getElementById('agent-summary');
        if (!container) return;

        // Collect all agents from all networks
        const allAgents = [];
        for (const network of this.networks) {
            for (const [agentId, agent] of Object.entries(network.agents || {})) {
                allAgents.push({
                    id: agentId,
                    networkId: network.network_id,
                    ...agent
                });
            }
        }

        if (allAgents.length === 0) {
            container.innerHTML = '<div class="empty-state">No agents deployed</div>';
            return;
        }

        let html = '';
        for (const agent of allAgents) {
            const status = agent.status || 'unknown';
            html += `
                <div class="agent-summary-item" data-agent="${agent.id}" data-network="${agent.networkId}">
                    <div class="agent-dot ${status}"></div>
                    <div class="agent-summary-info">
                        <div class="agent-summary-name">${agent.id}</div>
                        <div class="agent-summary-ip">${agent.ip_address || '-'}</div>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;

        // Add click handlers
        container.querySelectorAll('.agent-summary-item').forEach(item => {
            item.addEventListener('click', () => {
                const agentId = item.dataset.agent;
                const networkId = item.dataset.network;
                // Navigate to agent dashboard
                window.location.href = `/agent?agent=${agentId}&network=${networkId}`;
            });
        });
    }

    updateProtocolDistribution() {
        let ospfCount = 0;
        let bgpCount = 0;
        let isisCount = 0;
        let mplsCount = 0;
        let vxlanCount = 0;

        for (const network of this.networks) {
            for (const agent of Object.values(network.agents || {})) {
                if (agent.ospf) ospfCount++;
                if (agent.bgp) bgpCount++;
                if (agent.isis) isisCount++;
                if (agent.mpls) mplsCount++;
                if (agent.vxlan) vxlanCount++;
            }
        }

        document.getElementById('proto-ospf').textContent = ospfCount;
        document.getElementById('proto-bgp').textContent = bgpCount;
        document.getElementById('proto-isis').textContent = isisCount;
        document.getElementById('proto-mpls').textContent = mplsCount;
        document.getElementById('proto-vxlan').textContent = vxlanCount;
    }

    updateTopology() {
        const svg = document.getElementById('topology-svg');
        if (!svg) return;

        // Build topology from networks
        const nodes = [];
        const links = [];
        const nodeMap = new Map();

        for (const network of this.networks) {
            for (const [agentId, agent] of Object.entries(network.agents || {})) {
                const nodeId = `${network.network_id}-${agentId}`;
                nodes.push({
                    id: nodeId,
                    name: agentId,
                    network: network.network_id,
                    status: agent.status || 'unknown',
                    ip: agent.ip_address
                });
                nodeMap.set(agentId, nodeId);
            }

            // Create links between agents in same network (simplified mesh)
            const agentIds = Object.keys(network.agents || {});
            for (let i = 0; i < agentIds.length; i++) {
                for (let j = i + 1; j < agentIds.length; j++) {
                    links.push({
                        source: `${network.network_id}-${agentIds[i]}`,
                        target: `${network.network_id}-${agentIds[j]}`,
                        protocol: 'ospf' // Default
                    });
                }
            }
        }

        this.renderTopology(svg, nodes, links);
    }

    renderTopology(svg, nodes, links) {
        const width = svg.clientWidth || 800;
        const height = 400;
        const centerX = width / 2;
        const centerY = height / 2;

        // Clear SVG
        svg.innerHTML = '';

        if (nodes.length === 0) {
            // Show empty state
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', centerX);
            text.setAttribute('y', centerY);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#888');
            text.textContent = 'No topology data';
            svg.appendChild(text);
            return;
        }

        // Calculate positions (circular layout)
        const radius = Math.min(width, height) * 0.35;
        nodes.forEach((node, i) => {
            const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
            node.x = centerX + radius * Math.cos(angle);
            node.y = centerY + radius * Math.sin(angle);
        });

        // Draw links
        for (const link of links) {
            const source = nodes.find(n => n.id === link.source);
            const target = nodes.find(n => n.id === link.target);

            if (source && target) {
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', source.x);
                line.setAttribute('y1', source.y);
                line.setAttribute('x2', target.x);
                line.setAttribute('y2', target.y);

                // Color based on protocol
                const colors = {
                    ospf: '#00d9ff',
                    bgp: '#a78bfa',
                    isis: '#facc15'
                };
                line.setAttribute('stroke', colors[link.protocol] || '#2a2a4e');
                line.setAttribute('stroke-width', '2');

                svg.appendChild(line);
            }
        }

        // Draw nodes
        for (const node of nodes) {
            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            g.setAttribute('transform', `translate(${node.x}, ${node.y})`);
            g.style.cursor = 'pointer';

            // Background circle
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('r', '20');
            circle.setAttribute('fill', '#16213e');

            const statusColors = {
                running: '#4ade80',
                stopped: '#888',
                error: '#ef4444'
            };
            circle.setAttribute('stroke', statusColors[node.status] || '#2a2a4e');
            circle.setAttribute('stroke-width', '3');

            // Highlight selected network
            if (this.selectedNetwork && node.network === this.selectedNetwork) {
                circle.setAttribute('stroke-width', '4');
                circle.setAttribute('filter', 'url(#glow)');
            }

            g.appendChild(circle);

            // Node label
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('y', '4');
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#eee');
            text.setAttribute('font-size', '9');
            text.textContent = this.truncate(node.name, 6);
            g.appendChild(text);

            // Click handler
            g.addEventListener('click', () => {
                window.location.href = `/agent?agent=${node.name}&network=${node.network}`;
            });

            svg.appendChild(g);
        }

        // Add glow filter for selected nodes
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        defs.innerHTML = `
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                </feMerge>
            </filter>
        `;
        svg.insertBefore(defs, svg.firstChild);
    }

    truncate(str, len) {
        if (!str) return '';
        return str.length > len ? str.substring(0, len) + '..' : str;
    }

    updateHealth() {
        let totalAdj = 0;
        let fullAdj = 0;

        for (const network of this.networks) {
            for (const agent of Object.values(network.agents || {})) {
                if (agent.ospf) {
                    totalAdj += agent.ospf.neighbors || 0;
                    fullAdj += agent.ospf.full_neighbors || 0;
                }
            }
        }

        const adjEl = document.getElementById('health-adjacencies');
        if (adjEl) {
            adjEl.textContent = `${fullAdj}/${totalAdj}`;
            adjEl.className = 'health-value ' + (fullAdj === totalAdj ? 'good' : 'warning');
        }

        const convEl = document.getElementById('health-convergence');
        if (convEl) {
            const converged = fullAdj === totalAdj || totalAdj === 0;
            convEl.textContent = converged ? 'OK' : 'Converging...';
            convEl.className = 'health-value ' + (converged ? 'good' : 'warning');
        }

        // Uptime (from oldest network)
        const uptimeEl = document.getElementById('health-uptime');
        if (uptimeEl && this.networks.length > 0) {
            const oldest = this.networks
                .filter(n => n.started_at)
                .sort((a, b) => new Date(a.started_at) - new Date(b.started_at))[0];

            if (oldest && oldest.started_at) {
                const uptime = this.formatUptime(new Date(oldest.started_at));
                uptimeEl.textContent = uptime;
            }
        }
    }

    formatUptime(startDate) {
        const diff = Date.now() - startDate.getTime();
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days}d ${hours % 24}h`;
        if (hours > 0) return `${hours}h ${minutes % 60}m`;
        if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
        return `${seconds}s`;
    }

    addEvent(severity, message) {
        const time = new Date().toLocaleTimeString().slice(0, 5);

        this.events.unshift({
            time,
            severity,
            message
        });

        // Keep last 20 events
        if (this.events.length > 20) {
            this.events.pop();
        }

        this.updateEventsList();
    }

    updateEventsList() {
        const container = document.getElementById('events-list');
        if (!container) return;

        if (this.events.length === 0) {
            container.innerHTML = `
                <div class="event-item">
                    <span class="event-time">--:--</span>
                    <span class="event-dot info"></span>
                    <span class="event-message">No events yet</span>
                </div>
            `;
            return;
        }

        let html = '';
        for (const event of this.events) {
            html += `
                <div class="event-item">
                    <span class="event-time">${event.time}</span>
                    <span class="event-dot ${event.severity}"></span>
                    <span class="event-message">${event.message}</span>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    setupEventListeners() {
        // Handle visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.loadData();
            }
        });
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Global instance
let overviewDashboard = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    overviewDashboard = new OverviewDashboard();
});

// Cleanup
window.addEventListener('beforeunload', () => {
    if (overviewDashboard) {
        overviewDashboard.destroy();
    }
});

// Global functions
function refreshTopology() {
    if (overviewDashboard) {
        overviewDashboard.loadData();
    }
}
