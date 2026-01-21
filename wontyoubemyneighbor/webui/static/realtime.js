/**
 * Real-Time Network Monitoring
 *
 * Provides WebSocket-based live updates for network monitoring dashboard
 */

class RealtimeMonitor {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
        this.metrics = {};
        this.charts = {};
        this.networkTopology = null;
        this.updateInterval = null;

        // Metric history for charts (keep last 60 data points)
        this.metricHistory = {
            packets: [],
            neighbors: [],
            routes: [],
            timestamps: []
        };
        this.maxHistoryPoints = 60;
    }

    init() {
        this.connectWebSocket();
        this.initializeCharts();
        this.startPeriodicUpdates();

        // Event listeners
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.refreshAll();
            }
        });
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/monitor`;

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
        this.updateConnectionIndicator('connected');
        console.log('Real-time monitor connected');

        // Request initial data
        this.send({ type: 'subscribe', topics: ['metrics', 'topology', 'events'] });
    }

    onDisconnect() {
        this.updateConnectionIndicator('disconnected');
        console.log('Real-time monitor disconnected');
        this.scheduleReconnect();
    }

    onError(error) {
        console.error('WebSocket error:', error);
        this.updateConnectionIndicator('error');
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
            this.updateConnectionIndicator('reconnecting');
            setTimeout(() => this.connectWebSocket(), delay);
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    onMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'metrics':
                    this.updateMetrics(data.data);
                    break;
                case 'topology':
                    this.updateTopology(data.data);
                    break;
                case 'event':
                    this.handleEvent(data.data);
                    break;
                case 'agent_status':
                    this.updateAgentStatus(data.data);
                    break;
                case 'protocol_update':
                    this.updateProtocolStatus(data.data);
                    break;
            }
        } catch (err) {
            console.error('Error parsing message:', err);
        }
    }

    updateConnectionIndicator(status) {
        const indicator = document.getElementById('realtime-status');
        if (!indicator) return;

        const statusClasses = {
            connected: 'status-connected',
            disconnected: 'status-disconnected',
            reconnecting: 'status-reconnecting',
            error: 'status-error'
        };

        const statusText = {
            connected: 'Live',
            disconnected: 'Offline',
            reconnecting: 'Reconnecting...',
            error: 'Error'
        };

        indicator.className = 'realtime-indicator ' + (statusClasses[status] || '');
        indicator.textContent = statusText[status] || status;
    }

    updateMetrics(metrics) {
        this.metrics = metrics;

        // Store in history
        const now = new Date();
        this.metricHistory.timestamps.push(now);
        this.metricHistory.packets.push(metrics.totalPackets || 0);
        this.metricHistory.neighbors.push(metrics.totalNeighbors || 0);
        this.metricHistory.routes.push(metrics.totalRoutes || 0);

        // Trim history
        while (this.metricHistory.timestamps.length > this.maxHistoryPoints) {
            this.metricHistory.timestamps.shift();
            this.metricHistory.packets.shift();
            this.metricHistory.neighbors.shift();
            this.metricHistory.routes.shift();
        }

        // Update UI
        this.renderMetricCards(metrics);
        this.updateCharts();
    }

    renderMetricCards(metrics) {
        // Network-wide metrics
        this.updateMetricCard('total-networks', metrics.runningNetworks || 0, 'networks');
        this.updateMetricCard('total-agents', metrics.totalAgents || 0, 'agents');
        this.updateMetricCard('total-neighbors', metrics.totalNeighbors || 0, 'neighbors');
        this.updateMetricCard('total-routes', metrics.totalRoutes || 0, 'routes');

        // Protocol-specific metrics
        if (metrics.protocols) {
            this.updateProtocolMetrics(metrics.protocols);
        }
    }

    updateMetricCard(id, value, unit) {
        const card = document.getElementById(id);
        if (!card) return;

        const valueEl = card.querySelector('.metric-value');
        const oldValue = parseInt(valueEl?.textContent) || 0;

        if (valueEl) {
            valueEl.textContent = value;

            // Animate change
            if (value !== oldValue) {
                valueEl.classList.add('metric-changed');
                setTimeout(() => valueEl.classList.remove('metric-changed'), 500);
            }
        }
    }

    updateProtocolMetrics(protocols) {
        const container = document.getElementById('protocol-metrics');
        if (!container) return;

        let html = '';

        // OSPF
        if (protocols.ospf) {
            html += this.renderProtocolCard('OSPF', protocols.ospf, 'ospf');
        }

        // BGP
        if (protocols.bgp) {
            html += this.renderProtocolCard('BGP', protocols.bgp, 'bgp');
        }

        // IS-IS
        if (protocols.isis) {
            html += this.renderProtocolCard('IS-IS', protocols.isis, 'isis');
        }

        // MPLS
        if (protocols.mpls) {
            html += this.renderProtocolCard('MPLS', protocols.mpls, 'mpls');
        }

        // VXLAN/EVPN
        if (protocols.vxlan) {
            html += this.renderProtocolCard('VXLAN/EVPN', protocols.vxlan, 'vxlan');
        }

        container.innerHTML = html;
    }

    renderProtocolCard(name, data, type) {
        const statusClass = data.active ? 'active' : 'inactive';

        let metricsHtml = '';
        for (const [key, value] of Object.entries(data.metrics || {})) {
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            metricsHtml += `
                <div class="protocol-metric">
                    <span class="metric-label">${label}</span>
                    <span class="metric-value">${value}</span>
                </div>
            `;
        }

        return `
            <div class="protocol-card ${type}" data-protocol="${type}">
                <div class="protocol-header">
                    <span class="protocol-name">${name}</span>
                    <span class="protocol-status ${statusClass}">${data.active ? 'Active' : 'Inactive'}</span>
                </div>
                <div class="protocol-body">
                    ${metricsHtml}
                </div>
            </div>
        `;
    }

    updateTopology(topology) {
        this.networkTopology = topology;
        this.renderTopologyView(topology);
    }

    renderTopologyView(topology) {
        const container = document.getElementById('topology-view');
        if (!container || !topology) return;

        // Simple SVG-based topology visualization
        const width = container.clientWidth || 800;
        const height = 400;
        const nodes = topology.nodes || [];
        const links = topology.links || [];

        // Calculate node positions (simple circular layout)
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(width, height) * 0.35;

        nodes.forEach((node, i) => {
            const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
            node.x = centerX + radius * Math.cos(angle);
            node.y = centerY + radius * Math.sin(angle);
        });

        // Build SVG
        let svg = `
            <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}">
                <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#00d9ff"/>
                    </marker>
                </defs>
        `;

        // Draw links
        links.forEach(link => {
            const source = nodes.find(n => n.id === link.source);
            const target = nodes.find(n => n.id === link.target);
            if (source && target) {
                const statusClass = link.status === 'up' ? 'link-up' : 'link-down';
                svg += `
                    <line class="topology-link ${statusClass}"
                          x1="${source.x}" y1="${source.y}"
                          x2="${target.x}" y2="${target.y}"
                          stroke="${link.status === 'up' ? '#4ade80' : '#ef4444'}"
                          stroke-width="2"
                          data-protocol="${link.protocol || 'unknown'}"/>
                `;
            }
        });

        // Draw nodes
        nodes.forEach(node => {
            const statusColor = node.status === 'running' ? '#4ade80' :
                              node.status === 'error' ? '#ef4444' : '#888';
            svg += `
                <g class="topology-node" data-agent="${node.id}" transform="translate(${node.x}, ${node.y})">
                    <circle r="25" fill="#16213e" stroke="${statusColor}" stroke-width="3"/>
                    <text y="5" text-anchor="middle" fill="#eee" font-size="10">${this.truncate(node.name, 8)}</text>
                </g>
            `;
        });

        svg += '</svg>';
        container.innerHTML = svg;

        // Add click handlers for nodes
        container.querySelectorAll('.topology-node').forEach(node => {
            node.addEventListener('click', () => {
                const agentId = node.dataset.agent;
                this.showAgentDetails(agentId);
            });
        });
    }

    truncate(str, len) {
        if (!str) return '';
        return str.length > len ? str.substring(0, len) + '...' : str;
    }

    handleEvent(event) {
        // Add event to the event log
        const eventsContainer = document.getElementById('events-log');
        if (!eventsContainer) return;

        const eventEl = document.createElement('div');
        eventEl.className = `event-item event-${event.severity || 'info'}`;

        const time = new Date(event.timestamp || Date.now()).toLocaleTimeString();

        eventEl.innerHTML = `
            <span class="event-time">${time}</span>
            <span class="event-source">${event.source || 'System'}</span>
            <span class="event-message">${event.message}</span>
        `;

        eventsContainer.insertBefore(eventEl, eventsContainer.firstChild);

        // Limit events shown
        while (eventsContainer.children.length > 100) {
            eventsContainer.removeChild(eventsContainer.lastChild);
        }

        // Flash notification for important events
        if (event.severity === 'warning' || event.severity === 'error') {
            this.showNotification(event);
        }
    }

    updateAgentStatus(agent) {
        const agentCard = document.querySelector(`[data-agent-id="${agent.id}"]`);
        if (!agentCard) return;

        // Update status indicator
        const statusDot = agentCard.querySelector('.agent-status-dot');
        if (statusDot) {
            statusDot.className = `agent-status-dot ${agent.status}`;
        }

        // Update protocol badges
        const protocolContainer = agentCard.querySelector('.agent-protocols');
        if (protocolContainer && agent.protocols) {
            let badgesHtml = '';
            agent.protocols.forEach(proto => {
                const statusClass = proto.active ? 'active' : 'inactive';
                badgesHtml += `<span class="protocol-badge ${proto.name.toLowerCase()} ${statusClass}">${proto.name}</span>`;
            });
            protocolContainer.innerHTML = badgesHtml;
        }
    }

    updateProtocolStatus(update) {
        // Update specific protocol card
        const card = document.querySelector(`[data-protocol="${update.protocol}"]`);
        if (!card) return;

        const statusEl = card.querySelector('.protocol-status');
        if (statusEl) {
            statusEl.className = `protocol-status ${update.active ? 'active' : 'inactive'}`;
            statusEl.textContent = update.active ? 'Active' : 'Inactive';
        }

        // Update metrics
        if (update.metrics) {
            const body = card.querySelector('.protocol-body');
            if (body) {
                let metricsHtml = '';
                for (const [key, value] of Object.entries(update.metrics)) {
                    const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    metricsHtml += `
                        <div class="protocol-metric">
                            <span class="metric-label">${label}</span>
                            <span class="metric-value">${value}</span>
                        </div>
                    `;
                }
                body.innerHTML = metricsHtml;
            }
        }
    }

    showAgentDetails(agentId) {
        // Request detailed info for agent
        this.send({ type: 'get_agent_details', agent_id: agentId });
    }

    showNotification(event) {
        const notification = document.createElement('div');
        notification.className = `toast-notification toast-${event.severity}`;
        notification.innerHTML = `
            <span class="toast-icon">${event.severity === 'error' ? '!' : '⚠'}</span>
            <span class="toast-message">${event.message}</span>
        `;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => notification.classList.add('show'), 10);

        // Remove after delay
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }

    initializeCharts() {
        // Initialize simple sparkline charts if containers exist
        const chartContainers = ['packets-chart', 'neighbors-chart', 'routes-chart'];
        chartContainers.forEach(id => {
            const container = document.getElementById(id);
            if (container) {
                this.charts[id] = { container, data: [] };
            }
        });
    }

    updateCharts() {
        // Update sparkline charts with new data
        this.renderSparkline('packets-chart', this.metricHistory.packets);
        this.renderSparkline('neighbors-chart', this.metricHistory.neighbors);
        this.renderSparkline('routes-chart', this.metricHistory.routes);
    }

    renderSparkline(containerId, data) {
        const container = document.getElementById(containerId);
        if (!container || !data || data.length < 2) return;

        const width = container.clientWidth || 100;
        const height = container.clientHeight || 30;
        const padding = 2;

        const max = Math.max(...data, 1);
        const min = Math.min(...data, 0);
        const range = max - min || 1;

        const points = data.map((value, i) => {
            const x = padding + (i / (data.length - 1)) * (width - 2 * padding);
            const y = height - padding - ((value - min) / range) * (height - 2 * padding);
            return `${x},${y}`;
        }).join(' ');

        container.innerHTML = `
            <svg width="100%" height="100%" viewBox="0 0 ${width} ${height}">
                <polyline
                    fill="none"
                    stroke="#00d9ff"
                    stroke-width="1.5"
                    points="${points}"/>
            </svg>
        `;
    }

    startPeriodicUpdates() {
        // Request updates every 5 seconds
        this.updateInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'get_metrics' });
            }
        }, 5000);
    }

    refreshAll() {
        this.send({ type: 'get_metrics' });
        this.send({ type: 'get_topology' });
    }

    destroy() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Global instance
let realtimeMonitor = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    realtimeMonitor = new RealtimeMonitor();
    realtimeMonitor.init();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (realtimeMonitor) {
        realtimeMonitor.destroy();
    }
});
