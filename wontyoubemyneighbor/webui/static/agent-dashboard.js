/**
 * Agent Dashboard - Protocol-Specific Metrics
 *
 * Provides detailed per-agent monitoring with protocol-specific dashboards
 */

class AgentDashboard {
    constructor() {
        this.ws = null;
        this.agentId = null;
        this.protocols = {};
        this.activeProtocol = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;

        // Store detailed data for markmap visualization
        this.interfaceDetails = [];
        this.ospfNeighborDetails = [];
        this.bgpPeerDetails = [];
        this.ospfRoutes = [];
        this.bgpRoutes = [];
        this.isisAdjacencies = [];

        this.init();
    }

    init() {
        // Get agent ID from URL params or use default
        const urlParams = new URLSearchParams(window.location.search);
        this.agentId = urlParams.get('agent_id') || urlParams.get('agent') || 'local';

        this.connectWebSocket();
        this.setupEventListeners();

        // Build initial tabs (MCP tabs will show immediately)
        this.buildProtocolTabs();

        // Set default active protocol to chat
        this.activeProtocol = 'chat';
        this.selectProtocol('chat');

        // Setup chat functionality
        this.setupChat();
    }

    connectWebSocket() {
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
        this.updateConnectionStatus(true);
        console.log('Agent dashboard connected');

        // Request initial status
        this.requestStatus();
        this.requestRoutes();
    }

    onDisconnect() {
        this.updateConnectionStatus(false);
        console.log('Agent dashboard disconnected');
        this.scheduleReconnect();
    }

    onError(error) {
        console.error('WebSocket error:', error);
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
            setTimeout(() => this.connectWebSocket(), delay);
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    requestStatus() {
        this.send({ type: 'get_status' });
    }

    requestRoutes() {
        this.send({ type: 'get_routes' });
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
                    // Could add log streaming here
                    break;
                case 'test_results':
                    // Re-enable the run tests button
                    this._testsRunning = false;
                    const btn = document.getElementById('run-all-tests-btn');
                    if (btn) {
                        btn.textContent = 'Run All Tests';
                        btn.disabled = false;
                    }
                    // Handle different response formats
                    const results = data.data.results || data.data || [];
                    this.updateTestResults(Array.isArray(results) ? results : []);
                    break;
                case 'testing':
                    this.updateTestingData(data.data);
                    break;
                case 'gait':
                    this.updateGAITData(data.data);
                    break;
                case 'markmap':
                    this.updateMarkmapData(data.data);
                    break;
            }
        } catch (err) {
            console.error('Error parsing message:', err);
        }
    }

    updateConnectionStatus(connected) {
        const dot = document.getElementById('ws-status');
        const text = document.getElementById('connection-text');

        if (dot) {
            dot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
        }
        if (text) {
            text.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    updateStatus(status) {
        // Update agent info banner
        document.getElementById('agent-name').textContent = status.agent_name || 'Agent Dashboard';
        document.getElementById('router-id').textContent = status.router_id || '--';

        // Update per-agent 3D view link with this agent's ID
        const agent3dLink = document.getElementById('agent3dViewLink');
        if (agent3dLink) {
            const agentIdentifier = status.agent_name || status.router_id || 'local';
            agent3dLink.href = `/topology3d?agent=${encodeURIComponent(agentIdentifier)}`;
        }

        // Update uptime
        document.getElementById('uptime').textContent = status.uptime || '--';

        // Agentic info (provider and model)
        if (status.agentic) {
            document.getElementById('llm-provider').textContent = status.agentic.provider || '--';
            document.getElementById('llm-model').textContent = status.agentic.model || '--';
        }

        // Determine active protocols and build tabs
        this.protocols = {};
        let totalNeighbors = 0;

        if (status.ospf) {
            this.protocols.ospf = status.ospf;
            totalNeighbors += status.ospf.neighbors || 0;
        }

        if (status.bgp && !status.bgp.error) {
            this.protocols.bgp = status.bgp;
            totalNeighbors += status.bgp.established_peers || 0;
        }

        // Check for other protocols in extended status
        if (status.isis) {
            this.protocols.isis = status.isis;
        }

        if (status.mpls) {
            this.protocols.mpls = status.mpls;
        }

        if (status.vxlan) {
            this.protocols.vxlan = status.vxlan;
        }

        if (status.dhcp) {
            this.protocols.dhcp = status.dhcp;
        }

        if (status.dns) {
            this.protocols.dns = status.dns;
        }

        document.getElementById('active-protocols').textContent = Object.keys(this.protocols).length;
        document.getElementById('total-neighbors').textContent = totalNeighbors;

        // Build protocol tabs
        this.buildProtocolTabs();

        // Update individual protocol data
        this.updateInterfacesData(status.interfaces);
        this.updateOSPFData(status.ospf);
        this.updateOSPFv3Data(status.ospfv3);
        this.updateBGPData(status.bgp);
        this.updateISISData(status.isis);
        this.updateMPLSData(status.mpls);
        this.updateVXLANData(status.vxlan);
        this.updateDHCPData(status.dhcp);
        this.updateDNSData(status.dns);

        // Update MCP data (Testing, GAIT, Markmap)
        if (status.testing) {
            this.updateTestingData(status.testing);
        }
        if (status.gait) {
            this.updateGAITData(status.gait);
        }
        if (status.markmap) {
            this.updateMarkmapData(status.markmap);
        }

        // Update protocol test suites based on active protocols
        this.updateProtocolTestSuites();

        // Auto-select Interfaces tab if none selected, otherwise first protocol
        if (!this.activeProtocol) {
            this.selectProtocol('interfaces');
        }
    }

    updateInterfacesData(interfaces) {
        if (!interfaces || !Array.isArray(interfaces)) {
            interfaces = [];
        }

        // Store for markmap visualization
        this.interfaceDetails = interfaces;

        // Calculate metrics
        const total = interfaces.length;
        const up = interfaces.filter(i => i.status === 'up' || i.s === 'up').length;
        const down = total - up;
        const withIp = interfaces.filter(i => {
            const addrs = i.addresses || i.a || [];
            return addrs.length > 0;
        }).length;

        document.getElementById('if-total').textContent = total;
        document.getElementById('if-up').textContent = up;
        document.getElementById('if-down').textContent = down;
        document.getElementById('if-with-ip').textContent = withIp;

        // Update interfaces table
        const ifTable = document.getElementById('interfaces-table');
        if (ifTable) {
            if (interfaces.length === 0) {
                ifTable.innerHTML = '<tr><td colspan="6" class="empty-state">No interfaces configured</td></tr>';
            } else {
                let html = '';
                for (const iface of interfaces) {
                    const name = iface.name || iface.n || iface.id;
                    const type = iface.type || iface.t || 'eth';
                    const addresses = iface.addresses || iface.a || [];
                    const mtu = iface.mtu || 1500;
                    const status = iface.status || iface.s || 'up';
                    const description = iface.description || '-';

                    const typeNames = {
                        'eth': 'Ethernet',
                        'lo': 'Loopback',
                        'vlan': 'VLAN',
                        'tun': 'Tunnel',
                        'sub': 'Sub-Interface'
                    };
                    const typeDisplay = typeNames[type] || type;

                    const stateClass = status === 'up' ? 'up' : 'down';
                    const addrDisplay = addresses.length > 0 ? addresses.join(', ') : '-';

                    html += `
                        <tr>
                            <td>${name}</td>
                            <td>${typeDisplay}</td>
                            <td>${addrDisplay}</td>
                            <td>${mtu}</td>
                            <td><span class="status-badge ${stateClass}">${status}</span></td>
                            <td>${description}</td>
                        </tr>
                    `;
                }
                ifTable.innerHTML = html;
            }
        }
    }

    buildProtocolTabs() {
        const tabsContainer = document.getElementById('protocol-tabs');
        if (!tabsContainer) return;

        // Protocol tabs - only show if that protocol is active on this agent
        const protocolNames = {
            bgp: 'BGP',
            ospf: 'OSPF',
            ospfv3: 'OSPFv3',
            isis: 'IS-IS',
            mpls: 'MPLS',
            vxlan: 'VXLAN/EVPN',
            dhcp: 'DHCP',
            dns: 'DNS'
        };

        // Core MCP/feature tabs - always shown (LLDP is added separately after Interfaces)
        const mcpTabs = {
            testing: 'Testing',
            gait: 'GAIT',
            markmap: 'Markmap',
            prometheus: 'Prometheus',
            grafana: 'Grafana',
            logs: 'Logs'
        };

        let html = '';

        // Always add Chat tab first (main interaction point)
        const chatActive = this.activeProtocol === 'chat' ? 'active' : '';
        html += `
            <button class="protocol-tab chat ${chatActive}" data-protocol="chat">
                <span class="protocol-indicator active"></span>
                💬 Chat
            </button>
        `;

        // Add Interfaces tab (always active since every agent has interfaces)
        const interfacesActive = this.activeProtocol === 'interfaces' ? 'active' : '';
        html += `
            <button class="protocol-tab interfaces ${interfacesActive}" data-protocol="interfaces">
                <span class="protocol-indicator active"></span>
                Interfaces
            </button>
        `;

        // Add LLDP tab right after Interfaces (underlay discovery)
        const lldpActive = this.activeProtocol === 'lldp' ? 'active' : '';
        html += `
            <button class="protocol-tab lldp ${lldpActive}" data-protocol="lldp">
                <span class="protocol-indicator active"></span>
                LLDP
            </button>
        `;

        for (const [proto, data] of Object.entries(this.protocols)) {
            const active = proto === this.activeProtocol ? 'active' : '';
            const name = protocolNames[proto] || proto.toUpperCase();
            html += `
                <button class="protocol-tab ${proto} ${active}" data-protocol="${proto}">
                    <span class="protocol-indicator active"></span>
                    ${name}
                </button>
            `;
        }

        // Add core tabs (Routes, GAIT, Markmap, Testing, Logs)
        // Everything else is accessible via Chat commands
        for (const [tab, name] of Object.entries(mcpTabs)) {
            const active = tab === this.activeProtocol ? 'active' : '';
            html += `
                <button class="protocol-tab ${tab} ${active}" data-protocol="${tab}">
                    <span class="protocol-indicator active"></span>
                    ${name}
                </button>
            `;
        }

        tabsContainer.innerHTML = html;

        // Add click handlers (including interfaces and MCP tabs)
        tabsContainer.querySelectorAll('.protocol-tab:not([disabled])').forEach(tab => {
            tab.addEventListener('click', () => {
                this.selectProtocol(tab.dataset.protocol);
            });
        });
    }

    selectProtocol(protocol) {
        this.activeProtocol = protocol;

        // Update tab states
        document.querySelectorAll('.protocol-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.protocol === protocol);
        });

        // Show/hide content
        document.querySelectorAll('.protocol-content').forEach(content => {
            content.classList.toggle('active', content.id === `${protocol}-content`);
        });

        // Request data for tabs that need it
        if (protocol === 'gait') {
            this.send({ type: 'get_gait', agent_id: this.agentId });
        } else if (protocol === 'markmap') {
            this.send({ type: 'get_markmap', agent_id: this.agentId });
        } else if (protocol === 'testing') {
            this.fetchPreviousTestResults();
        } else if (protocol === 'prometheus') {
            this.fetchPrometheusData();
        } else if (protocol === 'grafana') {
            this.fetchGrafanaData();
        } else if (protocol === 'lldp') {
            this.fetchLLDPData();
        } else if (protocol === 'logs') {
            this.fetchLogsData();
        }
    }

    fetchPrometheusData() {
        // Fetch metrics from the agent-specific endpoint
        const agentId = this.agentId || 'local';
        fetch(`/api/agent/${agentId}/metrics`)
            .then(r => r.json())
            .then(data => {
                console.log('Prometheus API response:', data);
                console.log('Chart data - rx_bytes:', data.rx_bytes, 'tx_bytes:', data.tx_bytes, 'lsa_count:', data.lsa_count, 'neighbor_count:', data.neighbor_count);
                this.updatePrometheusDisplay(data);
            })
            .catch(err => console.log('Prometheus fetch error:', err));
    }

    updatePrometheusDisplay(data) {
        if (!data || data.error) {
            console.log('Prometheus data error:', data?.error);
            return;
        }

        const metrics = data.metrics || [];

        // Update metric counts
        let gauges = 0, counters = 0, histograms = 0;
        metrics.forEach(m => {
            if (m.type === 'gauge') gauges++;
            else if (m.type === 'counter') counters++;
            else if (m.type === 'histogram') histograms++;
        });

        const totalEl = document.getElementById('prometheus-total');
        const gaugesEl = document.getElementById('prometheus-gauges');
        const countersEl = document.getElementById('prometheus-counters');
        const histogramsEl = document.getElementById('prometheus-histograms');

        if (totalEl) totalEl.textContent = metrics.length;
        if (gaugesEl) gaugesEl.textContent = gauges;
        if (countersEl) countersEl.textContent = counters;
        if (histogramsEl) histogramsEl.textContent = histograms;

        // Extract system metrics for CPU/Memory/Disk panels
        let cpuPercent = 0, memoryPercent = 0, diskPercent = 0;
        metrics.forEach(m => {
            if (m.name === 'system_cpu_percent') cpuPercent = m.value || 0;
            else if (m.name === 'system_memory_percent') memoryPercent = m.value || 0;
            else if (m.name === 'system_disk_percent') diskPercent = m.value || 0;
        });

        // Update CPU panel
        const cpuValueEl = document.getElementById('prometheus-cpu-value');
        const cpuBarEl = document.getElementById('prometheus-cpu-bar');
        if (cpuValueEl) cpuValueEl.textContent = cpuPercent.toFixed(1) + '%';
        if (cpuBarEl) cpuBarEl.style.width = Math.min(cpuPercent, 100) + '%';

        // Update Memory panel
        const memValueEl = document.getElementById('prometheus-memory-value');
        const memBarEl = document.getElementById('prometheus-memory-bar');
        if (memValueEl) memValueEl.textContent = memoryPercent.toFixed(1) + '%';
        if (memBarEl) memBarEl.style.width = Math.min(memoryPercent, 100) + '%';

        // Update Disk panel
        const diskValueEl = document.getElementById('prometheus-disk-value');
        const diskBarEl = document.getElementById('prometheus-disk-bar');
        if (diskValueEl) diskValueEl.textContent = diskPercent.toFixed(1) + '%';
        if (diskBarEl) diskBarEl.style.width = Math.min(diskPercent, 100) + '%';

        // Update charts with data from API response
        const now = new Date().toLocaleTimeString();

        // Initialize charts if not already done
        if (!this.prometheusChartsInitialized) {
            this.initPrometheusCharts();
            this.prometheusChartsInitialized = true;
        }

        // Update Neighbor State chart
        if (this.prometheusNeighborChart) {
            this.prometheusNeighborChart.data.labels.push(now);
            this.prometheusNeighborChart.data.datasets[0].data.push(data.neighbor_count || 0);
            if (this.prometheusNeighborChart.data.labels.length > 30) {
                this.prometheusNeighborChart.data.labels.shift();
                this.prometheusNeighborChart.data.datasets[0].data.shift();
            }
            this.prometheusNeighborChart.update('none');
        }

        // Update Traffic chart (RX and TX)
        if (this.prometheusTrafficChart) {
            this.prometheusTrafficChart.data.labels.push(now);
            this.prometheusTrafficChart.data.datasets[0].data.push(data.rx_bytes || 0);
            this.prometheusTrafficChart.data.datasets[1].data.push(data.tx_bytes || 0);
            if (this.prometheusTrafficChart.data.labels.length > 30) {
                this.prometheusTrafficChart.data.labels.shift();
                this.prometheusTrafficChart.data.datasets[0].data.shift();
                this.prometheusTrafficChart.data.datasets[1].data.shift();
            }
            this.prometheusTrafficChart.update('none');
        }

        // Update Protocol Messages chart
        if (this.prometheusMessagesChart) {
            this.prometheusMessagesChart.data.datasets[0].data = [
                data.messages_sent || 0,
                data.messages_recv || 0,
                0, 0, 0  // LSR, LSU, LSAck placeholders
            ];
            this.prometheusMessagesChart.update('none');
        }

        // Update LSA/Route Updates chart
        if (this.prometheusUpdatesChart) {
            this.prometheusUpdatesChart.data.labels.push(now);
            this.prometheusUpdatesChart.data.datasets[0].data.push(data.lsa_count || 0);
            if (this.prometheusUpdatesChart.data.labels.length > 30) {
                this.prometheusUpdatesChart.data.labels.shift();
                this.prometheusUpdatesChart.data.datasets[0].data.shift();
            }
            this.prometheusUpdatesChart.update('none');
        }

        // Update separate RX chart
        if (this.prometheusRxChart) {
            this.prometheusRxChart.data.labels.push(now);
            this.prometheusRxChart.data.datasets[0].data.push(data.rx_bytes || 0);
            if (this.prometheusRxChart.data.labels.length > 30) {
                this.prometheusRxChart.data.labels.shift();
                this.prometheusRxChart.data.datasets[0].data.shift();
            }
            this.prometheusRxChart.update('none');
        }

        // Update separate TX chart
        if (this.prometheusTxChart) {
            this.prometheusTxChart.data.labels.push(now);
            this.prometheusTxChart.data.datasets[0].data.push(data.tx_bytes || 0);
            if (this.prometheusTxChart.data.labels.length > 30) {
                this.prometheusTxChart.data.labels.shift();
                this.prometheusTxChart.data.datasets[0].data.shift();
            }
            this.prometheusTxChart.update('none');
        }

        // ============= OSPF Protocol Dashboard =============
        const ospfSection = document.getElementById('prometheus-ospf-section');
        const ospfData = data.ospf || {};

        if (ospfSection) {
            // Show/hide OSPF section based on activity
            if (ospfData.active || ospfData.hello_sent > 0 || ospfData.hello_recv > 0) {
                ospfSection.style.display = 'block';

                // Update OSPF stat cards
                const helloSentEl = document.getElementById('ospf-hello-sent');
                const helloRecvEl = document.getElementById('ospf-hello-recv');
                const dbdTotalEl = document.getElementById('ospf-dbd-total');
                const lsuTotalEl = document.getElementById('ospf-lsu-total');
                const lsackTotalEl = document.getElementById('ospf-lsack-total');

                if (helloSentEl) helloSentEl.textContent = ospfData.hello_sent || 0;
                if (helloRecvEl) helloRecvEl.textContent = ospfData.hello_recv || 0;
                if (dbdTotalEl) dbdTotalEl.textContent = (ospfData.dbd_sent || 0) + (ospfData.dbd_recv || 0);
                if (lsuTotalEl) lsuTotalEl.textContent = (ospfData.lsu_sent || 0) + (ospfData.lsu_recv || 0);
                if (lsackTotalEl) lsackTotalEl.textContent = (ospfData.lsack_sent || 0) + (ospfData.lsack_recv || 0);

                // Update OSPF badges
                const neighborBadge = document.getElementById('ospf-neighbor-badge');
                const lsdbBadge = document.getElementById('ospf-lsdb-badge');
                const routesBadge = document.getElementById('ospf-routes-badge');

                if (neighborBadge) neighborBadge.textContent = (ospfData.neighbor_count || data.neighbor_count || 0) + ' Neighbors';
                if (lsdbBadge) lsdbBadge.textContent = (data.lsa_count || 0) + ' LSAs';
                if (routesBadge) routesBadge.textContent = (data.route_count || 0) + ' Routes';

                // Update OSPF Neighbors Timeline chart
                if (this.ospfNeighborsChart) {
                    this.ospfNeighborsChart.data.labels.push(now);
                    this.ospfNeighborsChart.data.datasets[0].data.push(ospfData.neighbor_count || data.neighbor_count || 0);
                    if (this.ospfNeighborsChart.data.labels.length > 30) {
                        this.ospfNeighborsChart.data.labels.shift();
                        this.ospfNeighborsChart.data.datasets[0].data.shift();
                    }
                    this.ospfNeighborsChart.update('none');
                }

                // Update OSPF Messages chart
                if (this.ospfMessagesChart) {
                    this.ospfMessagesChart.data.datasets[0].data = [
                        ospfData.hello_sent || 0,
                        ospfData.dbd_sent || 0,
                        ospfData.lsr_sent || 0,
                        ospfData.lsu_sent || 0,
                        ospfData.lsack_sent || 0
                    ];
                    this.ospfMessagesChart.data.datasets[1].data = [
                        ospfData.hello_recv || 0,
                        ospfData.dbd_recv || 0,
                        ospfData.lsr_recv || 0,
                        ospfData.lsu_recv || 0,
                        ospfData.lsack_recv || 0
                    ];
                    this.ospfMessagesChart.update('none');
                }
            } else {
                ospfSection.style.display = 'none';
            }
        }

        // ============= BGP Protocol Dashboard =============
        const bgpSection = document.getElementById('prometheus-bgp-section');
        const bgpData = data.bgp || {};

        if (bgpSection) {
            // Show/hide BGP section based on activity, configured peers, or routes
            if (bgpData.active || bgpData.peer_count > 0 || bgpData.routes_count > 0 || bgpData.open_sent > 0 || bgpData.keepalive_sent > 0) {
                bgpSection.style.display = 'block';

                // Update BGP stat cards
                const openTotalEl = document.getElementById('bgp-open-total');
                const updateTotalEl = document.getElementById('bgp-update-total');
                const keepaliveTotalEl = document.getElementById('bgp-keepalive-total');
                const notificationTotalEl = document.getElementById('bgp-notification-total');

                if (openTotalEl) openTotalEl.textContent = (bgpData.open_sent || 0) + (bgpData.open_recv || 0);
                if (updateTotalEl) updateTotalEl.textContent = (bgpData.update_sent || 0) + (bgpData.update_recv || 0);
                if (keepaliveTotalEl) keepaliveTotalEl.textContent = (bgpData.keepalive_sent || 0) + (bgpData.keepalive_recv || 0);
                if (notificationTotalEl) notificationTotalEl.textContent = (bgpData.notification_sent || 0) + (bgpData.notification_recv || 0);

                // Update BGP badges
                const peersBadge = document.getElementById('bgp-peers-badge');
                const establishedBadge = document.getElementById('bgp-established-badge');
                const bgpRoutesBadge = document.getElementById('bgp-routes-badge');

                if (peersBadge) peersBadge.textContent = (bgpData.peer_count || 0) + ' Peers';
                if (establishedBadge) establishedBadge.textContent = (bgpData.established_count || 0) + ' Established';
                if (bgpRoutesBadge) bgpRoutesBadge.textContent = (bgpData.routes_count || 0) + ' Routes';

                // Update BGP Peers Timeline chart
                if (this.bgpPeersChart) {
                    this.bgpPeersChart.data.labels.push(now);
                    this.bgpPeersChart.data.datasets[0].data.push(bgpData.peer_count || 0);
                    if (this.bgpPeersChart.data.labels.length > 30) {
                        this.bgpPeersChart.data.labels.shift();
                        this.bgpPeersChart.data.datasets[0].data.shift();
                    }
                    this.bgpPeersChart.update('none');
                }

                // Update BGP Messages chart
                if (this.bgpMessagesChart) {
                    this.bgpMessagesChart.data.datasets[0].data = [
                        bgpData.open_sent || 0,
                        bgpData.update_sent || 0,
                        bgpData.keepalive_sent || 0,
                        bgpData.notification_sent || 0
                    ];
                    this.bgpMessagesChart.data.datasets[1].data = [
                        bgpData.open_recv || 0,
                        bgpData.update_recv || 0,
                        bgpData.keepalive_recv || 0,
                        bgpData.notification_recv || 0
                    ];
                    this.bgpMessagesChart.update('none');
                }
            } else {
                bgpSection.style.display = 'none';
            }
        }

        // Update metrics table
        const tableBody = document.getElementById('prometheus-metrics-table');
        if (tableBody) {
            if (metrics.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No metrics collected yet</td></tr>';
            } else {
                let html = '';
                metrics.forEach(m => {
                    const labels = m.labels ? Object.entries(m.labels).map(([k,v]) => `${k}="${v}"`).join(', ') : '-';
                    html += `
                        <tr>
                            <td style="font-family: monospace; color: #e6522c;">${m.name || '-'}</td>
                            <td><span class="status-badge">${m.type || '-'}</span></td>
                            <td style="font-weight: bold;">${m.value !== undefined ? m.value : '-'}</td>
                            <td style="font-size: 0.85em; color: var(--text-secondary);">${labels}</td>
                            <td style="font-size: 0.85em;">${m.description || '-'}</td>
                        </tr>
                    `;
                });
                tableBody.innerHTML = html;
            }
        }
    }

    initPrometheusCharts() {
        // Initialize Neighbor State chart
        const neighborCtx = document.getElementById('prometheus-neighbor-chart');
        if (neighborCtx && !this.prometheusNeighborChart) {
            this.prometheusNeighborChart = new Chart(neighborCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Neighbors',
                        data: [],
                        borderColor: '#e6522c',
                        backgroundColor: 'rgba(230, 82, 44, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize Traffic chart
        const trafficCtx = document.getElementById('prometheus-traffic-chart');
        if (trafficCtx && !this.prometheusTrafficChart) {
            this.prometheusTrafficChart = new Chart(trafficCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'RX', data: [], borderColor: '#22d3ee', backgroundColor: 'rgba(34, 211, 238, 0.1)', fill: true, tension: 0.4 },
                        { label: 'TX', data: [], borderColor: '#f97316', backgroundColor: 'rgba(249, 115, 22, 0.1)', fill: true, tension: 0.4 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize Messages chart
        const messagesCtx = document.getElementById('prometheus-messages-chart');
        if (messagesCtx && !this.prometheusMessagesChart) {
            this.prometheusMessagesChart = new Chart(messagesCtx, {
                type: 'bar',
                data: {
                    labels: ['Sent', 'Recv', 'LSR', 'LSU', 'LSAck'],
                    datasets: [{
                        label: 'Messages',
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: ['#e6522c', '#f97316', '#fbbf24', '#4ade80', '#22d3ee']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize Updates chart
        const updatesCtx = document.getElementById('prometheus-updates-chart');
        if (updatesCtx && !this.prometheusUpdatesChart) {
            this.prometheusUpdatesChart = new Chart(updatesCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'LSA Updates',
                        data: [],
                        borderColor: '#a855f7',
                        backgroundColor: 'rgba(168, 85, 247, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize separate RX chart
        const rxCtx = document.getElementById('prometheus-rx-chart');
        if (rxCtx && !this.prometheusRxChart) {
            this.prometheusRxChart = new Chart(rxCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'RX Bytes',
                        data: [],
                        borderColor: '#22d3ee',
                        backgroundColor: 'rgba(34, 211, 238, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize separate TX chart
        const txCtx = document.getElementById('prometheus-tx-chart');
        if (txCtx && !this.prometheusTxChart) {
            this.prometheusTxChart = new Chart(txCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'TX Bytes',
                        data: [],
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize OSPF Neighbors Timeline chart
        const ospfNeighborsCtx = document.getElementById('ospf-neighbors-chart');
        if (ospfNeighborsCtx && !this.ospfNeighborsChart) {
            this.ospfNeighborsChart = new Chart(ospfNeighborsCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'OSPF Neighbors',
                        data: [],
                        borderColor: '#4ade80',
                        backgroundColor: 'rgba(74, 222, 128, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize OSPF Message Types chart
        const ospfMessagesCtx = document.getElementById('ospf-messages-chart');
        if (ospfMessagesCtx && !this.ospfMessagesChart) {
            this.ospfMessagesChart = new Chart(ospfMessagesCtx, {
                type: 'bar',
                data: {
                    labels: ['Hello', 'DBD', 'LSR', 'LSU', 'LSAck'],
                    datasets: [
                        {
                            label: 'Sent',
                            data: [0, 0, 0, 0, 0],
                            backgroundColor: '#4ade80'
                        },
                        {
                            label: 'Recv',
                            data: [0, 0, 0, 0, 0],
                            backgroundColor: '#22d3ee'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize BGP Peers Timeline chart
        const bgpPeersCtx = document.getElementById('bgp-peers-chart');
        if (bgpPeersCtx && !this.bgpPeersChart) {
            this.bgpPeersChart = new Chart(bgpPeersCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'BGP Peers',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Initialize BGP Message Types chart
        const bgpMessagesCtx = document.getElementById('bgp-messages-chart');
        if (bgpMessagesCtx && !this.bgpMessagesChart) {
            this.bgpMessagesChart = new Chart(bgpMessagesCtx, {
                type: 'bar',
                data: {
                    labels: ['OPEN', 'UPDATE', 'KEEPALIVE', 'NOTIFICATION'],
                    datasets: [
                        {
                            label: 'Sent',
                            data: [0, 0, 0, 0],
                            backgroundColor: '#3b82f6'
                        },
                        {
                            label: 'Recv',
                            data: [0, 0, 0, 0],
                            backgroundColor: '#22c55e'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }
    }

    fetchGrafanaData() {
        fetch('/api/grafana/dashboards')
            .then(r => r.json())
            .then(data => this.updateGrafanaDisplay(data))
            .catch(err => console.log('Grafana fetch error:', err));
    }

    updateGrafanaDisplay(data) {
        if (!data) return;

        const dashboards = data.dashboards || [];

        // Update dashboard count
        const countEl = document.getElementById('grafana-dashboards');
        if (countEl) countEl.textContent = dashboards.length || 3;  // Default 3 pre-built dashboards

        // Update panels count (sum of all dashboard panels)
        const panelsEl = document.getElementById('grafana-panels');
        if (panelsEl) {
            const totalPanels = dashboards.reduce((sum, d) => sum + (d.panels?.length || 0), 0);
            panelsEl.textContent = totalPanels || 12;  // Default for pre-built panels
        }

        // Update last refresh time
        const refreshEl = document.getElementById('grafana-last-refresh');
        if (refreshEl) {
            refreshEl.textContent = new Date().toLocaleTimeString();
        }

        if (data.error) {
            console.log('Grafana info:', data.error);
        }
    }

    fetchLogsData() {
        // Fetch agent logs - this triggers the inline logs JS
        fetch('/api/logs?tail=500')
            .then(r => r.json())
            .then(data => this.updateLogsDisplay(data))
            .catch(err => console.log('Logs fetch error:', err));
    }

    updateLogsDisplay(data) {
        if (!data) return;

        const logs = data.logs || [];

        // Update metrics
        const totalEl = document.getElementById('logs-total');
        const errorsEl = document.getElementById('logs-errors');
        const warningsEl = document.getElementById('logs-warnings');

        if (totalEl) totalEl.textContent = logs.length;
        if (errorsEl) errorsEl.textContent = logs.filter(l => l.level === 'ERROR').length;
        if (warningsEl) warningsEl.textContent = logs.filter(l => l.level === 'WARNING').length;

        // The actual log rendering is handled by the inline script in agent-dashboard.html
    }

    updateOSPFData(ospf) {
        if (!ospf) return;

        // Store for markmap visualization
        this.ospfNeighborDetails = ospf.neighbor_details || [];

        document.getElementById('ospf-neighbors').textContent = ospf.neighbors || 0;
        document.getElementById('ospf-full').textContent = ospf.full_neighbors || 0;
        document.getElementById('ospf-lsdb').innerHTML = `${ospf.lsdb_size || 0} <span class="metric-unit">LSAs</span>`;
        document.getElementById('ospf-routes').textContent = ospf.routes || 0;

        // Update neighbors table
        const neighborsTable = document.getElementById('ospf-neighbors-table');
        if (neighborsTable && ospf.neighbor_details) {
            if (ospf.neighbor_details.length === 0) {
                neighborsTable.innerHTML = '<tr><td colspan="4" class="empty-state">No neighbors</td></tr>';
            } else {
                let html = '';
                for (const n of ospf.neighbor_details) {
                    const stateClass = n.is_full ? 'full' : 'init';
                    html += `
                        <tr>
                            <td>${n.router_id}</td>
                            <td>${n.ip}</td>
                            <td><span class="status-badge ${stateClass}">${n.state}</span></td>
                            <td>${n.dr || '-'}</td>
                        </tr>
                    `;
                }
                neighborsTable.innerHTML = html;
            }
        }
    }

    updateOSPFv3Data(ospfv3) {
        if (!ospfv3) return;

        // Store for markmap visualization
        this.ospfv3NeighborDetails = ospfv3.neighbor_details || [];

        document.getElementById('ospfv3-neighbors').textContent = ospfv3.neighbors || 0;
        document.getElementById('ospfv3-full').textContent = ospfv3.full_neighbors || 0;
        document.getElementById('ospfv3-lsdb').innerHTML = `${ospfv3.lsdb_size || 0} <span class="metric-unit">LSAs</span>`;
        document.getElementById('ospfv3-routes').textContent = ospfv3.routes || 0;

        // Update neighbors table
        const neighborsTable = document.getElementById('ospfv3-neighbors-table');
        if (neighborsTable && ospfv3.neighbor_details) {
            if (ospfv3.neighbor_details.length === 0) {
                neighborsTable.innerHTML = '<tr><td colspan="4" class="empty-state">No IPv6 neighbors</td></tr>';
            } else {
                let html = '';
                for (const n of ospfv3.neighbor_details) {
                    const stateClass = n.is_full ? 'full' : 'init';
                    html += `
                        <tr>
                            <td>${n.router_id}</td>
                            <td>${n.ipv6 || n.ip || '-'}</td>
                            <td><span class="status-badge ${stateClass}">${n.state}</span></td>
                            <td>${n.interface || '-'}</td>
                        </tr>
                    `;
                }
                neighborsTable.innerHTML = html;
            }
        }
    }

    updateBGPData(bgp) {
        if (!bgp || bgp.error) return;

        // Store for markmap visualization
        this.bgpPeerDetails = bgp.peer_details || [];

        document.getElementById('bgp-peers').textContent = bgp.total_peers || 0;
        document.getElementById('bgp-established').textContent = bgp.established_peers || 0;
        document.getElementById('bgp-prefixes-in').textContent = bgp.loc_rib_routes || 0;
        document.getElementById('bgp-prefixes-out').textContent = bgp.advertised_routes || 0;

        // Update peers table
        const peersTable = document.getElementById('bgp-peers-table');
        if (peersTable && bgp.peer_details) {
            if (bgp.peer_details.length === 0) {
                peersTable.innerHTML = '<tr><td colspan="4" class="empty-state">No peers</td></tr>';
            } else {
                let html = '';
                for (const p of bgp.peer_details) {
                    const stateClass = p.state === 'Established' ? 'established' : 'idle';
                    html += `
                        <tr>
                            <td>${p.ip}</td>
                            <td>${p.remote_as}</td>
                            <td><span class="status-badge ${stateClass}">${p.state}</span></td>
                            <td>${p.peer_type}</td>
                        </tr>
                    `;
                }
                peersTable.innerHTML = html;
            }
        }
    }

    updateRoutes(routes) {
        // Store for markmap visualization
        this.ospfRoutes = routes.ospf || [];
        this.bgpRoutes = routes.bgp || [];
        this.ospfv3Routes = routes.ospfv3 || [];
        this.bgpIpv6Routes = routes.bgp_ipv6 || [];

        // OSPF IPv4 routes
        const ospfRoutesTable = document.getElementById('ospf-routes-table');
        if (ospfRoutesTable && routes.ospf) {
            if (routes.ospf.length === 0) {
                ospfRoutesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No routes</td></tr>';
            } else {
                let html = '';
                for (const r of routes.ospf.slice(0, 20)) {
                    html += `
                        <tr>
                            <td>${r.prefix}</td>
                            <td>${r.next_hop || 'Direct'}</td>
                            <td>${r.interface || r.outgoing_interface || '-'}</td>
                            <td>${r.cost}</td>
                            <td>${r.type || 'Intra'}</td>
                        </tr>
                    `;
                }
                ospfRoutesTable.innerHTML = html;
            }
        }

        // OSPFv3 IPv6 routes
        const ospfv3RoutesTable = document.getElementById('ospfv3-routes-table');
        if (ospfv3RoutesTable && routes.ospfv3) {
            if (routes.ospfv3.length === 0) {
                ospfv3RoutesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No IPv6 routes</td></tr>';
            } else {
                let html = '';
                for (const r of routes.ospfv3.slice(0, 20)) {
                    html += `
                        <tr>
                            <td>${r.prefix}</td>
                            <td>${r.next_hop || 'Direct'}</td>
                            <td>${r.interface || r.outgoing_interface || '-'}</td>
                            <td>${r.cost}</td>
                            <td>${r.type || 'Intra'}</td>
                        </tr>
                    `;
                }
                ospfv3RoutesTable.innerHTML = html;
            }
        }

        // BGP IPv4 routes
        const bgpRoutesTable = document.getElementById('bgp-routes-table');
        if (bgpRoutesTable && routes.bgp) {
            if (routes.bgp.length === 0) {
                bgpRoutesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No IPv4 routes</td></tr>';
            } else {
                let html = '';
                for (const r of routes.bgp.slice(0, 20)) {
                    html += `
                        <tr>
                            <td>${r.prefix}</td>
                            <td>${r.next_hop}</td>
                            <td>${r.interface || r.outgoing_interface || '-'}</td>
                            <td>${r.as_path || '-'}</td>
                            <td>${r.origin || 'IGP'}</td>
                        </tr>
                    `;
                }
                bgpRoutesTable.innerHTML = html;
            }
        }

        // BGP IPv6 routes
        const bgpIpv6RoutesTable = document.getElementById('bgp-ipv6-routes-table');
        if (bgpIpv6RoutesTable && routes.bgp_ipv6) {
            if (routes.bgp_ipv6.length === 0) {
                bgpIpv6RoutesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No IPv6 routes</td></tr>';
            } else {
                let html = '';
                for (const r of routes.bgp_ipv6.slice(0, 20)) {
                    html += `
                        <tr>
                            <td>${r.prefix}</td>
                            <td>${r.next_hop}</td>
                            <td>${r.interface || r.outgoing_interface || '-'}</td>
                            <td>${r.as_path || '-'}</td>
                            <td>${r.origin || 'IGP'}</td>
                        </tr>
                    `;
                }
                bgpIpv6RoutesTable.innerHTML = html;
            }
        }
    }

    updateISISData(isis) {
        if (!isis) return;

        document.getElementById('isis-adjacencies').textContent = isis.adjacencies || 0;
        document.getElementById('isis-lsps').textContent = isis.lsp_count || 0;
        document.getElementById('isis-level').textContent = isis.level || 'L1/L2';
        document.getElementById('isis-area').textContent = isis.area || '--';

        // Update adjacencies table
        const adjTable = document.getElementById('isis-adjacencies-table');
        if (adjTable && isis.adjacency_details) {
            if (isis.adjacency_details.length === 0) {
                adjTable.innerHTML = '<tr><td colspan="5" class="empty-state">No adjacencies</td></tr>';
            } else {
                let html = '';
                for (const a of isis.adjacency_details) {
                    const stateClass = a.state === 'Up' ? 'up' : 'down';
                    html += `
                        <tr>
                            <td>${a.system_id}</td>
                            <td>${a.interface}</td>
                            <td>${a.level}</td>
                            <td><span class="status-badge ${stateClass}">${a.state}</span></td>
                            <td>${a.hold_time}s</td>
                        </tr>
                    `;
                }
                adjTable.innerHTML = html;
            }
        }
    }

    updateMPLSData(mpls) {
        if (!mpls) return;

        document.getElementById('mpls-lfib').textContent = mpls.lfib_entries || 0;
        document.getElementById('mpls-labels').textContent = mpls.labels_allocated || 0;
        document.getElementById('mpls-ldp-neighbors').textContent = mpls.ldp_neighbors || 0;
        document.getElementById('mpls-packets').textContent = mpls.packets_forwarded || 0;

        // Update LFIB table
        const lfibTable = document.getElementById('mpls-lfib-table');
        if (lfibTable && mpls.lfib_details) {
            if (mpls.lfib_details.length === 0) {
                lfibTable.innerHTML = '<tr><td colspan="4" class="empty-state">No entries</td></tr>';
            } else {
                let html = '';
                for (const e of mpls.lfib_details) {
                    html += `
                        <tr>
                            <td>${e.in_label}</td>
                            <td>${e.out_label || '-'}</td>
                            <td>${e.next_hop}</td>
                            <td>${e.action}</td>
                        </tr>
                    `;
                }
                lfibTable.innerHTML = html;
            }
        }

        // Update LDP sessions table
        const ldpTable = document.getElementById('mpls-ldp-table');
        if (ldpTable && mpls.ldp_sessions) {
            if (mpls.ldp_sessions.length === 0) {
                ldpTable.innerHTML = '<tr><td colspan="4" class="empty-state">No sessions</td></tr>';
            } else {
                let html = '';
                for (const s of mpls.ldp_sessions) {
                    const stateClass = s.state === 'Operational' ? 'active' : 'pending';
                    html += `
                        <tr>
                            <td>${s.peer}</td>
                            <td><span class="status-badge ${stateClass}">${s.state}</span></td>
                            <td>${s.labels_sent || 0}</td>
                            <td>${s.labels_received || 0}</td>
                        </tr>
                    `;
                }
                ldpTable.innerHTML = html;
            }
        }
    }

    updateVXLANData(vxlan) {
        if (!vxlan) return;

        document.getElementById('vxlan-vnis').textContent = vxlan.vni_count || 0;
        document.getElementById('vxlan-vteps').textContent = vxlan.vtep_count || 0;
        document.getElementById('vxlan-macs').textContent = vxlan.mac_entries || 0;
        document.getElementById('vxlan-routes').textContent = vxlan.evpn_routes || 0;

        // Update VNI table
        const vniTable = document.getElementById('vxlan-vni-table');
        if (vniTable && vxlan.vni_details) {
            if (vxlan.vni_details.length === 0) {
                vniTable.innerHTML = '<tr><td colspan="4" class="empty-state">No VNIs</td></tr>';
            } else {
                let html = '';
                for (const v of vxlan.vni_details) {
                    html += `
                        <tr>
                            <td>${v.vni}</td>
                            <td>${v.type}</td>
                            <td>${v.vlan || '-'}</td>
                            <td>${v.vtep_count}</td>
                        </tr>
                    `;
                }
                vniTable.innerHTML = html;
            }
        }

        // Update VTEP table
        const vtepTable = document.getElementById('vxlan-vtep-table');
        if (vtepTable && vxlan.vtep_details) {
            if (vxlan.vtep_details.length === 0) {
                vtepTable.innerHTML = '<tr><td colspan="3" class="empty-state">No VTEPs</td></tr>';
            } else {
                let html = '';
                for (const t of vxlan.vtep_details) {
                    const stateClass = t.status === 'up' ? 'up' : 'down';
                    html += `
                        <tr>
                            <td>${t.ip}</td>
                            <td>${t.vnis.join(', ')}</td>
                            <td><span class="status-badge ${stateClass}">${t.status}</span></td>
                        </tr>
                    `;
                }
                vtepTable.innerHTML = html;
            }
        }
    }

    updateDHCPData(dhcp) {
        if (!dhcp) return;

        document.getElementById('dhcp-pools').textContent = dhcp.pool_count || 0;
        document.getElementById('dhcp-leases').textContent = dhcp.active_leases || 0;
        document.getElementById('dhcp-available').textContent = dhcp.available_ips || 0;
        document.getElementById('dhcp-requests').textContent = dhcp.total_requests || 0;

        // Update leases table
        const leasesTable = document.getElementById('dhcp-leases-table');
        if (leasesTable && dhcp.lease_details) {
            if (dhcp.lease_details.length === 0) {
                leasesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No leases</td></tr>';
            } else {
                let html = '';
                for (const l of dhcp.lease_details) {
                    const stateClass = l.state === 'active' ? 'active' : 'pending';
                    html += `
                        <tr>
                            <td>${l.ip_address}</td>
                            <td>${l.mac_address}</td>
                            <td>${l.hostname || '-'}</td>
                            <td>${l.expires}</td>
                            <td><span class="status-badge ${stateClass}">${l.state}</span></td>
                        </tr>
                    `;
                }
                leasesTable.innerHTML = html;
            }
        }
    }

    updateDNSData(dns) {
        if (!dns) return;

        document.getElementById('dns-zones').textContent = dns.zone_count || 0;
        document.getElementById('dns-records').textContent = dns.record_count || 0;
        document.getElementById('dns-queries').textContent = dns.queries_per_minute || 0;
        document.getElementById('dns-cache-hits').innerHTML = `${dns.cache_hit_rate || 0}<span class="metric-unit">%</span>`;

        // Update zones table
        const zonesTable = document.getElementById('dns-zones-table');
        if (zonesTable && dns.zone_details) {
            if (dns.zone_details.length === 0) {
                zonesTable.innerHTML = '<tr><td colspan="4" class="empty-state">No zones</td></tr>';
            } else {
                let html = '';
                for (const z of dns.zone_details) {
                    const stateClass = z.status === 'active' ? 'active' : 'pending';
                    html += `
                        <tr>
                            <td>${z.name}</td>
                            <td>${z.type}</td>
                            <td>${z.record_count}</td>
                            <td><span class="status-badge ${stateClass}">${z.status}</span></td>
                        </tr>
                    `;
                }
                zonesTable.innerHTML = html;
            }
        }

        // Update recent queries table
        const queriesTable = document.getElementById('dns-queries-table');
        if (queriesTable && dns.recent_queries) {
            if (dns.recent_queries.length === 0) {
                queriesTable.innerHTML = '<tr><td colspan="4" class="empty-state">No queries</td></tr>';
            } else {
                let html = '';
                for (const q of dns.recent_queries) {
                    html += `
                        <tr>
                            <td>${q.query}</td>
                            <td>${q.type}</td>
                            <td>${q.result}</td>
                            <td>${q.time}</td>
                        </tr>
                    `;
                }
                queriesTable.innerHTML = html;
            }
        }
    }

    setupEventListeners() {
        // Periodic refresh
        setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.requestStatus();
                this.requestRoutes();
            }
        }, 10000);

        // Testing tab event listeners
        this.setupTestingEvents();

        // GAIT tab event listeners
        this.setupGAITEvents();

        // Markmap tab event listeners
        this.setupMarkmapEvents();

        // Metrics tab event listeners
        this.setupMetricsEvents();

        // Grafana tab event listeners
        this.setupGrafanaEvents();

        // LLDP tab event listeners
        this.setupLLDPEvents();

        // LACP tab event listeners
        this.setupLACPEvents();

        // Subinterface tab event listeners
        this.setupSubinterfaceEvents();

        // BGP AFI tab event listeners
        this.setupBGPAFITabs();

        // Email tab event listeners
        this.setupEmailEvents();

        // Firewall tab event listeners
        this.setupFirewallEvents();

        // SSH tab event listeners
        this.setupSSHEvents();

        // NETCONF tab event listeners
        this.setupNETCONFEvents();

        // MCP External tab event listeners
        this.setupMCPExternalEvents();

        // Health tab event listeners
        this.setupHealthEvents();

        // Traffic Simulation tab event listeners
        this.setupSimulationEvents();

        // Time-Travel Replay tab event listeners
        this.setupReplayEvents();
    }

    setupBGPAFITabs() {
        const afiTabs = document.querySelectorAll('.bgp-afi-tabs .afi-tab');
        afiTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const afi = tab.dataset.afi;

                // Update tab active states
                afiTabs.forEach(t => {
                    t.classList.remove('active');
                    t.style.background = 'var(--bg-tertiary)';
                    t.style.color = 'var(--text-secondary)';
                });
                tab.classList.add('active');
                tab.style.background = 'var(--accent-cyan)';
                tab.style.color = 'white';

                // Show/hide AFI content
                document.querySelectorAll('.bgp-afi-content').forEach(content => {
                    content.style.display = 'none';
                });
                const activeContent = document.getElementById(`bgp-afi-${afi}`);
                if (activeContent) {
                    activeContent.style.display = 'block';
                }
            });
        });
    }

    // ==================== TESTING TAB (pyATS MCP) ====================
    setupTestingEvents() {
        // Save schedule button
        const saveScheduleBtn = document.getElementById('save-schedule-btn');
        if (saveScheduleBtn) {
            saveScheduleBtn.addEventListener('click', () => this.saveTestSchedule());
        }

        // Results filter
        const resultsFilter = document.getElementById('results-filter');
        if (resultsFilter) {
            resultsFilter.addEventListener('change', (e) => this.filterTestResults(e.target.value));
        }

        // pyATS MCP run tests button
        const runPyATSBtn = document.getElementById('run-pyats-mcp-btn');
        if (runPyATSBtn) {
            runPyATSBtn.addEventListener('click', () => this.runPyATSMCPTests());
        }

        // Select all tests button
        const selectAllBtn = document.getElementById('select-all-tests-btn');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => this.toggleAllTests());
        }

        // Update selected count when checkboxes change
        const testCheckboxes = document.querySelectorAll('#test-suites-list input[type="checkbox"]');
        testCheckboxes.forEach(cb => {
            cb.addEventListener('change', () => this.updateSelectedCount());
        });

        // Check pyATS MCP status and update count on load
        this.checkPyATSMCPStatus();
        this.updateSelectedCount();

        // Fetch previous test results on page load for persistence
        this.fetchPreviousTestResults();
    }

    updateSelectedCount() {
        const checkboxes = document.querySelectorAll('#test-suites-list input[type="checkbox"]:checked');
        const countEl = document.getElementById('testing-suites');
        if (countEl) {
            countEl.textContent = checkboxes.length;
        }
    }

    toggleAllTests() {
        const checkboxes = document.querySelectorAll('#test-suites-list input[type="checkbox"]');
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        checkboxes.forEach(cb => cb.checked = !allChecked);
        this.updateSelectedCount();

        const btn = document.getElementById('select-all-tests-btn');
        if (btn) {
            btn.textContent = allChecked ? 'Select All' : 'Deselect All';
        }
    }

    async checkPyATSMCPStatus() {
        try {
            const response = await fetch('/api/pyats/status');
            const data = await response.json();

            const badge = document.getElementById('pyats-mcp-status');
            const statusEl = document.getElementById('testing-mcp-status');

            if (badge) {
                badge.style.background = 'var(--accent-cyan)';
                badge.title = 'pyATS MCP Ready';
            }
            if (statusEl) {
                statusEl.textContent = 'Ready';
                statusEl.style.color = 'var(--accent-cyan)';
            }
        } catch (err) {
            console.log('pyATS MCP status check:', err.message);
        }
    }

    async runPyATSMCPTests() {
        // Get selected test types from unified list
        const typeCheckboxes = document.querySelectorAll('#test-suites-list input[type="checkbox"]:checked');
        const selectedTypes = Array.from(typeCheckboxes)
            .map(cb => cb.dataset.pyatsType)
            .filter(t => t); // Filter out undefined

        if (selectedTypes.length === 0) {
            this.showNotification('Please select at least one test type', 'error');
            return;
        }

        // Update button state
        const btn = document.getElementById('run-pyats-mcp-btn');
        const originalText = btn.textContent;
        btn.textContent = 'Running...';
        btn.disabled = true;

        // Update status
        const statusEl = document.getElementById('testing-mcp-status');
        if (statusEl) {
            statusEl.textContent = 'Running...';
            statusEl.style.color = 'var(--accent-yellow)';
        }

        try {
            const response = await fetch('/api/pyats/run-dynamic-tests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ test_types: selectedTypes })
            });

            const data = await response.json();

            if (data.success) {
                // Display test results in the results table
                this.displayPyATSGeneratedTests(data.tests, data.agent_config, data.summary);

                // Update status based on results
                const summary = data.summary || { passed: 0, failed: 0, pass_rate: 0 };
                if (statusEl) {
                    if (summary.failed > 0) {
                        statusEl.textContent = `${summary.failed} Failed`;
                        statusEl.style.color = 'var(--status-down)';
                    } else {
                        statusEl.textContent = 'All Passed';
                        statusEl.style.color = 'var(--status-up)';
                    }
                }

                // Update last run time
                document.getElementById('testing-last-run').textContent = new Date().toLocaleTimeString();

                // Show success notification with results
                const resultMsg = summary.failed > 0
                    ? `${summary.passed}/${summary.total} tests passed (${summary.failed} failed)`
                    : `All ${summary.total} tests passed!`;
                this.showNotification(resultMsg, summary.failed > 0 ? 'error' : 'success');
            } else {
                if (statusEl) {
                    statusEl.textContent = 'Error';
                    statusEl.style.color = 'var(--status-down)';
                }
                this.showNotification(`Error: ${data.error || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            console.error('pyATS MCP test error:', err);
            if (statusEl) {
                statusEl.textContent = 'Error';
                statusEl.style.color = 'var(--status-down)';
            }
            this.showNotification(`Failed: ${err.message}`, 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }

    displayPyATSGeneratedTests(tests, agentConfig, summary) {
        const table = document.getElementById('test-results-table');
        if (!table) return;

        // Handle missing data
        tests = tests || [];
        agentConfig = agentConfig || { agent_id: 'unknown', router_id: 'unknown', protocols: [], interface_count: 0 };
        summary = summary || { total: 0, passed: 0, failed: 0, pass_rate: 0 };

        // Clear existing rows
        table.innerHTML = '';

        // Add summary row
        const summaryRow = document.createElement('tr');
        const summaryColor = summary.failed > 0 ? 'var(--status-down)' : 'var(--status-up)';
        summaryRow.innerHTML = `
            <td colspan="5" style="background: var(--bg-tertiary); padding: 12px; font-size: 0.85rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>Test Results</strong> for ${agentConfig.agent_id}
                        <br><span style="color: var(--text-secondary);">Protocols: ${(agentConfig.protocols || []).join(', ') || 'None'} | Interfaces: ${agentConfig.interface_count}</span>
                    </div>
                    <div style="text-align: right;">
                        <span style="color: ${summaryColor}; font-size: 1.2rem; font-weight: 600;">${summary.pass_rate}%</span>
                        <br><span style="color: var(--text-secondary); font-size: 0.8rem;">${summary.passed}/${summary.total} passed</span>
                    </div>
                </div>
            </td>
        `;
        table.appendChild(summaryRow);

        // Add each test result
        tests.forEach(test => {
            const row = document.createElement('tr');
            row.className = 'test-result-row';

            // Determine status badge class
            const status = test.status || 'UNKNOWN';
            const statusClass = status === 'PASSED' ? 'passed' : status === 'FAILED' ? 'failed' : 'skipped';
            const statusIcon = status === 'PASSED' ? '✓' : status === 'FAILED' ? '✗' : '?';

            // Format duration
            const duration = test.duration_ms ? `${test.duration_ms}ms` : '--';

            // Format time
            const time = test.timestamp ? new Date(test.timestamp).toLocaleTimeString() : '--';

            row.innerHTML = `
                <td>
                    <strong>${test.test_name}</strong>
                    <br><span style="color: var(--text-secondary); font-size: 0.8rem;">${test.description || ''}</span>
                </td>
                <td><span class="protocol-badge">${test.category}</span></td>
                <td><span class="status-badge ${statusClass}">${statusIcon} ${status}</span></td>
                <td>${duration}</td>
                <td>
                    <button class="btn-small view-test-btn" title="View test details">
                        Details
                    </button>
                </td>
            `;
            table.appendChild(row);

            // Add click handler for view button
            const viewBtn = row.querySelector('.view-test-btn');
            viewBtn.addEventListener('click', () => this.showTestDetails(test));

            // Add expandable details row if test has details
            if (test.details && test.details.length > 0) {
                const detailsRow = document.createElement('tr');
                detailsRow.className = 'test-detail-row';
                detailsRow.style.display = 'none';
                detailsRow.innerHTML = `
                    <td colspan="5" style="background: var(--bg-primary); padding: 10px 15px; font-size: 0.85rem;">
                        <div style="font-family: monospace; white-space: pre-wrap;">${test.details.join('\n')}</div>
                    </td>
                `;
                table.appendChild(detailsRow);

                // Toggle details on row click
                row.style.cursor = 'pointer';
                row.addEventListener('click', (e) => {
                    if (e.target.tagName !== 'BUTTON') {
                        detailsRow.style.display = detailsRow.style.display === 'none' ? 'table-row' : 'none';
                        row.classList.toggle('expanded');
                    }
                });
            }
        });

        // Update metrics
        document.getElementById('testing-suites').textContent = tests.length;
        document.getElementById('testing-last-run').textContent = new Date().toLocaleTimeString();

        // Update pass rate
        const passRateEl = document.getElementById('testing-pass-rate');
        if (passRateEl) {
            passRateEl.innerHTML = `${summary.pass_rate}<span class="metric-unit">%</span>`;
            passRateEl.style.color = summary.failed > 0 ? 'var(--status-down)' : 'var(--status-up)';
        }
    }

    showTestDetails(test) {
        // Determine status styling
        const status = test.status || 'UNKNOWN';
        const statusColor = status === 'PASSED' ? 'var(--status-up)' : status === 'FAILED' ? 'var(--status-down)' : 'var(--accent-yellow)';
        const statusIcon = status === 'PASSED' ? '✓' : status === 'FAILED' ? '✗' : '?';

        // Format details
        const details = test.details || [];
        const detailsHtml = details.length > 0
            ? `<div style="font-family: monospace; background: var(--bg-tertiary); padding: 12px; border-radius: 6px; white-space: pre-wrap;">${details.join('\n')}</div>`
            : '<p style="color: var(--text-secondary);">No detailed results available</p>';

        // Format results
        const results = test.results || [];
        const resultsHtml = results.length > 0
            ? results.map(r => {
                const rStatus = r.status || 'UNKNOWN';
                const rColor = rStatus === 'PASSED' ? 'var(--status-up)' : 'var(--status-down)';
                const target = r.target || r.neighbor || r.peer || r.interface || 'unknown';
                return `<div style="display: flex; justify-content: space-between; padding: 6px 10px; background: var(--bg-tertiary); border-radius: 4px; margin-bottom: 4px;">
                    <span>${target}</span>
                    <span style="color: ${rColor}; font-weight: 500;">${rStatus}</span>
                </div>`;
            }).join('')
            : '';

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'test-details-modal';
        modal.innerHTML = `
            <div class="modal-content" style="background: var(--bg-secondary); padding: 20px; border-radius: 12px; max-width: 700px; max-height: 80vh; overflow-y: auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <div>
                        <h3 style="margin: 0;">${test.test_name}</h3>
                        <span style="color: ${statusColor}; font-weight: 600;">${statusIcon} ${status}</span>
                        ${test.duration_ms ? `<span style="color: var(--text-secondary); margin-left: 10px;">${test.duration_ms}ms</span>` : ''}
                    </div>
                    <button class="close-modal-btn" style="background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary);">&times;</button>
                </div>
                <p style="color: var(--text-secondary);">${test.description || ''}</p>

                <h4 style="margin-top: 20px;">Test Output</h4>
                ${detailsHtml}

                ${resultsHtml ? `<h4 style="margin-top: 15px;">Individual Results</h4>${resultsHtml}` : ''}

                <h4 style="margin-top: 15px;">Expected Outcomes</h4>
                <ul style="margin: 0; padding-left: 20px; color: var(--text-secondary);">
                    ${(test.expected_outcomes || []).map(o => `<li>${o}</li>`).join('')}
                </ul>

                <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;">
                    <code style="font-size: 0.75rem; color: var(--text-secondary);">${test.test_id}</code>
                    <span style="font-size: 0.8rem; color: var(--text-secondary);">${test.timestamp ? new Date(test.timestamp).toLocaleString() : ''}</span>
                </div>
            </div>
        `;
        modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000;';

        document.body.appendChild(modal);

        // Close handlers
        modal.querySelector('.close-modal-btn').addEventListener('click', () => modal.remove());
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px;
            background: ${type === 'success' ? 'var(--status-up)' : type === 'error' ? 'var(--status-down)' : 'var(--accent-cyan)'};
            color: white; font-weight: 500; z-index: 1001; animation: slideIn 0.3s ease;
        `;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 4000);
    }

    runAllTests() {
        // Get selected test suites
        const suiteCheckboxes = document.querySelectorAll('#test-suites-list input[type="checkbox"]:checked');
        const selectedSuites = Array.from(suiteCheckboxes).map(cb => cb.dataset.suite);

        if (selectedSuites.length === 0) {
            alert('Please select at least one test suite');
            return;
        }

        // Update button state
        const btn = document.getElementById('run-all-tests-btn');
        btn.textContent = 'Running...';
        btn.disabled = true;

        // Track that we're waiting for results
        this._testsRunning = true;

        // Send test request via WebSocket - real results will arrive via onMessage handler
        this.send({
            type: 'run_tests',
            suites: selectedSuites,
            agent_id: this.agentId
        });

        // Timeout safety - re-enable button after 60 seconds if no response
        setTimeout(() => {
            if (this._testsRunning) {
                btn.textContent = 'Run All Tests';
                btn.disabled = false;
                this._testsRunning = false;
            }
        }, 60000);
    }

    async fetchPreviousTestResults() {
        // Fetch previous test results on page load for persistence
        try {
            const response = await fetch('/api/tests/results?limit=50');
            if (response.ok) {
                const data = await response.json();
                if (data.results && data.results.length > 0) {
                    this.updateTestResults(data.results);
                }
            }
        } catch (err) {
            console.log('No previous test results available:', err.message);
        }
    }

    generateMockTestResults(suites) {
        // Detailed test definitions with descriptions and failure reasons
        const testDefinitions = {
            'common_connectivity': [
                { name: 'Ping Loopback', desc: 'Verify loopback interface responds to ICMP', failReason: 'No response from loopback address' },
                { name: 'Ping Neighbors', desc: 'Verify all configured neighbors are reachable', failReason: 'Neighbor 10.0.0.2 unreachable - no route' },
                { name: 'TCP Port Check', desc: 'Verify critical TCP ports are listening', failReason: 'Port 179 (BGP) not listening' },
                { name: 'DNS Resolution', desc: 'Verify DNS queries resolve correctly', failReason: 'DNS timeout - no response from server' }
            ],
            'common_interface': [
                { name: 'Interface Up', desc: 'Verify all configured interfaces are up', failReason: 'eth1 is admin down' },
                { name: 'IP Assigned', desc: 'Verify interfaces have assigned IPs', failReason: 'eth2 missing IPv4 address' },
                { name: 'MTU Check', desc: 'Verify interface MTU matches expected', failReason: 'eth0 MTU 1400, expected 1500' },
                { name: 'Duplex/Speed', desc: 'Verify duplex and speed settings', failReason: 'eth1 half-duplex detected' }
            ],
            'common_resource': [
                { name: 'CPU Usage', desc: 'Verify CPU usage below threshold (80%)', failReason: 'CPU at 92% - exceeds threshold' },
                { name: 'Memory Usage', desc: 'Verify memory usage below threshold (85%)', failReason: 'Memory at 89% - exceeds threshold' },
                { name: 'Disk Space', desc: 'Verify disk space available (>10%)', failReason: 'Root partition at 95% capacity' },
                { name: 'Process Count', desc: 'Verify critical processes running', failReason: 'ospfd process not found' },
                { name: 'Uptime Check', desc: 'Verify system uptime reasonable', failReason: 'System rebooted 5 min ago unexpectedly' }
            ],
            'protocol_ospf': [
                { name: 'OSPF Neighbors Full', desc: 'Verify all OSPF neighbors reach FULL state', failReason: 'Neighbor 1.1.1.1 stuck in EXSTART' },
                { name: 'LSDB Consistent', desc: 'Verify LSDB is synchronized with neighbors', failReason: 'LSA age mismatch with neighbor' },
                { name: 'SPF Converged', desc: 'Verify SPF calculation completed', failReason: 'SPF running longer than 30s' },
                { name: 'Routes Installed', desc: 'Verify OSPF routes in routing table', failReason: 'Expected route 10.0.0.0/24 missing' },
                { name: 'Hello Timer', desc: 'Verify hello interval matches config', failReason: 'Hello mismatch: local 10s, neighbor 30s' }
            ],
            'protocol_bgp': [
                { name: 'BGP Sessions Up', desc: 'Verify all BGP sessions established', failReason: 'Peer 192.168.1.1 in IDLE state' },
                { name: 'Prefixes Received', desc: 'Verify expected prefixes received', failReason: 'Expected 100 prefixes, got 0' },
                { name: 'Prefixes Advertised', desc: 'Verify routes advertised to peers', failReason: 'No routes advertised to peer AS65001' },
                { name: 'AS Path Valid', desc: 'Verify AS paths are valid', failReason: 'AS loop detected in path' },
                { name: 'Route Refresh', desc: 'Verify route refresh capability', failReason: 'Route refresh not supported by peer' }
            ],
            'protocol_isis': [
                { name: 'IS-IS Adjacency', desc: 'Verify IS-IS adjacencies are up', failReason: 'Adjacency on eth0 is DOWN' },
                { name: 'LSP Exchange', desc: 'Verify LSP database synchronized', failReason: 'Missing LSP from system 0000.0000.0002' },
                { name: 'Metric Correct', desc: 'Verify interface metrics configured', failReason: 'Wide metric not enabled' }
            ],
            'protocol_mpls': [
                { name: 'LDP Sessions', desc: 'Verify LDP sessions operational', failReason: 'LDP session to 10.0.0.3 down' },
                { name: 'Label Binding', desc: 'Verify label bindings received', failReason: 'No label for prefix 10.10.0.0/24' },
                { name: 'LFIB Entries', desc: 'Verify forwarding table populated', failReason: 'LFIB missing entry for label 1000' }
            ],
            'protocol_vxlan': [
                { name: 'VTEP Reachable', desc: 'Verify remote VTEPs are reachable', failReason: 'VTEP 10.255.0.2 unreachable' },
                { name: 'VNI Mapping', desc: 'Verify VNI to VLAN mapping correct', failReason: 'VNI 10010 not mapped to VLAN' },
                { name: 'MAC Learning', desc: 'Verify MAC addresses learned', failReason: 'No MACs learned on VNI 10010' }
            ],
            'protocol_dhcp': [
                { name: 'Pool Available', desc: 'Verify DHCP pool has addresses', failReason: 'Pool exhausted - 0 addresses left' },
                { name: 'Lease Valid', desc: 'Verify leases are being assigned', failReason: 'No leases assigned in last hour' },
                { name: 'Options Correct', desc: 'Verify DHCP options configured', failReason: 'Option 3 (gateway) not set' }
            ],
            'protocol_dns': [
                { name: 'Zone Loaded', desc: 'Verify DNS zones loaded correctly', failReason: 'Zone example.com failed to load' },
                { name: 'Forward Lookup', desc: 'Verify forward DNS resolution', failReason: 'Resolution timeout for host.example.com' },
                { name: 'Reverse Lookup', desc: 'Verify reverse DNS resolution', failReason: 'No PTR record for 10.0.0.1' }
            ]
        };

        const results = [];
        const statusWeights = { passed: 0.7, failed: 0.2, skipped: 0.1 };

        for (const suite of suites) {
            const tests = testDefinitions[suite] || [];
            for (const test of tests) {
                // Weighted random status
                const rand = Math.random();
                let status;
                if (rand < statusWeights.passed) status = 'passed';
                else if (rand < statusWeights.passed + statusWeights.failed) status = 'failed';
                else status = 'skipped';

                results.push({
                    test_id: `${suite}_${test.name.toLowerCase().replace(/\s+/g, '_')}`,
                    test_name: test.name,
                    description: test.desc,
                    suite_name: suite.replace('common_', '').replace('protocol_', '').replace(/_/g, ' '),
                    status: status,
                    failure_reason: status === 'failed' ? test.failReason : null,
                    duration: (Math.random() * 2 + 0.1).toFixed(2) + 's',
                    timestamp: new Date().toLocaleTimeString()
                });
            }
        }
        return results;
    }

    updateTestResults(results) {
        const table = document.getElementById('test-results-table');
        if (!table) return;

        if (results.length === 0) {
            table.innerHTML = '<tr><td colspan="5" class="empty-state">No test results yet. Run tests to see results.</td></tr>';
            return;
        }

        // Calculate summary
        const passed = results.filter(r => r.status === 'passed').length;
        const failed = results.filter(r => r.status === 'failed').length;
        const skipped = results.filter(r => r.status === 'skipped').length;
        const total = results.length;
        const passRate = Math.round((passed / total) * 100);

        // Update metrics
        document.getElementById('testing-suites').textContent = new Set(results.map(r => r.suite_name)).size;
        document.getElementById('testing-last-run').textContent = new Date().toLocaleTimeString();
        document.getElementById('testing-pass-rate').innerHTML = `${passRate}<span class="metric-unit">%</span>`;

        // Build table HTML with expandable rows for details
        let html = '';
        for (const r of results) {
            const description = r.description || 'No description available';
            const failureReason = r.failure_reason || '';

            // Main result row
            html += `
                <tr data-status="${r.status}" class="test-result-row" onclick="this.classList.toggle('expanded'); this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'table-row' ? 'none' : 'table-row';">
                    <td>
                        <strong>${r.test_name}</strong>
                        <span style="color: var(--text-secondary); font-size: 0.75rem; display: block; margin-top: 2px;">
                            ${description}
                        </span>
                    </td>
                    <td>${r.suite_name}</td>
                    <td><span class="status-badge ${r.status}">${r.status}</span></td>
                    <td>${r.duration}</td>
                    <td>${r.timestamp}</td>
                </tr>
            `;

            // Detail row (hidden by default, shown on click)
            if (r.status === 'failed' && failureReason) {
                html += `
                    <tr class="test-detail-row" style="display: none;">
                        <td colspan="5" style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid var(--accent-red); padding: 12px 20px;">
                            <strong style="color: var(--accent-red);">Failure Reason:</strong>
                            <span style="color: var(--text-primary); margin-left: 8px;">${failureReason}</span>
                        </td>
                    </tr>
                `;
            } else if (r.status === 'skipped') {
                html += `
                    <tr class="test-detail-row" style="display: none;">
                        <td colspan="5" style="background: rgba(250, 204, 21, 0.1); border-left: 3px solid var(--accent-yellow); padding: 12px 20px;">
                            <strong style="color: var(--accent-yellow);">Skipped:</strong>
                            <span style="color: var(--text-primary); margin-left: 8px;">Test skipped - prerequisites not met or not applicable</span>
                        </td>
                    </tr>
                `;
            } else {
                html += `
                    <tr class="test-detail-row" style="display: none;">
                        <td colspan="5" style="background: rgba(74, 222, 128, 0.1); border-left: 3px solid var(--accent-green); padding: 12px 20px;">
                            <strong style="color: var(--accent-green);">Passed:</strong>
                            <span style="color: var(--text-primary); margin-left: 8px;">Test completed successfully - all assertions passed</span>
                        </td>
                    </tr>
                `;
            }
        }

        // Add summary row at the top
        const summaryHtml = `
            <tr style="background: var(--bg-tertiary);">
                <td colspan="5" style="padding: 12px; font-size: 0.9rem;">
                    <strong>Summary:</strong>
                    <span style="color: var(--accent-green); margin-left: 15px;">${passed} passed</span>
                    <span style="color: var(--accent-red); margin-left: 15px;">${failed} failed</span>
                    <span style="color: var(--accent-yellow); margin-left: 15px;">${skipped} skipped</span>
                    <span style="color: var(--text-secondary); margin-left: 15px;">(${total} total)</span>
                    <span style="color: var(--text-secondary); float: right; font-size: 0.8rem;">Click a row for details</span>
                </td>
            </tr>
        `;

        table.innerHTML = summaryHtml + html;

        // Store results for filtering
        this.testResults = results;
    }

    filterTestResults(filter) {
        const rows = document.querySelectorAll('#test-results-table tr.test-result-row');
        rows.forEach(row => {
            const detailRow = row.nextElementSibling;
            if (filter === 'all') {
                row.style.display = '';
                // Keep detail rows hidden unless explicitly expanded
            } else {
                const matchesFilter = row.dataset.status === filter;
                row.style.display = matchesFilter ? '' : 'none';
                // Also hide the detail row if the main row is hidden
                if (detailRow && detailRow.classList.contains('test-detail-row')) {
                    detailRow.style.display = 'none';
                }
            }
        });
    }

    saveTestSchedule() {
        const interval = document.getElementById('schedule-interval').value;
        const onChangeEnabled = document.getElementById('schedule-on-change').checked;

        // Send schedule configuration via WebSocket
        this.send({
            type: 'update_test_schedule',
            agent_id: this.agentId,
            interval_minutes: parseInt(interval),
            run_on_change: onChangeEnabled
        });

        // Update next run display
        if (interval > 0) {
            const nextRun = new Date(Date.now() + parseInt(interval) * 60000);
            document.getElementById('testing-next-run').textContent = nextRun.toLocaleTimeString();
        } else {
            document.getElementById('testing-next-run').textContent = '--';
        }

        // Show confirmation
        const btn = document.getElementById('save-schedule-btn');
        const originalText = btn.textContent;
        btn.textContent = 'Saved!';
        setTimeout(() => btn.textContent = originalText, 2000);
    }

    updateTestingData(testing) {
        if (!testing) return;

        document.getElementById('testing-suites').textContent = testing.suite_count || 0;
        document.getElementById('testing-last-run').textContent = testing.last_run || 'Never';
        document.getElementById('testing-pass-rate').innerHTML = `${testing.pass_rate || '--'}<span class="metric-unit">%</span>`;
        document.getElementById('testing-next-run').textContent = testing.next_run || '--';

        // Update protocol-specific test suites based on active protocols
        this.updateProtocolTestSuites();

        if (testing.results) {
            this.updateTestResults(testing.results);
        }
    }

    updateProtocolTestSuites() {
        const container = document.getElementById('protocol-test-suites');
        if (!container) return;

        let html = '';

        // Add test suites for active protocols
        if (this.protocols.ospf) {
            html += this.createTestSuiteItem('ospf', 'OSPF Tests', 5);
        }
        if (this.protocols.bgp) {
            html += this.createTestSuiteItem('bgp', 'BGP Tests', 5);
        }
        if (this.protocols.isis) {
            html += this.createTestSuiteItem('isis', 'IS-IS Tests', 3);
        }
        if (this.protocols.vxlan) {
            html += this.createTestSuiteItem('vxlan', 'VXLAN/EVPN Tests', 3);
        }
        if (this.protocols.mpls) {
            html += this.createTestSuiteItem('mpls', 'MPLS/LDP Tests', 3);
        }
        if (this.protocols.dhcp) {
            html += this.createTestSuiteItem('dhcp', 'DHCP Tests', 3);
        }
        if (this.protocols.dns) {
            html += this.createTestSuiteItem('dns', 'DNS Tests', 3);
        }

        container.innerHTML = html;
    }

    createTestSuiteItem(suiteId, suiteName, testCount) {
        return `
            <div class="test-suite-item">
                <label class="test-suite-checkbox">
                    <input type="checkbox" checked data-suite="protocol_${suiteId}">
                    <span class="checkmark"></span>
                    ${suiteName}
                </label>
                <span class="test-count">${testCount} tests</span>
            </div>
        `;
    }

    // ==================== GAIT TAB ====================
    setupGAITEvents() {
        // Search input
        const searchInput = document.getElementById('gait-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => this.filterGAITHistory(e.target.value));
        }

        // Filter dropdown
        const filterSelect = document.getElementById('gait-filter');
        if (filterSelect) {
            filterSelect.addEventListener('change', (e) => this.filterGAITByType(e.target.value));
        }

        // Export button
        const exportBtn = document.getElementById('export-gait-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportGAITLogs());
        }
    }

    updateGAITData(gait) {
        if (!gait) return;

        document.getElementById('gait-turns').textContent = gait.total_turns || 0;
        document.getElementById('gait-user-msgs').textContent = gait.user_messages || 0;
        document.getElementById('gait-agent-msgs').textContent = gait.agent_messages || 0;
        document.getElementById('gait-actions').textContent = gait.actions_taken || 0;

        if (gait.history) {
            this.renderGAITTimeline(gait.history);
        }
    }

    renderGAITTimeline(history) {
        const timeline = document.getElementById('gait-timeline');
        if (!timeline) return;

        if (!history || history.length === 0) {
            timeline.innerHTML = `
                <div class="timeline-item user">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="timeline-sender">System</span>
                            <span class="timeline-time">--</span>
                        </div>
                        <div class="timeline-message">No conversation history available. GAIT tracking will record all interactions.</div>
                    </div>
                </div>
            `;
            return;
        }

        let html = '';
        for (const item of history) {
            const type = item.type || 'user';
            const sender = item.sender || (type === 'user' ? 'User' : type === 'agent' ? 'Agent' : type === 'action' ? 'Action' : 'System');
            const time = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : '--';
            const message = item.message || item.text || '';
            const commitId = item.commit_id || '';

            // Sender icon based on type
            const senderIcon = type === 'user' ? '👤' : type === 'agent' ? '🤖' : type === 'action' ? '⚡' : '📋';

            // Commit ID badge if available
            const commitBadge = commitId ? `<span class="commit-badge" title="Commit ID: ${commitId}">${commitId.substring(0, 8)}</span>` : '';

            html += `
                <div class="timeline-item ${type}" data-type="${type}" data-commit="${commitId}">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="timeline-sender">${senderIcon} ${sender}</span>
                            ${commitBadge}
                            <span class="timeline-time">${time}</span>
                        </div>
                        <div class="timeline-message">${this.escapeHtml(message)}</div>
                    </div>
                </div>
            `;
        }
        timeline.innerHTML = html;

        // Store history for filtering
        this.gaitHistory = history;
    }

    filterGAITHistory(searchTerm) {
        const items = document.querySelectorAll('#gait-timeline .timeline-item');
        const term = searchTerm.toLowerCase();

        items.forEach(item => {
            const message = item.querySelector('.timeline-message').textContent.toLowerCase();
            item.style.display = message.includes(term) ? '' : 'none';
        });
    }

    filterGAITByType(type) {
        const items = document.querySelectorAll('#gait-timeline .timeline-item');

        items.forEach(item => {
            if (type === 'all') {
                item.style.display = '';
            } else {
                item.style.display = item.dataset.type === type ? '' : 'none';
            }
        });
    }

    exportGAITLogs() {
        // Get all timeline items
        const items = document.querySelectorAll('#gait-timeline .timeline-item');
        let logs = [];

        items.forEach(item => {
            logs.push({
                type: item.dataset.type,
                sender: item.querySelector('.timeline-sender').textContent,
                time: item.querySelector('.timeline-time').textContent,
                message: item.querySelector('.timeline-message').textContent
            });
        });

        // Create downloadable JSON file
        const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `gait-logs-${this.agentId}-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ==================== MARKMAP TAB ====================
    setupMarkmapEvents() {
        this.markmapAutoRefresh = true;
        this.markmapRefreshInterval = null;
        this.markmapInstance = null;
        this.markmapLibraryLoaded = false;
        this.markmapLastRefresh = null;
        this.markmapRefreshIntervalMs = 5 * 60 * 1000; // 5 minutes default

        // Load markmap library dynamically
        this.loadMarkmapLibrary();

        // Auto-refresh checkbox
        const autoRefreshCb = document.getElementById('markmap-auto-refresh');
        if (autoRefreshCb) {
            autoRefreshCb.addEventListener('change', (e) => {
                this.markmapAutoRefresh = e.target.checked;
                if (this.markmapAutoRefresh) {
                    this.startMarkmapAutoRefresh();
                } else {
                    this.stopMarkmapAutoRefresh();
                }
            });
        }

        // Refresh interval selector (similar to testing scheduler)
        const intervalSelect = document.getElementById('markmap-refresh-interval');
        if (intervalSelect) {
            intervalSelect.addEventListener('change', (e) => {
                const minutes = parseInt(e.target.value) || 5;
                this.markmapRefreshIntervalMs = minutes * 60 * 1000;
                if (this.markmapAutoRefresh) {
                    this.stopMarkmapAutoRefresh();
                    this.startMarkmapAutoRefresh();
                }
            });
        }

        // Refresh button
        const refreshBtn = document.getElementById('markmap-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshMarkmap());
        }

        // Export button
        const exportBtn = document.getElementById('markmap-export-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportMarkmapSVG());
        }

        // Fullscreen button
        const fullscreenBtn = document.getElementById('markmap-fullscreen-btn');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleMarkmapFullscreen());
        }

        // Initial render after library loads
        this.waitForMarkmapLibrary().then(() => {
            this.refreshMarkmap();
        });

        // Start scheduled auto-refresh (5 minute interval like testing)
        if (this.markmapAutoRefresh) {
            this.startMarkmapAutoRefresh();
        }
    }

    loadMarkmapLibrary() {
        // Check if already loaded - try different variable names
        if (this._checkMarkmapLoaded()) {
            this.markmapLibraryLoaded = true;
            return Promise.resolve();
        }

        // Load d3 first, then markmap
        return new Promise((resolve, reject) => {
            // Load D3
            if (typeof d3 === 'undefined') {
                const d3Script = document.createElement('script');
                d3Script.src = 'https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js';
                d3Script.onload = () => this.loadMarkmapScripts(resolve, reject);
                d3Script.onerror = () => reject(new Error('Failed to load D3'));
                document.head.appendChild(d3Script);
            } else {
                this.loadMarkmapScripts(resolve, reject);
            }
        });
    }

    _checkMarkmapLoaded() {
        // Check various ways markmap might be exposed
        // Log for debugging
        console.log('Checking markmap globals:', {
            markmap: typeof markmap,
            'window.markmap': typeof window.markmap,
            markmapLib: typeof markmapLib,
            markmapView: typeof markmapView,
            'window.markmapLib': typeof window.markmapLib
        });

        // Check markmap global
        if (typeof markmap !== 'undefined' && markmap) {
            if (markmap.Transformer && markmap.Markmap) return true;
            // Some versions expose at markmap.markmap
            if (markmap.markmap && markmap.markmap.Transformer) return true;
        }

        // Check window.markmap
        if (typeof window.markmap !== 'undefined' && window.markmap) {
            if (window.markmap.Transformer && window.markmap.Markmap) return true;
        }

        // Check separate lib and view
        if (typeof markmapLib !== 'undefined' && typeof markmapView !== 'undefined') {
            if (markmapLib.Transformer && markmapView.Markmap) return true;
        }

        // Check window versions
        if (typeof window.markmapLib !== 'undefined' && typeof window.markmapView !== 'undefined') {
            if (window.markmapLib.Transformer && window.markmapView.Markmap) return true;
        }

        return false;
    }

    _getMarkmap() {
        // Get the markmap object from wherever it's defined
        if (typeof markmap !== 'undefined' && markmap) {
            if (markmap.Transformer && markmap.Markmap) return markmap;
            if (markmap.markmap && markmap.markmap.Transformer) return markmap.markmap;
        }

        if (typeof window.markmap !== 'undefined' && window.markmap) {
            if (window.markmap.Transformer && window.markmap.Markmap) return window.markmap;
        }

        // Try markmapLib + markmapView combo
        if (typeof markmapLib !== 'undefined' && typeof markmapView !== 'undefined') {
            if (markmapLib.Transformer && markmapView.Markmap) {
                return { Transformer: markmapLib.Transformer, Markmap: markmapView.Markmap };
            }
        }

        // Window versions
        if (typeof window.markmapLib !== 'undefined' && typeof window.markmapView !== 'undefined') {
            if (window.markmapLib.Transformer && window.markmapView.Markmap) {
                return { Transformer: window.markmapLib.Transformer, Markmap: window.markmapView.Markmap };
            }
        }

        return null;
    }

    loadMarkmapScripts(resolve, reject) {
        // Try unpkg first as it's more reliable for browser bundles
        const libScript = document.createElement('script');
        libScript.src = 'https://unpkg.com/markmap-lib@0.15.4/dist/browser/index.js';
        libScript.onload = () => {
            const viewScript = document.createElement('script');
            viewScript.src = 'https://unpkg.com/markmap-view@0.15.4/dist/browser/index.js';
            viewScript.onload = () => {
                setTimeout(() => {
                    if (this._checkMarkmapLoaded()) {
                        this.markmapLibraryLoaded = true;
                        console.log('Markmap library loaded successfully');
                        resolve();
                    } else {
                        console.warn('Markmap scripts loaded but globals not found, trying fallback');
                        this.loadMarkmapFallback(resolve, reject);
                    }
                }, 200);
            };
            viewScript.onerror = () => {
                console.warn('markmap-view failed, trying fallback');
                this.loadMarkmapFallback(resolve, reject);
            };
            document.head.appendChild(viewScript);
        };
        libScript.onerror = () => {
            console.warn('markmap-lib failed, trying fallback');
            this.loadMarkmapFallback(resolve, reject);
        };
        document.head.appendChild(libScript);
    }

    loadMarkmapFallback(resolve, reject) {
        // Try unpkg CDN as fallback
        console.log('Trying unpkg CDN for markmap...');

        // Load lib from unpkg
        const libScript = document.createElement('script');
        libScript.src = 'https://unpkg.com/markmap-lib@0.15.4/dist/browser/index.js';
        libScript.onload = () => {
            const viewScript = document.createElement('script');
            viewScript.src = 'https://unpkg.com/markmap-view@0.15.4/dist/browser/index.js';
            viewScript.onload = () => {
                setTimeout(() => {
                    if (this._checkMarkmapLoaded()) {
                        this.markmapLibraryLoaded = true;
                        console.log('Markmap loaded via unpkg fallback');
                        resolve();
                    } else {
                        // Last resort - try the autoloader
                        const autoScript = document.createElement('script');
                        autoScript.src = 'https://cdn.jsdelivr.net/npm/markmap-autoloader@0.15.4';
                        autoScript.onload = () => {
                            setTimeout(() => {
                                if (this._checkMarkmapLoaded()) {
                                    this.markmapLibraryLoaded = true;
                                    console.log('Markmap loaded via autoloader');
                                    resolve();
                                } else {
                                    console.error('All markmap loading methods failed');
                                    reject(new Error('Markmap library failed to expose globals'));
                                }
                            }, 300);
                        };
                        autoScript.onerror = () => reject(new Error('All markmap loading methods failed'));
                        document.head.appendChild(autoScript);
                    }
                }, 200);
            };
            viewScript.onerror = () => reject(new Error('unpkg markmap-view failed'));
            document.head.appendChild(viewScript);
        };
        libScript.onerror = () => reject(new Error('unpkg markmap-lib failed'));
        document.head.appendChild(libScript);
    }

    waitForMarkmapLibrary() {
        return new Promise((resolve) => {
            const check = () => {
                if (this.markmapLibraryLoaded || (typeof markmap !== 'undefined' && markmap.Transformer)) {
                    this.markmapLibraryLoaded = true;
                    resolve();
                } else {
                    setTimeout(check, 100);
                }
            };
            // Also try loading if not already loading
            this.loadMarkmapLibrary().then(resolve).catch(() => {
                // Retry check in case it loaded from elsewhere
                setTimeout(check, 500);
            });
        });
    }

    startMarkmapAutoRefresh() {
        if (this.markmapRefreshInterval) return;

        // Use scheduler-based refresh similar to testing page (5 minute default)
        this.markmapRefreshInterval = setInterval(() => {
            // Refresh when markmap tab is active OR when significant time has passed
            const now = Date.now();
            const shouldRefresh = this.activeProtocol === 'markmap' ||
                                  !this.markmapLastRefresh ||
                                  (now - this.markmapLastRefresh) >= this.markmapRefreshIntervalMs;

            if (shouldRefresh) {
                this.refreshMarkmap();
                this.markmapLastRefresh = now;
                this.updateMarkmapNextRefresh();
            }
        }, Math.min(this.markmapRefreshIntervalMs, 30000)); // Check every 30s or interval, whichever is smaller

        // Update next refresh display
        this.updateMarkmapNextRefresh();
    }

    stopMarkmapAutoRefresh() {
        if (this.markmapRefreshInterval) {
            clearInterval(this.markmapRefreshInterval);
            this.markmapRefreshInterval = null;
        }
    }

    updateMarkmapNextRefresh() {
        const nextRefreshEl = document.getElementById('markmap-next-refresh');
        if (nextRefreshEl && this.markmapAutoRefresh) {
            const nextTime = new Date(Date.now() + this.markmapRefreshIntervalMs);
            nextRefreshEl.textContent = nextTime.toLocaleTimeString();
        } else if (nextRefreshEl) {
            nextRefreshEl.textContent = '--';
        }
    }

    refreshMarkmap() {
        // Generate markdown from current agent state and render locally
        const markdown = this.generateAgentMarkdownState();
        this.renderMarkmap(markdown);

        // Update last refresh timestamp
        const lastRefreshEl = document.getElementById('markmap-last-refresh');
        if (lastRefreshEl) {
            lastRefreshEl.textContent = new Date().toLocaleTimeString();
        }
    }

    renderMarkmap(markdown, retryCount = 0) {
        const svgElement = document.getElementById('markmap-svg');
        if (!svgElement) return;

        // Check if container has valid dimensions (prevents NaN transform errors)
        const rect = svgElement.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            // Container not visible yet, defer rendering (max 10 retries)
            if (retryCount < 10) {
                console.log(`Markmap container not visible, deferring render (attempt ${retryCount + 1}/10)`);
                setTimeout(() => this.renderMarkmap(markdown, retryCount + 1), 500);
            } else {
                console.log('Markmap container not visible after 10 attempts, using fallback');
                this._renderMarkmapFallback(svgElement, markdown, 'Tab not visible - switch to Markmap tab to view');
            }
            return;
        }

        const mm = this._getMarkmap();

        // Check if markmap library is loaded
        if (!this.markmapLibraryLoaded || !mm) {
            // Show loading state with the markdown content as a simple tree view
            this._renderMarkmapFallback(svgElement, markdown, 'Loading mindmap library...');

            // Try loading library again
            this.waitForMarkmapLibrary().then(() => this.refreshMarkmap());
            return;
        }

        try {
            // Clear existing content and instance for fresh render
            svgElement.innerHTML = '';
            this.markmapInstance = null;

            // Transform markdown to markmap data
            const transformer = new mm.Transformer();
            const { root } = transformer.transform(markdown);

            // Create the markmap with dark theme colors
            this.markmapInstance = mm.Markmap.create(svgElement, {
                colorFreezeLevel: 2,
                duration: 500,
                maxWidth: 300,
                zoom: true,
                pan: true,
                color: (node) => {
                    // Custom color scheme for dark theme - check node structure
                    const colors = ['#00bcd4', '#4ade80', '#facc15', '#f97316', '#a78bfa', '#f472b6'];
                    const depth = node.state?.depth ?? node.depth ?? 0;
                    return colors[depth % colors.length];
                }
            }, root);

            // Apply dark theme styles to SVG elements after a short delay
            setTimeout(() => {
                svgElement.querySelectorAll('text').forEach(text => {
                    text.style.fill = '#e0e0e0';
                });
                svgElement.querySelectorAll('path').forEach(path => {
                    if (!path.getAttribute('fill') || path.getAttribute('fill') === 'none') {
                        path.style.stroke = '#546e7a';
                    }
                });
            }, 100);

        } catch (err) {
            console.error('Markmap render error:', err);
            // Show the markdown as a fallback tree view
            this._renderMarkmapFallback(svgElement, markdown, `Render error: ${err.message}`);
        }
    }

    _renderMarkmapFallback(svgElement, markdown, statusMessage) {
        // Render a simple text-based view when library isn't available
        svgElement.innerHTML = '';

        // Create a foreignObject to hold HTML content
        const foreignObj = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        foreignObj.setAttribute('x', '0');
        foreignObj.setAttribute('y', '0');
        foreignObj.setAttribute('width', '100%');
        foreignObj.setAttribute('height', '100%');

        const container = document.createElement('div');
        container.style.cssText = `
            width: 100%;
            height: 100%;
            padding: 20px;
            box-sizing: border-box;
            overflow: auto;
            background: #0d1117;
        `;

        // Status message
        const status = document.createElement('div');
        status.style.cssText = 'color: #00bcd4; margin-bottom: 15px; font-size: 14px;';
        status.textContent = statusMessage;
        container.appendChild(status);

        // Parse markdown into simple tree
        const tree = document.createElement('div');
        tree.style.cssText = 'color: #e0e0e0; font-family: monospace; font-size: 13px; line-height: 1.6;';

        const lines = markdown.split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                const div = document.createElement('div');
                const match = line.match(/^(#{1,6})\s*(.*)$/);
                if (match) {
                    const level = match[1].length;
                    const text = match[2];
                    const colors = ['#00bcd4', '#4ade80', '#facc15', '#f97316', '#a78bfa', '#f472b6'];
                    div.style.cssText = `
                        padding-left: ${(level - 1) * 20}px;
                        color: ${colors[(level - 1) % colors.length]};
                        font-weight: ${level <= 2 ? 'bold' : 'normal'};
                    `;
                    div.textContent = (level > 1 ? '├─ ' : '● ') + text;
                } else {
                    div.style.paddingLeft = '40px';
                    div.textContent = '  ' + line.trim();
                }
                tree.appendChild(div);
            }
        });

        container.appendChild(tree);
        foreignObj.appendChild(container);
        svgElement.appendChild(foreignObj);
    }

    updateMarkmapData(markmap) {
        // If server sends pre-rendered SVG, use it
        if (markmap && markmap.svg) {
            const container = document.getElementById('markmap-svg');
            if (container) {
                container.innerHTML = markmap.svg;
            }
        } else {
            // Otherwise refresh from local state
            this.refreshMarkmap();
        }
    }

    generateAgentMarkdownState() {
        // Generate detailed markdown representation of agent state for markmap
        const agentName = document.getElementById('agent-name').textContent || 'Agent';
        let md = `# ${agentName}\n\n`;

        // Router info
        const routerId = document.getElementById('router-id').textContent;
        if (routerId && routerId !== '--') {
            md += `## Router ID: ${routerId}\n\n`;
        }

        // ==================== INTERFACES SECTION ====================
        const ifTotal = this.interfaceDetails.length || document.getElementById('if-total').textContent || '0';
        const ifUp = this.interfaceDetails.filter(i => (i.status || i.s) === 'up').length;
        const ifDown = parseInt(ifTotal) - ifUp;

        md += `## Interfaces (${ifTotal})\n`;

        if (this.interfaceDetails.length > 0) {
            // Group interfaces by type
            const upInterfaces = this.interfaceDetails.filter(i => (i.status || i.s) === 'up');
            const downInterfaces = this.interfaceDetails.filter(i => (i.status || i.s) !== 'up');

            if (upInterfaces.length > 0) {
                md += `### Up (${upInterfaces.length})\n`;
                for (const iface of upInterfaces) {
                    const name = iface.name || iface.n || iface.id;
                    const type = iface.type || iface.t || 'eth';
                    const addresses = iface.addresses || iface.a || [];
                    const mtu = iface.mtu || 1500;

                    md += `#### ${name}\n`;
                    md += `##### Type: ${this._getInterfaceTypeName(type)}\n`;
                    if (addresses.length > 0) {
                        for (const addr of addresses) {
                            md += `##### IP: ${addr}\n`;
                        }
                    }
                    md += `##### MTU: ${mtu}\n`;
                }
            }

            if (downInterfaces.length > 0) {
                md += `### Down (${downInterfaces.length})\n`;
                for (const iface of downInterfaces) {
                    const name = iface.name || iface.n || iface.id;
                    md += `#### ${name} (disabled)\n`;
                }
            }
        } else {
            md += `### Up: ${ifUp}\n`;
            md += `### Down: ${ifDown}\n`;
        }

        // ==================== PROTOCOLS SECTION ====================
        const protocolCount = Object.keys(this.protocols).length;
        if (protocolCount > 0) {
            md += `## Protocols (${protocolCount})\n`;

            for (const [proto, data] of Object.entries(this.protocols)) {
                md += `### ${proto.toUpperCase()}\n`;

                if (proto === 'ospf' && data) {
                    md += `#### Summary\n`;
                    md += `##### Neighbors: ${data.neighbors || 0}\n`;
                    md += `##### Full: ${data.full_neighbors || 0}\n`;
                    md += `##### LSDB: ${data.lsdb_size || 0} LSAs\n`;
                    md += `##### Routes: ${data.routes || 0}\n`;

                    // OSPF Neighbor Details
                    if (this.ospfNeighborDetails.length > 0) {
                        md += `#### Neighbors\n`;
                        for (const n of this.ospfNeighborDetails) {
                            const stateIcon = n.is_full ? '✓' : '○';
                            md += `##### ${stateIcon} ${n.router_id}\n`;
                            md += `###### IP: ${n.ip}\n`;
                            md += `###### State: ${n.state}\n`;
                            if (n.dr) md += `###### DR: ${n.dr}\n`;
                        }
                    }

                    // OSPF Routes (top 10)
                    if (this.ospfRoutes.length > 0) {
                        md += `#### Routes (${this.ospfRoutes.length})\n`;
                        for (const r of this.ospfRoutes.slice(0, 10)) {
                            md += `##### ${r.prefix}\n`;
                            md += `###### Next Hop: ${r.next_hop || 'Direct'}\n`;
                            md += `###### Cost: ${r.cost}\n`;
                            if (r.type) md += `###### Type: ${r.type}\n`;
                        }
                        if (this.ospfRoutes.length > 10) {
                            md += `##### ... and ${this.ospfRoutes.length - 10} more\n`;
                        }
                    }

                } else if (proto === 'bgp' && data) {
                    md += `#### Summary\n`;
                    md += `##### Local AS: ${data.local_as || '-'}\n`;
                    md += `##### Total Peers: ${data.total_peers || 0}\n`;
                    md += `##### Established: ${data.established_peers || 0}\n`;
                    md += `##### Prefixes In: ${data.loc_rib_routes || 0}\n`;
                    md += `##### Prefixes Out: ${data.advertised_routes || 0}\n`;

                    // BGP Peer Details
                    if (this.bgpPeerDetails.length > 0) {
                        md += `#### Peers\n`;
                        for (const p of this.bgpPeerDetails) {
                            const stateIcon = p.state === 'Established' ? '✓' : '○';
                            md += `##### ${stateIcon} AS ${p.remote_as}\n`;
                            md += `###### IP: ${p.ip}\n`;
                            md += `###### State: ${p.state}\n`;
                            md += `###### Type: ${p.peer_type}\n`;
                        }
                    }

                    // BGP Routes (top 10)
                    if (this.bgpRoutes.length > 0) {
                        md += `#### Routes (${this.bgpRoutes.length})\n`;
                        for (const r of this.bgpRoutes.slice(0, 10)) {
                            md += `##### ${r.prefix}\n`;
                            md += `###### Next Hop: ${r.next_hop}\n`;
                            if (r.as_path) md += `###### AS Path: ${r.as_path}\n`;
                            if (r.origin) md += `###### Origin: ${r.origin}\n`;
                        }
                        if (this.bgpRoutes.length > 10) {
                            md += `##### ... and ${this.bgpRoutes.length - 10} more\n`;
                        }
                    }

                } else if (proto === 'isis' && data) {
                    md += `#### Summary\n`;
                    md += `##### Adjacencies: ${data.adjacencies || 0}\n`;
                    md += `##### LSPs: ${data.lsp_count || 0}\n`;
                    md += `##### Level: ${data.level || 'L1/L2'}\n`;
                    md += `##### Area: ${data.area || '-'}\n`;

                    // IS-IS Adjacency Details
                    if (this.isisAdjacencies.length > 0) {
                        md += `#### Adjacencies\n`;
                        for (const a of this.isisAdjacencies) {
                            const stateIcon = a.state === 'Up' ? '✓' : '○';
                            md += `##### ${stateIcon} ${a.system_id}\n`;
                            md += `###### Interface: ${a.interface}\n`;
                            md += `###### Level: ${a.level}\n`;
                            md += `###### Hold Time: ${a.hold_time}s\n`;
                        }
                    }

                } else if (proto === 'mpls' && data) {
                    md += `#### Summary\n`;
                    md += `##### LFIB Entries: ${data.lfib_entries || 0}\n`;
                    md += `##### Labels Allocated: ${data.labels_allocated || 0}\n`;
                    md += `##### LDP Neighbors: ${data.ldp_neighbors || 0}\n`;

                } else if (proto === 'vxlan' && data) {
                    md += `#### Summary\n`;
                    md += `##### VNIs: ${data.vni_count || 0}\n`;
                    md += `##### VTEPs: ${data.vtep_count || 0}\n`;
                    md += `##### MAC Entries: ${data.mac_entries || 0}\n`;

                } else if (proto === 'dhcp' && data) {
                    md += `#### Summary\n`;
                    md += `##### Pools: ${data.pool_count || 0}\n`;
                    md += `##### Active Leases: ${data.active_leases || 0}\n`;

                } else if (proto === 'dns' && data) {
                    md += `#### Summary\n`;
                    md += `##### Zones: ${data.zone_count || 0}\n`;
                    md += `##### Records: ${data.record_count || 0}\n`;
                }
            }
        } else {
            md += `## Protocols\n`;
            md += `### No active protocols\n`;
        }

        // ==================== STATUS SECTION ====================
        const wsStatus = document.getElementById('connection-text').textContent || 'Unknown';
        md += `## Status\n`;
        md += `### WebSocket: ${wsStatus}\n`;
        md += `### Last Update: ${new Date().toLocaleTimeString()}\n`;

        return md;
    }

    _getInterfaceTypeName(type) {
        const typeNames = {
            'eth': 'Ethernet',
            'lo': 'Loopback',
            'vlan': 'VLAN',
            'tun': 'Tunnel',
            'sub': 'Sub-Interface',
            'bond': 'Bond',
            'bridge': 'Bridge'
        };
        return typeNames[type] || type;
    }

    exportMarkmapSVG() {
        const svg = document.getElementById('markmap-svg');
        if (!svg) return;

        const svgData = new XMLSerializer().serializeToString(svg);
        const blob = new Blob([svgData], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `agent-state-${this.agentId}-${new Date().toISOString().split('T')[0]}.svg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    toggleMarkmapFullscreen() {
        const container = document.getElementById('markmap-container');
        const btn = document.getElementById('markmap-fullscreen-btn');

        if (container.classList.contains('fullscreen')) {
            container.classList.remove('fullscreen');
            btn.textContent = 'Fullscreen';
            document.body.style.overflow = '';
        } else {
            container.classList.add('fullscreen');
            btn.textContent = 'Exit Fullscreen';
            document.body.style.overflow = 'hidden';
        }
    }

    // ==================== CHAT METHODS ====================
    setupChat() {
        this.chatMessageCount = { sent: 0, received: 0 };

        const chatInput = document.getElementById('chat-input');
        const chatSendBtn = document.getElementById('chat-send-btn');

        if (chatInput && chatSendBtn) {
            // Send on button click
            chatSendBtn.addEventListener('click', () => this.sendChatMessage());

            // Send on Enter key
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendChatMessage();
                }
            });
        }
    }

    async sendChatMessage() {
        const chatInput = document.getElementById('chat-input');
        const chatMessages = document.getElementById('chat-messages');
        const chatSendBtn = document.getElementById('chat-send-btn');

        if (!chatInput || !chatMessages) return;

        const message = chatInput.value.trim();
        if (!message) return;

        // Disable input while processing
        chatInput.disabled = true;
        chatSendBtn.disabled = true;

        // Add user message to chat
        this.addChatMessage(message, 'user');
        chatInput.value = '';

        // Update counter
        this.chatMessageCount.sent++;
        document.getElementById('chat-sent').textContent = this.chatMessageCount.sent;

        try {
            // Send to API
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });

            const data = await response.json();

            if (data.response) {
                this.addChatMessage(data.response, 'assistant');
                this.chatMessageCount.received++;
                document.getElementById('chat-received').textContent = this.chatMessageCount.received;
            } else if (data.error) {
                this.addChatMessage(`Error: ${data.error}`, 'system');
            }
        } catch (error) {
            this.addChatMessage(`Failed to send message: ${error.message}`, 'system');
        } finally {
            // Re-enable input
            chatInput.disabled = false;
            chatSendBtn.disabled = false;
            chatInput.focus();
        }
    }

    addChatMessage(text, type) {
        const chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}`;
        messageDiv.innerHTML = this.formatChatMessage(text);

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    formatChatMessage(text) {
        // Basic markdown-like formatting
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    // ==================== METRICS TAB (Prometheus MCP) ====================
    async fetchMetrics() {
        try {
            const response = await fetch(`/api/metrics?agent_id=${this.agentId}`);
            if (response.ok) {
                const data = await response.json();
                this.updateMetricsDisplay(data);
            }
        } catch (error) {
            console.error('Failed to fetch metrics:', error);
        }
    }

    updateMetricsDisplay(data) {
        const metrics = data.metrics || {};

        // Update summary cards
        const totalMetrics = Object.keys(metrics).length;
        document.getElementById('metrics-total').textContent = totalMetrics;
        document.getElementById('metrics-gauges').textContent =
            Object.values(metrics).filter(m => m.type === 'gauge').length;
        document.getElementById('metrics-counters').textContent =
            Object.values(metrics).filter(m => m.type === 'counter').length;
        document.getElementById('metrics-last-update').textContent = new Date().toLocaleTimeString();

        // Update metrics table
        const table = document.getElementById('metrics-table');
        if (!table) return;

        if (totalMetrics === 0) {
            table.innerHTML = '<tr><td colspan="5" class="empty-state">No metrics available. Agent metrics will appear here when enabled.</td></tr>';
            return;
        }

        let html = '';
        for (const [name, metric] of Object.entries(metrics)) {
            const type = metric.type || 'gauge';
            const values = metric.values || [];
            const help = metric.help || '-';

            for (const v of values.slice(0, 10)) {
                const labels = Object.entries(v.labels || {})
                    .filter(([k]) => !['agent_id', 'router_id'].includes(k))
                    .map(([k, val]) => `${k}="${val}"`)
                    .join(', ');

                html += `
                    <tr>
                        <td>${name}</td>
                        <td><span class="status-badge ${type}">${type}</span></td>
                        <td style="font-family: monospace; color: var(--accent-cyan);">${v.value.toFixed(2)}</td>
                        <td style="font-size: 0.8rem; color: var(--text-secondary);">${labels || '-'}</td>
                        <td style="font-size: 0.8rem;">${help}</td>
                    </tr>
                `;
            }
        }
        table.innerHTML = html;

        // Update interface metrics chart
        this.updateInterfaceMetricsChart(metrics);

        // Update protocol metrics chart
        this.updateProtocolMetricsChart(metrics);
    }

    updateInterfaceMetricsChart(metrics) {
        const container = document.getElementById('interface-metrics-chart');
        if (!container) return;

        // Extract interface metrics
        const rxBytes = metrics['interface_rx_bytes_total']?.values || [];
        const txBytes = metrics['interface_tx_bytes_total']?.values || [];

        if (rxBytes.length === 0 && txBytes.length === 0) {
            container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 20px;">No interface traffic data available</div>';
            return;
        }

        // Create simple bar chart
        let html = '<div style="display: flex; flex-direction: column; gap: 8px; padding: 10px;">';

        for (const rx of rxBytes.slice(0, 5)) {
            const iface = rx.labels?.interface || 'unknown';
            const rxVal = rx.value;
            const tx = txBytes.find(t => t.labels?.interface === iface);
            const txVal = tx?.value || 0;
            const maxVal = Math.max(rxVal, txVal, 1);

            html += `
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.85rem; margin-bottom: 4px;">${iface}</div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="width: 30px; font-size: 0.75rem; color: var(--accent-cyan);">RX</span>
                        <div style="flex: 1; background: var(--bg-secondary); height: 16px; border-radius: 4px; overflow: hidden;">
                            <div style="width: ${(rxVal/maxVal*100).toFixed(1)}%; height: 100%; background: var(--accent-cyan);"></div>
                        </div>
                        <span style="width: 80px; font-size: 0.75rem; text-align: right;">${this.formatBytes(rxVal)}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; margin-top: 2px;">
                        <span style="width: 30px; font-size: 0.75rem; color: var(--accent-green);">TX</span>
                        <div style="flex: 1; background: var(--bg-secondary); height: 16px; border-radius: 4px; overflow: hidden;">
                            <div style="width: ${(txVal/maxVal*100).toFixed(1)}%; height: 100%; background: var(--accent-green);"></div>
                        </div>
                        <span style="width: 80px; font-size: 0.75rem; text-align: right;">${this.formatBytes(txVal)}</span>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;
    }

    updateProtocolMetricsChart(metrics) {
        const container = document.getElementById('protocol-metrics-chart');
        if (!container) return;

        // Extract protocol metrics
        const protocolMetrics = [];

        if (metrics['ospf_neighbors_total']) {
            protocolMetrics.push({ name: 'OSPF Neighbors', value: metrics['ospf_neighbors_total'].values[0]?.value || 0, color: 'var(--accent-cyan)' });
        }
        if (metrics['ospf_routes_total']) {
            protocolMetrics.push({ name: 'OSPF Routes', value: metrics['ospf_routes_total'].values[0]?.value || 0, color: 'var(--accent-cyan)' });
        }
        if (metrics['bgp_peers_established']) {
            protocolMetrics.push({ name: 'BGP Peers', value: metrics['bgp_peers_established'].values[0]?.value || 0, color: 'var(--accent-purple)' });
        }
        if (metrics['bgp_loc_rib_routes']) {
            protocolMetrics.push({ name: 'BGP Routes', value: metrics['bgp_loc_rib_routes'].values[0]?.value || 0, color: 'var(--accent-purple)' });
        }
        if (metrics['isis_adjacencies_total']) {
            protocolMetrics.push({ name: 'ISIS Adjacencies', value: metrics['isis_adjacencies_total'].values[0]?.value || 0, color: 'var(--accent-yellow)' });
        }

        if (protocolMetrics.length === 0) {
            container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 20px;">No protocol metrics available</div>';
            return;
        }

        const maxVal = Math.max(...protocolMetrics.map(m => m.value), 1);

        let html = '<div style="display: flex; flex-direction: column; gap: 12px; padding: 10px;">';
        for (const m of protocolMetrics) {
            html += `
                <div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                        <span>${m.name}</span>
                        <span style="color: ${m.color}; font-weight: bold;">${m.value}</span>
                    </div>
                    <div style="background: var(--bg-secondary); height: 20px; border-radius: 4px; overflow: hidden;">
                        <div style="width: ${(m.value/maxVal*100).toFixed(1)}%; height: 100%; background: ${m.color}; transition: width 0.3s;"></div>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    setupPrometheusEvents() {
        const refreshBtn = document.getElementById('prometheus-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchPrometheusMetrics());
        }

        const exportBtn = document.getElementById('prometheus-export-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportPrometheusMetrics());
        }

        const scrapeBtn = document.getElementById('prometheus-scrape-btn');
        if (scrapeBtn) {
            scrapeBtn.addEventListener('click', () => this.showPrometheusScrapeEndpoint());
        }

        // Initialize Prometheus charts
        this.initPrometheusCharts();

        // Auto-refresh prometheus metrics every 10 seconds when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'prometheus') {
                this.fetchPrometheusMetrics();
            }
        }, 10000);
    }

    async fetchPrometheusMetrics() {
        try {
            const response = await fetch(`/api/agent/${this.agentId}/metrics`);
            if (response.ok) {
                const data = await response.json();
                this.updatePrometheusDisplay(data);
            }
        } catch (error) {
            console.error('Failed to fetch Prometheus metrics:', error);
        }
    }

    async exportPrometheusMetrics() {
        try {
            const response = await fetch(`/api/agent/${this.agentId}/metrics/prometheus`);
            if (response.ok) {
                const text = await response.text();
                const blob = new Blob([text], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `prometheus-${this.agentId}-${new Date().toISOString().split('T')[0]}.prom`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Failed to export Prometheus metrics:', error);
        }
    }

    showPrometheusScrapeEndpoint() {
        const endpoint = `${window.location.origin}/api/agent/${this.agentId}/metrics/prometheus`;
        alert(`Prometheus Scrape Endpoint:\n\n${endpoint}\n\nAdd this to your prometheus.yml:\n\n- job_name: 'asi-agent-${this.agentId}'\n  static_configs:\n    - targets: ['${window.location.host}']\n  metrics_path: '/api/agent/${this.agentId}/metrics/prometheus'`);
    }

    // Legacy metrics alias for backward compatibility
    setupMetricsEvents() {
        this.setupPrometheusEvents();
    }

    async fetchMetrics() {
        return this.fetchPrometheusMetrics();
    }

    async exportMetrics() {
        try {
            const response = await fetch(`/api/metrics/export?agent_id=${this.agentId}`);
            if (response.ok) {
                const text = await response.text();
                const blob = new Blob([text], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `metrics-${this.agentId}-${new Date().toISOString().split('T')[0]}.prom`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Failed to export metrics:', error);
        }
    }

    // ==================== GRAFANA TAB ====================
    async loadGrafanaDashboard() {
        const container = document.getElementById('grafana-dashboard-container');
        if (!container) return;

        // Show loading state
        container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary);">Loading Grafana dashboard...</div>';

        try {
            const response = await fetch(`/api/grafana/dashboard?agent_id=${this.agentId}`);
            if (response.ok) {
                const data = await response.json();
                this.renderGrafanaDashboard(data);
            } else {
                this.renderGrafanaEmbed();
            }
        } catch (error) {
            console.error('Failed to load Grafana dashboard:', error);
            this.renderGrafanaEmbed();
        }
    }

    renderGrafanaDashboard(data) {
        const container = document.getElementById('grafana-dashboard-container');
        if (!container) return;

        const panels = data.panels || [];

        if (panels.length === 0) {
            this.renderGrafanaEmbed();
            return;
        }

        let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">';

        for (const panel of panels) {
            html += `
                <div class="grafana-panel" style="background: var(--bg-tertiary); border-radius: 8px; overflow: hidden;">
                    <div style="background: var(--bg-secondary); padding: 12px 15px; border-bottom: 1px solid var(--border-color);">
                        <h4 style="margin: 0; font-size: 0.95rem;">${panel.title}</h4>
                        <p style="margin: 4px 0 0; font-size: 0.8rem; color: var(--text-secondary);">${panel.description || ''}</p>
                    </div>
                    <div class="panel-content" style="padding: 15px; min-height: 200px;">
                        ${this.renderGrafanaPanel(panel)}
                    </div>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;
    }

    renderGrafanaPanel(panel) {
        const type = panel.type || 'stat';
        const data = panel.data || {};

        switch (type) {
            case 'stat':
                return `
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 150px;">
                        <div style="font-size: 3rem; font-weight: bold; color: var(--accent-cyan);">${data.value || 0}</div>
                        <div style="font-size: 0.9rem; color: var(--text-secondary);">${data.label || ''}</div>
                    </div>
                `;
            case 'gauge':
                const percent = Math.min(100, Math.max(0, (data.value / data.max * 100) || 0));
                const color = percent > 80 ? 'var(--accent-red)' : percent > 60 ? 'var(--accent-yellow)' : 'var(--accent-green)';
                return `
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 150px;">
                        <div style="position: relative; width: 120px; height: 120px;">
                            <svg viewBox="0 0 36 36" style="transform: rotate(-90deg);">
                                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                    fill="none" stroke="var(--bg-secondary)" stroke-width="3"/>
                                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                    fill="none" stroke="${color}" stroke-width="3"
                                    stroke-dasharray="${percent}, 100"/>
                            </svg>
                            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold;">${data.value || 0}</div>
                                <div style="font-size: 0.7rem; color: var(--text-secondary);">${data.unit || ''}</div>
                            </div>
                        </div>
                    </div>
                `;
            case 'timeseries':
                // Simple sparkline visualization
                const points = data.values || [];
                if (points.length === 0) return '<div style="text-align: center; color: var(--text-secondary);">No data</div>';

                const max = Math.max(...points.map(p => p.value));
                const min = Math.min(...points.map(p => p.value));
                const range = max - min || 1;

                const pathPoints = points.map((p, i) => {
                    const x = (i / (points.length - 1)) * 100;
                    const y = 100 - ((p.value - min) / range) * 80;
                    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                }).join(' ');

                return `
                    <svg viewBox="0 0 100 100" style="width: 100%; height: 150px;">
                        <path d="${pathPoints}" fill="none" stroke="var(--accent-cyan)" stroke-width="2"/>
                    </svg>
                `;
            case 'table':
                const rows = data.rows || [];
                const columns = data.columns || [];
                if (rows.length === 0) return '<div style="text-align: center; color: var(--text-secondary);">No data</div>';

                let tableHtml = '<table class="data-table" style="font-size: 0.85rem;">';
                tableHtml += '<thead><tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr></thead>';
                tableHtml += '<tbody>' + rows.map(row => '<tr>' + row.map(cell => `<td>${cell}</td>`).join('') + '</tr>').join('') + '</tbody>';
                tableHtml += '</table>';
                return tableHtml;
            default:
                return `<div style="text-align: center; color: var(--text-secondary);">Unsupported panel type: ${type}</div>`;
        }
    }

    renderGrafanaEmbed() {
        const container = document.getElementById('grafana-dashboard-container');
        if (!container) return;

        // Show embedded dashboard templates or connection info
        container.innerHTML = `
            <div style="padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h3 style="color: var(--text-primary); margin-bottom: 10px;">Grafana Dashboard</h3>
                    <p style="color: var(--text-secondary);">View agent metrics visualizations</p>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
                    <!-- Agent Overview Panel -->
                    <div style="background: var(--bg-tertiary); border-radius: 8px; padding: 20px;">
                        <h4 style="color: var(--accent-cyan); margin-bottom: 15px;">Agent Overview</h4>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                            <div style="text-align: center; padding: 15px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 2rem; font-weight: bold; color: var(--accent-green);" id="grafana-agent-up">1</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Agent Status</div>
                            </div>
                            <div style="text-align: center; padding: 15px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 2rem; font-weight: bold; color: var(--accent-cyan);" id="grafana-protocols">${Object.keys(this.protocols).length}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Active Protocols</div>
                            </div>
                        </div>
                    </div>

                    <!-- OSPF Panel -->
                    <div style="background: var(--bg-tertiary); border-radius: 8px; padding: 20px;">
                        <h4 style="color: var(--accent-cyan); margin-bottom: 15px;">OSPF Metrics</h4>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div style="padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 1.5rem; font-weight: bold;" id="grafana-ospf-neighbors">${document.getElementById('ospf-neighbors')?.textContent || '0'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Neighbors</div>
                            </div>
                            <div style="padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 1.5rem; font-weight: bold;" id="grafana-ospf-routes">${document.getElementById('ospf-routes')?.textContent || '0'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Routes</div>
                            </div>
                        </div>
                    </div>

                    <!-- BGP Panel -->
                    <div style="background: var(--bg-tertiary); border-radius: 8px; padding: 20px;">
                        <h4 style="color: var(--accent-purple); margin-bottom: 15px;">BGP Metrics</h4>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div style="padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 1.5rem; font-weight: bold;" id="grafana-bgp-peers">${document.getElementById('bgp-established')?.textContent || '0'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Established</div>
                            </div>
                            <div style="padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 1.5rem; font-weight: bold;" id="grafana-bgp-prefixes">${document.getElementById('bgp-prefixes-in')?.textContent || '0'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Prefixes</div>
                            </div>
                        </div>
                    </div>

                    <!-- System Resources Panel -->
                    <div style="background: var(--bg-tertiary); border-radius: 8px; padding: 20px;">
                        <h4 style="color: var(--accent-green); margin-bottom: 15px;">System Resources</h4>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                                    <span>CPU</span>
                                    <span id="grafana-cpu">--</span>
                                </div>
                                <div style="background: var(--bg-secondary); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div id="grafana-cpu-bar" style="width: 0%; height: 100%; background: var(--accent-cyan); transition: width 0.3s;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                                    <span>Memory</span>
                                    <span id="grafana-memory">--</span>
                                </div>
                                <div style="background: var(--bg-secondary); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div id="grafana-memory-bar" style="width: 0%; height: 100%; background: var(--accent-purple); transition: width 0.3s;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                                    <span>Disk</span>
                                    <span id="grafana-disk">--</span>
                                </div>
                                <div style="background: var(--bg-secondary); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div id="grafana-disk-bar" style="width: 0%; height: 100%; background: var(--accent-green); transition: width 0.3s;"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div style="margin-top: 30px; text-align: center;">
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 15px;">
                        Connect to an external Grafana instance for more detailed visualizations
                    </p>
                    <input type="text" id="grafana-url-input" placeholder="http://localhost:3000"
                        style="padding: 10px 15px; background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); width: 300px; margin-right: 10px;">
                    <button class="btn btn-secondary" id="grafana-connect-btn">Connect</button>
                </div>
            </div>
        `;

        // Setup connect button
        const connectBtn = document.getElementById('grafana-connect-btn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.connectToGrafana());
        }

        // Fetch system metrics for the embedded panels
        this.fetchSystemMetricsForGrafana();
    }

    async fetchSystemMetricsForGrafana() {
        try {
            const response = await fetch(`/api/metrics?agent_id=${this.agentId}`);
            if (response.ok) {
                const data = await response.json();
                const metrics = data.metrics || {};

                // Update CPU
                const cpu = metrics['system_cpu_percent']?.values[0]?.value;
                if (cpu !== undefined) {
                    const cpuEl = document.getElementById('grafana-cpu');
                    const cpuBar = document.getElementById('grafana-cpu-bar');
                    if (cpuEl) cpuEl.textContent = cpu.toFixed(1) + '%';
                    if (cpuBar) cpuBar.style.width = cpu + '%';
                }

                // Update Memory
                const memory = metrics['system_memory_percent']?.values[0]?.value;
                if (memory !== undefined) {
                    const memEl = document.getElementById('grafana-memory');
                    const memBar = document.getElementById('grafana-memory-bar');
                    if (memEl) memEl.textContent = memory.toFixed(1) + '%';
                    if (memBar) memBar.style.width = memory + '%';
                }

                // Update Disk
                const disk = metrics['system_disk_percent']?.values[0]?.value;
                if (disk !== undefined) {
                    const diskEl = document.getElementById('grafana-disk');
                    const diskBar = document.getElementById('grafana-disk-bar');
                    if (diskEl) diskEl.textContent = disk.toFixed(1) + '%';
                    if (diskBar) diskBar.style.width = disk + '%';
                }
            }
        } catch (error) {
            console.error('Failed to fetch system metrics:', error);
        }
    }

    connectToGrafana() {
        const input = document.getElementById('grafana-url-input');
        if (!input) return;

        const url = input.value.trim();
        if (!url) {
            alert('Please enter a Grafana URL');
            return;
        }

        // Store Grafana URL in localStorage
        localStorage.setItem('grafana_url', url);

        // Open Grafana in new tab with agent-specific dashboard
        const dashboardUrl = `${url}/d/agent-${this.agentId}?refresh=10s`;
        window.open(dashboardUrl, '_blank');
    }

    setupGrafanaEvents() {
        const refreshBtn = document.getElementById('grafana-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadGrafanaDashboard());
        }

        const fullscreenBtn = document.getElementById('grafana-fullscreen-btn');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleGrafanaFullscreen());
        }

        const dashboardSelect = document.getElementById('grafana-dashboard-select');
        if (dashboardSelect) {
            dashboardSelect.addEventListener('change', (e) => this.switchGrafanaDashboard(e.target.value));
        }

        // Initialize Grafana charts
        this.initGrafanaCharts();

        // Auto-refresh Grafana every 10 seconds when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'grafana') {
                this.updateGrafanaCharts();
            }
        }, 10000);
    }

    initGrafanaCharts() {
        // State gauge chart
        const stateCtx = document.getElementById('grafana-state-gauge');
        if (stateCtx) {
            this.grafanaStateChart = new Chart(stateCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Healthy', 'Warning', 'Critical'],
                    datasets: [{
                        data: [85, 10, 5],
                        backgroundColor: ['#4ade80', '#fbbf24', '#ef4444'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%',
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
        }

        // Neighbor sparkline
        const neighborCtx = document.getElementById('grafana-neighbor-sparkline');
        if (neighborCtx) {
            this.grafanaNeighborChart = new Chart(neighborCtx, {
                type: 'line',
                data: {
                    labels: Array(10).fill(''),
                    datasets: [{
                        data: [2, 2, 3, 3, 3, 2, 2, 3, 3, 3],
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { display: false }, y: { display: false } }
                }
            });
        }

        // Routes sparkline
        const routesCtx = document.getElementById('grafana-routes-sparkline');
        if (routesCtx) {
            this.grafanaRoutesChart = new Chart(routesCtx, {
                type: 'line',
                data: {
                    labels: Array(10).fill(''),
                    datasets: [{
                        data: [10, 12, 15, 14, 16, 18, 17, 19, 20, 21],
                        borderColor: '#4ade80',
                        backgroundColor: 'rgba(74, 222, 128, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { display: false }, y: { display: false } }
                }
            });
        }

        // LSA chart
        const lsaCtx = document.getElementById('grafana-lsa-chart');
        if (lsaCtx) {
            this.grafanaLsaChart = new Chart(lsaCtx, {
                type: 'bar',
                data: {
                    labels: ['Router', 'Network', 'Summary', 'External'],
                    datasets: [{
                        data: [5, 3, 8, 12],
                        backgroundColor: ['#f97316', '#22d3ee', '#a855f7', '#4ade80']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } } }
                }
            });
        }

        // Interface utilization
        const ifUtilCtx = document.getElementById('grafana-interface-util');
        if (ifUtilCtx) {
            this.grafanaIfUtilChart = new Chart(ifUtilCtx, {
                type: 'line',
                data: {
                    labels: Array(20).fill(''),
                    datasets: [
                        { label: 'eth0', data: Array(20).fill(0).map(() => Math.random() * 50), borderColor: '#22d3ee', tension: 0.4 },
                        { label: 'eth1', data: Array(20).fill(0).map(() => Math.random() * 30), borderColor: '#f97316', tension: 0.4 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }

        // Packet rate
        const pktRateCtx = document.getElementById('grafana-packet-rate');
        if (pktRateCtx) {
            this.grafanaPktRateChart = new Chart(pktRateCtx, {
                type: 'line',
                data: {
                    labels: Array(20).fill(''),
                    datasets: [
                        { label: 'RX pps', data: Array(20).fill(0).map(() => Math.random() * 1000), borderColor: '#4ade80', tension: 0.4 },
                        { label: 'TX pps', data: Array(20).fill(0).map(() => Math.random() * 800), borderColor: '#a855f7', tension: 0.4 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
                    scales: {
                        x: { display: false },
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
        }
    }

    async updateGrafanaCharts() {
        try {
            const response = await fetch(`/api/agent/${this.agentId}/status`);
            if (response.ok) {
                const data = await response.json();

                // Update dashboard stats
                document.getElementById('grafana-last-refresh').textContent = new Date().toLocaleTimeString();

                // Add new data points to charts
                if (this.grafanaNeighborChart) {
                    const neighborData = this.grafanaNeighborChart.data.datasets[0].data;
                    neighborData.push(data.neighbor_count || neighborData[neighborData.length - 1] || 0);
                    if (neighborData.length > 20) neighborData.shift();
                    this.grafanaNeighborChart.update('none');
                }

                if (this.grafanaRoutesChart) {
                    const routeData = this.grafanaRoutesChart.data.datasets[0].data;
                    routeData.push(data.route_count || routeData[routeData.length - 1] || 0);
                    if (routeData.length > 20) routeData.shift();
                    this.grafanaRoutesChart.update('none');
                }

                // Update utilization with random simulation (replace with real data)
                if (this.grafanaIfUtilChart) {
                    this.grafanaIfUtilChart.data.datasets.forEach(ds => {
                        ds.data.push(Math.random() * 50 + 10);
                        if (ds.data.length > 20) ds.data.shift();
                    });
                    this.grafanaIfUtilChart.update('none');
                }

                if (this.grafanaPktRateChart) {
                    this.grafanaPktRateChart.data.datasets.forEach(ds => {
                        ds.data.push(Math.random() * 1000);
                        if (ds.data.length > 20) ds.data.shift();
                    });
                    this.grafanaPktRateChart.update('none');
                }
            }
        } catch (error) {
            console.error('Failed to update Grafana charts:', error);
        }
    }

    toggleGrafanaFullscreen() {
        const container = document.getElementById('grafana-panels-container');
        if (container) {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                container.requestFullscreen();
            }
        }
    }

    switchGrafanaDashboard(dashboard) {
        // Switch between different dashboard views
        console.log('Switching to dashboard:', dashboard);
        this.loadGrafanaDashboard();
    }

    // ==================== LLDP TAB ====================
    async fetchLLDPData() {
        try {
            // Fetch neighbors and statistics in parallel from real lldpd
            const [neighborsRes, statsRes] = await Promise.all([
                fetch(`/api/lldp/neighbors?agent_id=${this.agentId}`),
                fetch(`/api/lldp/statistics?agent_id=${this.agentId}`)
            ]);

            if (neighborsRes.ok) {
                const data = await neighborsRes.json();
                this.updateLLDPNeighbors(data);
            }

            if (statsRes.ok) {
                const data = await statsRes.json();
                this.updateLLDPStatistics(data);
            }
        } catch (error) {
            console.error('Failed to fetch LLDP data:', error);
        }
    }

    updateLLDPNeighbors(data) {
        const neighbors = data.neighbors || [];
        const count = data.count || 0;

        // Update summary cards
        document.getElementById('lldp-neighbors').textContent = count;

        // Count unique interfaces
        const interfaces = new Set(neighbors.map(n => n.local_interface));
        document.getElementById('lldp-interfaces').textContent = interfaces.size;

        // Update neighbors table
        const table = document.getElementById('lldp-neighbors-table');
        if (!table) return;

        if (neighbors.length === 0) {
            table.innerHTML = '<tr><td colspan="6" class="empty-state">No LLDP neighbors discovered. LLDP frames are exchanged every 30 seconds.</td></tr>';
            return;
        }

        let html = '';
        for (const n of neighbors) {
            const mgmtIp = n.management_ipv4 || n.management_ipv6 || '-';
            const capabilities = n.capabilities?.join(', ') || '-';
            const lastSeen = new Date(n.last_seen).toLocaleTimeString();
            const expired = n.expired ? ' (expired)' : '';

            html += `
                <tr class="${n.expired ? 'expired' : ''}">
                    <td>${n.local_interface}</td>
                    <td>
                        <strong>${n.system_name || n.chassis_id}</strong>
                        ${n.system_description ? `<br><span style="font-size: 0.8rem; color: var(--text-secondary);">${n.system_description}</span>` : ''}
                    </td>
                    <td>${n.port_id}${n.port_description ? ` (${n.port_description})` : ''}</td>
                    <td style="font-family: monospace;">${mgmtIp}</td>
                    <td>${capabilities}</td>
                    <td>${lastSeen}${expired}</td>
                </tr>
            `;
        }
        table.innerHTML = html;
    }

    updateLLDPStatistics(data) {
        const stats = data.statistics || {};

        // Update summary cards
        document.getElementById('lldp-frames-tx').textContent = stats.frames_sent || 0;
        document.getElementById('lldp-frames-rx').textContent = stats.frames_received || 0;

        // Update statistics panel
        document.getElementById('lldp-stat-frames-sent').textContent = stats.frames_sent || 0;
        document.getElementById('lldp-stat-frames-received').textContent = stats.frames_received || 0;
        document.getElementById('lldp-stat-neighbors-added').textContent = stats.neighbors_added || 0;
        document.getElementById('lldp-stat-neighbors-expired').textContent = stats.neighbors_expired || 0;
        document.getElementById('lldp-stat-tx-interval').textContent = (stats.tx_interval || 30) + 's';

        const statusEl = document.getElementById('lldp-stat-status');
        if (statusEl) {
            statusEl.textContent = stats.running ? 'Running' : 'Stopped';
            statusEl.style.color = stats.running ? 'var(--accent-green)' : 'var(--accent-red)';
        }
    }

    setupLLDPEvents() {
        const refreshBtn = document.getElementById('lldp-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchLLDPData());
        }

        // Auto-refresh LLDP data every 30 seconds when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'lldp') {
                this.fetchLLDPData();
            }
        }, 30000);
    }

    // ==================== LACP TAB ====================
    async fetchLACPData() {
        try {
            const response = await fetch(`/api/lacp/lags?agent_id=${this.agentId}`);
            if (response.ok) {
                const data = await response.json();
                this.updateLACPDisplay(data);
            }
        } catch (error) {
            console.error('Failed to fetch LACP data:', error);
        }
    }

    updateLACPDisplay(data) {
        const lags = data.lags || [];

        // Calculate summary stats
        const activeLags = lags.filter(l => l.oper_state === 'up').length;
        let totalMembers = 0;
        let activeMembers = 0;

        for (const lag of lags) {
            totalMembers += lag.total_members || 0;
            activeMembers += lag.active_members || 0;
        }

        // Update summary cards
        document.getElementById('lacp-lag-count').textContent = lags.length;
        document.getElementById('lacp-active-lags').textContent = activeLags;
        document.getElementById('lacp-total-members').textContent = totalMembers;
        document.getElementById('lacp-active-members').textContent = activeMembers;

        // Update LAGs table
        const table = document.getElementById('lacp-lags-table');
        if (!table) return;

        if (lags.length === 0) {
            table.innerHTML = '<tr><td colspan="7" class="empty-state">No LAGs configured. Click "Create LAG" to add one.</td></tr>';
            return;
        }

        let html = '';
        for (const lag of lags) {
            const stateClass = lag.oper_state === 'up' ? 'up' : 'down';
            const modeDisplay = lag.mode.charAt(0).toUpperCase() + lag.mode.slice(1);
            const lbDisplay = lag.load_balance.replace('+', ' + ').toUpperCase();

            html += `
                <tr>
                    <td><strong>${lag.name}</strong></td>
                    <td>${modeDisplay}</td>
                    <td>${lbDisplay}</td>
                    <td>${lag.total_members}</td>
                    <td>${lag.active_members} / ${lag.min_links}</td>
                    <td><span class="status-badge ${stateClass}">${lag.oper_state.toUpperCase()}</span></td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.showLAGMembers('${lag.name}')">Members</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteLAG('${lag.name}')">Delete</button>
                    </td>
                </tr>
            `;
        }
        table.innerHTML = html;
    }

    showLAGMembers(lagName) {
        // Show the member section
        const memberSection = document.getElementById('lacp-member-section');
        if (memberSection) {
            memberSection.style.display = 'block';
        }

        document.getElementById('lacp-selected-lag').textContent = lagName;
        this.selectedLAG = lagName;

        // Fetch LAG details
        this.fetchLAGMembers(lagName);
    }

    async fetchLAGMembers(lagName) {
        try {
            const response = await fetch(`/api/lacp/lag/${lagName}`);
            if (response.ok) {
                const data = await response.json();
                this.updateLAGMembersDisplay(data.lag);
            }
        } catch (error) {
            console.error('Failed to fetch LAG members:', error);
        }
    }

    updateLAGMembersDisplay(lag) {
        const table = document.getElementById('lacp-members-table');
        if (!table || !lag) return;

        const members = Object.values(lag.members || {});

        if (members.length === 0) {
            table.innerHTML = '<tr><td colspan="8" class="empty-state">No members in this LAG. Click "Add Member" to add one.</td></tr>';
            return;
        }

        let html = '';
        for (const member of members) {
            const stateClass = member.state === 'active' ? 'up' : 'down';
            const partnerInfo = member.partner ? `${member.partner.system_id}:${member.partner.port_id}` : '-';

            html += `
                <tr>
                    <td><strong>${member.interface}</strong></td>
                    <td>${member.port_id}</td>
                    <td>${member.port_priority}</td>
                    <td><span class="status-badge ${stateClass}">${member.state.toUpperCase()}</span></td>
                    <td>${member.lacpdu_sent}</td>
                    <td>${member.lacpdu_received}</td>
                    <td style="font-size: 0.85rem;">${partnerInfo}</td>
                    <td>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.removeLAGMember('${lag.name}', '${member.interface}')">Remove</button>
                    </td>
                </tr>
            `;
        }
        table.innerHTML = html;
    }

    async createLAG() {
        const name = document.getElementById('lacp-new-lag-name').value.trim();
        const mode = document.getElementById('lacp-new-lag-mode').value;
        const loadBalance = document.getElementById('lacp-new-lag-lb').value;
        const minLinks = parseInt(document.getElementById('lacp-new-lag-min').value) || 1;

        if (!name) {
            alert('Please enter a LAG name');
            return;
        }

        try {
            const response = await fetch(`/api/lacp/lag?name=${encodeURIComponent(name)}&mode=${mode}&load_balance=${encodeURIComponent(loadBalance)}&min_links=${minLinks}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.hideLACPModal();
                this.fetchLACPData();
            } else {
                alert('Failed to create LAG: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to create LAG:', error);
            alert('Failed to create LAG: ' + error.message);
        }
    }

    async deleteLAG(lagName) {
        if (!confirm(`Are you sure you want to delete LAG "${lagName}"?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/lacp/lag/${lagName}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.fetchLACPData();
                // Hide member section if this LAG was selected
                if (this.selectedLAG === lagName) {
                    document.getElementById('lacp-member-section').style.display = 'none';
                }
            } else {
                alert('Failed to delete LAG: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete LAG:', error);
        }
    }

    async addLAGMember() {
        const interface_name = prompt('Enter interface name to add (e.g., eth1):');
        if (!interface_name) return;

        try {
            const response = await fetch(`/api/lacp/lag/${this.selectedLAG}/member?interface=${encodeURIComponent(interface_name)}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.fetchLAGMembers(this.selectedLAG);
                this.fetchLACPData(); // Refresh counts
            } else {
                alert('Failed to add member: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to add LAG member:', error);
        }
    }

    async removeLAGMember(lagName, interface_name) {
        if (!confirm(`Remove ${interface_name} from ${lagName}?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/lacp/lag/${lagName}/member/${interface_name}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.fetchLAGMembers(lagName);
                this.fetchLACPData(); // Refresh counts
            } else {
                alert('Failed to remove member: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to remove LAG member:', error);
        }
    }

    showLACPModal() {
        const modal = document.getElementById('lacp-create-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    hideLACPModal() {
        const modal = document.getElementById('lacp-create-modal');
        if (modal) {
            modal.style.display = 'none';
            // Clear form
            document.getElementById('lacp-new-lag-name').value = '';
            document.getElementById('lacp-new-lag-mode').value = 'active';
            document.getElementById('lacp-new-lag-lb').value = 'layer3+4';
            document.getElementById('lacp-new-lag-min').value = '1';
        }
    }

    setupLACPEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('lacp-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchLACPData());
        }

        // Create LAG button
        const createBtn = document.getElementById('lacp-create-lag-btn');
        if (createBtn) {
            createBtn.addEventListener('click', () => this.showLACPModal());
        }

        // Add member button
        const addMemberBtn = document.getElementById('lacp-add-member-btn');
        if (addMemberBtn) {
            addMemberBtn.addEventListener('click', () => this.addLAGMember());
        }

        // Modal buttons
        const cancelBtn = document.getElementById('lacp-cancel-create');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.hideLACPModal());
        }

        const confirmBtn = document.getElementById('lacp-confirm-create');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.createLAG());
        }

        // Close modal on outside click
        const modal = document.getElementById('lacp-create-modal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideLACPModal();
                }
            });
        }

        // Auto-refresh LACP data every 5 seconds when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'lacp') {
                this.fetchLACPData();
            }
        }, 5000);
    }

    // ==================== SUBINTERFACE TAB (802.1Q VLANs) ====================
    async fetchSubinterfaceData() {
        try {
            const response = await fetch(`/api/subinterfaces?agent_id=${this.agentId}`);
            if (response.ok) {
                const data = await response.json();
                this.updateSubinterfaceDisplay(data);
            }
        } catch (error) {
            console.error('Failed to fetch subinterface data:', error);
        }
    }

    updateSubinterfaceDisplay(data) {
        const subinterfaces = data.subinterfaces || [];
        const stats = data.statistics || {};

        // Separate VLAN and L3 routed subinterfaces
        const vlanSubifs = subinterfaces.filter(s => !s.is_l3_routed && s.vlan_id !== null);
        const l3Subifs = subinterfaces.filter(s => s.is_l3_routed || s.encapsulation === 'none');

        // Calculate summary stats
        const activeSubifs = subinterfaces.filter(s => s.is_up).length;

        // Update metric cards
        document.getElementById('subif-physical-count').textContent = stats.physical_interfaces || 0;
        document.getElementById('subif-vlan-count').textContent = vlanSubifs.length;
        document.getElementById('subif-l3-count').textContent = l3Subifs.length;
        document.getElementById('subif-active-count').textContent = activeSubifs;

        // Update VLAN subinterfaces table
        const vlanTableBody = document.getElementById('subif-table');
        if (vlanSubifs.length === 0) {
            vlanTableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No VLAN subinterfaces configured</td></tr>';
        } else {
            vlanTableBody.innerHTML = vlanSubifs.map(subif => `
                <tr>
                    <td><strong>${this.escapeHtml(subif.name)}</strong></td>
                    <td>${this.escapeHtml(subif.parent_interface)}</td>
                    <td><span style="color: #ec4899; font-weight: 600;">VLAN ${subif.vlan_id}</span></td>
                    <td>${subif.ipv4_addresses.length > 0 ? subif.ipv4_addresses.map(a => `<code>${this.escapeHtml(a)}</code>`).join('<br>') : '<span style="color: var(--text-secondary);">None</span>'}</td>
                    <td>${subif.ipv6_addresses.length > 0 ? subif.ipv6_addresses.map(a => `<code>${this.escapeHtml(a)}</code>`).join('<br>') : '<span style="color: var(--text-secondary);">None</span>'}</td>
                    <td>${subif.mtu}</td>
                    <td>
                        <span class="status-badge ${subif.is_up ? 'success' : 'danger'}">
                            ${subif.is_up ? 'Up' : 'Down'}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.showSubinterfaceDetails('${subif.parent_interface}', ${subif.vlan_id})">Details</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteSubinterface('${subif.parent_interface}', ${subif.vlan_id})">Delete</button>
                    </td>
                </tr>
            `).join('');
        }

        // Update L3 routed subinterfaces table
        const l3TableBody = document.getElementById('subif-l3-table');
        if (l3TableBody) {
            if (l3Subifs.length === 0) {
                l3TableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No L3 routed subinterfaces configured</td></tr>';
            } else {
                l3TableBody.innerHTML = l3Subifs.map(subif => `
                    <tr>
                        <td><strong>${this.escapeHtml(subif.name)}</strong></td>
                        <td>${this.escapeHtml(subif.parent_interface)}</td>
                        <td><span style="color: #a855f7; font-weight: 600;">${subif.subif_index || 0}</span></td>
                        <td>${subif.ipv4_addresses.length > 0 ? `<code>${this.escapeHtml(subif.ipv4_addresses[0])}</code>` : '<span style="color: var(--text-secondary);">None</span>'}</td>
                        <td>${subif.ipv6_addresses.length > 0 ? `<code>${this.escapeHtml(subif.ipv6_addresses[0])}</code>` : '<span style="color: var(--text-secondary);">None</span>'}</td>
                        <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;" title="${this.escapeHtml(subif.description || '')}">${subif.description || '-'}</td>
                        <td>
                            <span class="status-badge ${subif.is_up ? 'success' : 'danger'}">
                                ${subif.is_up ? 'Up' : 'Down'}
                            </span>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteL3Subinterface('${subif.parent_interface}', ${subif.subif_index || 0})">Delete</button>
                        </td>
                    </tr>
                `).join('');
            }
        }
    }

    // Delete L3 routed subinterface
    async deleteL3Subinterface(parent, index) {
        if (!confirm(`Delete L3 subinterface ${parent}:${index}?`)) return;

        try {
            const response = await fetch(`/api/subinterfaces/l3/${parent}/${index}?agent_id=${this.agentId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                this.fetchSubinterfaceData();
            } else {
                const error = await response.json();
                alert(`Failed to delete: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Failed to delete L3 subinterface:', error);
        }
    }

    async showSubinterfaceDetails(parent, vlanId) {
        try {
            const response = await fetch(`/api/subinterfaces/${parent}/${vlanId}`);
            if (response.ok) {
                const data = await response.json();
                if (data.subinterface) {
                    this.selectedSubinterface = { parent, vlanId };
                    this.updateSubinterfaceDetailDisplay(data.subinterface);
                    document.getElementById('subif-detail-section').style.display = 'block';
                }
            }
        } catch (error) {
            console.error('Failed to fetch subinterface details:', error);
        }
    }

    updateSubinterfaceDetailDisplay(subif) {
        document.getElementById('subif-selected-name').textContent = subif.name;

        // Configuration details
        const configHtml = `
            <div style="display: grid; gap: 8px;">
                <div><strong>Name:</strong> ${this.escapeHtml(subif.name)}</div>
                <div><strong>Parent:</strong> ${this.escapeHtml(subif.parent_interface)}</div>
                <div><strong>VLAN ID:</strong> ${subif.vlan_id}</div>
                <div><strong>Encapsulation:</strong> ${this.escapeHtml(subif.encapsulation)}</div>
                <div><strong>MTU:</strong> ${subif.mtu}</div>
                <div><strong>Description:</strong> ${subif.description || 'None'}</div>
                <div><strong>Admin State:</strong> ${subif.admin_state}</div>
                <div><strong>Oper State:</strong> ${subif.oper_state}</div>
                <div><strong>Created:</strong> ${subif.created_at}</div>
                <hr style="border-color: var(--border-color);">
                <div><strong>IPv4 Addresses:</strong></div>
                ${subif.ipv4_addresses.length > 0
                    ? subif.ipv4_addresses.map(a => `<div style="margin-left: 15px;"><code>${this.escapeHtml(a)}</code> <button class="btn btn-sm btn-danger" onclick="agentDashboard.removeSubinterfaceIP('${subif.parent_interface}', ${subif.vlan_id}, '${a}', false)">Remove</button></div>`).join('')
                    : '<div style="margin-left: 15px; color: var(--text-secondary);">None configured</div>'
                }
                <div><strong>IPv6 Addresses:</strong></div>
                ${subif.ipv6_addresses.length > 0
                    ? subif.ipv6_addresses.map(a => `<div style="margin-left: 15px;"><code>${this.escapeHtml(a)}</code> <button class="btn btn-sm btn-danger" onclick="agentDashboard.removeSubinterfaceIP('${subif.parent_interface}', ${subif.vlan_id}, '${a}', true)">Remove</button></div>`).join('')
                    : '<div style="margin-left: 15px; color: var(--text-secondary);">None configured</div>'
                }
            </div>
        `;
        document.getElementById('subif-detail-config').innerHTML = configHtml;

        // Statistics
        const stats = subif.statistics || {};
        const statsHtml = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">RX Bytes</div>
                    <div style="font-size: 1.1rem;">${this.formatBytes(stats.rx_bytes || 0)}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">TX Bytes</div>
                    <div style="font-size: 1.1rem;">${this.formatBytes(stats.tx_bytes || 0)}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">RX Packets</div>
                    <div style="font-size: 1.1rem;">${stats.rx_packets || 0}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">TX Packets</div>
                    <div style="font-size: 1.1rem;">${stats.tx_packets || 0}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">RX Errors</div>
                    <div style="font-size: 1.1rem; color: ${stats.rx_errors > 0 ? 'var(--accent-red)' : 'inherit'};">${stats.rx_errors || 0}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">TX Errors</div>
                    <div style="font-size: 1.1rem; color: ${stats.tx_errors > 0 ? 'var(--accent-red)' : 'inherit'};">${stats.tx_errors || 0}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">RX Dropped</div>
                    <div style="font-size: 1.1rem; color: ${stats.rx_dropped > 0 ? 'var(--accent-yellow)' : 'inherit'};">${stats.rx_dropped || 0}</div>
                </div>
                <div>
                    <div style="color: var(--text-secondary); font-size: 0.8rem;">TX Dropped</div>
                    <div style="font-size: 1.1rem; color: ${stats.tx_dropped > 0 ? 'var(--accent-yellow)' : 'inherit'};">${stats.tx_dropped || 0}</div>
                </div>
            </div>
        `;
        document.getElementById('subif-detail-stats').innerHTML = statsHtml;
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async createSubinterface() {
        const parent = document.getElementById('subif-new-parent').value.trim();
        const vlanId = parseInt(document.getElementById('subif-new-vlan').value);
        const description = document.getElementById('subif-new-desc').value.trim();
        const ipv4 = document.getElementById('subif-new-ipv4').value.trim();
        const ipv6 = document.getElementById('subif-new-ipv6').value.trim();
        const mtu = document.getElementById('subif-new-mtu').value ? parseInt(document.getElementById('subif-new-mtu').value) : null;

        if (!parent || !vlanId) {
            alert('Parent interface and VLAN ID are required');
            return;
        }

        if (vlanId < 1 || vlanId > 4094) {
            alert('VLAN ID must be between 1 and 4094');
            return;
        }

        try {
            const params = new URLSearchParams({
                parent_interface: parent,
                vlan_id: vlanId
            });
            if (description) params.append('description', description);
            if (ipv4) params.append('ipv4_address', ipv4);
            if (ipv6) params.append('ipv6_address', ipv6);
            if (mtu) params.append('mtu', mtu);

            const response = await fetch(`/api/subinterfaces?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.hideSubinterfaceModal();
                this.fetchSubinterfaceData();
            } else {
                alert('Failed to create subinterface: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to create subinterface:', error);
            alert('Failed to create subinterface: ' + error.message);
        }
    }

    async deleteSubinterface(parent, vlanId) {
        if (!confirm(`Delete subinterface ${parent}.${vlanId}?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/subinterfaces/${parent}/${vlanId}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.success) {
                this.fetchSubinterfaceData();
                // Hide detail section if this was selected
                if (this.selectedSubinterface &&
                    this.selectedSubinterface.parent === parent &&
                    this.selectedSubinterface.vlanId === vlanId) {
                    document.getElementById('subif-detail-section').style.display = 'none';
                }
            } else {
                alert('Failed to delete subinterface: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete subinterface:', error);
        }
    }

    async addSubinterfaceIP() {
        if (!this.selectedSubinterface) {
            alert('Please select a subinterface first');
            return;
        }

        const address = document.getElementById('subif-add-ip-addr').value.trim();
        const isIpv6 = document.getElementById('subif-add-ip-type').value === 'ipv6';

        if (!address) {
            alert('IP address is required');
            return;
        }

        try {
            const { parent, vlanId } = this.selectedSubinterface;
            const params = new URLSearchParams({
                address: address,
                is_ipv6: isIpv6
            });

            const response = await fetch(`/api/subinterfaces/${parent}/${vlanId}/ip?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.hideSubinterfaceIPModal();
                this.showSubinterfaceDetails(parent, vlanId);
                this.fetchSubinterfaceData();
            } else {
                alert('Failed to add IP address: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to add IP address:', error);
        }
    }

    async removeSubinterfaceIP(parent, vlanId, address, isIpv6) {
        if (!confirm(`Remove IP address ${address}?`)) {
            return;
        }

        try {
            const params = new URLSearchParams({
                address: address,
                is_ipv6: isIpv6
            });

            const response = await fetch(`/api/subinterfaces/${parent}/${vlanId}/ip?${params}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.success) {
                this.showSubinterfaceDetails(parent, vlanId);
                this.fetchSubinterfaceData();
            } else {
                alert('Failed to remove IP address: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to remove IP address:', error);
        }
    }

    showSubinterfaceModal() {
        const modal = document.getElementById('subif-create-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    hideSubinterfaceModal() {
        const modal = document.getElementById('subif-create-modal');
        if (modal) {
            modal.style.display = 'none';
            // Clear form
            document.getElementById('subif-new-parent').value = '';
            document.getElementById('subif-new-vlan').value = '';
            document.getElementById('subif-new-desc').value = '';
            document.getElementById('subif-new-ipv4').value = '';
            document.getElementById('subif-new-ipv6').value = '';
            document.getElementById('subif-new-mtu').value = '';
        }
    }

    showSubinterfaceIPModal() {
        const modal = document.getElementById('subif-ip-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    hideSubinterfaceIPModal() {
        const modal = document.getElementById('subif-ip-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('subif-add-ip-addr').value = '';
            document.getElementById('subif-add-ip-type').value = 'ipv4';
        }
    }

    setupSubinterfaceEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('subif-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchSubinterfaceData());
        }

        // Create subinterface button
        const createBtn = document.getElementById('subif-create-btn');
        if (createBtn) {
            createBtn.addEventListener('click', () => this.showSubinterfaceModal());
        }

        // Add IP button
        const addIPBtn = document.getElementById('subif-add-ip-btn');
        if (addIPBtn) {
            addIPBtn.addEventListener('click', () => this.showSubinterfaceIPModal());
        }

        // Create modal buttons
        const cancelCreateBtn = document.getElementById('subif-cancel-create');
        if (cancelCreateBtn) {
            cancelCreateBtn.addEventListener('click', () => this.hideSubinterfaceModal());
        }

        const confirmCreateBtn = document.getElementById('subif-confirm-create');
        if (confirmCreateBtn) {
            confirmCreateBtn.addEventListener('click', () => this.createSubinterface());
        }

        // IP modal buttons
        const cancelIPBtn = document.getElementById('subif-cancel-ip');
        if (cancelIPBtn) {
            cancelIPBtn.addEventListener('click', () => this.hideSubinterfaceIPModal());
        }

        const confirmIPBtn = document.getElementById('subif-confirm-ip');
        if (confirmIPBtn) {
            confirmIPBtn.addEventListener('click', () => this.addSubinterfaceIP());
        }

        // Close modals on outside click
        const createModal = document.getElementById('subif-create-modal');
        if (createModal) {
            createModal.addEventListener('click', (e) => {
                if (e.target === createModal) {
                    this.hideSubinterfaceModal();
                }
            });
        }

        const ipModal = document.getElementById('subif-ip-modal');
        if (ipModal) {
            ipModal.addEventListener('click', (e) => {
                if (e.target === ipModal) {
                    this.hideSubinterfaceIPModal();
                }
            });
        }

        // Auto-refresh subinterface data every 5 seconds when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'subif') {
                this.fetchSubinterfaceData();
            }
        }, 5000);

        // L3 Subinterface Modal Event Listeners
        const l3CreateBtn = document.getElementById('subif-create-l3-btn');
        if (l3CreateBtn) {
            l3CreateBtn.addEventListener('click', () => this.showCreateL3SubifModal());
        }
    }

    // Show tab for VLAN vs L3 subinterfaces
    showSubifTab(tabType) {
        const vlanSection = document.getElementById('subif-vlan-section');
        const l3Section = document.getElementById('subif-l3-section');
        const vlanTab = document.getElementById('subif-tab-vlan');
        const l3Tab = document.getElementById('subif-tab-l3');

        if (tabType === 'vlan') {
            vlanSection.style.display = 'block';
            l3Section.style.display = 'none';
            vlanTab.style.background = '#ec4899';
            vlanTab.style.borderColor = '#ec4899';
            vlanTab.classList.remove('btn-secondary');
            l3Tab.classList.add('btn-secondary');
            l3Tab.style.background = '';
            l3Tab.style.borderColor = '';
        } else {
            vlanSection.style.display = 'none';
            l3Section.style.display = 'block';
            l3Tab.style.background = '#ec4899';
            l3Tab.style.borderColor = '#ec4899';
            l3Tab.classList.remove('btn-secondary');
            vlanTab.classList.add('btn-secondary');
            vlanTab.style.background = '';
            vlanTab.style.borderColor = '';
        }
    }

    // Show L3 subinterface creation modal
    showCreateL3SubifModal() {
        const modal = document.getElementById('subif-create-l3-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }

    // Hide L3 subinterface creation modal
    hideCreateL3SubifModal() {
        const modal = document.getElementById('subif-create-l3-modal');
        if (modal) {
            modal.style.display = 'none';
            // Clear form
            document.getElementById('subif-l3-parent').value = '';
            document.getElementById('subif-l3-index').value = '';
            document.getElementById('subif-l3-desc').value = '';
            document.getElementById('subif-l3-ipv4').value = '';
            document.getElementById('subif-l3-ipv6').value = '';
        }
    }

    // Create L3 routed subinterface
    async createL3Subinterface() {
        const parent = document.getElementById('subif-l3-parent').value.trim();
        const index = document.getElementById('subif-l3-index').value.trim();
        const description = document.getElementById('subif-l3-desc').value.trim();
        const ipv4 = document.getElementById('subif-l3-ipv4').value.trim();
        const ipv6 = document.getElementById('subif-l3-ipv6').value.trim();

        if (!parent) {
            alert('Parent interface is required');
            return;
        }
        if (!index) {
            alert('Subinterface index is required');
            return;
        }
        if (!ipv4) {
            alert('IPv4 address is required for L3 subinterfaces');
            return;
        }

        try {
            const response = await fetch('/api/subinterfaces/l3', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: this.agentId,
                    parent_interface: parent,
                    subif_index: parseInt(index),
                    description: description,
                    ipv4_address: ipv4,
                    ipv6_address: ipv6 || null,
                    encapsulation: 'none',
                    interface_mode: 'l3_sub'
                })
            });

            if (response.ok) {
                this.hideCreateL3SubifModal();
                this.fetchSubinterfaceData();
            } else {
                const error = await response.json();
                alert(`Failed to create L3 subinterface: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Failed to create L3 subinterface:', error);
            alert('Failed to create L3 subinterface');
        }
    }

    // ==================== EMAIL TAB (SMTP Notifications) ====================
    async fetchEmailData() {
        try {
            // Fetch statistics and history in parallel
            const [statsRes, historyRes, rulesRes] = await Promise.all([
                fetch('/api/smtp/statistics'),
                fetch('/api/smtp/history?limit=20'),
                fetch('/api/smtp/alerts')
            ]);

            if (statsRes.ok) {
                const statsData = await statsRes.json();
                this.updateEmailStats(statsData.statistics || {});
            }

            if (historyRes.ok) {
                const historyData = await historyRes.json();
                this.updateEmailHistory(historyData.emails || []);
            }

            if (rulesRes.ok) {
                const rulesData = await rulesRes.json();
                this.updateEmailRules(rulesData.rules || []);
            }
        } catch (error) {
            console.error('Failed to fetch email data:', error);
        }
    }

    updateEmailStats(stats) {
        document.getElementById('email-sent-count').textContent = stats.sent || 0;
        document.getElementById('email-failed-count').textContent = stats.failed || 0;
        document.getElementById('email-rule-count').textContent = stats.alert_rules || 0;
        document.getElementById('email-success-rate').innerHTML = `${Math.round(stats.success_rate || 100)}<span class="metric-unit">%</span>`;

        // Update config fields if available
        if (stats.config) {
            document.getElementById('smtp-server').value = stats.config.server || 'localhost';
            document.getElementById('smtp-port').value = stats.config.port || 587;
            document.getElementById('smtp-from').value = stats.config.from_address || 'agent@network.local';

            const security = stats.config.use_ssl ? 'ssl' : (stats.config.use_tls ? 'tls' : 'none');
            document.getElementById('smtp-security').value = security;
        }
    }

    updateEmailHistory(emails) {
        const tableBody = document.getElementById('email-history-table');
        if (emails.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No emails sent yet</td></tr>';
            return;
        }

        tableBody.innerHTML = emails.map(email => {
            const statusClass = email.status === 'sent' ? 'success' :
                               email.status === 'failed' ? 'danger' : 'warning';
            const priorityClass = email.priority === 'urgent' ? 'danger' :
                                 email.priority === 'high' ? 'warning' : 'info';

            const time = email.sent_at || email.created_at;
            return `
                <tr>
                    <td>${time ? new Date(time).toLocaleString() : '--'}</td>
                    <td>${this.escapeHtml(email.to.join(', '))}</td>
                    <td>${this.escapeHtml(email.subject)}</td>
                    <td><span class="status-badge ${statusClass}">${email.status}</span></td>
                    <td><span class="status-badge ${priorityClass}">${email.priority}</span></td>
                </tr>
            `;
        }).join('');
    }

    updateEmailRules(rules) {
        const tableBody = document.getElementById('email-rules-table');
        if (rules.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No alert rules configured</td></tr>';
            return;
        }

        tableBody.innerHTML = rules.map(rule => {
            const priorityClass = rule.priority === 'urgent' ? 'danger' :
                                 rule.priority === 'high' ? 'warning' : 'info';
            return `
                <tr>
                    <td><strong>${this.escapeHtml(rule.name)}</strong></td>
                    <td>${this.escapeHtml(rule.alert_type)}</td>
                    <td>${this.escapeHtml(rule.recipients.join(', '))}</td>
                    <td><span class="status-badge ${priorityClass}">${rule.priority}</span></td>
                    <td>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteAlertRule('${rule.name}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async saveEmailConfig() {
        const server = document.getElementById('smtp-server').value;
        const port = document.getElementById('smtp-port').value;
        const security = document.getElementById('smtp-security').value;
        const username = document.getElementById('smtp-username').value;
        const password = document.getElementById('smtp-password').value;
        const fromAddress = document.getElementById('smtp-from').value;

        const useTls = security === 'tls';
        const useSsl = security === 'ssl';

        try {
            const params = new URLSearchParams({
                server,
                port,
                use_tls: useTls,
                use_ssl: useSsl,
                from_address: fromAddress
            });
            if (username) params.append('username', username);
            if (password) params.append('password', password);

            const response = await fetch(`/api/smtp/config?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                alert('SMTP configuration saved successfully');
                this.fetchEmailData();
            } else {
                alert('Failed to save config: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to save SMTP config:', error);
            alert('Failed to save SMTP config: ' + error.message);
        }
    }

    showTestEmailModal() {
        const modal = document.getElementById('email-test-modal');
        if (modal) modal.style.display = 'flex';
    }

    hideTestEmailModal() {
        const modal = document.getElementById('email-test-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('email-test-recipient').value = '';
        }
    }

    async sendTestEmail() {
        const recipient = document.getElementById('email-test-recipient').value.trim();
        if (!recipient) {
            alert('Please enter a recipient email address');
            return;
        }

        try {
            const response = await fetch(`/api/smtp/test?recipient=${encodeURIComponent(recipient)}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                alert('Test email sent successfully');
                this.hideTestEmailModal();
                this.fetchEmailData();
            } else {
                alert('Failed to send test email: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to send test email:', error);
            alert('Failed to send test email: ' + error.message);
        }
    }

    showAddRuleModal() {
        const modal = document.getElementById('email-rule-modal');
        if (modal) modal.style.display = 'flex';
    }

    hideAddRuleModal() {
        const modal = document.getElementById('email-rule-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('email-rule-name').value = '';
            document.getElementById('email-rule-type').value = 'test_failure';
            document.getElementById('email-rule-recipients').value = '';
            document.getElementById('email-rule-priority').value = 'normal';
            document.getElementById('email-rule-cooldown').value = '300';
        }
    }

    async saveAlertRule() {
        const name = document.getElementById('email-rule-name').value.trim();
        const alertType = document.getElementById('email-rule-type').value;
        const recipients = document.getElementById('email-rule-recipients').value.trim();
        const priority = document.getElementById('email-rule-priority').value;
        const cooldown = document.getElementById('email-rule-cooldown').value;

        if (!name || !recipients) {
            alert('Please fill in rule name and recipients');
            return;
        }

        try {
            const params = new URLSearchParams({
                name,
                alert_type: alertType,
                recipients,
                priority,
                cooldown
            });

            const response = await fetch(`/api/smtp/alerts?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.hideAddRuleModal();
                this.fetchEmailData();
            } else {
                alert('Failed to add alert rule: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to add alert rule:', error);
            alert('Failed to add alert rule: ' + error.message);
        }
    }

    async deleteAlertRule(ruleName) {
        if (!confirm(`Delete alert rule "${ruleName}"?`)) return;

        try {
            const response = await fetch(`/api/smtp/alerts/${encodeURIComponent(ruleName)}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.success) {
                this.fetchEmailData();
            } else {
                alert('Failed to delete rule: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete alert rule:', error);
        }
    }

    setupEmailEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('email-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchEmailData());
        }

        // Save config button
        const saveConfigBtn = document.getElementById('email-save-config-btn');
        if (saveConfigBtn) {
            saveConfigBtn.addEventListener('click', () => this.saveEmailConfig());
        }

        // Test email button
        const testBtn = document.getElementById('email-test-btn');
        if (testBtn) {
            testBtn.addEventListener('click', () => this.showTestEmailModal());
        }

        // Add rule button
        const addRuleBtn = document.getElementById('email-add-rule-btn');
        if (addRuleBtn) {
            addRuleBtn.addEventListener('click', () => this.showAddRuleModal());
        }

        // Test email modal buttons
        const testCancelBtn = document.getElementById('email-test-cancel');
        if (testCancelBtn) {
            testCancelBtn.addEventListener('click', () => this.hideTestEmailModal());
        }

        const testSendBtn = document.getElementById('email-test-send');
        if (testSendBtn) {
            testSendBtn.addEventListener('click', () => this.sendTestEmail());
        }

        // Rule modal buttons
        const ruleCancelBtn = document.getElementById('email-rule-cancel');
        if (ruleCancelBtn) {
            ruleCancelBtn.addEventListener('click', () => this.hideAddRuleModal());
        }

        const ruleSaveBtn = document.getElementById('email-rule-save');
        if (ruleSaveBtn) {
            ruleSaveBtn.addEventListener('click', () => this.saveAlertRule());
        }

        // Close modals on outside click
        const testModal = document.getElementById('email-test-modal');
        if (testModal) {
            testModal.addEventListener('click', (e) => {
                if (e.target === testModal) this.hideTestEmailModal();
            });
        }

        const ruleModal = document.getElementById('email-rule-modal');
        if (ruleModal) {
            ruleModal.addEventListener('click', (e) => {
                if (e.target === ruleModal) this.hideAddRuleModal();
            });
        }

        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'email') {
                this.fetchEmailData();
            }
        }, 10000);  // Every 10 seconds
    }

    // ==================== FIREWALL TAB (ACLs) ====================
    async fetchFirewallData() {
        try {
            const [aclsRes, blockedRes] = await Promise.all([
                fetch('/api/firewall/acls'),
                fetch('/api/firewall/blocked?limit=20')
            ]);

            if (aclsRes.ok) {
                const data = await aclsRes.json();
                this.updateFirewallDisplay(data);
            }

            if (blockedRes.ok) {
                const data = await blockedRes.json();
                this.updateBlockedTraffic(data.blocked || []);
            }
        } catch (error) {
            console.error('Failed to fetch firewall data:', error);
        }
    }

    updateFirewallDisplay(data) {
        const acls = data.acls || [];
        const stats = data.statistics || {};

        // Update metric cards
        document.getElementById('fw-acl-count').textContent = stats.total_acls || 0;
        document.getElementById('fw-rule-count').textContent = stats.total_rules || 0;
        document.getElementById('fw-blocked-count').textContent = stats.blocked_packets || 0;
        document.getElementById('fw-hits-count').textContent = stats.total_hits || 0;

        // Update ACLs table
        const tableBody = document.getElementById('fw-acls-table');
        if (acls.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No ACLs configured. Click "Create ACL" to add one.</td></tr>';
            return;
        }

        tableBody.innerHTML = acls.map(acl => {
            const interfaces = Object.keys(acl.interfaces || {}).join(', ') || 'None';
            const statusClass = acl.enabled ? 'success' : 'warning';
            return `
                <tr>
                    <td><strong>${this.escapeHtml(acl.name)}</strong></td>
                    <td>${acl.acl_type}</td>
                    <td>${acl.entry_count}</td>
                    <td>${interfaces}</td>
                    <td>${acl.statistics?.total_hits || 0}</td>
                    <td><span class="status-badge ${statusClass}">${acl.enabled ? 'Enabled' : 'Disabled'}</span></td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.showACLRules('${acl.name}')">Rules</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteACL('${acl.name}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    updateBlockedTraffic(blocked) {
        const tableBody = document.getElementById('fw-blocked-table');
        if (blocked.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No blocked traffic</td></tr>';
            return;
        }

        tableBody.innerHTML = blocked.slice(0, 20).map(entry => {
            const time = new Date(entry.timestamp * 1000).toLocaleTimeString();
            return `
                <tr>
                    <td>${time}</td>
                    <td>${entry.interface}</td>
                    <td>${entry.src_ip}${entry.src_port ? ':' + entry.src_port : ''}</td>
                    <td>${entry.dst_ip}${entry.dst_port ? ':' + entry.dst_port : ''}</td>
                    <td>${entry.protocol}</td>
                    <td>${entry.acl}</td>
                    <td>${entry.rule || 'implicit'}</td>
                </tr>
            `;
        }).join('');
    }

    async showACLRules(aclName) {
        this.selectedACL = aclName;
        document.getElementById('fw-selected-acl').textContent = aclName;
        document.getElementById('fw-rules-section').style.display = 'block';

        try {
            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(aclName)}`);
            if (response.ok) {
                const data = await response.json();
                if (data.acl) {
                    this.updateACLRulesTable(data.acl.entries || []);
                }
            }
        } catch (error) {
            console.error('Failed to fetch ACL rules:', error);
        }
    }

    updateACLRulesTable(entries) {
        const tableBody = document.getElementById('fw-rules-table');
        if (entries.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No rules. Click "Add Rule" to create one.</td></tr>';
            return;
        }

        tableBody.innerHTML = entries.map(entry => {
            const actionClass = entry.action === 'permit' ? 'success' : 'danger';
            const src = entry.source_ip + (entry.source_port ? ':' + entry.source_port : '');
            const dst = entry.dest_ip + (entry.dest_port ? ':' + entry.dest_port : '');
            return `
                <tr>
                    <td>${entry.sequence}</td>
                    <td><span class="status-badge ${actionClass}">${entry.action}</span></td>
                    <td>${entry.protocol}</td>
                    <td>${src}</td>
                    <td>${dst}</td>
                    <td>${entry.statistics?.packets_matched || 0}</td>
                    <td>
                        <button class="btn btn-sm ${entry.enabled ? 'btn-success' : 'btn-warning'}"
                                onclick="agentDashboard.toggleRule('${this.selectedACL}', ${entry.sequence}, ${!entry.enabled})">
                            ${entry.enabled ? 'Yes' : 'No'}
                        </button>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.deleteRule('${this.selectedACL}', ${entry.sequence})">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    showCreateACLModal() {
        const modal = document.getElementById('fw-acl-modal');
        if (modal) modal.style.display = 'flex';
    }

    hideCreateACLModal() {
        const modal = document.getElementById('fw-acl-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('fw-new-acl-name').value = '';
            document.getElementById('fw-new-acl-desc').value = '';
            document.getElementById('fw-new-acl-type').value = 'extended';
        }
    }

    async createACL() {
        const name = document.getElementById('fw-new-acl-name').value.trim();
        const description = document.getElementById('fw-new-acl-desc').value.trim();
        const aclType = document.getElementById('fw-new-acl-type').value;

        if (!name) {
            alert('ACL name is required');
            return;
        }

        try {
            const params = new URLSearchParams({ name, description, acl_type: aclType });
            const response = await fetch(`/api/firewall/acl?${params}`, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.hideCreateACLModal();
                this.fetchFirewallData();
            } else {
                alert('Failed to create ACL: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to create ACL:', error);
            alert('Failed to create ACL: ' + error.message);
        }
    }

    async deleteACL(aclName) {
        if (!confirm(`Delete ACL "${aclName}" and all its rules?`)) return;

        try {
            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(aclName)}`, { method: 'DELETE' });
            const data = await response.json();

            if (data.success) {
                this.fetchFirewallData();
                if (this.selectedACL === aclName) {
                    document.getElementById('fw-rules-section').style.display = 'none';
                }
            } else {
                alert('Failed to delete ACL: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete ACL:', error);
        }
    }

    showAddRuleModal() {
        if (!this.selectedACL) {
            alert('Please select an ACL first');
            return;
        }
        const modal = document.getElementById('fw-rule-modal');
        if (modal) modal.style.display = 'flex';
    }

    hideAddRuleModal() {
        const modal = document.getElementById('fw-rule-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('fw-rule-seq').value = '10';
            document.getElementById('fw-rule-action').value = 'permit';
            document.getElementById('fw-rule-proto').value = 'any';
            document.getElementById('fw-rule-desc').value = '';
            document.getElementById('fw-rule-src-ip').value = 'any';
            document.getElementById('fw-rule-src-port').value = '';
            document.getElementById('fw-rule-dst-ip').value = 'any';
            document.getElementById('fw-rule-dst-port').value = '';
            document.getElementById('fw-rule-log').checked = false;
        }
    }

    async addRule() {
        if (!this.selectedACL) return;

        const sequence = parseInt(document.getElementById('fw-rule-seq').value);
        const action = document.getElementById('fw-rule-action').value;
        const protocol = document.getElementById('fw-rule-proto').value;
        const description = document.getElementById('fw-rule-desc').value;
        const sourceIp = document.getElementById('fw-rule-src-ip').value || 'any';
        const sourcePort = document.getElementById('fw-rule-src-port').value || null;
        const destIp = document.getElementById('fw-rule-dst-ip').value || 'any';
        const destPort = document.getElementById('fw-rule-dst-port').value || null;
        const log = document.getElementById('fw-rule-log').checked;

        try {
            const params = new URLSearchParams({
                sequence, action, protocol, source_ip: sourceIp, dest_ip: destIp, log
            });
            if (sourcePort) params.append('source_port', sourcePort);
            if (destPort) params.append('dest_port', destPort);
            if (description) params.append('description', description);

            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(this.selectedACL)}/rule?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.hideAddRuleModal();
                this.showACLRules(this.selectedACL);
                this.fetchFirewallData();
            } else {
                alert('Failed to add rule: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to add rule:', error);
            alert('Failed to add rule: ' + error.message);
        }
    }

    async deleteRule(aclName, sequence) {
        if (!confirm(`Delete rule ${sequence}?`)) return;

        try {
            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(aclName)}/rule/${sequence}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.success) {
                this.showACLRules(aclName);
                this.fetchFirewallData();
            } else {
                alert('Failed to delete rule: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete rule:', error);
        }
    }

    async toggleRule(aclName, sequence, enabled) {
        try {
            const params = new URLSearchParams({ enabled });
            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(aclName)}/rule/${sequence}?${params}`, {
                method: 'PUT'
            });
            const data = await response.json();

            if (data.success) {
                this.showACLRules(aclName);
            }
        } catch (error) {
            console.error('Failed to toggle rule:', error);
        }
    }

    showApplyACLModal() {
        if (!this.selectedACL) {
            alert('Please select an ACL first');
            return;
        }
        const modal = document.getElementById('fw-apply-modal');
        if (modal) modal.style.display = 'flex';
    }

    hideApplyACLModal() {
        const modal = document.getElementById('fw-apply-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('fw-apply-interface').value = '';
            document.getElementById('fw-apply-direction').value = 'in';
        }
    }

    async applyACL() {
        if (!this.selectedACL) return;

        const interface_name = document.getElementById('fw-apply-interface').value.trim();
        const direction = document.getElementById('fw-apply-direction').value;

        if (!interface_name) {
            alert('Interface name is required');
            return;
        }

        try {
            const params = new URLSearchParams({ interface: interface_name, direction });
            const response = await fetch(`/api/firewall/acl/${encodeURIComponent(this.selectedACL)}/apply?${params}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.hideApplyACLModal();
                this.fetchFirewallData();
                alert(`ACL applied to ${interface_name} (${direction})`);
            } else {
                alert('Failed to apply ACL: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to apply ACL:', error);
            alert('Failed to apply ACL: ' + error.message);
        }
    }

    setupFirewallEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('fw-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchFirewallData());
        }

        // Create ACL button
        const createACLBtn = document.getElementById('fw-create-acl-btn');
        if (createACLBtn) {
            createACLBtn.addEventListener('click', () => this.showCreateACLModal());
        }

        // Add rule button
        const addRuleBtn = document.getElementById('fw-add-rule-btn');
        if (addRuleBtn) {
            addRuleBtn.addEventListener('click', () => this.showAddRuleModal());
        }

        // Apply ACL button
        const applyACLBtn = document.getElementById('fw-apply-acl-btn');
        if (applyACLBtn) {
            applyACLBtn.addEventListener('click', () => this.showApplyACLModal());
        }

        // ACL modal buttons
        const aclCancelBtn = document.getElementById('fw-acl-cancel');
        if (aclCancelBtn) {
            aclCancelBtn.addEventListener('click', () => this.hideCreateACLModal());
        }

        const aclCreateBtn = document.getElementById('fw-acl-create');
        if (aclCreateBtn) {
            aclCreateBtn.addEventListener('click', () => this.createACL());
        }

        // Rule modal buttons
        const ruleCancelBtn = document.getElementById('fw-rule-cancel');
        if (ruleCancelBtn) {
            ruleCancelBtn.addEventListener('click', () => this.hideAddRuleModal());
        }

        const ruleSaveBtn = document.getElementById('fw-rule-save');
        if (ruleSaveBtn) {
            ruleSaveBtn.addEventListener('click', () => this.addRule());
        }

        // Apply modal buttons
        const applyCancelBtn = document.getElementById('fw-apply-cancel');
        if (applyCancelBtn) {
            applyCancelBtn.addEventListener('click', () => this.hideApplyACLModal());
        }

        const applySaveBtn = document.getElementById('fw-apply-save');
        if (applySaveBtn) {
            applySaveBtn.addEventListener('click', () => this.applyACL());
        }

        // Close modals on outside click
        ['fw-acl-modal', 'fw-rule-modal', 'fw-apply-modal'].forEach(modalId => {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        modal.style.display = 'none';
                    }
                });
            }
        });

        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'firewall') {
                this.fetchFirewallData();
            }
        }, 5000);
    }

    // ==================== SSH TAB ====================
    async fetchSSHData() {
        try {
            const [serversRes, sessionsRes] = await Promise.all([
                fetch('/api/ssh/servers'),
                fetch('/api/ssh/sessions')
            ]);

            const serversData = await serversRes.json();
            const sessionsData = await sessionsRes.json();

            this.updateSSHDisplay(serversData, sessionsData);
        } catch (error) {
            console.error('Failed to fetch SSH data:', error);
        }
    }

    updateSSHDisplay(serversData, sessionsData) {
        // Update summary cards
        const servers = serversData.servers || {};
        const sessions = sessionsData.sessions || [];

        document.getElementById('ssh-server-count').textContent = Object.keys(servers).length;
        document.getElementById('ssh-session-count').textContent = sessions.length;

        // Calculate totals from all servers
        let totalConnections = 0;
        let totalCommands = 0;
        for (const [name, stats] of Object.entries(servers)) {
            totalConnections += stats.total_connections || 0;
            totalCommands += stats.total_commands || 0;
        }
        document.getElementById('ssh-total-connections').textContent = totalConnections;
        document.getElementById('ssh-total-commands').textContent = totalCommands;

        // Update servers table
        this.updateSSHServersTable(servers);

        // Update sessions table
        this.updateSSHSessionsTable(sessions);
    }

    updateSSHServersTable(servers) {
        const tbody = document.getElementById('ssh-servers-tbody');
        if (!tbody) return;

        if (Object.keys(servers).length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">No SSH servers running</td></tr>';
            return;
        }

        let html = '';
        for (const [agentName, stats] of Object.entries(servers)) {
            html += `
                <tr>
                    <td>${this.escapeHtml(agentName)}</td>
                    <td><span class="status-badge status-up">Running</span></td>
                    <td>${stats.port || '-'}</td>
                    <td>${stats.active_sessions || 0}</td>
                    <td>${stats.total_connections || 0}</td>
                    <td>${stats.total_commands || 0}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.viewSSHServer('${this.escapeHtml(agentName)}')">View</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.stopSSHServer('${this.escapeHtml(agentName)}')">Stop</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateSSHSessionsTable(sessions) {
        const tbody = document.getElementById('ssh-sessions-tbody');
        if (!tbody) return;

        if (sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">No active sessions</td></tr>';
            return;
        }

        let html = '';
        for (const session of sessions) {
            const duration = Math.floor(session.duration_seconds || 0);
            const durationStr = duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m ${duration % 60}s`;

            html += `
                <tr>
                    <td><code>${this.escapeHtml(session.session_id)}</code></td>
                    <td>${this.escapeHtml(session.agent_name || '-')}</td>
                    <td>${this.escapeHtml(session.username)}</td>
                    <td>${this.escapeHtml(session.remote_address)}:${session.remote_port}</td>
                    <td>${durationStr}</td>
                    <td>${session.commands_executed || 0}</td>
                    <td><span class="status-badge status-up">${this.escapeHtml(session.state)}</span></td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    async viewSSHServer(agentName) {
        try {
            const response = await fetch(`/api/ssh/server/${encodeURIComponent(agentName)}`);
            const data = await response.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            // Show server details in a modal or alert
            const config = data.config || {};
            const stats = data.statistics || {};

            const details = `
SSH Server: ${agentName}
─────────────────────────
Port: ${config.port || '-'}
Password Auth: ${config.password_auth ? 'Yes' : 'No'}
Public Key Auth: ${config.public_key_auth ? 'Yes' : 'No'}
Max Sessions: ${config.max_sessions || '-'}
Idle Timeout: ${config.idle_timeout || '-'}s

Statistics:
─────────────────────────
Active Sessions: ${stats.active_sessions || 0}
Total Connections: ${stats.total_connections || 0}
Failed Auth: ${stats.failed_auth_attempts || 0}
Total Commands: ${stats.total_commands || 0}
Uptime: ${Math.floor((stats.uptime_seconds || 0) / 60)} minutes
            `.trim();

            alert(details);
        } catch (error) {
            console.error('Failed to view SSH server:', error);
            alert('Failed to get server details');
        }
    }

    async startSSHServer() {
        const agentName = document.getElementById('ssh-agent-name').value.trim();
        const port = parseInt(document.getElementById('ssh-port').value) || 2200;
        const username = document.getElementById('ssh-username').value.trim() || 'admin';
        const password = document.getElementById('ssh-password').value.trim() || 'admin';
        const maxSessions = parseInt(document.getElementById('ssh-max-sessions').value) || 10;
        const idleTimeout = parseInt(document.getElementById('ssh-idle-timeout').value) || 300;

        if (!agentName) {
            alert('Agent name is required');
            return;
        }

        try {
            const params = new URLSearchParams({
                agent_name: agentName,
                port: port.toString(),
                default_username: username,
                default_password: password,
                max_sessions: maxSessions.toString(),
                idle_timeout: idleTimeout.toString()
            });

            const response = await fetch(`/api/ssh/server?${params}`, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.hideStartSSHModal();
                this.fetchSSHData();
                alert(`SSH server started for ${agentName} on port ${port}`);
            } else {
                alert('Failed to start SSH server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to start SSH server:', error);
            alert('Failed to start SSH server');
        }
    }

    async stopSSHServer(agentName) {
        if (!confirm(`Stop SSH server for ${agentName}?`)) return;

        try {
            const response = await fetch(`/api/ssh/server/${encodeURIComponent(agentName)}`, { method: 'DELETE' });
            const data = await response.json();

            if (data.success) {
                this.fetchSSHData();
            } else {
                alert('Failed to stop SSH server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to stop SSH server:', error);
            alert('Failed to stop SSH server');
        }
    }

    showStartSSHModal() {
        const modal = document.getElementById('start-ssh-modal');
        if (modal) {
            // Reset form
            document.getElementById('ssh-agent-name').value = this.agentId || '';
            document.getElementById('ssh-port').value = '2200';
            document.getElementById('ssh-username').value = 'admin';
            document.getElementById('ssh-password').value = 'admin';
            document.getElementById('ssh-max-sessions').value = '10';
            document.getElementById('ssh-idle-timeout').value = '300';
            modal.style.display = 'flex';
        }
    }

    hideStartSSHModal() {
        const modal = document.getElementById('start-ssh-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    setupSSHEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('ssh-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchSSHData());
        }

        // Start server button
        const startBtn = document.getElementById('ssh-start-btn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.showStartSSHModal());
        }

        // Modal controls
        const modal = document.getElementById('start-ssh-modal');
        if (modal) {
            const closeBtn = modal.querySelector('.modal-close');
            const cancelBtn = modal.querySelector('.btn-cancel');
            const saveBtn = modal.querySelector('.btn-save');

            if (closeBtn) closeBtn.addEventListener('click', () => this.hideStartSSHModal());
            if (cancelBtn) cancelBtn.addEventListener('click', () => this.hideStartSSHModal());
            if (saveBtn) saveBtn.addEventListener('click', () => this.startSSHServer());

            // Close on outside click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.hideStartSSHModal();
            });
        }

        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'ssh') {
                this.fetchSSHData();
            }
        }, 10000);  // Every 10 seconds
    }

    // ==================== NETCONF TAB ====================
    async fetchNETCONFData() {
        try {
            const [netconfRes, restconfRes] = await Promise.all([
                fetch('/api/netconf/servers'),
                fetch('/api/restconf/servers')
            ]);

            const netconfData = await netconfRes.json();
            const restconfData = await restconfRes.json();

            this.updateNETCONFDisplay(netconfData, restconfData);
        } catch (error) {
            console.error('Failed to fetch NETCONF data:', error);
        }
    }

    updateNETCONFDisplay(netconfData, restconfData) {
        // Update summary cards
        const netconfServers = netconfData.servers || {};
        const restconfServers = restconfData.servers || {};
        const netconfSessions = netconfData.active_sessions || [];

        document.getElementById('netconf-server-count').textContent = Object.keys(netconfServers).length;
        document.getElementById('restconf-server-count').textContent = Object.keys(restconfServers).length;
        document.getElementById('netconf-session-count').textContent = netconfSessions.length;

        // Calculate totals
        let totalOps = 0;
        for (const [name, stats] of Object.entries(netconfServers)) {
            totalOps += stats.total_operations || 0;
        }
        for (const [name, stats] of Object.entries(restconfServers)) {
            totalOps += stats.total_requests || 0;
        }
        document.getElementById('netconf-total-ops').textContent = totalOps;

        // Update servers tables
        this.updateNETCONFServersTable(netconfServers);
        this.updateRESTCONFServersTable(restconfServers);
        this.updateNETCONFSessionsTable(netconfSessions);
    }

    updateNETCONFServersTable(servers) {
        const tbody = document.getElementById('netconf-servers-tbody');
        if (!tbody) return;

        if (Object.keys(servers).length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No NETCONF servers running</td></tr>';
            return;
        }

        let html = '';
        for (const [agentName, stats] of Object.entries(servers)) {
            html += `
                <tr>
                    <td>${this.escapeHtml(agentName)}</td>
                    <td><span class="status-badge status-up">Running</span></td>
                    <td>830</td>
                    <td>${stats.active_sessions || 0}</td>
                    <td>${stats.total_operations || 0}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.viewNETCONFConfig('${this.escapeHtml(agentName)}')">Config</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.stopNETCONFServer('${this.escapeHtml(agentName)}')">Stop</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateRESTCONFServersTable(servers) {
        const tbody = document.getElementById('restconf-servers-tbody');
        if (!tbody) return;

        if (Object.keys(servers).length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No RESTCONF servers running</td></tr>';
            return;
        }

        let html = '';
        for (const [agentName, stats] of Object.entries(servers)) {
            html += `
                <tr>
                    <td>${this.escapeHtml(agentName)}</td>
                    <td><span class="status-badge status-up">Running</span></td>
                    <td>8443</td>
                    <td>${stats.total_requests || 0}</td>
                    <td>${stats.failed_requests || 0}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.viewRESTCONFData('${this.escapeHtml(agentName)}')">Data</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.stopRESTCONFServer('${this.escapeHtml(agentName)}')">Stop</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateNETCONFSessionsTable(sessions) {
        const tbody = document.getElementById('netconf-sessions-tbody');
        if (!tbody) return;

        if (sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No active NETCONF sessions</td></tr>';
            return;
        }

        let html = '';
        for (const session of sessions) {
            const duration = Math.floor(session.duration_seconds || 0);
            const durationStr = duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m`;

            html += `
                <tr>
                    <td><code>${this.escapeHtml(session.session_id)}</code></td>
                    <td>${this.escapeHtml(session.agent_name || '-')}</td>
                    <td>${this.escapeHtml(session.username)}</td>
                    <td>${this.escapeHtml(session.remote_address)}</td>
                    <td>${durationStr}</td>
                    <td>${session.operations_count || 0}</td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    async viewNETCONFConfig(agentName) {
        try {
            const response = await fetch(`/api/netconf/config/${encodeURIComponent(agentName)}?datastore=running`);
            const data = await response.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            const configStr = JSON.stringify(data.config, null, 2);
            alert(`NETCONF Running Config for ${agentName}:\n\n${configStr.substring(0, 1000)}${configStr.length > 1000 ? '\n...(truncated)' : ''}`);
        } catch (error) {
            console.error('Failed to view NETCONF config:', error);
            alert('Failed to get NETCONF config');
        }
    }

    async viewRESTCONFData(agentName) {
        try {
            const response = await fetch(`/api/restconf/data/${encodeURIComponent(agentName)}?path=/`);
            const data = await response.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            const dataStr = JSON.stringify(data, null, 2);
            alert(`RESTCONF Data for ${agentName}:\n\n${dataStr.substring(0, 1000)}${dataStr.length > 1000 ? '\n...(truncated)' : ''}`);
        } catch (error) {
            console.error('Failed to view RESTCONF data:', error);
            alert('Failed to get RESTCONF data');
        }
    }

    async startNETCONFServer() {
        const agentName = document.getElementById('netconf-agent-name').value.trim();
        const port = parseInt(document.getElementById('netconf-port').value) || 830;
        const withCandidate = document.getElementById('netconf-candidate').checked;
        const withStartup = document.getElementById('netconf-startup').checked;

        if (!agentName) {
            alert('Agent name is required');
            return;
        }

        try {
            const params = new URLSearchParams({
                agent_name: agentName,
                port: port.toString(),
                with_candidate: withCandidate.toString(),
                with_startup: withStartup.toString()
            });

            const response = await fetch(`/api/netconf/server?${params}`, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.hideStartNETCONFModal();
                this.fetchNETCONFData();
                alert(`NETCONF server started for ${agentName} on port ${port}`);
            } else {
                alert('Failed to start NETCONF server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to start NETCONF server:', error);
            alert('Failed to start NETCONF server');
        }
    }

    async stopNETCONFServer(agentName) {
        if (!confirm(`Stop NETCONF server for ${agentName}?`)) return;

        try {
            const response = await fetch(`/api/netconf/server/${encodeURIComponent(agentName)}`, { method: 'DELETE' });
            const data = await response.json();

            if (data.success) {
                this.fetchNETCONFData();
            } else {
                alert('Failed to stop NETCONF server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to stop NETCONF server:', error);
        }
    }

    async startRESTCONFServer() {
        const agentName = document.getElementById('restconf-agent-name').value.trim();
        const port = parseInt(document.getElementById('restconf-port').value) || 8443;
        const useHttps = document.getElementById('restconf-https').checked;

        if (!agentName) {
            alert('Agent name is required');
            return;
        }

        try {
            const params = new URLSearchParams({
                agent_name: agentName,
                port: port.toString(),
                use_https: useHttps.toString()
            });

            const response = await fetch(`/api/restconf/server?${params}`, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.hideStartRESTCONFModal();
                this.fetchNETCONFData();
                alert(`RESTCONF server started for ${agentName} on port ${port}`);
            } else {
                alert('Failed to start RESTCONF server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to start RESTCONF server:', error);
            alert('Failed to start RESTCONF server');
        }
    }

    async stopRESTCONFServer(agentName) {
        if (!confirm(`Stop RESTCONF server for ${agentName}?`)) return;

        try {
            const response = await fetch(`/api/restconf/server/${encodeURIComponent(agentName)}`, { method: 'DELETE' });
            const data = await response.json();

            if (data.success) {
                this.fetchNETCONFData();
            } else {
                alert('Failed to stop RESTCONF server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to stop RESTCONF server:', error);
        }
    }

    showStartNETCONFModal() {
        const modal = document.getElementById('start-netconf-modal');
        if (modal) {
            document.getElementById('netconf-agent-name').value = this.agentId || '';
            document.getElementById('netconf-port').value = '830';
            document.getElementById('netconf-candidate').checked = true;
            document.getElementById('netconf-startup').checked = true;
            modal.style.display = 'flex';
        }
    }

    hideStartNETCONFModal() {
        const modal = document.getElementById('start-netconf-modal');
        if (modal) modal.style.display = 'none';
    }

    showStartRESTCONFModal() {
        const modal = document.getElementById('start-restconf-modal');
        if (modal) {
            document.getElementById('restconf-agent-name').value = this.agentId || '';
            document.getElementById('restconf-port').value = '8443';
            document.getElementById('restconf-https').checked = true;
            modal.style.display = 'flex';
        }
    }

    hideStartRESTCONFModal() {
        const modal = document.getElementById('start-restconf-modal');
        if (modal) modal.style.display = 'none';
    }

    setupNETCONFEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('netconf-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchNETCONFData());
        }

        // Start NETCONF button
        const startNetconfBtn = document.getElementById('netconf-start-btn');
        if (startNetconfBtn) {
            startNetconfBtn.addEventListener('click', () => this.showStartNETCONFModal());
        }

        // Start RESTCONF button
        const startRestconfBtn = document.getElementById('restconf-start-btn');
        if (startRestconfBtn) {
            startRestconfBtn.addEventListener('click', () => this.showStartRESTCONFModal());
        }

        // NETCONF Modal controls
        const netconfModal = document.getElementById('start-netconf-modal');
        if (netconfModal) {
            const closeBtn = netconfModal.querySelector('.modal-close');
            const cancelBtn = netconfModal.querySelector('.btn-cancel');
            const saveBtn = netconfModal.querySelector('.btn-save');

            if (closeBtn) closeBtn.addEventListener('click', () => this.hideStartNETCONFModal());
            if (cancelBtn) cancelBtn.addEventListener('click', () => this.hideStartNETCONFModal());
            if (saveBtn) saveBtn.addEventListener('click', () => this.startNETCONFServer());

            netconfModal.addEventListener('click', (e) => {
                if (e.target === netconfModal) this.hideStartNETCONFModal();
            });
        }

        // RESTCONF Modal controls
        const restconfModal = document.getElementById('start-restconf-modal');
        if (restconfModal) {
            const closeBtn = restconfModal.querySelector('.modal-close');
            const cancelBtn = restconfModal.querySelector('.btn-cancel');
            const saveBtn = restconfModal.querySelector('.btn-save');

            if (closeBtn) closeBtn.addEventListener('click', () => this.hideStartRESTCONFModal());
            if (cancelBtn) cancelBtn.addEventListener('click', () => this.hideStartRESTCONFModal());
            if (saveBtn) saveBtn.addEventListener('click', () => this.startRESTCONFServer());

            restconfModal.addEventListener('click', (e) => {
                if (e.target === restconfModal) this.hideStartRESTCONFModal();
            });
        }

        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'netconf') {
                this.fetchNETCONFData();
            }
        }, 10000);  // Every 10 seconds
    }

    // ==================== MCP EXTERNAL TAB ====================
    async fetchMCPExternalData() {
        try {
            const [serversRes, connectionsRes, toolsRes] = await Promise.all([
                fetch('/api/mcp/servers'),
                fetch('/api/mcp/connections'),
                fetch('/api/mcp/tools')
            ]);

            const serversData = await serversRes.json();
            const connectionsData = await connectionsRes.json();
            const toolsData = await toolsRes.json();

            this.updateMCPExternalDisplay(serversData, connectionsData, toolsData);
        } catch (error) {
            console.error('Failed to fetch MCP External data:', error);
        }
    }

    updateMCPExternalDisplay(serversData, connectionsData, toolsData) {
        // Update summary cards
        const servers = serversData.servers || {};
        const connections = connectionsData.connections || [];
        const tools = toolsData.tools || {};

        document.getElementById('mcp-server-count').textContent = Object.keys(servers).length;
        document.getElementById('mcp-connection-count').textContent = connections.length;

        // Count total tools across all servers
        let totalTools = 0;
        for (const [sid, toolList] of Object.entries(tools)) {
            totalTools += toolList.length;
        }
        document.getElementById('mcp-tool-count').textContent = totalTools;

        // Calculate total requests
        let totalRequests = 0;
        for (const [sid, stats] of Object.entries(servers)) {
            totalRequests += stats.total_requests || 0;
        }
        document.getElementById('mcp-request-count').textContent = totalRequests;

        // Update tables
        this.updateMCPServersTable(servers);
        this.updateMCPConnectionsTable(connections);
        this.updateMCPToolsTable(tools);
    }

    updateMCPServersTable(servers) {
        const tbody = document.getElementById('mcp-servers-tbody');
        if (!tbody) return;

        if (Object.keys(servers).length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">No MCP servers running. Start a server to allow external tools to connect.</td></tr>';
            return;
        }

        let html = '';
        for (const [serverId, stats] of Object.entries(servers)) {
            const parts = serverId.split(':');
            const serverType = parts[0] || 'unknown';
            const agentName = parts[1] || 'global';
            const port = parts[2] || '-';

            html += `
                <tr>
                    <td><code>${this.escapeHtml(serverId)}</code></td>
                    <td><span class="status-badge ${serverType === 'network' ? 'status-up' : 'status-warning'}">${serverType}</span></td>
                    <td>${this.escapeHtml(agentName)}</td>
                    <td>${port}</td>
                    <td>${stats.active_connections || 0}</td>
                    <td>${stats.total_requests || 0}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="agentDashboard.viewMCPTools('${this.escapeHtml(serverId)}')">Tools</button>
                        <button class="btn btn-sm btn-danger" onclick="agentDashboard.stopMCPServer('${this.escapeHtml(serverId)}')">Stop</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateMCPConnectionsTable(connections) {
        const tbody = document.getElementById('mcp-connections-tbody');
        if (!tbody) return;

        if (connections.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No active connections</td></tr>';
            return;
        }

        let html = '';
        for (const conn of connections) {
            const duration = Math.floor(conn.duration_seconds || 0);
            const durationStr = duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m`;

            html += `
                <tr>
                    <td><code>${this.escapeHtml(conn.connection_id)}</code></td>
                    <td>${this.escapeHtml(conn.client_name)}</td>
                    <td>${this.escapeHtml(conn.remote_address)}</td>
                    <td>${durationStr}</td>
                    <td>${conn.requests_count || 0}</td>
                    <td><span class="status-badge status-up">${this.escapeHtml(conn.state)}</span></td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateMCPToolsTable(tools) {
        const tbody = document.getElementById('mcp-tools-tbody');
        if (!tbody) return;

        const allTools = [];
        for (const [serverId, toolList] of Object.entries(tools)) {
            for (const tool of toolList) {
                allTools.push({ ...tool, serverId });
            }
        }

        if (allTools.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No tools available (start an MCP server first)</td></tr>';
            return;
        }

        let html = '';
        for (const tool of allTools.slice(0, 15)) {  // Show first 15 tools
            const paramCount = tool.inputSchema?.required?.length || 0;
            html += `
                <tr>
                    <td><code>${this.escapeHtml(tool.name)}</code></td>
                    <td>${this.escapeHtml(tool.description.substring(0, 60))}${tool.description.length > 60 ? '...' : ''}</td>
                    <td>${paramCount} params</td>
                    <td><code>${this.escapeHtml(tool.serverId)}</code></td>
                </tr>
            `;
        }
        if (allTools.length > 15) {
            html += `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">... and ${allTools.length - 15} more tools</td></tr>`;
        }
        tbody.innerHTML = html;
    }

    async viewMCPTools(serverId) {
        try {
            const response = await fetch(`/api/mcp/server/${encodeURIComponent(serverId)}`);
            const data = await response.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            const tools = data.tools || [];
            let toolsStr = tools.map(t => `- ${t.name}: ${t.description}`).join('\n');
            if (toolsStr.length > 2000) {
                toolsStr = toolsStr.substring(0, 2000) + '\n... (truncated)';
            }

            alert(`MCP Server: ${serverId}\n\nAvailable Tools (${tools.length}):\n\n${toolsStr}`);
        } catch (error) {
            console.error('Failed to view MCP tools:', error);
            alert('Failed to get tools');
        }
    }

    async startMCPServer() {
        const serverType = document.getElementById('mcp-server-type').value;
        const agentName = document.getElementById('mcp-agent-name').value.trim();
        const port = parseInt(document.getElementById('mcp-port').value) || 3000;
        const apiKey = document.getElementById('mcp-api-key').value.trim();
        const requireAuth = document.getElementById('mcp-require-auth').checked;

        if (serverType === 'agent' && !agentName) {
            alert('Agent name is required for agent-level servers');
            return;
        }

        try {
            const params = new URLSearchParams({
                server_type: serverType,
                port: port.toString(),
                require_auth: requireAuth.toString()
            });
            if (agentName) params.append('agent_name', agentName);
            if (apiKey) params.append('api_key', apiKey);

            const response = await fetch(`/api/mcp/server?${params}`, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.hideStartMCPModal();
                this.fetchMCPExternalData();
                alert(`MCP server started: ${data.server_id}\nPort: ${port}`);
            } else {
                alert('Failed to start MCP server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to start MCP server:', error);
            alert('Failed to start MCP server');
        }
    }

    async stopMCPServer(serverId) {
        if (!confirm(`Stop MCP server ${serverId}?`)) return;

        try {
            const response = await fetch(`/api/mcp/server/${encodeURIComponent(serverId)}`, { method: 'DELETE' });
            const data = await response.json();

            if (data.success) {
                this.fetchMCPExternalData();
            } else {
                alert('Failed to stop MCP server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to stop MCP server:', error);
        }
    }

    showStartMCPModal() {
        const modal = document.getElementById('start-mcp-modal');
        if (modal) {
            document.getElementById('mcp-server-type').value = 'network';
            document.getElementById('mcp-agent-name').value = '';
            document.getElementById('mcp-port').value = '3000';
            document.getElementById('mcp-api-key').value = '';
            document.getElementById('mcp-require-auth').checked = true;
            modal.style.display = 'flex';
        }
    }

    hideStartMCPModal() {
        const modal = document.getElementById('start-mcp-modal');
        if (modal) modal.style.display = 'none';
    }

    setupMCPExternalEvents() {
        // Refresh button
        const refreshBtn = document.getElementById('mcp-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchMCPExternalData());
        }

        // Start server button
        const startBtn = document.getElementById('mcp-start-btn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.showStartMCPModal());
        }

        // Modal controls
        const modal = document.getElementById('start-mcp-modal');
        if (modal) {
            const closeBtn = modal.querySelector('.modal-close');
            const cancelBtn = modal.querySelector('.btn-cancel');
            const saveBtn = modal.querySelector('.btn-save');

            if (closeBtn) closeBtn.addEventListener('click', () => this.hideStartMCPModal());
            if (cancelBtn) cancelBtn.addEventListener('click', () => this.hideStartMCPModal());
            if (saveBtn) saveBtn.addEventListener('click', () => this.startMCPServer());

            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.hideStartMCPModal();
            });
        }

        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'mcpext') {
                this.fetchMCPExternalData();
            }
        }, 10000);  // Every 10 seconds
    }

    // ==================== HEALTH METHODS ====================

    async fetchHealthData() {
        try {
            const response = await fetch('/api/health/network');
            const data = await response.json();

            if (data.error) {
                console.error('Health data error:', data.error);
                return;
            }

            this.updateHealthDisplay(data);
        } catch (error) {
            console.error('Error fetching health data:', error);
        }
    }

    updateHealthDisplay(data) {
        // Update metrics cards
        const scoreEl = document.getElementById('health-network-score');
        if (scoreEl) {
            scoreEl.textContent = `${Math.round(data.score)}%`;
            scoreEl.style.color = this.getHealthColor(data.severity);
        }

        const healthyEl = document.getElementById('health-healthy-agents');
        if (healthyEl) healthyEl.textContent = data.healthy_agents || 0;

        const degradedEl = document.getElementById('health-degraded-agents');
        if (degradedEl) degradedEl.textContent = data.degraded_agents || 0;

        const criticalEl = document.getElementById('health-critical-agents');
        if (criticalEl) criticalEl.textContent = data.critical_agents || 0;

        // Update health gauge
        this.updateHealthGauge(data.score, data.severity);

        // Update trend
        this.updateHealthTrend(data.trend);

        // Update component bars
        this.updateHealthComponent('protocol', data.average_protocol_health);
        this.updateHealthComponent('test', data.average_test_health);
        this.updateHealthComponent('resource', data.average_resource_health);
        this.updateHealthComponent('config', data.average_config_health);

        // Update issues list
        this.updateHealthIssues(data.issues || [], data.warnings || []);

        // Update recommendations list
        this.updateHealthRecommendations(data.recommendations || []);

        // Update agents table
        this.updateHealthAgentsTable(data.agents || {});
    }

    getHealthColor(severity) {
        switch (severity) {
            case 'excellent': return '#10b981';
            case 'good': return '#84cc16';
            case 'warning': return '#facc15';
            case 'degraded': return '#f97316';
            case 'critical': return '#ef4444';
            default: return 'var(--text-primary)';
        }
    }

    updateHealthGauge(score, severity) {
        const circle = document.getElementById('health-gauge-circle');
        const scoreText = document.getElementById('health-gauge-score');
        const labelText = document.getElementById('health-gauge-label');

        if (circle) {
            // Calculate stroke-dashoffset (534 is full circle circumference)
            const offset = 534 - (score / 100 * 534);
            circle.style.strokeDashoffset = offset;

            // Set color class
            circle.className = `health-gauge-circle health-gauge-value ${severity}`;
        }

        if (scoreText) {
            scoreText.textContent = Math.round(score);
            scoreText.style.color = this.getHealthColor(severity);
        }

        if (labelText) {
            labelText.textContent = severity ? severity.charAt(0).toUpperCase() + severity.slice(1) : 'Unknown';
        }
    }

    updateHealthTrend(trend) {
        const trendDiv = document.getElementById('health-trend');
        const iconEl = document.getElementById('health-trend-icon');
        const labelEl = document.getElementById('health-trend-label');

        if (trendDiv) {
            trendDiv.className = `health-trend ${trend || 'stable'}`;
        }

        if (iconEl) {
            switch (trend) {
                case 'improving': iconEl.textContent = '↗'; break;
                case 'declining': iconEl.textContent = '↘'; break;
                default: iconEl.textContent = '→';
            }
        }

        if (labelEl) {
            labelEl.textContent = trend ? trend.charAt(0).toUpperCase() + trend.slice(1) : 'Stable';
        }
    }

    updateHealthComponent(name, score) {
        const bar = document.getElementById(`health-${name}-bar`);
        const scoreEl = document.getElementById(`health-${name}-score`);

        if (bar) {
            bar.style.width = `${score}%`;
            bar.style.background = this.getHealthColor(this.getSeverityFromScore(score));
        }

        if (scoreEl) {
            scoreEl.textContent = `${Math.round(score)}%`;
            scoreEl.style.color = this.getHealthColor(this.getSeverityFromScore(score));
        }
    }

    getSeverityFromScore(score) {
        if (score >= 90) return 'excellent';
        if (score >= 70) return 'good';
        if (score >= 50) return 'warning';
        if (score >= 25) return 'degraded';
        return 'critical';
    }

    updateHealthIssues(issues, warnings) {
        const container = document.getElementById('health-issues-list');
        if (!container) return;

        const allIssues = [
            ...issues.map(i => ({ text: i, type: 'error' })),
            ...warnings.map(w => ({ text: w, type: 'warning' }))
        ];

        if (allIssues.length === 0) {
            container.innerHTML = '<p style="color: var(--accent-green); padding: 15px;">No issues detected - network is healthy!</p>';
            return;
        }

        let html = '<ul style="list-style: none; padding: 10px; margin: 0;">';
        for (const issue of allIssues.slice(0, 10)) {
            const icon = issue.type === 'error' ? '🔴' : '🟡';
            html += `<li style="padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                ${icon} ${this.escapeHtml(issue.text)}
            </li>`;
        }
        html += '</ul>';

        container.innerHTML = html;
    }

    updateHealthRecommendations(recommendations) {
        const container = document.getElementById('health-recommendations-list');
        if (!container) return;

        if (recommendations.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No recommendations at this time</p>';
            return;
        }

        let html = '<ul style="list-style: none; padding: 10px; margin: 0;">';
        for (const rec of recommendations.slice(0, 10)) {
            html += `<li style="padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                💡 ${this.escapeHtml(rec)}
            </li>`;
        }
        html += '</ul>';

        container.innerHTML = html;
    }

    updateHealthAgentsTable(agents) {
        const tbody = document.getElementById('health-agents-table');
        if (!tbody) return;

        const agentList = Object.values(agents);

        if (agentList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-secondary);">No agents</td></tr>';
            return;
        }

        let html = '';
        for (const agent of agentList) {
            const statusColor = this.getHealthColor(agent.severity);
            const trendIcon = agent.trend === 'improving' ? '↗' : agent.trend === 'declining' ? '↘' : '→';
            const trendColor = agent.trend === 'improving' ? '#10b981' : agent.trend === 'declining' ? '#ef4444' : 'var(--text-secondary)';

            html += `
                <tr>
                    <td>${this.escapeHtml(agent.agent_name)}</td>
                    <td style="color: ${statusColor}; font-weight: bold;">${Math.round(agent.score)}%</td>
                    <td style="color: ${statusColor};">${agent.severity}</td>
                    <td style="color: ${trendColor};">${trendIcon} ${agent.trend}</td>
                    <td>${Math.round(agent.protocol_health)}%</td>
                    <td>${Math.round(agent.test_health)}%</td>
                    <td>${Math.round(agent.resource_health)}%</td>
                    <td>${Math.round(agent.config_health)}%</td>
                </tr>
            `;
        }

        tbody.innerHTML = html;
    }

    setupHealthEvents() {
        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'health') {
                this.fetchHealthData();
            }
        }, 15000);  // Every 15 seconds
    }

    // ==================== TRAFFIC SIMULATION TAB ====================

    async fetchSimulationData() {
        try {
            const [statusRes, flowsRes, heatmapRes, congestionRes] = await Promise.all([
                fetch('/api/simulation/status'),
                fetch('/api/simulation/flows'),
                fetch('/api/simulation/heatmap'),
                fetch('/api/simulation/congestion')
            ]);

            const status = await statusRes.json();
            const flows = await flowsRes.json();
            const heatmap = await heatmapRes.json();
            const congestion = await congestionRes.json();

            this.updateSimulationDisplay(status, flows, heatmap, congestion);
        } catch (error) {
            console.error('Error fetching simulation data:', error);
        }
    }

    updateSimulationDisplay(status, flows, heatmap, congestion) {
        // Update metrics
        document.getElementById('sim-active-flows').textContent = status.active_flows || 0;
        document.getElementById('sim-total-throughput').textContent = status.total_throughput_human || '0 bps';
        document.getElementById('sim-congested-links').textContent = status.congested_links || 0;
        document.getElementById('sim-status').textContent = status.simulation_running ? 'Running' : 'Stopped';

        // Update heatmap table
        this.updateHeatmapTable(heatmap);

        // Update congestion report
        this.updateCongestionReport(congestion);

        // Update flows table
        this.updateFlowsTable(flows);
    }

    updateHeatmapTable(heatmap) {
        const tbody = document.getElementById('sim-heatmap-table');
        if (!tbody) return;

        if (!heatmap.links || heatmap.links.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No traffic data</td></tr>';
            return;
        }

        let html = '';
        for (const link of heatmap.links) {
            const utilColor = this.getUtilizationColor(link.utilization);
            const statusClass = link.congestion === 'critical' ? 'critical' :
                               link.congestion === 'high' ? 'warning' : 'success';

            html += `
                <tr>
                    <td>${link.source} ↔ ${link.target}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="flex: 1; background: var(--bg-tertiary); border-radius: 4px; height: 8px;">
                                <div style="width: ${Math.min(100, link.utilization)}%; background: ${utilColor}; height: 100%; border-radius: 4px;"></div>
                            </div>
                            <span style="min-width: 45px;">${link.utilization.toFixed(1)}%</span>
                        </div>
                    </td>
                    <td>${this.formatRate(link.rate_bps)}</td>
                    <td><span class="status-badge ${statusClass}">${link.congestion}</span></td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateCongestionReport(congestion) {
        const container = document.getElementById('sim-congestion');
        if (!container) return;

        if (!congestion.details || congestion.details.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No congestion detected</p>';
            return;
        }

        let html = '';
        for (const item of congestion.details) {
            html += `
                <div style="background: var(--bg-tertiary); padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 3px solid ${item.congestion === 'critical' ? '#ef4444' : '#f97316'};">
                    <div style="font-weight: 600; margin-bottom: 5px;">${item.source_agent} ↔ ${item.dest_agent}</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary);">
                        Utilization: ${item.utilization_pct.toFixed(1)}% | Flows: ${item.flow_count}
                    </div>
                    <div style="font-size: 0.85rem; margin-top: 8px; color: #facc15;">
                        💡 ${item.recommendation || 'Monitor this link'}
                    </div>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    updateFlowsTable(flows) {
        const tbody = document.getElementById('sim-flows-table');
        if (!tbody) return;

        if (!flows.flows || flows.flows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-secondary);">No flows configured</td></tr>';
            return;
        }

        let html = '';
        for (const flow of flows.flows) {
            const statusClass = flow.active ? 'success' : 'inactive';
            const statusText = flow.active ? 'Active' : 'Inactive';

            html += `
                <tr>
                    <td><code style="font-size: 0.8rem;">${flow.flow_id}</code></td>
                    <td>${flow.source_agent}:${flow.source_interface}</td>
                    <td>${flow.dest_agent}:${flow.dest_interface}</td>
                    <td>${flow.protocol.toUpperCase()}</td>
                    <td>${flow.rate_human || this.formatRate(flow.rate_bps)}</td>
                    <td>${flow.pattern}</td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>
                        <button class="btn btn-small ${flow.active ? 'btn-warning' : 'btn-primary'}"
                                onclick="dashboard.toggleFlow('${flow.flow_id}', ${!flow.active})">
                            ${flow.active ? 'Stop' : 'Start'}
                        </button>
                        <button class="btn btn-small btn-danger" onclick="dashboard.deleteFlow('${flow.flow_id}')">Delete</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    getUtilizationColor(utilization) {
        if (utilization >= 90) return '#ef4444';  // red - critical
        if (utilization >= 75) return '#f97316';  // orange - high
        if (utilization >= 50) return '#facc15';  // yellow - medium
        if (utilization >= 25) return '#84cc16';  // lime - low
        return '#22c55e';  // green - none
    }

    formatRate(bps) {
        if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(1)} Gbps`;
        if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`;
        if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} Kbps`;
        return `${bps.toFixed(0)} bps`;
    }

    async startSimulation() {
        try {
            const response = await fetch('/api/simulation/start', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error starting simulation:', error);
        }
    }

    async stopSimulation() {
        try {
            const response = await fetch('/api/simulation/stop', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error stopping simulation:', error);
        }
    }

    async createScenario() {
        const select = document.getElementById('sim-scenario-select');
        const scenario = select.value;
        if (!scenario) {
            alert('Please select a scenario');
            return;
        }

        // Get agents from the current network (demo agents for now)
        const agents = ['router-1', 'router-2', 'router-3', 'switch-1'];

        try {
            const response = await fetch(`/api/simulation/scenarios/${scenario}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(agents)
            });
            const result = await response.json();
            if (result.flows) {
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error creating scenario:', error);
        }
    }

    showCreateFlowModal() {
        document.getElementById('create-flow-modal').style.display = 'flex';
    }

    hideCreateFlowModal() {
        document.getElementById('create-flow-modal').style.display = 'none';
    }

    async createFlow() {
        const sourceAgent = document.getElementById('flow-source-agent').value;
        const sourceIf = document.getElementById('flow-source-if').value;
        const destAgent = document.getElementById('flow-dest-agent').value;
        const destIf = document.getElementById('flow-dest-if').value;
        const rateMbps = parseFloat(document.getElementById('flow-rate').value);
        const protocol = document.getElementById('flow-protocol').value;
        const application = document.getElementById('flow-application').value;
        const pattern = document.getElementById('flow-pattern').value;

        if (!sourceAgent || !destAgent) {
            alert('Please enter source and destination agents');
            return;
        }

        try {
            const params = new URLSearchParams({
                source_agent: sourceAgent,
                source_interface: sourceIf,
                dest_agent: destAgent,
                dest_interface: destIf,
                rate_bps: rateMbps * 1_000_000,
                protocol: protocol,
                application: application,
                pattern: pattern
            });

            const response = await fetch(`/api/simulation/flows?${params}`, { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.hideCreateFlowModal();
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error creating flow:', error);
        }
    }

    async toggleFlow(flowId, active) {
        try {
            const response = await fetch(`/api/simulation/flows/${flowId}/active?active=${active}`, {
                method: 'PUT'
            });
            const result = await response.json();
            if (result.success) {
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error toggling flow:', error);
        }
    }

    async deleteFlow(flowId) {
        if (!confirm('Delete this flow?')) return;

        try {
            const response = await fetch(`/api/simulation/flows/${flowId}`, { method: 'DELETE' });
            const result = await response.json();
            if (result.success) {
                this.fetchSimulationData();
            }
        } catch (error) {
            console.error('Error deleting flow:', error);
        }
    }

    setupSimulationEvents() {
        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'simulation') {
                this.fetchSimulationData();
            }
        }, 2000);  // Every 2 seconds for real-time traffic visualization
    }

    // ==================== TIME-TRAVEL REPLAY TAB ====================

    async fetchReplayData() {
        try {
            const [statusRes, sessionsRes, eventsRes] = await Promise.all([
                fetch('/api/replay/status'),
                fetch('/api/replay/sessions'),
                fetch('/api/replay/events?limit=50')
            ]);

            const status = await statusRes.json();
            const sessions = await sessionsRes.json();
            const events = await eventsRes.json();

            this.updateReplayDisplay(status, sessions, events);
        } catch (error) {
            console.error('Error fetching replay data:', error);
        }
    }

    updateReplayDisplay(status, sessions, events) {
        // Update metrics
        document.getElementById('replay-sessions-count').textContent = status.total_sessions || 0;
        document.getElementById('replay-snapshots-count').textContent = status.total_snapshots || 0;
        document.getElementById('replay-events-count').textContent = status.total_events || 0;

        const statusText = status.is_replaying ? 'Replaying' :
                          status.current_session ? 'Recording' : 'Idle';
        document.getElementById('replay-status').textContent = statusText;

        // Update session selector
        this.updateSessionSelector(sessions.sessions || []);

        // Update current session info
        this.updateCurrentSession(status, sessions.sessions || []);

        // Update events table
        this.updateReplayEventsTable(events.events || []);

        // Update replay state
        this.updateReplayState(status);
    }

    updateSessionSelector(sessions) {
        const select = document.getElementById('replay-session-select');
        if (!select) return;

        const currentValue = select.value;
        let html = '<option value="">-- Select Session --</option>';

        for (const session of sessions) {
            const selected = session.session_id === currentValue ? 'selected' : '';
            const status = session.active ? ' (Recording)' : '';
            html += `<option value="${session.session_id}" ${selected}>${session.name}${status}</option>`;
        }

        select.innerHTML = html;
    }

    updateCurrentSession(status, sessions) {
        const container = document.getElementById('replay-current-session');
        if (!container) return;

        if (!status.current_session) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No active recording session</p>';
            return;
        }

        const session = sessions.find(s => s.session_id === status.current_session);
        if (!session) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No active recording session</p>';
            return;
        }

        const duration = session.duration_seconds ?
            this.formatDuration(session.duration_seconds) : 'Just started';

        container.innerHTML = `
            <div style="background: var(--bg-tertiary); padding: 15px; border-radius: 8px; border-left: 3px solid #8b5cf6;">
                <div style="font-weight: 600; margin-bottom: 5px;">${session.name}</div>
                <div style="font-size: 0.85rem; color: var(--text-secondary); display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px;">
                    <div>
                        <div>Duration</div>
                        <div style="color: var(--text-primary);">${duration}</div>
                    </div>
                    <div>
                        <div>Snapshots</div>
                        <div style="color: var(--text-primary);">${session.snapshot_count || 0}</div>
                    </div>
                    <div>
                        <div>Events</div>
                        <div style="color: var(--text-primary);">${session.event_count || 0}</div>
                    </div>
                </div>
            </div>
        `;
    }

    formatDuration(seconds) {
        if (seconds < 60) return `${Math.floor(seconds)}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }

    updateReplayEventsTable(events) {
        const tbody = document.getElementById('replay-events-table');
        if (!tbody) return;

        if (!events || events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No events recorded</td></tr>';
            return;
        }

        let html = '';
        for (const event of events.slice().reverse()) {  // Most recent first
            const time = new Date(event.timestamp).toLocaleTimeString();
            const severityClass = event.severity === 'error' ? 'danger' :
                                 event.severity === 'warning' ? 'warning' : 'success';

            html += `
                <tr>
                    <td>${time}</td>
                    <td><code style="font-size: 0.8rem;">${event.event_type}</code></td>
                    <td>${event.agent_id}</td>
                    <td>${event.protocol.toUpperCase()}</td>
                    <td>${event.description}</td>
                    <td><span class="status-badge ${severityClass}">${event.severity}</span></td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    updateReplayState(status) {
        const container = document.getElementById('replay-state');
        if (!container) return;

        if (!status.is_replaying) {
            container.innerHTML = '<p style="color: var(--text-secondary);">Currently in live mode</p>';
            return;
        }

        const replayTime = new Date(status.replay_time).toLocaleString();
        container.innerHTML = `
            <div style="background: var(--bg-tertiary); padding: 15px; border-radius: 8px; border-left: 3px solid #facc15;">
                <div style="font-weight: 600; color: #facc15; margin-bottom: 5px;">⏪ Replay Mode</div>
                <div style="font-size: 0.9rem;">Viewing network state at:</div>
                <div style="font-size: 1.1rem; color: var(--text-primary); margin-top: 5px;">${replayTime}</div>
            </div>
        `;
    }

    async loadTimeline() {
        const select = document.getElementById('replay-session-select');
        const sessionId = select.value;

        if (!sessionId) {
            document.getElementById('replay-timeline').innerHTML =
                '<p style="color: var(--text-secondary); padding: 15px;">Select a session to view timeline</p>';
            return;
        }

        try {
            const response = await fetch(`/api/replay/timeline?session_id=${sessionId}`);
            const data = await response.json();

            if (data.error) {
                document.getElementById('replay-timeline').innerHTML =
                    `<p style="color: var(--accent-red); padding: 15px;">${data.error}</p>`;
                return;
            }

            this.renderTimeline(data);
        } catch (error) {
            console.error('Error loading timeline:', error);
        }
    }

    renderTimeline(data) {
        const container = document.getElementById('replay-timeline');
        if (!container) return;

        if (!data.timeline || data.timeline.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No timeline data</p>';
            return;
        }

        let html = '';
        for (const item of data.timeline) {
            const time = new Date(item.timestamp).toLocaleTimeString();
            const isSnapshot = item.type === 'snapshot';

            if (isSnapshot) {
                html += `
                    <div style="padding: 10px; margin: 5px 0; background: var(--bg-tertiary); border-radius: 6px; border-left: 3px solid #8b5cf6; cursor: pointer;" onclick="dashboard.replayToSnapshot('${item.timestamp}')">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 500;">📷 Snapshot</span>
                            <span style="color: var(--text-secondary); font-size: 0.85rem;">${time}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 5px;">
                            ${item.agent_count || 0} agents
                        </div>
                    </div>
                `;
            } else {
                const icon = this.getEventIcon(item.event_type);
                const severityColor = item.severity === 'error' ? '#ef4444' :
                                     item.severity === 'warning' ? '#facc15' : '#10b981';

                html += `
                    <div style="padding: 10px; margin: 5px 0; background: var(--bg-tertiary); border-radius: 6px; border-left: 3px solid ${severityColor};">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span>${icon} ${item.event_type}</span>
                            <span style="color: var(--text-secondary); font-size: 0.85rem;">${time}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 5px;">
                            ${item.description}
                        </div>
                    </div>
                `;
            }
        }

        container.innerHTML = html;
    }

    getEventIcon(eventType) {
        if (eventType.includes('up')) return '🟢';
        if (eventType.includes('down')) return '🔴';
        if (eventType.includes('change')) return '🔄';
        if (eventType.includes('received')) return '📥';
        if (eventType.includes('withdrawn')) return '📤';
        return '📌';
    }

    async replayToSnapshot(timestamp) {
        try {
            const response = await fetch(`/api/replay/rewind?timestamp=${encodeURIComponent(timestamp)}`, {
                method: 'POST'
            });
            const result = await response.json();
            if (result.success) {
                this.fetchReplayData();
            }
        } catch (error) {
            console.error('Error replaying to snapshot:', error);
        }
    }

    async replayToTime() {
        const input = document.getElementById('replay-time-input');
        const timestamp = input.value;

        if (!timestamp) {
            alert('Please select a time');
            return;
        }

        try {
            const isoTimestamp = new Date(timestamp).toISOString();
            const response = await fetch(`/api/replay/rewind?timestamp=${encodeURIComponent(isoTimestamp)}`, {
                method: 'POST'
            });
            const result = await response.json();
            if (result.success) {
                this.fetchReplayData();
            } else {
                alert(result.error || 'Failed to replay to time');
            }
        } catch (error) {
            console.error('Error replaying to time:', error);
        }
    }

    async clearReplay() {
        try {
            const response = await fetch('/api/replay/clear', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.fetchReplayData();
            }
        } catch (error) {
            console.error('Error clearing replay:', error);
        }
    }

    startRecording() {
        document.getElementById('start-recording-modal').style.display = 'flex';
    }

    hideStartRecordingModal() {
        document.getElementById('start-recording-modal').style.display = 'none';
    }

    async confirmStartRecording() {
        const name = document.getElementById('recording-name').value || 'Recording';
        const description = document.getElementById('recording-description').value || '';
        const interval = parseInt(document.getElementById('recording-interval').value) || 30;

        try {
            const params = new URLSearchParams({
                name: name,
                description: description,
                snapshot_interval: interval
            });

            const response = await fetch(`/api/replay/sessions?${params}`, { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.hideStartRecordingModal();
                this.fetchReplayData();
            }
        } catch (error) {
            console.error('Error starting recording:', error);
        }
    }

    async stopRecording() {
        try {
            const response = await fetch('/api/replay/sessions/stop', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.fetchReplayData();
            }
        } catch (error) {
            console.error('Error stopping recording:', error);
        }
    }

    async takeSnapshot() {
        try {
            const response = await fetch('/api/replay/snapshots', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                this.fetchReplayData();
            } else {
                alert(result.error || 'No active recording session');
            }
        } catch (error) {
            console.error('Error taking snapshot:', error);
        }
    }

    setupReplayEvents() {
        // Auto-refresh when tab is active
        setInterval(() => {
            if (this.activeProtocol === 'replay') {
                this.fetchReplayData();
            }
        }, 5000);  // Every 5 seconds
    }

    // ==================== NETWORK DIFF TAB ====================

    currentDiffResult = null;

    async fetchDiffData() {
        try {
            const [statusRes, snapshotsRes] = await Promise.all([
                fetch('/api/diff/status'),
                fetch('/api/replay/snapshots?limit=50')
            ]);

            const status = await statusRes.json();
            const snapshots = await snapshotsRes.json();

            this.updateDiffDisplay(status, snapshots);
        } catch (error) {
            console.error('Error fetching diff data:', error);
        }
    }

    updateDiffDisplay(status, snapshots) {
        // Update metrics
        document.getElementById('diff-total-count').textContent = status.total_diffs || 0;
        document.getElementById('diff-changes-count').textContent = status.total_changes || 0;

        // Populate snapshot selectors
        this.populateSnapshotSelectors(snapshots.snapshots || []);
    }

    populateSnapshotSelectors(snapshots) {
        const beforeSelect = document.getElementById('diff-before-select');
        const afterSelect = document.getElementById('diff-after-select');

        if (!beforeSelect || !afterSelect) return;

        let html = '<option value="">-- Select Snapshot --</option>';
        for (const snap of snapshots) {
            const time = new Date(snap.timestamp).toLocaleString();
            html += `<option value="${snap.snapshot_id}">${snap.snapshot_id} - ${time}</option>`;
        }

        beforeSelect.innerHTML = html;
        afterSelect.innerHTML = html;
    }

    async compareSnapshots() {
        const beforeId = document.getElementById('diff-before-select').value;
        const afterId = document.getElementById('diff-after-select').value;

        if (!beforeId || !afterId) {
            alert('Please select both before and after snapshots');
            return;
        }

        if (beforeId === afterId) {
            alert('Please select different snapshots to compare');
            return;
        }

        try {
            const params = new URLSearchParams({
                before_snapshot_id: beforeId,
                after_snapshot_id: afterId
            });

            const response = await fetch(`/api/diff/compare?${params}`, { method: 'POST' });
            const result = await response.json();

            if (result.error) {
                alert(result.error);
                return;
            }

            this.currentDiffResult = result;
            this.renderDiffResults(result);
        } catch (error) {
            console.error('Error comparing snapshots:', error);
        }
    }

    renderDiffResults(result) {
        // Update summary counts
        const summary = result.summary || {};
        document.getElementById('diff-added-count').textContent = summary.added || 0;
        document.getElementById('diff-removed-count').textContent = summary.removed || 0;

        // Render results table
        this.renderDiffTable(result.items || []);

        // Render category summary
        this.renderCategorySummary(summary.by_category || {});

        // Render impact summary
        this.renderImpactSummary(summary.by_impact || {});
    }

    renderDiffTable(items) {
        const container = document.getElementById('diff-results');
        if (!container) return;

        if (!items || items.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No differences found</p>';
            return;
        }

        let html = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Category</th>
                        <th>Agent</th>
                        <th>Description</th>
                        <th>Old Value</th>
                        <th>New Value</th>
                        <th>Impact</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const item of items) {
            const typeClass = item.diff_type === 'added' ? 'success' :
                             item.diff_type === 'removed' ? 'danger' : 'warning';
            const impactClass = item.impact === 'high' ? 'danger' :
                               item.impact === 'medium' ? 'warning' : 'success';

            html += `
                <tr>
                    <td><span class="status-badge ${typeClass}">${item.diff_type}</span></td>
                    <td>${item.category}</td>
                    <td>${item.agent_id || '-'}</td>
                    <td>${item.description}</td>
                    <td style="font-size: 0.85rem; color: #ef4444;">${this.formatDiffValue(item.old_value)}</td>
                    <td style="font-size: 0.85rem; color: #4ade80;">${this.formatDiffValue(item.new_value)}</td>
                    <td><span class="status-badge ${impactClass}">${item.impact}</span></td>
                </tr>
            `;
        }

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    formatDiffValue(value) {
        if (value === null || value === undefined) return '-';
        if (typeof value === 'object') {
            return JSON.stringify(value, null, 2).substring(0, 50) + '...';
        }
        return String(value);
    }

    renderCategorySummary(byCategory) {
        const container = document.getElementById('diff-category-summary');
        if (!container) return;

        if (!byCategory || Object.keys(byCategory).length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No diff generated</p>';
            return;
        }

        const colors = {
            route: '#3b82f6',
            neighbor: '#8b5cf6',
            topology: '#06b6d4',
            protocol: '#10b981',
            agent: '#f59e0b',
            config: '#ec4899'
        };

        let html = '';
        for (const [category, count] of Object.entries(byCategory)) {
            const color = colors[category] || '#6b7280';
            html += `
                <div style="display: flex; align-items: center; gap: 10px; margin: 8px 0;">
                    <div style="width: 12px; height: 12px; background: ${color}; border-radius: 2px;"></div>
                    <span style="text-transform: capitalize; min-width: 100px;">${category}</span>
                    <div style="flex: 1; background: var(--bg-tertiary); border-radius: 4px; height: 8px;">
                        <div style="width: ${Math.min(100, count * 10)}%; background: ${color}; height: 100%; border-radius: 4px;"></div>
                    </div>
                    <span style="min-width: 30px; text-align: right;">${count}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    renderImpactSummary(byImpact) {
        const container = document.getElementById('diff-impact-summary');
        if (!container) return;

        const impactColors = {
            low: '#22c55e',
            medium: '#facc15',
            high: '#f97316',
            critical: '#ef4444'
        };

        let html = '';
        for (const level of ['critical', 'high', 'medium', 'low']) {
            const count = byImpact[level] || 0;
            const color = impactColors[level];
            html += `
                <div style="display: flex; align-items: center; gap: 10px; margin: 8px 0;">
                    <div style="width: 12px; height: 12px; background: ${color}; border-radius: 2px;"></div>
                    <span style="text-transform: capitalize; min-width: 100px;">${level}</span>
                    <div style="flex: 1; background: var(--bg-tertiary); border-radius: 4px; height: 8px;">
                        <div style="width: ${Math.min(100, count * 20)}%; background: ${color}; height: 100%; border-radius: 4px;"></div>
                    </div>
                    <span style="min-width: 30px; text-align: right;">${count}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    filterDiffResults() {
        if (!this.currentDiffResult) return;

        const categoryFilter = document.getElementById('diff-category-filter').value;
        const typeFilter = document.getElementById('diff-type-filter').value;

        let items = this.currentDiffResult.items || [];

        if (categoryFilter) {
            items = items.filter(item => item.category === categoryFilter);
        }
        if (typeFilter) {
            items = items.filter(item => item.diff_type === typeFilter);
        }

        this.renderDiffTable(items);
    }

    // ==================== INTELLIGENT SUGGESTIONS TAB ====================

    currentSuggestions = [];
    suggestionsHistory = [];

    async fetchSuggestionsData() {
        try {
            const [statusRes, suggestionsRes, historyRes] = await Promise.all([
                fetch('/api/suggestions/status'),
                fetch('/api/suggestions'),
                fetch('/api/suggestions/history?limit=20')
            ]);

            const status = await statusRes.json();
            const suggestions = await suggestionsRes.json();
            const history = await historyRes.json();

            this.updateSuggestionsDisplay(status, suggestions, history);
        } catch (error) {
            console.error('Error fetching suggestions data:', error);
        }
    }

    updateSuggestionsDisplay(status, suggestions, history) {
        // Store current suggestions
        this.currentSuggestions = suggestions.suggestions || [];
        this.suggestionsHistory = history.history || [];

        // Update metrics
        document.getElementById('suggestions-total-count').textContent = status.total_suggestions || 0;

        // Count by priority
        let critical = 0, high = 0, medium = 0;
        for (const s of this.currentSuggestions) {
            if (s.priority === 'critical') critical++;
            else if (s.priority === 'high') high++;
            else if (s.priority === 'medium') medium++;
        }

        document.getElementById('suggestions-critical-count').textContent = critical;
        document.getElementById('suggestions-high-count').textContent = high;
        document.getElementById('suggestions-medium-count').textContent = medium;

        // Update count label
        const countLabel = document.getElementById('suggestions-count-label');
        if (countLabel) {
            countLabel.textContent = `${this.currentSuggestions.length} suggestions`;
        }

        // Render suggestions list
        this.renderSuggestionsList(this.currentSuggestions);

        // Render summaries
        this.renderSuggestionsCategorySummary(this.currentSuggestions);
        this.renderSuggestionsPrioritySummary(this.currentSuggestions);

        // Render history
        this.renderSuggestionsHistory(this.suggestionsHistory);
    }

    async analyzeSuggestions() {
        try {
            const includeInfo = document.getElementById('suggestions-include-info')?.checked || false;

            const response = await fetch(`/api/suggestions/analyze?include_info=${includeInfo}`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.error) {
                alert('Analysis error: ' + result.error);
                return;
            }

            // Update display with new analysis
            this.currentSuggestions = result.suggestions || [];
            this.renderSuggestionsList(this.currentSuggestions);
            this.renderSuggestionsCategorySummary(this.currentSuggestions);
            this.renderSuggestionsPrioritySummary(this.currentSuggestions);

            // Update metrics
            document.getElementById('suggestions-total-count').textContent = result.count || 0;

            // Count by priority
            let critical = 0, high = 0, medium = 0;
            for (const s of this.currentSuggestions) {
                if (s.priority === 'critical') critical++;
                else if (s.priority === 'high') high++;
                else if (s.priority === 'medium') medium++;
            }

            document.getElementById('suggestions-critical-count').textContent = critical;
            document.getElementById('suggestions-high-count').textContent = high;
            document.getElementById('suggestions-medium-count').textContent = medium;

            const countLabel = document.getElementById('suggestions-count-label');
            if (countLabel) {
                countLabel.textContent = `${this.currentSuggestions.length} suggestions`;
            }
        } catch (error) {
            console.error('Error analyzing suggestions:', error);
        }
    }

    async refreshSuggestions() {
        try {
            await fetch('/api/suggestions/refresh', { method: 'POST' });
            this.fetchSuggestionsData();
        } catch (error) {
            console.error('Error refreshing suggestions:', error);
        }
    }

    renderSuggestionsList(suggestions) {
        const container = document.getElementById('suggestions-list');
        if (!container) return;

        if (!suggestions || suggestions.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No suggestions available. Click "Analyze Network" to generate suggestions.</p>';
            return;
        }

        const priorityColors = {
            critical: '#ef4444',
            high: '#f97316',
            medium: '#facc15',
            low: '#22c55e',
            info: '#3b82f6'
        };

        const categoryIcons = {
            performance: '⚡',
            security: '🔒',
            redundancy: '🔄',
            scalability: '📈',
            best_practice: '✅',
            configuration: '⚙️',
            monitoring: '📊',
            troubleshooting: '🔧'
        };

        let html = '';
        for (const s of suggestions) {
            const priorityColor = priorityColors[s.priority] || '#6b7280';
            const icon = categoryIcons[s.category] || '💡';

            html += `
                <div class="suggestion-card" style="background: var(--bg-tertiary); border-radius: 8px; padding: 15px; margin-bottom: 10px; border-left: 4px solid ${priorityColor};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <span style="font-size: 1.2rem;">${icon}</span>
                            <span style="font-weight: 600; color: var(--text-primary);">${s.title}</span>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <span class="status-badge" style="background: ${priorityColor}22; color: ${priorityColor}; text-transform: capitalize;">${s.priority}</span>
                            <span class="status-badge" style="background: var(--bg-secondary); text-transform: capitalize;">${s.category}</span>
                        </div>
                    </div>
                    <p style="color: var(--text-secondary); margin-bottom: 10px; font-size: 0.9rem;">${s.description}</p>
                    ${s.recommendation ? `<p style="color: var(--accent-cyan); font-size: 0.85rem;"><strong>Recommendation:</strong> ${s.recommendation}</p>` : ''}
                    ${s.affected_agents && s.affected_agents.length > 0 ? `<p style="color: var(--text-secondary); font-size: 0.8rem; margin-top: 8px;"><strong>Affected:</strong> ${s.affected_agents.join(', ')}</p>` : ''}
                    <div style="display: flex; gap: 10px; margin-top: 10px;">
                        ${s.auto_applicable ? `<button class="btn btn-primary btn-sm" onclick="dashboard.applySuggestion('${s.suggestion_id}')" style="padding: 4px 12px; font-size: 0.8rem;">Apply</button>` : ''}
                        <button class="btn btn-secondary btn-sm" onclick="dashboard.dismissSuggestion('${s.suggestion_id}')" style="padding: 4px 12px; font-size: 0.8rem;">Dismiss</button>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    async applySuggestion(suggestionId) {
        try {
            const response = await fetch(`/api/suggestions/${suggestionId}/apply`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.applied) {
                alert('Suggestion applied successfully');
                this.fetchSuggestionsData();
            } else {
                alert('Failed to apply suggestion: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error applying suggestion:', error);
        }
    }

    async dismissSuggestion(suggestionId) {
        const reason = prompt('Reason for dismissing (optional):');

        try {
            const params = new URLSearchParams();
            if (reason) params.append('reason', reason);

            const response = await fetch(`/api/suggestions/${suggestionId}/dismiss?${params}`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.dismissed) {
                // Remove from current list
                this.currentSuggestions = this.currentSuggestions.filter(s => s.suggestion_id !== suggestionId);
                this.renderSuggestionsList(this.currentSuggestions);
                this.renderSuggestionsCategorySummary(this.currentSuggestions);
                this.renderSuggestionsPrioritySummary(this.currentSuggestions);

                // Update count
                document.getElementById('suggestions-total-count').textContent = this.currentSuggestions.length;
                const countLabel = document.getElementById('suggestions-count-label');
                if (countLabel) {
                    countLabel.textContent = `${this.currentSuggestions.length} suggestions`;
                }
            }
        } catch (error) {
            console.error('Error dismissing suggestion:', error);
        }
    }

    filterSuggestions() {
        const categoryFilter = document.getElementById('suggestions-category-filter').value;
        const priorityFilter = document.getElementById('suggestions-priority-filter').value;
        const includeInfo = document.getElementById('suggestions-include-info')?.checked || false;

        let filtered = [...this.currentSuggestions];

        if (categoryFilter) {
            filtered = filtered.filter(s => s.category === categoryFilter);
        }

        if (priorityFilter) {
            filtered = filtered.filter(s => s.priority === priorityFilter);
        }

        if (!includeInfo) {
            filtered = filtered.filter(s => s.priority !== 'info');
        }

        this.renderSuggestionsList(filtered);

        // Update count label
        const countLabel = document.getElementById('suggestions-count-label');
        if (countLabel) {
            countLabel.textContent = `${filtered.length} suggestions (filtered)`;
        }
    }

    renderSuggestionsCategorySummary(suggestions) {
        const container = document.getElementById('suggestions-category-summary');
        if (!container) return;

        const byCat = {};
        for (const s of suggestions) {
            byCat[s.category] = (byCat[s.category] || 0) + 1;
        }

        if (Object.keys(byCat).length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No analysis performed</p>';
            return;
        }

        const colors = {
            performance: '#3b82f6',
            security: '#ef4444',
            redundancy: '#8b5cf6',
            scalability: '#10b981',
            best_practice: '#22c55e',
            configuration: '#f59e0b',
            monitoring: '#06b6d4',
            troubleshooting: '#ec4899'
        };

        let html = '';
        for (const [category, count] of Object.entries(byCat)) {
            const color = colors[category] || '#6b7280';
            html += `
                <div style="display: flex; align-items: center; gap: 10px; margin: 8px 0;">
                    <div style="width: 12px; height: 12px; background: ${color}; border-radius: 2px;"></div>
                    <span style="text-transform: capitalize; min-width: 100px;">${category.replace('_', ' ')}</span>
                    <div style="flex: 1; background: var(--bg-tertiary); border-radius: 4px; height: 8px;">
                        <div style="width: ${Math.min(100, count * 15)}%; background: ${color}; height: 100%; border-radius: 4px;"></div>
                    </div>
                    <span style="min-width: 30px; text-align: right;">${count}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    renderSuggestionsPrioritySummary(suggestions) {
        const container = document.getElementById('suggestions-priority-summary');
        if (!container) return;

        const byPri = {};
        for (const s of suggestions) {
            byPri[s.priority] = (byPri[s.priority] || 0) + 1;
        }

        const priorityColors = {
            critical: '#ef4444',
            high: '#f97316',
            medium: '#facc15',
            low: '#22c55e',
            info: '#3b82f6'
        };

        let html = '';
        for (const level of ['critical', 'high', 'medium', 'low', 'info']) {
            const count = byPri[level] || 0;
            if (count === 0) continue;

            const color = priorityColors[level];
            html += `
                <div style="display: flex; align-items: center; gap: 10px; margin: 8px 0;">
                    <div style="width: 12px; height: 12px; background: ${color}; border-radius: 2px;"></div>
                    <span style="text-transform: capitalize; min-width: 100px;">${level}</span>
                    <div style="flex: 1; background: var(--bg-tertiary); border-radius: 4px; height: 8px;">
                        <div style="width: ${Math.min(100, count * 20)}%; background: ${color}; height: 100%; border-radius: 4px;"></div>
                    </div>
                    <span style="min-width: 30px; text-align: right;">${count}</span>
                </div>
            `;
        }

        if (html === '') {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No analysis performed</p>';
        } else {
            container.innerHTML = html;
        }
    }

    renderSuggestionsHistory(history) {
        const table = document.getElementById('suggestions-history-table');
        if (!table) return;

        if (!history || history.length === 0) {
            table.innerHTML = '<tr><td colspan="4" class="empty-state">No recent activity</td></tr>';
            return;
        }

        let html = '';
        for (const h of history) {
            const time = h.timestamp ? new Date(h.timestamp).toLocaleString() : '-';
            const actionClass = h.action === 'applied' ? 'success' :
                               h.action === 'dismissed' ? 'warning' : '';

            html += `
                <tr>
                    <td>${time}</td>
                    <td><span class="status-badge ${actionClass}">${h.action}</span></td>
                    <td>${h.suggestion_title || h.suggestion_id}</td>
                    <td>${h.reason || '-'}</td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    // ==================== SCENARIO BUILDER TAB ====================

    currentScenarios = [];
    currentScenarioId = null;
    scenarioTemplates = [];

    async fetchScenariosData() {
        try {
            const [statusRes, scenariosRes, resultsRes, templatesRes] = await Promise.all([
                fetch('/api/scenarios/status'),
                fetch('/api/scenarios'),
                fetch('/api/scenarios/results'),
                fetch('/api/scenarios/templates')
            ]);

            const status = await statusRes.json();
            const scenarios = await scenariosRes.json();
            const results = await resultsRes.json();
            const templates = await templatesRes.json();

            this.updateScenariosDisplay(status, scenarios, results, templates);
        } catch (error) {
            console.error('Error fetching scenarios data:', error);
        }
    }

    updateScenariosDisplay(status, scenarios, results, templates) {
        this.currentScenarios = scenarios.scenarios || [];
        this.scenarioTemplates = templates.templates || [];

        // Update metrics
        document.getElementById('scenarios-total-count').textContent = status.total_scenarios || 0;
        document.getElementById('scenarios-templates-count').textContent = status.total_templates || 0;

        const byStatus = status.by_status || {};
        document.getElementById('scenarios-completed-count').textContent = byStatus.completed || 0;
        document.getElementById('scenarios-failed-count').textContent = byStatus.failed || 0;

        // Update count label
        const countLabel = document.getElementById('scenarios-count-label');
        if (countLabel) {
            countLabel.textContent = `${this.currentScenarios.length} scenarios`;
        }

        // Render scenarios table
        this.renderScenariosTable(this.currentScenarios);

        // Render results table
        this.renderScenariosResultsTable(results.results || []);
    }

    renderScenariosTable(scenarios) {
        const table = document.getElementById('scenarios-table');
        if (!table) return;

        if (!scenarios || scenarios.length === 0) {
            table.innerHTML = '<tr><td colspan="6" class="empty-state">No scenarios. Create one to get started.</td></tr>';
            return;
        }

        const statusColors = {
            draft: '#6b7280',
            ready: '#3b82f6',
            running: '#f59e0b',
            completed: '#22c55e',
            failed: '#ef4444',
            aborted: '#ef4444'
        };

        let html = '';
        for (const s of scenarios) {
            const statusColor = statusColors[s.status] || '#6b7280';

            html += `
                <tr>
                    <td>
                        <strong>${s.name}</strong>
                        ${s.description ? `<br><small style="color: var(--text-secondary);">${s.description.substring(0, 50)}...</small>` : ''}
                    </td>
                    <td><span style="text-transform: capitalize;">${s.category}</span></td>
                    <td>${s.step_count || 0}</td>
                    <td><span class="status-badge" style="background: ${statusColor}22; color: ${statusColor};">${s.status}</span></td>
                    <td>${s.updated_at ? new Date(s.updated_at).toLocaleDateString() : '-'}</td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-sm btn-secondary" onclick="dashboard.editScenario('${s.scenario_id}')" title="Edit">Edit</button>
                            ${s.status === 'ready' ? `<button class="btn btn-sm btn-primary" onclick="dashboard.runScenarioById('${s.scenario_id}')" title="Run">Run</button>` : ''}
                            <button class="btn btn-sm btn-secondary" onclick="dashboard.deleteScenario('${s.scenario_id}')" title="Delete" style="color: #ef4444;">Del</button>
                        </div>
                    </td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    renderScenariosResultsTable(results) {
        const table = document.getElementById('scenarios-results-table');
        if (!table) return;

        if (!results || results.length === 0) {
            table.innerHTML = '<tr><td colspan="6" class="empty-state">No results yet</td></tr>';
            return;
        }

        const statusColors = {
            completed: '#22c55e',
            failed: '#ef4444',
            aborted: '#f59e0b'
        };

        let html = '';
        for (const r of results.slice(0, 10)) {
            const statusColor = statusColors[r.status] || '#6b7280';
            const durationMs = r.duration_ms || 0;
            const duration = durationMs > 1000 ? `${(durationMs / 1000).toFixed(1)}s` : `${durationMs}ms`;

            html += `
                <tr>
                    <td>${r.scenario_id}</td>
                    <td><span class="status-badge" style="background: ${statusColor}22; color: ${statusColor};">${r.status}</span></td>
                    <td>${r.total_steps || 0}</td>
                    <td style="color: #22c55e;">${r.passed_steps || 0}</td>
                    <td style="color: #ef4444;">${r.failed_steps || 0}</td>
                    <td>${duration}</td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    filterScenarios() {
        const categoryFilter = document.getElementById('scenarios-category-filter').value;
        const statusFilter = document.getElementById('scenarios-status-filter').value;

        let filtered = [...this.currentScenarios];

        if (categoryFilter) {
            filtered = filtered.filter(s => s.category === categoryFilter);
        }
        if (statusFilter) {
            filtered = filtered.filter(s => s.status === statusFilter);
        }

        this.renderScenariosTable(filtered);

        const countLabel = document.getElementById('scenarios-count-label');
        if (countLabel) {
            countLabel.textContent = `${filtered.length} scenarios (filtered)`;
        }
    }

    showCreateScenarioModal() {
        document.getElementById('create-scenario-modal').style.display = 'flex';
        document.getElementById('new-scenario-name').value = '';
        document.getElementById('new-scenario-description').value = '';
        document.getElementById('new-scenario-category').value = 'general';
        document.getElementById('new-scenario-tags').value = '';
    }

    hideCreateScenarioModal() {
        document.getElementById('create-scenario-modal').style.display = 'none';
    }

    async createScenario() {
        const name = document.getElementById('new-scenario-name').value.trim();
        const description = document.getElementById('new-scenario-description').value.trim();
        const category = document.getElementById('new-scenario-category').value;
        const tags = document.getElementById('new-scenario-tags').value.trim();

        if (!name) {
            alert('Please enter a scenario name');
            return;
        }

        try {
            const params = new URLSearchParams({
                name,
                description,
                category
            });
            if (tags) params.append('tags', tags);

            const response = await fetch(`/api/scenarios?${params}`, { method: 'POST' });
            const result = await response.json();

            if (result.created) {
                this.hideCreateScenarioModal();
                this.fetchScenariosData();
                this.editScenario(result.scenario.scenario_id);
            } else {
                alert('Failed to create scenario: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating scenario:', error);
        }
    }

    editScenario(scenarioId) {
        this.currentScenarioId = scenarioId;
        const scenario = this.currentScenarios.find(s => s.scenario_id === scenarioId);
        if (!scenario) return;

        document.getElementById('scenario-editor').style.display = 'block';
        document.getElementById('scenario-editor-title').textContent = `Edit: ${scenario.name}`;

        this.renderScenarioSteps(scenario.steps || []);
    }

    closeScenarioEditor() {
        document.getElementById('scenario-editor').style.display = 'none';
        this.currentScenarioId = null;
    }

    renderScenarioSteps(steps) {
        const container = document.getElementById('scenario-steps-container');
        if (!container) return;

        if (!steps || steps.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No steps defined. Click "Add Step" to add steps to this scenario.</p>';
            return;
        }

        const stepTypeIcons = {
            verify_connectivity: '🔗',
            verify_route: '🛣️',
            verify_neighbor: '🤝',
            verify_convergence: '⏱️',
            interface_up: '🟢',
            interface_down: '🔴',
            link_fail: '💥',
            link_restore: '🔧',
            traffic_start: '📤',
            traffic_stop: '📥',
            wait: '⏳',
            checkpoint: '💾',
            log_message: '📝',
            config_change: '⚙️'
        };

        let html = '';
        for (let i = 0; i < steps.length; i++) {
            const step = steps[i];
            const icon = stepTypeIcons[step.step_type] || '▶️';

            html += `
                <div class="scenario-step" style="background: var(--bg-tertiary); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #8b5cf6;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <span style="font-size: 1.1rem; margin-right: 8px;">${icon}</span>
                            <strong>${i + 1}. ${step.name}</strong>
                            <span class="status-badge" style="margin-left: 8px; font-size: 0.75rem;">${step.step_type}</span>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.removeStep('${step.step_id}')" style="color: #ef4444; padding: 2px 8px;">×</button>
                    </div>
                    ${step.description ? `<p style="color: var(--text-secondary); margin: 5px 0 0 30px; font-size: 0.85rem;">${step.description}</p>` : ''}
                    ${Object.keys(step.parameters || {}).length > 0 ? `<p style="color: var(--accent-cyan); margin: 5px 0 0 30px; font-size: 0.8rem;">Params: ${JSON.stringify(step.parameters)}</p>` : ''}
                </div>
            `;
        }

        container.innerHTML = html;
    }

    addScenarioStep() {
        if (!this.currentScenarioId) return;
        document.getElementById('add-step-modal').style.display = 'flex';
        document.getElementById('step-name').value = '';
        document.getElementById('step-description').value = '';
        document.getElementById('step-type').value = 'verify_connectivity';
        document.getElementById('step-timeout').value = 60;
        document.getElementById('step-continue-on-failure').checked = false;
        this.updateStepParams();
    }

    hideAddStepModal() {
        document.getElementById('add-step-modal').style.display = 'none';
    }

    updateStepParams() {
        const stepType = document.getElementById('step-type').value;
        const container = document.getElementById('step-params-container');

        const paramTemplates = {
            verify_connectivity: `
                <div class="form-group"><label>Source Agent</label><input type="text" id="param-source" placeholder="router-1"></div>
                <div class="form-group"><label>Destination</label><input type="text" id="param-destination" placeholder="10.0.0.1"></div>
            `,
            verify_route: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Prefix</label><input type="text" id="param-prefix" placeholder="10.0.0.0/24"></div>
                <div class="form-group"><label>Expected Next Hop</label><input type="text" id="param-next_hop" placeholder="10.0.0.2"></div>
            `,
            verify_neighbor: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Neighbor</label><input type="text" id="param-neighbor" placeholder="router-2"></div>
                <div class="form-group"><label>Protocol</label><select id="param-protocol"><option value="ospf">OSPF</option><option value="bgp">BGP</option><option value="isis">IS-IS</option></select></div>
            `,
            verify_convergence: `
                <div class="form-group"><label>Timeout (seconds)</label><input type="number" id="param-timeout" value="30" min="1"></div>
            `,
            interface_up: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Interface</label><input type="text" id="param-interface" placeholder="eth0"></div>
            `,
            interface_down: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Interface</label><input type="text" id="param-interface" placeholder="eth0"></div>
            `,
            link_fail: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Interface</label><input type="text" id="param-interface" placeholder="eth0"></div>
            `,
            link_restore: `
                <div class="form-group"><label>Agent</label><input type="text" id="param-agent" placeholder="router-1"></div>
                <div class="form-group"><label>Interface</label><input type="text" id="param-interface" placeholder="eth0"></div>
            `,
            traffic_start: `
                <div class="form-group"><label>Source</label><input type="text" id="param-source" placeholder="router-1"></div>
                <div class="form-group"><label>Destination</label><input type="text" id="param-destination" placeholder="router-2"></div>
                <div class="form-group"><label>Rate (Mbps)</label><input type="number" id="param-rate" value="10" min="1"></div>
            `,
            traffic_stop: `
                <div class="form-group"><label>Source</label><input type="text" id="param-source" placeholder="router-1"></div>
                <div class="form-group"><label>Destination</label><input type="text" id="param-destination" placeholder="router-2"></div>
            `,
            wait: `
                <div class="form-group"><label>Duration (seconds)</label><input type="number" id="param-duration" value="5" min="1"></div>
            `,
            checkpoint: `
                <div class="form-group"><label>Checkpoint Name</label><input type="text" id="param-checkpoint_name" placeholder="baseline"></div>
            `,
            log_message: `
                <div class="form-group"><label>Message</label><input type="text" id="param-message" placeholder="Starting test..."></div>
                <div class="form-group"><label>Level</label><select id="param-level"><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option></select></div>
            `
        };

        container.innerHTML = paramTemplates[stepType] || '';
    }

    async confirmAddStep() {
        if (!this.currentScenarioId) return;

        const stepType = document.getElementById('step-type').value;
        const name = document.getElementById('step-name').value.trim();
        const description = document.getElementById('step-description').value.trim();
        const timeout = parseInt(document.getElementById('step-timeout').value) || 60;
        const continueOnFailure = document.getElementById('step-continue-on-failure').checked;

        if (!name) {
            alert('Please enter a step name');
            return;
        }

        // Collect parameters
        const parameters = {};
        const paramInputs = document.querySelectorAll('#step-params-container input, #step-params-container select');
        for (const input of paramInputs) {
            const paramName = input.id.replace('param-', '');
            const value = input.type === 'number' ? parseInt(input.value) : input.value.trim();
            if (value !== '' && value !== 0) {
                parameters[paramName] = value;
            }
        }

        try {
            const params = new URLSearchParams({
                step_type: stepType,
                name,
                description,
                timeout: timeout.toString(),
                continue_on_failure: continueOnFailure.toString()
            });

            // Add parameters as JSON body
            const response = await fetch(`/api/scenarios/${this.currentScenarioId}/step?${params}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parameters })
            });

            const result = await response.json();

            if (result.added) {
                this.hideAddStepModal();
                this.fetchScenariosData();
                // Re-open editor with updated scenario
                setTimeout(() => this.editScenario(this.currentScenarioId), 500);
            } else {
                alert('Failed to add step: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error adding step:', error);
        }
    }

    async removeStep(stepId) {
        if (!this.currentScenarioId || !confirm('Remove this step?')) return;

        try {
            const response = await fetch(`/api/scenarios/${this.currentScenarioId}/step/${stepId}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.removed) {
                this.fetchScenariosData();
                setTimeout(() => this.editScenario(this.currentScenarioId), 500);
            }
        } catch (error) {
            console.error('Error removing step:', error);
        }
    }

    async runScenario(dryRun = false) {
        if (!this.currentScenarioId) return;

        // First mark as ready
        await fetch(`/api/scenarios/${this.currentScenarioId}/ready`, { method: 'POST' });

        this.runScenarioById(this.currentScenarioId, dryRun);
    }

    async runScenarioById(scenarioId, dryRun = false) {
        try {
            const params = new URLSearchParams({ dry_run: dryRun.toString() });
            const response = await fetch(`/api/scenarios/${scenarioId}/run?${params}`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.started) {
                alert(`Scenario ${dryRun ? '(Dry Run) ' : ''}completed!\nPassed: ${result.result.passed_steps}/${result.result.total_steps}`);
                this.fetchScenariosData();
            } else {
                alert('Failed to run scenario: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error running scenario:', error);
        }
    }

    async deleteScenario(scenarioId) {
        if (!confirm('Delete this scenario?')) return;

        try {
            const response = await fetch(`/api/scenarios/${scenarioId}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.deleted) {
                this.fetchScenariosData();
                if (this.currentScenarioId === scenarioId) {
                    this.closeScenarioEditor();
                }
            }
        } catch (error) {
            console.error('Error deleting scenario:', error);
        }
    }

    showTemplatesModal() {
        document.getElementById('templates-modal').style.display = 'flex';
        this.renderTemplatesList();
    }

    hideTemplatesModal() {
        document.getElementById('templates-modal').style.display = 'none';
    }

    renderTemplatesList() {
        const container = document.getElementById('templates-list');
        if (!container) return;

        if (!this.scenarioTemplates || this.scenarioTemplates.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No templates available</p>';
            return;
        }

        let html = '';
        for (const t of this.scenarioTemplates) {
            html += `
                <div class="template-card" style="background: var(--bg-tertiary); border-radius: 8px; padding: 15px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong>${t.name}</strong>
                            <span class="status-badge" style="margin-left: 10px;">${t.category}</span>
                        </div>
                        <button class="btn btn-primary btn-sm" onclick="dashboard.useTemplate('${t.scenario_id}')">Use</button>
                    </div>
                    <p style="color: var(--text-secondary); margin: 8px 0; font-size: 0.9rem;">${t.description}</p>
                    <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                        ${(t.tags || []).map(tag => `<span style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">${tag}</span>`).join('')}
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.8rem; margin-top: 8px;">${t.step_count || 0} steps</p>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    async useTemplate(templateId) {
        const name = prompt('Enter a name for this scenario:');
        if (!name) return;

        try {
            const response = await fetch('/api/scenarios/from-template', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    template_id: templateId,
                    name,
                    variables: {}
                })
            });

            const result = await response.json();

            if (result.created) {
                this.hideTemplatesModal();
                this.fetchScenariosData();
                setTimeout(() => this.editScenario(result.scenario.scenario_id), 500);
            } else {
                alert('Failed to create from template: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error using template:', error);
        }
    }

    // ==================== MULTI-VENDOR SIMULATION TAB ====================

    currentVendors = [];
    currentCapabilities = [];
    selectedVendorId = null;

    async fetchVendorsData() {
        try {
            const [statusRes, vendorsRes, capsRes] = await Promise.all([
                fetch('/api/vendors/status'),
                fetch('/api/vendors'),
                fetch('/api/vendors/capabilities')
            ]);

            const status = await statusRes.json();
            const vendors = await vendorsRes.json();
            const caps = await capsRes.json();

            this.updateVendorsDisplay(status, vendors, caps);
        } catch (error) {
            console.error('Error fetching vendors data:', error);
        }
    }

    updateVendorsDisplay(status, vendors, caps) {
        this.currentVendors = vendors.vendors || [];
        this.currentCapabilities = caps.capabilities || [];

        // Update metrics
        document.getElementById('vendors-total-count').textContent = status.total_vendors || 0;

        const capSupported = status.capabilities_supported || {};
        document.getElementById('vendors-capabilities-count').textContent = Object.keys(capSupported).length;
        document.getElementById('vendors-netconf-count').textContent = capSupported.netconf || 0;
        document.getElementById('vendors-sr-count').textContent = (capSupported.sr_mpls || 0) + (capSupported.srv6 || 0);

        // Update count label
        const countLabel = document.getElementById('vendors-count-label');
        if (countLabel) {
            countLabel.textContent = `${this.currentVendors.length} vendors`;
        }

        // Render vendors grid
        this.renderVendorsGrid(this.currentVendors);

        // Render capabilities
        this.renderCapabilitiesList(capSupported);

        // Populate translator selectors
        this.populateVendorSelectors();
    }

    renderVendorsGrid(vendors) {
        const container = document.getElementById('vendors-grid');
        if (!container) return;

        if (!vendors || vendors.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No vendors available</p>';
            return;
        }

        const vendorColors = {
            'cisco': '#049fd9',
            'juniper': '#84b135',
            'arista': '#003d79',
            'nokia': '#124191',
            'frrouting': '#ff6b6b'
        };

        let html = '';
        for (const v of vendors) {
            const color = vendorColors[v.name] || '#6b7280';
            const capCount = v.capabilities?.length || 0;

            html += `
                <div class="vendor-card" style="background: var(--bg-tertiary); border-radius: 12px; padding: 20px; border-left: 4px solid ${color}; cursor: pointer;" onclick="dashboard.showVendorDetails('${v.vendor_id}')">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                        <div>
                            <h4 style="color: ${color}; margin-bottom: 4px;">${v.display_name}</h4>
                            <span style="color: var(--text-secondary); font-size: 0.85rem;">${v.os_name} ${v.os_version}</span>
                        </div>
                        <span class="status-badge" style="background: ${color}22; color: ${color};">${capCount} caps</span>
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 12px;">${v.description}</p>
                    <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                        ${(v.capabilities || []).slice(0, 6).map(c => `
                            <span style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; text-transform: uppercase;">${c}</span>
                        `).join('')}
                        ${(v.capabilities || []).length > 6 ? `<span style="color: var(--text-secondary); font-size: 0.7rem;">+${v.capabilities.length - 6} more</span>` : ''}
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    async showVendorDetails(vendorId) {
        this.selectedVendorId = vendorId;

        try {
            const [vendorRes, cliRes, profileRes] = await Promise.all([
                fetch(`/api/vendors/${vendorId}`),
                fetch(`/api/vendors/${vendorId}/cli`),
                fetch(`/api/vendors/${vendorId}/profile`)
            ]);

            const vendor = await vendorRes.json();
            const cli = await cliRes.json();
            const profile = await profileRes.json();

            if (vendor.vendor) {
                document.getElementById('vendor-details-section').style.display = 'block';
                document.getElementById('vendor-details-title').textContent = vendor.vendor.display_name;

                this.renderVendorProfile(profile.profile);
                this.renderVendorCLI(cli.cli_syntax);
            }
        } catch (error) {
            console.error('Error fetching vendor details:', error);
        }
    }

    closeVendorDetails() {
        document.getElementById('vendor-details-section').style.display = 'none';
        this.selectedVendorId = null;
    }

    renderVendorProfile(profile) {
        const container = document.getElementById('vendor-profile-details');
        if (!container || !profile) return;

        const items = [
            { label: 'Boot Time', value: `${profile.boot_time_seconds}s` },
            { label: 'OSPF Dead Interval', value: `${profile.ospf_default_dead_interval}s` },
            { label: 'OSPF Hello Interval', value: `${profile.ospf_default_hello_interval}s` },
            { label: 'BGP Hold Time', value: `${profile.bgp_default_hold_time}s` },
            { label: 'BGP Keepalive', value: `${profile.bgp_default_keepalive}s` },
            { label: 'Default MTU', value: profile.default_mtu },
            { label: 'OSPF Cost', value: profile.default_ospf_cost },
            { label: 'Auto-Cost Ref BW', value: `${profile.auto_cost_reference_bandwidth} Mbps` },
            { label: 'Max Routes', value: profile.max_routes?.toLocaleString() },
            { label: 'Max BGP Peers', value: profile.max_bgp_peers },
            { label: 'Max OSPF Neighbors', value: profile.max_ospf_neighbors },
            { label: 'IPv6 Support', value: profile.supports_ipv6_default ? 'Yes' : 'No' },
            { label: 'Commit Required', value: profile.config_commit_required ? 'Yes' : 'No' },
            { label: 'Enable Password', value: profile.requires_enable_password ? 'Required' : 'Not required' },
        ];

        let html = '';
        for (const item of items) {
            html += `
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-color);">
                    <span style="color: var(--text-secondary);">${item.label}</span>
                    <span style="color: var(--text-primary); font-family: monospace;">${item.value}</span>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    renderVendorCLI(cli) {
        const container = document.getElementById('vendor-cli-details');
        if (!container || !cli) return;

        const categories = {
            'Show Commands': ['show_version', 'show_interfaces', 'show_ip_route', 'show_ipv6_route', 'show_running_config'],
            'OSPF': ['show_ospf_neighbors', 'show_ospf_routes', 'show_ospf_database'],
            'BGP': ['show_bgp_summary', 'show_bgp_neighbors', 'show_bgp_routes'],
            'Interface Config': ['interface_config', 'ip_address', 'ipv6_address', 'shutdown', 'no_shutdown'],
            'Routing Config': ['router_ospf', 'router_bgp', 'network_statement'],
            'Mode': ['config_mode', 'exit_config', 'commit'],
            'Prompts': ['exec_prompt', 'privileged_prompt', 'config_prompt'],
        };

        let html = '';
        for (const [category, commands] of Object.entries(categories)) {
            html += `<h5 style="color: var(--accent-cyan); margin: 12px 0 8px 0; font-size: 0.85rem;">${category}</h5>`;
            for (const cmd of commands) {
                const value = cli[cmd] || '-';
                html += `
                    <div style="display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.8rem;">
                        <span style="color: var(--text-secondary);">${cmd.replace(/_/g, ' ')}</span>
                        <code style="color: #4ade80; background: var(--bg-secondary); padding: 1px 6px; border-radius: 3px;">${value}</code>
                    </div>
                `;
            }
        }

        container.innerHTML = html;
    }

    renderCapabilitiesList(capSupported) {
        const container = document.getElementById('vendors-capabilities-list');
        if (!container) return;

        const capColors = {
            ospf: '#3b82f6', ospfv3: '#3b82f6', bgp: '#8b5cf6', isis: '#f59e0b',
            mpls: '#10b981', evpn: '#ec4899', vxlan: '#06b6d4',
            netconf: '#14b8a6', restconf: '#14b8a6', snmp: '#6b7280',
            acl: '#ef4444', firewall: '#ef4444', bfd: '#facc15',
            sr_mpls: '#f97316', srv6: '#f97316', lacp: '#8b5cf6', lldp: '#06b6d4',
        };

        let html = '';
        for (const [cap, count] of Object.entries(capSupported).sort((a, b) => b[1] - a[1])) {
            const color = capColors[cap] || '#6b7280';
            html += `
                <span class="capability-badge" style="background: ${color}22; color: ${color}; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; display: flex; align-items: center; gap: 5px;" onclick="dashboard.filterByCapability('${cap}')">
                    ${cap.toUpperCase()}
                    <span style="background: ${color}44; padding: 1px 6px; border-radius: 10px; font-size: 0.7rem;">${count}</span>
                </span>
            `;
        }

        container.innerHTML = html;
    }

    filterByCapability(capability) {
        // Filter vendors by capability
        const filtered = this.currentVendors.filter(v =>
            v.capabilities && v.capabilities.includes(capability)
        );
        this.renderVendorsGrid(filtered);

        const countLabel = document.getElementById('vendors-count-label');
        if (countLabel) {
            countLabel.textContent = `${filtered.length} vendors with ${capability.toUpperCase()}`;
        }
    }

    populateVendorSelectors() {
        const fromSelect = document.getElementById('translate-from-vendor');
        const toSelect = document.getElementById('translate-to-vendor');

        if (!fromSelect || !toSelect) return;

        let html = '<option value="">-- Select Vendor --</option>';
        for (const v of this.currentVendors) {
            html += `<option value="${v.vendor_id}">${v.display_name}</option>`;
        }

        fromSelect.innerHTML = html;
        toSelect.innerHTML = html;
    }

    async translateCommand() {
        const fromVendor = document.getElementById('translate-from-vendor').value;
        const toVendor = document.getElementById('translate-to-vendor').value;
        const command = document.getElementById('translate-command').value.trim();

        if (!fromVendor || !toVendor || !command) {
            alert('Please select vendors and enter a command');
            return;
        }

        try {
            const params = new URLSearchParams({
                command,
                from_vendor: fromVendor,
                to_vendor: toVendor
            });

            const response = await fetch(`/api/vendors/translate?${params}`, { method: 'POST' });
            const result = await response.json();

            const resultDiv = document.getElementById('translate-result');
            if (resultDiv) {
                resultDiv.style.display = 'block';
                if (result.success) {
                    resultDiv.innerHTML = `
                        <div style="margin-bottom: 10px;">
                            <span style="color: var(--text-secondary);">Original (${fromVendor}):</span>
                            <code style="display: block; padding: 8px; margin-top: 4px; background: var(--bg-secondary); border-radius: 4px; color: #ef4444;">${result.original_command}</code>
                        </div>
                        <div>
                            <span style="color: var(--text-secondary);">Translated (${toVendor}):</span>
                            <code style="display: block; padding: 8px; margin-top: 4px; background: var(--bg-secondary); border-radius: 4px; color: #4ade80;">${result.translated_command}</code>
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `<span style="color: #ef4444;">Translation not available for this command</span>`;
                }
            }
        } catch (error) {
            console.error('Error translating command:', error);
        }
    }

    // ==================== CHAOS ENGINEERING TAB ====================

    chaosFailures = [];
    chaosHistory = [];
    chaosScenarios = [];

    async fetchChaosData() {
        try {
            const [statusRes, failuresRes, historyRes, scenariosRes] = await Promise.all([
                fetch('/api/chaos/status'),
                fetch('/api/chaos/failures'),
                fetch('/api/chaos/history?limit=20'),
                fetch('/api/chaos/scenarios')
            ]);

            const status = await statusRes.json();
            const failures = await failuresRes.json();
            const history = await historyRes.json();
            const scenarios = await scenariosRes.json();

            this.updateChaosDisplay(status, failures, history, scenarios);
        } catch (error) {
            console.error('Error fetching chaos data:', error);
        }
    }

    updateChaosDisplay(status, failures, history, scenarios) {
        this.chaosFailures = failures.failures || [];
        this.chaosHistory = history.history || [];
        this.chaosScenarios = scenarios.scenarios || [];

        // Update metrics
        document.getElementById('chaos-active-count').textContent = status.active_failures || 0;
        document.getElementById('chaos-total-count').textContent = status.total_injected || 0;

        const avgRecovery = status.avg_recovery_ms;
        if (avgRecovery && avgRecovery > 0) {
            document.getElementById('chaos-avg-recovery').textContent = avgRecovery > 1000 ?
                `${(avgRecovery / 1000).toFixed(1)}s` : `${avgRecovery.toFixed(0)}ms`;
        } else {
            document.getElementById('chaos-avg-recovery').textContent = '-';
        }

        document.getElementById('chaos-scenarios-count').textContent = status.scenarios_run || 0;

        // Update active label
        const activeLabel = document.getElementById('chaos-active-label');
        if (activeLabel) {
            activeLabel.textContent = `${this.chaosFailures.length} active`;
        }

        // Render tables
        this.renderChaosActiveTable(this.chaosFailures);
        this.renderChaosHistoryTable(this.chaosHistory);
        this.renderChaosScenariosGrid(this.chaosScenarios);
    }

    renderChaosActiveTable(failures) {
        const table = document.getElementById('chaos-active-table');
        if (!table) return;

        if (!failures || failures.length === 0) {
            table.innerHTML = '<tr><td colspan="6" class="empty-state">No active failures</td></tr>';
            return;
        }

        let html = '';
        for (const f of failures) {
            const started = new Date(f.start_time).toLocaleTimeString();
            const typeLabel = f.config?.failure_type || f.failure_type || 'unknown';

            html += `
                <tr>
                    <td style="font-family: monospace; font-size: 0.8rem;">${f.failure_id}</td>
                    <td><span class="status-badge" style="background: #ef444422; color: #ef4444;">${typeLabel}</span></td>
                    <td>${f.config?.target_agent || '-'}${f.config?.target_link ? ` (${f.config.target_link})` : ''}</td>
                    <td>${started}</td>
                    <td>${f.config?.duration_seconds || 0}s</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.clearFailure('${f.failure_id}')" style="color: #4ade80;">Clear</button>
                    </td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    renderChaosHistoryTable(history) {
        const table = document.getElementById('chaos-history-table');
        if (!table) return;

        if (!history || history.length === 0) {
            table.innerHTML = '<tr><td colspan="6" class="empty-state">No history</td></tr>';
            return;
        }

        let html = '';
        for (const h of history) {
            const time = h.start_time ? new Date(h.start_time).toLocaleString() : '-';
            const typeLabel = h.config?.failure_type || h.failure_type || 'unknown';
            const statusClass = h.status === 'cleared' ? 'success' :
                               h.status === 'failed' ? 'danger' : 'warning';
            const recovery = h.recovery_time_ms ?
                (h.recovery_time_ms > 1000 ? `${(h.recovery_time_ms / 1000).toFixed(1)}s` : `${h.recovery_time_ms}ms`) : '-';

            html += `
                <tr>
                    <td style="font-size: 0.85rem;">${time}</td>
                    <td><span class="status-badge">${typeLabel}</span></td>
                    <td>${h.config?.target_agent || '-'}</td>
                    <td>${h.config?.duration_seconds || 0}s</td>
                    <td>${recovery}</td>
                    <td><span class="status-badge ${statusClass}">${h.status}</span></td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    renderChaosScenariosGrid(scenarios) {
        const container = document.getElementById('chaos-scenarios-list');
        if (!container) return;

        if (!scenarios || scenarios.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No chaos scenarios available</p>';
            return;
        }

        const severityColors = {
            low: '#22c55e',
            medium: '#facc15',
            high: '#f97316',
            critical: '#ef4444'
        };

        let html = '';
        for (const s of scenarios) {
            const color = severityColors[s.severity] || '#6b7280';

            html += `
                <div class="chaos-scenario-card" style="background: var(--bg-tertiary); border-radius: 12px; padding: 15px; border-left: 4px solid ${color};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                        <div>
                            <h4 style="color: var(--text-primary); margin-bottom: 4px;">${s.name}</h4>
                            <span class="status-badge" style="background: ${color}22; color: ${color};">${s.severity || 'medium'}</span>
                        </div>
                        <button class="btn btn-sm btn-primary" onclick="dashboard.runChaosScenario('${s.id}')" style="background: #ef4444; border-color: #ef4444;">Run</button>
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.85rem;">${s.description || 'No description'}</p>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    showInjectFailureModal() {
        document.getElementById('inject-failure-modal').style.display = 'flex';
        document.getElementById('failure-type').value = 'link_down';
        document.getElementById('failure-target-agent').value = '';
        document.getElementById('failure-target-link').value = '';
        document.getElementById('failure-duration').value = '60';
        document.getElementById('failure-intensity').value = '1.0';
    }

    hideInjectFailureModal() {
        document.getElementById('inject-failure-modal').style.display = 'none';
    }

    async injectFailure() {
        const failureType = document.getElementById('failure-type').value;
        const targetAgent = document.getElementById('failure-target-agent').value.trim();
        const targetLink = document.getElementById('failure-target-link').value.trim();
        const duration = parseInt(document.getElementById('failure-duration').value) || 60;
        const intensity = parseFloat(document.getElementById('failure-intensity').value) || 1.0;

        if (!targetAgent) {
            alert('Please enter a target agent');
            return;
        }

        if (!confirm(`WARNING: This will inject a ${failureType} failure on ${targetAgent}. Continue?`)) {
            return;
        }

        try {
            const response = await fetch('/api/chaos/inject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    failure_type: failureType,
                    target_agent: targetAgent,
                    target_link: targetLink || null,
                    duration_seconds: duration,
                    intensity: intensity
                })
            });

            const result = await response.json();

            if (result.failure_id) {
                this.hideInjectFailureModal();
                this.fetchChaosData();
                alert(`Failure injected: ${result.failure_id}`);
            } else {
                alert('Failed to inject failure: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error injecting failure:', error);
        }
    }

    async clearFailure(failureId) {
        try {
            const response = await fetch(`/api/chaos/clear/${failureId}`, { method: 'POST' });
            const result = await response.json();

            if (result.cleared) {
                this.fetchChaosData();
            } else {
                alert('Failed to clear failure');
            }
        } catch (error) {
            console.error('Error clearing failure:', error);
        }
    }

    async clearAllFailures() {
        if (!confirm('Clear ALL active failures?')) return;

        try {
            await fetch('/api/chaos/clear-all', { method: 'POST' });
            this.fetchChaosData();
        } catch (error) {
            console.error('Error clearing all failures:', error);
        }
    }

    async runChaosScenario(scenarioId) {
        if (!confirm('Run this chaos scenario?')) return;

        try {
            const response = await fetch(`/api/chaos/scenarios/run/${scenarioId}`, { method: 'POST' });
            const result = await response.json();

            if (result.started) {
                alert('Chaos scenario started');
                this.fetchChaosData();
            } else {
                alert('Failed to start scenario: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error running chaos scenario:', error);
        }
    }

    // ==================== CONFIG TEMPLATES TAB ====================

    configTemplates = [];
    configVariables = [];
    configCategories = [];
    currentTemplateId = null;

    async fetchConfigTemplatesData() {
        try {
            const [statsRes, templatesRes, varsRes, catsRes] = await Promise.all([
                fetch('/api/templates/statistics'),
                fetch('/api/templates'),
                fetch('/api/templates/variables'),
                fetch('/api/templates/categories')
            ]);

            const stats = await statsRes.json();
            const templates = await templatesRes.json();
            const vars = await varsRes.json();
            const cats = await catsRes.json();

            this.updateConfigTemplatesDisplay(stats, templates, vars, cats);
        } catch (error) {
            console.error('Error fetching config templates data:', error);
        }
    }

    updateConfigTemplatesDisplay(stats, templates, vars, cats) {
        this.configTemplates = templates.templates || [];
        this.configVariables = vars.variables || [];
        this.configCategories = cats.categories || [];

        // Update metrics
        document.getElementById('config-total-count').textContent = stats.total_templates || 0;
        document.getElementById('config-categories-count').textContent = this.configCategories.length;
        document.getElementById('config-variables-count').textContent = stats.total_variables || 0;
        document.getElementById('config-renders-count').textContent = stats.total_renders || 0;

        // Update count label
        const countLabel = document.getElementById('config-templates-count-label');
        if (countLabel) {
            countLabel.textContent = `${this.configTemplates.length} templates`;
        }

        // Populate category filter
        this.populateCategoryFilter();

        // Render templates grid
        this.renderConfigTemplatesGrid(this.configTemplates);

        // Render variables table
        this.renderConfigVariablesTable(this.configVariables);
    }

    populateCategoryFilter() {
        const select = document.getElementById('config-category-filter');
        if (!select) return;

        let html = '<option value="">All Categories</option>';
        for (const cat of this.configCategories) {
            html += `<option value="${cat.value || cat}">${cat.name || cat}</option>`;
        }
        select.innerHTML = html;
    }

    renderConfigTemplatesGrid(templates) {
        const container = document.getElementById('config-templates-grid');
        if (!container) return;

        if (!templates || templates.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No templates available. Create one to get started.</p>';
            return;
        }

        const categoryColors = {
            routing: '#3b82f6',
            interface: '#10b981',
            security: '#ef4444',
            monitoring: '#f59e0b',
            mpls: '#8b5cf6',
            qos: '#06b6d4',
            custom: '#6b7280'
        };

        let html = '';
        for (const t of templates) {
            const color = categoryColors[t.category] || '#6b7280';
            const isEnabled = t.enabled !== false;

            html += `
                <div class="config-template-card" style="background: var(--bg-tertiary); border-radius: 12px; padding: 15px; border-left: 4px solid ${color}; opacity: ${isEnabled ? 1 : 0.6};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                        <div>
                            <h4 style="color: var(--text-primary); margin-bottom: 4px;">${t.name}</h4>
                            <span class="status-badge" style="background: ${color}22; color: ${color};">${t.category || 'custom'}</span>
                            ${!isEnabled ? '<span class="status-badge" style="margin-left: 5px;">disabled</span>' : ''}
                        </div>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-sm btn-secondary" onclick="dashboard.editConfigTemplate('${t.template_id || t.id}')">Edit</button>
                            <button class="btn btn-sm btn-secondary" onclick="dashboard.cloneConfigTemplate('${t.template_id || t.id}')">Clone</button>
                        </div>
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 10px;">${t.description || 'No description'}</p>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-secondary);">
                        <span>Variables: ${t.variable_count || 0}</span>
                        <span>Used: ${t.render_count || 0} times</span>
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    filterConfigTemplates() {
        const categoryFilter = document.getElementById('config-category-filter').value;
        const searchTerm = document.getElementById('config-search').value.toLowerCase().trim();

        let filtered = [...this.configTemplates];

        if (categoryFilter) {
            filtered = filtered.filter(t => t.category === categoryFilter);
        }

        if (searchTerm) {
            filtered = filtered.filter(t =>
                (t.name && t.name.toLowerCase().includes(searchTerm)) ||
                (t.description && t.description.toLowerCase().includes(searchTerm))
            );
        }

        this.renderConfigTemplatesGrid(filtered);

        const countLabel = document.getElementById('config-templates-count-label');
        if (countLabel) {
            countLabel.textContent = `${filtered.length} templates`;
        }
    }

    renderConfigVariablesTable(variables) {
        const table = document.getElementById('config-variables-table');
        if (!table) return;

        if (!variables || variables.length === 0) {
            table.innerHTML = '<tr><td colspan="5" class="empty-state">No variables defined</td></tr>';
            return;
        }

        let html = '';
        for (const v of variables) {
            html += `
                <tr>
                    <td style="font-family: monospace; color: #a855f7;">\${{ ${v.name} }}</td>
                    <td>${v.type || 'string'}</td>
                    <td>${v.scope || 'global'}</td>
                    <td style="font-family: monospace; font-size: 0.85rem;">${v.default_value || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.deleteConfigVariable('${v.variable_id || v.id}')" style="color: #ef4444;">Del</button>
                    </td>
                </tr>
            `;
        }

        table.innerHTML = html;
    }

    showCreateTemplateModal() {
        document.getElementById('create-template-modal').style.display = 'flex';
        document.getElementById('new-template-name').value = '';
        document.getElementById('new-template-description').value = '';
        document.getElementById('new-template-category').value = 'routing';
        document.getElementById('new-template-content').value = '';
    }

    hideCreateTemplateModal() {
        document.getElementById('create-template-modal').style.display = 'none';
    }

    async createConfigTemplate() {
        const name = document.getElementById('new-template-name').value.trim();
        const description = document.getElementById('new-template-description').value.trim();
        const category = document.getElementById('new-template-category').value;
        const content = document.getElementById('new-template-content').value;

        if (!name) {
            alert('Please enter a template name');
            return;
        }

        try {
            const response = await fetch('/api/templates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, category, content })
            });

            const result = await response.json();

            if (result.template_id || result.id) {
                this.hideCreateTemplateModal();
                this.fetchConfigTemplatesData();
            } else {
                alert('Failed to create template: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating template:', error);
        }
    }

    async editConfigTemplate(templateId) {
        this.currentTemplateId = templateId;

        try {
            const response = await fetch(`/api/templates/${templateId}`);
            const result = await response.json();

            if (result.template) {
                document.getElementById('config-editor-section').style.display = 'block';
                document.getElementById('config-editor-title').textContent = `Edit: ${result.template.name}`;
                document.getElementById('config-template-content').value = result.template.content || '';
                document.getElementById('config-rendered-output').textContent = 'Click "Render" to see output';
            }
        } catch (error) {
            console.error('Error loading template:', error);
        }
    }

    closeConfigEditor() {
        document.getElementById('config-editor-section').style.display = 'none';
        this.currentTemplateId = null;
    }

    async saveConfigTemplate() {
        if (!this.currentTemplateId) return;

        const content = document.getElementById('config-template-content').value;

        try {
            const response = await fetch(`/api/templates/${this.currentTemplateId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });

            const result = await response.json();

            if (result.updated) {
                alert('Template saved');
                this.fetchConfigTemplatesData();
            } else {
                alert('Failed to save template');
            }
        } catch (error) {
            console.error('Error saving template:', error);
        }
    }

    async renderConfigTemplate() {
        if (!this.currentTemplateId) return;

        try {
            const response = await fetch(`/api/templates/${this.currentTemplateId}/render`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ variables: {} })
            });

            const result = await response.json();

            const output = document.getElementById('config-rendered-output');
            if (result.rendered) {
                output.textContent = result.rendered;
                output.style.color = '#4ade80';
            } else {
                output.textContent = 'Error: ' + (result.error || 'Render failed');
                output.style.color = '#ef4444';
            }
        } catch (error) {
            console.error('Error rendering template:', error);
        }
    }

    async cloneConfigTemplate(templateId) {
        const name = prompt('Enter name for cloned template:');
        if (!name) return;

        try {
            const response = await fetch(`/api/templates/${templateId}/clone`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });

            const result = await response.json();

            if (result.template_id || result.id) {
                this.fetchConfigTemplatesData();
            } else {
                alert('Failed to clone template');
            }
        } catch (error) {
            console.error('Error cloning template:', error);
        }
    }

    showAddVariableModal() {
        // For now, use prompt
        const name = prompt('Variable name:');
        if (!name) return;

        const defaultValue = prompt('Default value (optional):');

        this.createConfigVariable(name, defaultValue);
    }

    async createConfigVariable(name, defaultValue) {
        try {
            const response = await fetch('/api/templates/variables', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    type: 'string',
                    scope: 'global',
                    default_value: defaultValue || ''
                })
            });

            const result = await response.json();

            if (result.variable_id || result.id) {
                this.fetchConfigTemplatesData();
            }
        } catch (error) {
            console.error('Error creating variable:', error);
        }
    }

    async deleteConfigVariable(variableId) {
        if (!confirm('Delete this variable?')) return;

        try {
            await fetch(`/api/templates/variables/${variableId}`, { method: 'DELETE' });
            this.fetchConfigTemplatesData();
        } catch (error) {
            console.error('Error deleting variable:', error);
        }
    }

    // ==================== DOCUMENTATION METHODS ====================
    async fetchDocumentationData() {
        try {
            const [statusRes, templatesRes, documentsRes] = await Promise.all([
                fetch('/api/documentation/status'),
                fetch('/api/documentation/templates'),
                fetch('/api/documentation/documents')
            ]);

            const status = await statusRes.json();
            const templates = await templatesRes.json();
            const documents = await documentsRes.json();

            this.docsData = {
                status: status,
                templates: templates.templates || [],
                documents: documents.documents || []
            };

            this.updateDocumentationDisplay();
        } catch (error) {
            console.error('Error fetching documentation data:', error);
        }
    }

    updateDocumentationDisplay() {
        const data = this.docsData || { status: {}, templates: [], documents: [] };
        const status = data.status || {};

        // Update metrics
        document.getElementById('docs-generated-count').textContent = status.documents_generated || data.documents.length || 0;
        document.getElementById('docs-templates-count').textContent = status.templates_available || data.templates.length || 0;
        document.getElementById('docs-formats-count').textContent = (status.export_formats || []).length || 4;
        document.getElementById('docs-sections-count').textContent = (status.section_types || []).length || 20;

        // Update templates grid
        this.renderDocsTemplatesGrid(data.templates);

        // Update documents table
        this.renderDocsDocumentsTable(data.documents);
    }

    renderDocsTemplatesGrid(templates) {
        const container = document.getElementById('docs-templates-grid');
        const label = document.getElementById('docs-templates-label');

        if (!templates || templates.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); padding: 15px;">No templates available</p>';
            label.textContent = '0 templates';
            return;
        }

        label.textContent = `${templates.length} template${templates.length !== 1 ? 's' : ''}`;

        const colors = {
            'full': '#0ea5e9',
            'overview': '#10b981',
            'ip_plan': '#f59e0b',
            'protocol_guide': '#8b5cf6',
            'security': '#ef4444',
            'change_report': '#ec4899'
        };

        container.innerHTML = templates.map(template => `
            <div style="background: var(--bg-secondary); border-radius: 8px; padding: 15px; border-left: 4px solid ${colors[template.template_id] || '#0ea5e9'};">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                    <h4 style="margin: 0; color: var(--text-primary);">${this.escapeHtml(template.name)}</h4>
                    <span style="background: ${colors[template.template_id] || '#0ea5e9'}20; color: ${colors[template.template_id] || '#0ea5e9'}; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">
                        ${template.template_id}
                    </span>
                </div>
                <p style="color: var(--text-secondary); font-size: 0.85rem; margin: 0 0 10px 0;">
                    ${this.escapeHtml(template.description)}
                </p>
                <div style="display: flex; gap: 15px; color: var(--text-secondary); font-size: 0.8rem;">
                    <span>${template.sections ? template.sections.length : 0} sections</span>
                    <span>${template.include_diagrams ? 'Diagrams' : ''}</span>
                    <span>${template.include_tables ? 'Tables' : ''}</span>
                </div>
                <button class="btn btn-secondary" style="margin-top: 10px; font-size: 0.8rem;" onclick="dashboard.useDocTemplate('${template.template_id}')">
                    Use Template
                </button>
            </div>
        `).join('');
    }

    renderDocsDocumentsTable(documents) {
        const tbody = document.getElementById('docs-documents-table');
        const label = document.getElementById('docs-documents-label');

        if (!documents || documents.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No documents generated yet</td></tr>';
            label.textContent = '0 documents';
            return;
        }

        label.textContent = `${documents.length} document${documents.length !== 1 ? 's' : ''}`;

        tbody.innerHTML = documents.map(doc => `
            <tr>
                <td><code style="color: #0ea5e9;">${doc.document_id}</code></td>
                <td>${this.escapeHtml(doc.network_name || 'Unknown')}</td>
                <td>${this.escapeHtml(doc.template_id)}</td>
                <td>${doc.generated_at ? new Date(doc.generated_at).toLocaleString() : 'N/A'}</td>
                <td>${doc.section_count || 0}</td>
                <td>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem;" onclick="dashboard.previewDocument('${doc.document_id}')">
                            Preview
                        </button>
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem;" onclick="dashboard.exportDocument('${doc.document_id}')">
                            Export
                        </button>
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem; color: #ef4444;" onclick="dashboard.deleteDocument('${doc.document_id}')">
                            Delete
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    useDocTemplate(templateId) {
        document.getElementById('docs-template-select').value = templateId;
    }

    async generateDocumentation() {
        const networkName = document.getElementById('docs-network-name').value || 'ASI Network';
        const template = document.getElementById('docs-template-select').value;
        const exportFormat = document.getElementById('docs-export-format').value;

        try {
            // Generate the document
            const genRes = await fetch('/api/documentation/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    network_name: networkName,
                    template: template
                })
            });

            const genData = await genRes.json();
            if (genData.error) {
                alert('Error: ' + genData.error);
                return;
            }

            const docId = genData.document.document_id;

            // Export to selected format
            const exportRes = await fetch(`/api/documentation/documents/${docId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: exportFormat })
            });

            const exportData = await exportRes.json();
            if (exportData.error) {
                alert('Error exporting: ' + exportData.error);
                return;
            }

            // Show preview
            this.showDocumentPreview(docId, exportData.content, exportFormat);

            // Refresh the list
            this.fetchDocumentationData();

        } catch (error) {
            console.error('Error generating documentation:', error);
            alert('Error generating documentation');
        }
    }

    showDocumentPreview(docId, content, format) {
        const section = document.getElementById('docs-preview-section');
        const title = document.getElementById('docs-preview-title');
        const contentEl = document.getElementById('docs-preview-content');

        this.currentDocId = docId;
        this.currentDocContent = content;
        this.currentDocFormat = format;

        title.textContent = `Document Preview - ${docId} (${format.toUpperCase()})`;

        if (format === 'html') {
            // Render HTML in an iframe-like way or sanitized
            contentEl.innerHTML = content;
            contentEl.style.whiteSpace = 'normal';
            contentEl.style.fontFamily = 'inherit';
        } else {
            contentEl.textContent = content;
            contentEl.style.whiteSpace = 'pre-wrap';
            contentEl.style.fontFamily = 'monospace';
        }

        section.style.display = 'block';
    }

    closeDocumentPreview() {
        document.getElementById('docs-preview-section').style.display = 'none';
    }

    async previewDocument(docId) {
        const format = document.getElementById('docs-export-format').value;

        try {
            const res = await fetch(`/api/documentation/documents/${docId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: format })
            });

            const data = await res.json();
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            this.showDocumentPreview(docId, data.content, format);
        } catch (error) {
            console.error('Error previewing document:', error);
        }
    }

    async exportDocument(docId) {
        const format = document.getElementById('docs-export-format').value;

        try {
            const res = await fetch(`/api/documentation/documents/${docId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: format })
            });

            const data = await res.json();
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            // Download as file
            const blob = new Blob([data.content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;

            const extensions = { markdown: 'md', html: 'html', json: 'json', text: 'txt' };
            a.download = `network-doc-${docId}.${extensions[format] || 'txt'}`;

            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

        } catch (error) {
            console.error('Error exporting document:', error);
        }
    }

    downloadDocument() {
        if (this.currentDocContent && this.currentDocId) {
            const format = this.currentDocFormat || 'markdown';
            const extensions = { markdown: 'md', html: 'html', json: 'json', text: 'txt' };

            const blob = new Blob([this.currentDocContent], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `network-doc-${this.currentDocId}.${extensions[format] || 'txt'}`;

            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
    }

    async deleteDocument(docId) {
        if (!confirm('Are you sure you want to delete this document?')) {
            return;
        }

        try {
            await fetch(`/api/documentation/documents/${docId}`, { method: 'DELETE' });
            this.fetchDocumentationData();
            this.closeDocumentPreview();
        } catch (error) {
            console.error('Error deleting document:', error);
        }
    }

    // ==================== ANALYTICS METHODS ====================
    async fetchAnalyticsData() {
        try {
            const [statusRes, endpointsRes, clientsRes, requestsRes, blockedRes, configRes] = await Promise.all([
                fetch('/api/analytics/status'),
                fetch(`/api/analytics/top/endpoints?limit=10&metric=${this.getAnalyticsMetric()}`),
                fetch('/api/analytics/top/clients?limit=10'),
                fetch('/api/analytics/requests?limit=50'),
                fetch('/api/analytics/ratelimit/blocked'),
                fetch('/api/analytics/ratelimit/config')
            ]);

            const status = await statusRes.json();
            const endpoints = await endpointsRes.json();
            const clients = await clientsRes.json();
            const requests = await requestsRes.json();
            const blocked = await blockedRes.json();
            const config = await configRes.json();

            this.analyticsData = {
                status: status,
                endpoints: endpoints.endpoints || [],
                clients: clients.clients || [],
                requests: requests.requests || [],
                blocked: blocked.blocked || [],
                config: config
            };

            this.updateAnalyticsDisplay();
        } catch (error) {
            console.error('Error fetching analytics data:', error);
        }
    }

    getAnalyticsMetric() {
        const select = document.getElementById('analytics-endpoint-metric');
        return select ? select.value : 'requests';
    }

    updateAnalyticsDisplay() {
        const data = this.analyticsData || { status: {}, endpoints: [], clients: [], requests: [], blocked: [], config: {} };
        const status = data.status || {};
        const config = data.config || {};

        // Update metrics
        document.getElementById('analytics-total-requests').textContent = (status.total_requests || 0).toLocaleString();
        document.getElementById('analytics-error-rate').textContent = (status.error_rate || 0) + '%';
        document.getElementById('analytics-unique-endpoints').textContent = status.unique_endpoints || 0;
        document.getElementById('analytics-unique-clients').textContent = status.unique_clients || 0;

        // Update rate limit config
        document.getElementById('analytics-rpm').textContent = config.requests_per_minute || 60;
        document.getElementById('analytics-rph').textContent = config.requests_per_hour || 1000;
        document.getElementById('analytics-burst').textContent = config.burst_limit || 20;
        document.getElementById('analytics-blocked-count').textContent = data.blocked.length;
        document.getElementById('analytics-ratelimit-enabled').checked = config.enabled !== false;

        // Update tables
        this.renderAnalyticsEndpointsTable(data.endpoints);
        this.renderAnalyticsClientsTable(data.clients);
        this.renderAnalyticsRequestsTable(data.requests);
        this.renderAnalyticsBlockedTable(data.blocked);

        // Update labels
        document.getElementById('analytics-clients-label').textContent = `${data.clients.length} clients`;
        document.getElementById('analytics-blocked-label').textContent = `${data.blocked.length} blocked`;
    }

    renderAnalyticsEndpointsTable(endpoints) {
        const tbody = document.getElementById('analytics-endpoints-table');

        if (!endpoints || endpoints.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No data yet</td></tr>';
            return;
        }

        tbody.innerHTML = endpoints.map(ep => `
            <tr>
                <td><code style="color: #6366f1; font-size: 0.85rem;">${this.escapeHtml(ep.endpoint)}</code></td>
                <td>${(ep.total_requests || 0).toLocaleString()}</td>
                <td style="color: ${ep.error_requests > 0 ? '#ef4444' : 'inherit'};">${ep.error_requests || 0}</td>
                <td style="color: ${ep.error_rate > 5 ? '#ef4444' : ep.error_rate > 1 ? '#f59e0b' : '#10b981'};">
                    ${(ep.error_rate || 0).toFixed(1)}%
                </td>
                <td>${(ep.avg_response_time_ms || 0).toFixed(1)}ms</td>
                <td>${(ep.requests_per_minute || 0).toFixed(1)}</td>
            </tr>
        `).join('');
    }

    renderAnalyticsClientsTable(clients) {
        const tbody = document.getElementById('analytics-clients-table');

        if (!clients || clients.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No data yet</td></tr>';
            return;
        }

        tbody.innerHTML = clients.map(client => `
            <tr>
                <td><code style="color: #6366f1;">${this.escapeHtml(client.client_ip)}</code></td>
                <td>${(client.total_requests || 0).toLocaleString()}</td>
                <td style="color: ${client.error_requests > 0 ? '#ef4444' : 'inherit'};">${client.error_requests || 0}</td>
                <td>${(client.avg_response_time_ms || 0).toFixed(1)}ms</td>
                <td>${client.unique_endpoints || 0}</td>
                <td>
                    ${client.is_rate_limited
                        ? '<span style="color: #ef4444;">Blocked</span>'
                        : '<span style="color: #10b981;">Active</span>'}
                </td>
                <td>
                    ${client.is_rate_limited
                        ? `<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="dashboard.unblockClient('${client.client_ip}')">Unblock</button>`
                        : '<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; color: #ef4444;" onclick="dashboard.blockClient(\'' + client.client_ip + '\')">Block</button>'}
                </td>
            </tr>
        `).join('');
    }

    renderAnalyticsRequestsTable(requests) {
        const tbody = document.getElementById('analytics-requests-table');

        if (!requests || requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No requests yet</td></tr>';
            return;
        }

        tbody.innerHTML = requests.slice(0, 50).map(req => {
            const time = new Date(req.timestamp).toLocaleTimeString();
            const isError = req.status_code >= 400;
            const methodColor = {
                'GET': '#10b981',
                'POST': '#6366f1',
                'PUT': '#f59e0b',
                'DELETE': '#ef4444',
                'PATCH': '#8b5cf6'
            }[req.method] || '#6b7280';

            return `
                <tr>
                    <td style="font-size: 0.85rem;">${time}</td>
                    <td><span style="color: ${methodColor}; font-weight: 500;">${req.method}</span></td>
                    <td><code style="font-size: 0.8rem; color: var(--text-secondary);">${this.escapeHtml(req.endpoint)}</code></td>
                    <td style="font-size: 0.85rem;">${req.client_ip}</td>
                    <td style="color: ${isError ? '#ef4444' : '#10b981'}; font-weight: 500;">${req.status_code}</td>
                    <td>${req.response_time_ms.toFixed(1)}ms</td>
                </tr>
            `;
        }).join('');
    }

    renderAnalyticsBlockedTable(blocked) {
        const tbody = document.getElementById('analytics-blocked-table');

        if (!blocked || blocked.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No blocked clients</td></tr>';
            return;
        }

        tbody.innerHTML = blocked.map(client => {
            const until = new Date(client.blocked_until).toLocaleString();
            const remaining = Math.ceil(client.remaining_seconds || 0);

            return `
                <tr>
                    <td><code style="color: #ef4444;">${this.escapeHtml(client.client_ip)}</code></td>
                    <td>${until}</td>
                    <td>${remaining}s</td>
                    <td>
                        <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="dashboard.unblockClient('${client.client_ip}')">
                            Unblock
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    refreshAnalytics() {
        this.fetchAnalyticsData();
    }

    async toggleRateLimit() {
        const enabled = document.getElementById('analytics-ratelimit-enabled').checked;

        try {
            await fetch('/api/analytics/ratelimit/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled })
            });
            this.fetchAnalyticsData();
        } catch (error) {
            console.error('Error toggling rate limit:', error);
        }
    }

    showRateLimitModal() {
        const config = this.analyticsData?.config || {};
        document.getElementById('ratelimit-rpm').value = config.requests_per_minute || 60;
        document.getElementById('ratelimit-rph').value = config.requests_per_hour || 1000;
        document.getElementById('ratelimit-burst').value = config.burst_limit || 20;
        document.getElementById('ratelimit-block-duration').value = config.block_duration_seconds || 60;
        document.getElementById('ratelimit-modal').style.display = 'flex';
    }

    hideRateLimitModal() {
        document.getElementById('ratelimit-modal').style.display = 'none';
    }

    async saveRateLimitConfig() {
        const config = {
            requests_per_minute: parseInt(document.getElementById('ratelimit-rpm').value),
            requests_per_hour: parseInt(document.getElementById('ratelimit-rph').value),
            burst_limit: parseInt(document.getElementById('ratelimit-burst').value),
            block_duration_seconds: parseInt(document.getElementById('ratelimit-block-duration').value)
        };

        try {
            await fetch('/api/analytics/ratelimit/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            this.hideRateLimitModal();
            this.fetchAnalyticsData();
        } catch (error) {
            console.error('Error saving rate limit config:', error);
        }
    }

    async unblockClient(clientIp) {
        try {
            await fetch(`/api/analytics/ratelimit/blocked/${encodeURIComponent(clientIp)}`, {
                method: 'DELETE'
            });
            this.fetchAnalyticsData();
        } catch (error) {
            console.error('Error unblocking client:', error);
        }
    }

    async blockClient(clientIp) {
        // This would need a server endpoint to manually block
        alert(`Manual blocking of ${clientIp} - use rate limit config whitelist/blacklist`);
    }

    // ==================== COMPLIANCE METHODS ====================
    async fetchComplianceData() {
        try {
            const [statusRes, rulesRes, reportsRes] = await Promise.all([
                fetch('/api/compliance/status'),
                fetch('/api/compliance/rules'),
                fetch('/api/compliance/reports?limit=10')
            ]);

            const status = await statusRes.json();
            const rules = await rulesRes.json();
            const reports = await reportsRes.json();

            this.complianceData = {
                status: status,
                rules: rules.rules || [],
                reports: reports.reports || []
            };

            this.updateComplianceDisplay();
        } catch (error) {
            console.error('Error fetching compliance data:', error);
        }
    }

    updateComplianceDisplay() {
        const data = this.complianceData || { status: {}, rules: [], reports: [] };
        const status = data.status || {};
        const reports = data.reports || [];

        // Update metrics
        document.getElementById('compliance-total-rules').textContent = status.total_rules || data.rules.length || 0;
        document.getElementById('compliance-reports-count').textContent = status.reports_generated || reports.length || 0;

        // If there's a latest report, show it
        if (reports.length > 0) {
            const latest = reports[0];
            document.getElementById('compliance-score').textContent = (latest.score || 0).toFixed(0) + '%';
            document.getElementById('compliance-violations').textContent = latest.violation_count || 0;

            // Show report summary
            this.showComplianceReportSummary(latest);
        } else {
            document.getElementById('compliance-score').textContent = '--';
            document.getElementById('compliance-violations').textContent = '0';
        }

        // Update tables
        this.renderComplianceRulesTable(data.rules);
        this.renderComplianceHistoryTable(reports);
    }

    showComplianceReportSummary(report) {
        const section = document.getElementById('compliance-report-section');
        section.style.display = 'block';

        document.getElementById('compliance-report-title').textContent = `Report ${report.report_id}`;
        document.getElementById('compliance-report-time').textContent = new Date(report.generated_at).toLocaleString();

        const bySeverity = report.by_severity || {};
        document.getElementById('compliance-critical').textContent = bySeverity.critical || 0;
        document.getElementById('compliance-high').textContent = bySeverity.high || 0;
        document.getElementById('compliance-medium').textContent = bySeverity.medium || 0;
        document.getElementById('compliance-low').textContent = bySeverity.low || 0;
        document.getElementById('compliance-info').textContent = bySeverity.info || 0;

        // Render violations
        this.renderComplianceViolationsTable(report.violations || []);
    }

    renderComplianceRulesTable(rules) {
        const tbody = document.getElementById('compliance-rules-table');
        const label = document.getElementById('compliance-rules-label');

        if (!rules || rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No rules available</td></tr>';
            label.textContent = '0 rules';
            return;
        }

        label.textContent = `${rules.length} rules`;

        const severityColors = {
            'critical': '#ef4444',
            'high': '#f59e0b',
            'medium': '#eab308',
            'low': '#22c55e',
            'info': '#6b7280'
        };

        tbody.innerHTML = rules.map(rule => `
            <tr>
                <td><code style="color: #f97316;">${rule.rule_id}</code></td>
                <td>${this.escapeHtml(rule.name)}</td>
                <td><span style="background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;">${rule.category}</span></td>
                <td><span style="color: ${severityColors[rule.severity] || '#6b7280'}; font-weight: 500;">${rule.severity}</span></td>
                <td>${rule.enabled ? '<span style="color: #22c55e;">Enabled</span>' : '<span style="color: #6b7280;">Disabled</span>'}</td>
                <td>
                    <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;"
                            onclick="dashboard.toggleComplianceRule('${rule.rule_id}', ${rule.enabled})">
                        ${rule.enabled ? 'Disable' : 'Enable'}
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderComplianceViolationsTable(violations) {
        const tbody = document.getElementById('compliance-violations-table');
        const label = document.getElementById('compliance-violations-label');

        if (!violations || violations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No violations found</td></tr>';
            label.textContent = '0 violations';
            return;
        }

        label.textContent = `${violations.length} violation${violations.length !== 1 ? 's' : ''}`;

        const severityColors = {
            'critical': '#ef4444',
            'high': '#f59e0b',
            'medium': '#eab308',
            'low': '#22c55e',
            'info': '#6b7280'
        };

        tbody.innerHTML = violations.map(v => `
            <tr>
                <td>
                    <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${severityColors[v.severity] || '#6b7280'}; margin-right: 6px;"></span>
                    <span style="color: ${severityColors[v.severity] || '#6b7280'}; font-weight: 500;">${v.severity}</span>
                </td>
                <td>
                    <code style="color: #f97316; font-size: 0.8rem;">${v.rule_id}</code><br>
                    <span style="font-size: 0.85rem;">${this.escapeHtml(v.rule_name)}</span>
                </td>
                <td>${this.escapeHtml(v.agent_id || 'N/A')}</td>
                <td style="font-size: 0.85rem; color: var(--text-secondary);">${this.escapeHtml(v.resource)}</td>
                <td style="font-size: 0.85rem;">${this.escapeHtml(v.description)}</td>
            </tr>
        `).join('');
    }

    renderComplianceHistoryTable(reports) {
        const tbody = document.getElementById('compliance-history-table');
        const label = document.getElementById('compliance-history-label');

        if (!reports || reports.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No reports yet</td></tr>';
            label.textContent = '0 reports';
            return;
        }

        label.textContent = `${reports.length} reports`;

        tbody.innerHTML = reports.map(report => {
            const date = new Date(report.generated_at).toLocaleString();
            const scoreColor = report.score >= 80 ? '#22c55e' : report.score >= 60 ? '#f59e0b' : '#ef4444';

            return `
                <tr>
                    <td><code style="color: #f97316;">${report.report_id}</code></td>
                    <td style="font-size: 0.85rem;">${date}</td>
                    <td>${report.rule_set}</td>
                    <td style="color: ${scoreColor}; font-weight: 600;">${report.score.toFixed(0)}%</td>
                    <td>${report.violation_count || 0}</td>
                    <td>
                        <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;"
                                onclick="dashboard.viewComplianceReport('${report.report_id}')">
                            View
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async runComplianceCheck() {
        const ruleSet = document.getElementById('compliance-rule-set').value;
        const category = document.getElementById('compliance-category').value;

        try {
            const body = { rule_set: ruleSet };
            if (category) {
                body.categories = [category];
            }

            const res = await fetch('/api/compliance/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            const data = await res.json();
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            // Refresh display with new report
            this.fetchComplianceData();

            // Show the new report
            if (data.report) {
                this.showComplianceReportSummary(data.report);
            }

        } catch (error) {
            console.error('Error running compliance check:', error);
            alert('Error running compliance check');
        }
    }

    async toggleComplianceRule(ruleId, isEnabled) {
        const endpoint = isEnabled ? 'disable' : 'enable';

        try {
            await fetch(`/api/compliance/rules/${ruleId}/${endpoint}`, {
                method: 'POST'
            });
            this.fetchComplianceData();
        } catch (error) {
            console.error('Error toggling rule:', error);
        }
    }

    async viewComplianceReport(reportId) {
        try {
            const res = await fetch(`/api/compliance/reports/${reportId}`);
            const data = await res.json();

            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            if (data.report) {
                this.showComplianceReportSummary(data.report);
            }
        } catch (error) {
            console.error('Error viewing report:', error);
        }
    }

    // ==================== EXPORTER METHODS ====================
    async fetchExporterData() {
        try {
            const [statusRes, historyRes] = await Promise.all([
                fetch('/api/exporter/status'),
                fetch('/api/exporter/history?limit=10')
            ]);

            const status = await statusRes.json();
            const history = await historyRes.json();

            this.exporterData = {
                status: status,
                history: history.history || []
            };

            this.updateExporterDisplay();
        } catch (error) {
            console.error('Error fetching exporter data:', error);
        }
    }

    updateExporterDisplay() {
        const data = this.exporterData || { status: {}, history: [] };
        const status = data.status || {};

        // Update metrics
        document.getElementById('exporter-total').textContent = status.total_exports || 0;
        document.getElementById('exporter-formats-count').textContent = (status.supported_formats || []).length || 10;

        // Try to get node/link counts from last export or a rough estimate
        if (data.history.length > 0) {
            document.getElementById('exporter-nodes').textContent = data.history[0].node_count || 0;
            document.getElementById('exporter-links').textContent = data.history[0].link_count || 0;
        }

        // Update history table
        this.renderExporterHistoryTable(data.history);
    }

    renderExporterHistoryTable(history) {
        const tbody = document.getElementById('exporter-history-table');
        const label = document.getElementById('exporter-history-label');

        if (!history || history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No exports yet</td></tr>';
            label.textContent = '0 exports';
            return;
        }

        label.textContent = `${history.length} exports`;

        const formatColors = {
            'dot': '#84cc16',
            'json': '#3b82f6',
            'yaml': '#f59e0b',
            'gns3': '#8b5cf6',
            'containerlab': '#ec4899',
            'netbox': '#06b6d4',
            'd2': '#ef4444',
            'mermaid': '#10b981',
            'cyjs': '#6366f1',
            'csv': '#64748b'
        };

        tbody.innerHTML = history.map(exp => {
            const date = new Date(exp.exported_at).toLocaleString();
            const color = formatColors[exp.format] || '#84cc16';

            return `
                <tr>
                    <td style="font-size: 0.85rem;">${this.escapeHtml(exp.filename)}</td>
                    <td><span style="color: ${color}; font-weight: 500;">${exp.format.toUpperCase()}</span></td>
                    <td>${exp.node_count}</td>
                    <td>${exp.link_count}</td>
                    <td style="font-size: 0.85rem;">${date}</td>
                </tr>
            `;
        }).join('');
    }

    async exportTopology() {
        const format = document.getElementById('exporter-format').value;
        const layout = document.getElementById('exporter-layout').value;
        const includeConfigs = document.getElementById('exporter-configs').checked;
        const includeInterfaces = document.getElementById('exporter-interfaces').checked;
        const includeRouting = document.getElementById('exporter-routing').checked;
        const includeLabels = document.getElementById('exporter-labels').checked;

        try {
            const res = await fetch('/api/exporter/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    format: format,
                    layout: layout,
                    include_configs: includeConfigs,
                    include_interfaces: includeInterfaces,
                    include_routing: includeRouting,
                    include_labels: includeLabels
                })
            });

            const data = await res.json();
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }

            // Store export data and show preview
            this.currentExport = data.export;
            this.showExportPreview(data.export);

            // Refresh history
            this.fetchExporterData();

        } catch (error) {
            console.error('Error exporting topology:', error);
            alert('Error exporting topology');
        }
    }

    showExportPreview(exportData) {
        const section = document.getElementById('exporter-preview-section');
        const title = document.getElementById('exporter-preview-title');
        const content = document.getElementById('exporter-preview-content');

        section.style.display = 'block';
        title.textContent = `Export Preview - ${exportData.filename}`;
        content.textContent = exportData.content;

        // Update node/link counts
        document.getElementById('exporter-nodes').textContent = exportData.node_count;
        document.getElementById('exporter-links').textContent = exportData.link_count;
    }

    closeExportPreview() {
        document.getElementById('exporter-preview-section').style.display = 'none';
    }

    downloadExport() {
        if (!this.currentExport) return;

        const blob = new Blob([this.currentExport.content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = this.currentExport.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    copyExport() {
        if (!this.currentExport) return;

        navigator.clipboard.writeText(this.currentExport.content).then(() => {
            alert('Copied to clipboard!');
        }).catch(err => {
            console.error('Copy failed:', err);
        });
    }

    // ==================== SCHEDULER METHODS ====================

    async fetchSchedulerData() {
        try {
            const [statusRes, jobsRes, triggersRes, historyRes] = await Promise.all([
                fetch('/api/scheduler/status'),
                fetch('/api/scheduler/jobs'),
                fetch('/api/scheduler/triggers'),
                fetch('/api/scheduler/history?limit=20')
            ]);

            this.schedulerData = {
                status: statusRes.ok ? await statusRes.json() : {},
                jobs: jobsRes.ok ? await jobsRes.json() : { jobs: [] },
                triggers: triggersRes.ok ? await triggersRes.json() : { triggers: [] },
                history: historyRes.ok ? await historyRes.json() : { history: [] }
            };

            this.renderSchedulerData();
        } catch (error) {
            console.error('Error fetching scheduler data:', error);
        }
    }

    renderSchedulerData() {
        const data = this.schedulerData || { status: {}, jobs: { jobs: [] }, triggers: { triggers: [] }, history: { history: [] } };

        // Update metrics
        const status = data.status || {};
        const jobs = data.jobs?.jobs || [];
        const triggers = data.triggers?.triggers || [];
        const history = data.history?.history || [];

        document.getElementById('scheduler-total-jobs').textContent = jobs.length;
        document.getElementById('scheduler-running-jobs').textContent = jobs.filter(j => j.status === 'RUNNING').length;
        document.getElementById('scheduler-triggers').textContent = triggers.length;
        document.getElementById('scheduler-status').textContent = status.status || 'IDLE';

        // Job counts by status
        document.getElementById('scheduler-enabled-jobs').textContent = jobs.filter(j => j.enabled).length;
        document.getElementById('scheduler-pending-jobs').textContent = jobs.filter(j => j.status === 'PENDING').length;
        document.getElementById('scheduler-completed-jobs').textContent = jobs.filter(j => j.status === 'COMPLETED').length;
        document.getElementById('scheduler-failed-jobs').textContent = jobs.filter(j => j.status === 'FAILED').length;

        // Render jobs table
        this.renderSchedulerJobsTable(jobs);

        // Render triggers table
        this.renderSchedulerTriggersTable(triggers);

        // Render history table
        this.renderSchedulerHistoryTable(history);
    }

    renderSchedulerJobsTable(jobs) {
        const tbody = document.getElementById('scheduler-jobs-table');
        const label = document.getElementById('scheduler-jobs-label');

        label.textContent = `${jobs.length} job${jobs.length !== 1 ? 's' : ''}`;

        if (!jobs.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No scheduled jobs</td></tr>';
            return;
        }

        let html = '';
        for (const job of jobs) {
            const statusClass = this.getSchedulerStatusClass(job.status);
            const priorityColor = this.getSchedulerPriorityColor(job.priority);
            const nextRun = job.next_run ? new Date(job.next_run).toLocaleString() : '--';

            html += `
                <tr>
                    <td style="font-family: monospace; font-size: 0.8rem;">${this.escapeHtml(job.id?.substring(0, 8) || '--')}...</td>
                    <td>${this.escapeHtml(job.name || 'Unnamed')}</td>
                    <td><span style="color: #f472b6;">${job.job_type || '--'}</span></td>
                    <td><span style="color: ${priorityColor};">${job.priority || 'MEDIUM'}</span></td>
                    <td><span class="status-badge ${statusClass}">${job.status || 'PENDING'}</span></td>
                    <td style="font-size: 0.85rem;">${nextRun}</td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button onclick="dashboard.runJob('${job.id}')" title="Run Now" style="padding: 4px 8px; background: #10b981; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Run</button>
                            ${job.enabled ?
                                `<button onclick="dashboard.disableJob('${job.id}')" title="Disable" style="padding: 4px 8px; background: #f59e0b; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Disable</button>` :
                                `<button onclick="dashboard.enableJob('${job.id}')" title="Enable" style="padding: 4px 8px; background: #3b82f6; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Enable</button>`
                            }
                            <button onclick="dashboard.deleteJob('${job.id}')" title="Delete" style="padding: 4px 8px; background: #ef4444; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">X</button>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderSchedulerTriggersTable(triggers) {
        const tbody = document.getElementById('scheduler-triggers-table');
        const label = document.getElementById('scheduler-triggers-label');

        label.textContent = `${triggers.length} trigger${triggers.length !== 1 ? 's' : ''}`;

        if (!triggers.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No triggers configured</td></tr>';
            return;
        }

        let html = '';
        for (const trigger of triggers) {
            const statusClass = trigger.status === 'ACTIVE' ? 'active' : (trigger.status === 'PAUSED' ? 'pending' : 'down');
            const nextFire = trigger.next_fire_time ? new Date(trigger.next_fire_time).toLocaleString() : '--';
            const schedule = trigger.cron_expression || (trigger.interval_seconds ? `Every ${trigger.interval_seconds}s` : trigger.run_date || '--');

            html += `
                <tr>
                    <td style="font-family: monospace; font-size: 0.8rem;">${this.escapeHtml(trigger.id?.substring(0, 8) || '--')}...</td>
                    <td><span style="color: #a78bfa;">${trigger.trigger_type || '--'}</span></td>
                    <td style="font-family: monospace; font-size: 0.8rem;">${this.escapeHtml(trigger.job_id?.substring(0, 8) || '--')}...</td>
                    <td><span class="status-badge ${statusClass}">${trigger.status || 'PENDING'}</span></td>
                    <td style="font-family: monospace; font-size: 0.85rem;">${this.escapeHtml(schedule)}</td>
                    <td style="font-size: 0.85rem;">${nextFire}</td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            ${trigger.status === 'ACTIVE' ?
                                `<button onclick="dashboard.disableTrigger('${trigger.id}')" title="Disable" style="padding: 4px 8px; background: #f59e0b; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Disable</button>` :
                                `<button onclick="dashboard.enableTrigger('${trigger.id}')" title="Enable" style="padding: 4px 8px; background: #3b82f6; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Enable</button>`
                            }
                            <button onclick="dashboard.deleteTrigger('${trigger.id}')" title="Delete" style="padding: 4px 8px; background: #ef4444; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">X</button>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderSchedulerHistoryTable(history) {
        const tbody = document.getElementById('scheduler-history-table');
        const label = document.getElementById('scheduler-history-label');

        label.textContent = `${history.length} execution${history.length !== 1 ? 's' : ''}`;

        if (!history.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No execution history</td></tr>';
            return;
        }

        let html = '';
        for (const exec of history) {
            const statusClass = this.getSchedulerStatusClass(exec.status);
            const startTime = exec.started_at ? new Date(exec.started_at).toLocaleString() : '--';
            const duration = exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(2)}s` : '--';
            const result = exec.result || exec.error || '--';

            html += `
                <tr>
                    <td style="font-family: monospace; font-size: 0.8rem;">${this.escapeHtml(exec.job_id?.substring(0, 8) || '--')}...</td>
                    <td>${this.escapeHtml(exec.job_name || 'Unknown')}</td>
                    <td><span class="status-badge ${statusClass}">${exec.status || '--'}</span></td>
                    <td style="font-size: 0.85rem;">${startTime}</td>
                    <td>${duration}</td>
                    <td style="font-size: 0.8rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(result)}">${this.escapeHtml(result.substring ? result.substring(0, 50) : String(result).substring(0, 50))}</td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    getSchedulerStatusClass(status) {
        switch (status) {
            case 'COMPLETED':
            case 'SUCCESS':
            case 'RUNNING':
                return 'active';
            case 'PENDING':
            case 'SCHEDULED':
                return 'pending';
            case 'FAILED':
            case 'ERROR':
            case 'CANCELLED':
                return 'error';
            default:
                return 'pending';
        }
    }

    getSchedulerPriorityColor(priority) {
        switch (priority) {
            case 'CRITICAL': return '#ef4444';
            case 'HIGH': return '#f97316';
            case 'MEDIUM': return '#facc15';
            case 'LOW': return '#10b981';
            default: return '#facc15';
        }
    }

    showCreateJobModal() {
        document.getElementById('create-job-modal').style.display = 'flex';
    }

    hideCreateJobModal() {
        document.getElementById('create-job-modal').style.display = 'none';
    }

    showCreateTriggerModal() {
        document.getElementById('create-trigger-modal').style.display = 'flex';
        this.updateTriggerForm();
    }

    hideCreateTriggerModal() {
        document.getElementById('create-trigger-modal').style.display = 'none';
    }

    updateTriggerForm() {
        const type = document.getElementById('trigger-type').value;
        document.getElementById('cron-fields').style.display = type === 'cron' ? 'block' : 'none';
        document.getElementById('interval-fields').style.display = type === 'interval' ? 'block' : 'none';
        document.getElementById('date-fields').style.display = type === 'date' ? 'block' : 'none';
        document.getElementById('event-fields').style.display = type === 'event' ? 'block' : 'none';
    }

    async createJob() {
        const name = document.getElementById('job-name').value;
        const jobType = document.getElementById('job-type').value;
        const priority = document.getElementById('job-priority').value;
        const description = document.getElementById('job-description').value;
        const maxRetries = parseInt(document.getElementById('job-max-retries').value);
        const timeout = parseInt(document.getElementById('job-timeout').value);

        if (!name) {
            alert('Please enter a job name');
            return;
        }

        try {
            const res = await fetch('/api/scheduler/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    job_type: jobType,
                    priority,
                    description,
                    config: {
                        max_retries: maxRetries,
                        timeout_seconds: timeout
                    }
                })
            });

            if (res.ok) {
                this.hideCreateJobModal();
                this.fetchSchedulerData();
            } else {
                const error = await res.json();
                alert(`Error creating job: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating job:', error);
            alert('Error creating job');
        }
    }

    async createTrigger() {
        const type = document.getElementById('trigger-type').value;
        const jobId = document.getElementById('trigger-job-id').value;

        if (!jobId) {
            alert('Please enter a job ID');
            return;
        }

        let endpoint = '';
        let body = { job_id: jobId };

        switch (type) {
            case 'cron':
                endpoint = '/api/scheduler/triggers/cron';
                body.cron_expression = document.getElementById('trigger-cron').value;
                if (!body.cron_expression) {
                    alert('Please enter a cron expression');
                    return;
                }
                break;
            case 'interval':
                endpoint = '/api/scheduler/triggers/interval';
                body.interval_seconds = parseInt(document.getElementById('trigger-interval').value);
                break;
            case 'date':
                endpoint = '/api/scheduler/triggers/date';
                const dateVal = document.getElementById('trigger-date').value;
                if (!dateVal) {
                    alert('Please select a date/time');
                    return;
                }
                body.run_date = new Date(dateVal).toISOString();
                break;
            case 'event':
                endpoint = '/api/scheduler/triggers/event';
                body.event_type = document.getElementById('trigger-event-type').value;
                if (!body.event_type) {
                    alert('Please enter an event type');
                    return;
                }
                break;
        }

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (res.ok) {
                this.hideCreateTriggerModal();
                this.fetchSchedulerData();
            } else {
                const error = await res.json();
                alert(`Error creating trigger: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating trigger:', error);
            alert('Error creating trigger');
        }
    }

    async runJob(jobId) {
        try {
            const res = await fetch(`/api/scheduler/jobs/${jobId}/run`, { method: 'POST' });
            if (res.ok) {
                this.fetchSchedulerData();
            } else {
                alert('Error running job');
            }
        } catch (error) {
            console.error('Error running job:', error);
        }
    }

    async enableJob(jobId) {
        try {
            const res = await fetch(`/api/scheduler/jobs/${jobId}/enable`, { method: 'POST' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error enabling job:', error);
        }
    }

    async disableJob(jobId) {
        try {
            const res = await fetch(`/api/scheduler/jobs/${jobId}/disable`, { method: 'POST' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error disabling job:', error);
        }
    }

    async deleteJob(jobId) {
        if (!confirm('Are you sure you want to delete this job?')) return;
        try {
            const res = await fetch(`/api/scheduler/jobs/${jobId}`, { method: 'DELETE' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error deleting job:', error);
        }
    }

    async enableTrigger(triggerId) {
        try {
            const res = await fetch(`/api/scheduler/triggers/${triggerId}/enable`, { method: 'POST' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error enabling trigger:', error);
        }
    }

    async disableTrigger(triggerId) {
        try {
            const res = await fetch(`/api/scheduler/triggers/${triggerId}/disable`, { method: 'POST' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error disabling trigger:', error);
        }
    }

    async deleteTrigger(triggerId) {
        if (!confirm('Are you sure you want to delete this trigger?')) return;
        try {
            const res = await fetch(`/api/scheduler/triggers/${triggerId}`, { method: 'DELETE' });
            if (res.ok) {
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error deleting trigger:', error);
        }
    }

    async tickScheduler() {
        try {
            const res = await fetch('/api/scheduler/tick', { method: 'POST' });
            if (res.ok) {
                const result = await res.json();
                alert(`Scheduler tick executed: ${result.jobs_run || 0} jobs run`);
                this.fetchSchedulerData();
            }
        } catch (error) {
            console.error('Error ticking scheduler:', error);
        }
    }

    // ==================== INVENTORY METHODS ====================

    async fetchInventoryData() {
        try {
            const [statusRes, devicesRes, alertsRes] = await Promise.all([
                fetch('/api/inventory/status'),
                fetch('/api/inventory/devices'),
                fetch('/api/inventory/alerts')
            ]);

            this.inventoryData = {
                status: statusRes.ok ? await statusRes.json() : {},
                devices: devicesRes.ok ? await devicesRes.json() : { devices: [] },
                alerts: alertsRes.ok ? await alertsRes.json() : { alerts: [] }
            };

            this.renderInventoryData();
        } catch (error) {
            console.error('Error fetching inventory data:', error);
        }
    }

    renderInventoryData() {
        const data = this.inventoryData || { status: {}, devices: { devices: [] }, alerts: { alerts: [] } };

        const status = data.status || {};
        const devices = data.devices?.devices || [];
        const alerts = data.alerts?.alerts || [];

        // Update main metrics
        document.getElementById('inventory-total-devices').textContent = status.total_devices || devices.length;
        document.getElementById('inventory-active-devices').textContent = (status.by_status?.active || 0);
        document.getElementById('inventory-sites').textContent = status.unique_sites || 0;
        document.getElementById('inventory-alerts').textContent = alerts.length;

        // Update type counts
        const byType = status.by_type || {};
        document.getElementById('inventory-routers').textContent = byType.router || 0;
        document.getElementById('inventory-switches').textContent = byType.switch || 0;
        document.getElementById('inventory-firewalls').textContent = byType.firewall || 0;
        document.getElementById('inventory-servers').textContent = byType.server || 0;
        document.getElementById('inventory-other').textContent =
            (byType.virtual_machine || 0) + (byType.container || 0) + (byType.appliance || 0) + (byType.other || 0);

        // Render alerts
        this.renderInventoryAlerts(alerts);

        // Render devices table
        this.renderInventoryDevicesTable(devices);

        // Render charts
        this.renderInventoryCharts(status);
    }

    renderInventoryAlerts(alerts) {
        const container = document.getElementById('inventory-alerts-container');
        const label = document.getElementById('inventory-alerts-label');

        label.textContent = `${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`;

        if (!alerts.length) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">No alerts</div>';
            return;
        }

        let html = '';
        for (const alert of alerts.slice(0, 10)) {
            const severityColor = alert.severity === 'critical' ? '#ef4444' : '#f59e0b';
            html += `
                <div style="display: flex; align-items: center; gap: 10px; padding: 10px; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 8px; border-left: 3px solid ${severityColor};">
                    <span style="background: ${severityColor}20; color: ${severityColor}; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase;">${alert.severity}</span>
                    <span style="font-weight: 500;">${this.escapeHtml(alert.device_name || '--')}</span>
                    <span style="color: var(--text-secondary); flex: 1;">${this.escapeHtml(alert.message || '')}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    renderInventoryDevicesTable(devices) {
        const tbody = document.getElementById('inventory-devices-table');
        const label = document.getElementById('inventory-devices-label');

        label.textContent = `${devices.length} device${devices.length !== 1 ? 's' : ''}`;

        if (!devices.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No devices in inventory</td></tr>';
            return;
        }

        let html = '';
        for (const device of devices) {
            const statusClass = this.getInventoryStatusClass(device.status);
            const typeColor = this.getDeviceTypeColor(device.device_type);

            html += `
                <tr>
                    <td style="font-weight: 500;">${this.escapeHtml(device.name || '--')}</td>
                    <td><span style="color: ${typeColor}; text-transform: capitalize;">${device.device_type || '--'}</span></td>
                    <td><span class="status-badge ${statusClass}">${device.status || 'unknown'}</span></td>
                    <td style="font-family: monospace;">${this.escapeHtml(device.management_ip || '--')}</td>
                    <td>${this.escapeHtml(device.hardware?.manufacturer || '--')}</td>
                    <td>${this.escapeHtml(device.hardware?.model || '--')}</td>
                    <td>${this.escapeHtml(device.location?.site || '--')}</td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button onclick="dashboard.viewDevice('${device.id}')" title="View Details" style="padding: 4px 8px; background: #3b82f6; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">View</button>
                            <button onclick="dashboard.deleteDevice('${device.id}')" title="Delete" style="padding: 4px 8px; background: #ef4444; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">X</button>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderInventoryCharts(status) {
        // By Vendor
        const vendorContainer = document.getElementById('inventory-by-vendor');
        const byVendor = status.by_vendor || {};
        if (Object.keys(byVendor).length > 0) {
            let html = '';
            for (const [vendor, count] of Object.entries(byVendor).slice(0, 5)) {
                const pct = Math.round((count / (status.total_devices || 1)) * 100);
                html += `
                    <div style="margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="font-size: 0.85rem;">${this.escapeHtml(vendor)}</span>
                            <span style="font-size: 0.85rem; color: var(--text-secondary);">${count}</span>
                        </div>
                        <div style="background: var(--bg-tertiary); height: 8px; border-radius: 4px; overflow: hidden;">
                            <div style="background: #22d3ee; height: 100%; width: ${pct}%;"></div>
                        </div>
                    </div>
                `;
            }
            vendorContainer.innerHTML = html;
        } else {
            vendorContainer.innerHTML = '<div style="text-align: center; color: var(--text-secondary);">No data</div>';
        }

        // By Site
        const siteContainer = document.getElementById('inventory-by-site');
        const bySite = status.by_site || {};
        if (Object.keys(bySite).length > 0) {
            let html = '';
            for (const [site, count] of Object.entries(bySite).slice(0, 5)) {
                const pct = Math.round((count / (status.total_devices || 1)) * 100);
                html += `
                    <div style="margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="font-size: 0.85rem;">${this.escapeHtml(site)}</span>
                            <span style="font-size: 0.85rem; color: var(--text-secondary);">${count}</span>
                        </div>
                        <div style="background: var(--bg-tertiary); height: 8px; border-radius: 4px; overflow: hidden;">
                            <div style="background: #a855f7; height: 100%; width: ${pct}%;"></div>
                        </div>
                    </div>
                `;
            }
            siteContainer.innerHTML = html;
        } else {
            siteContainer.innerHTML = '<div style="text-align: center; color: var(--text-secondary);">No data</div>';
        }

        // By Lifecycle
        const lifecycleContainer = document.getElementById('inventory-by-lifecycle');
        const byLifecycle = status.by_lifecycle || {};
        if (Object.keys(byLifecycle).length > 0) {
            let html = '';
            for (const [stage, count] of Object.entries(byLifecycle).slice(0, 5)) {
                const pct = Math.round((count / (status.total_devices || 1)) * 100);
                const color = this.getLifecycleColor(stage);
                html += `
                    <div style="margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="font-size: 0.85rem; text-transform: capitalize;">${stage.replace(/_/g, ' ')}</span>
                            <span style="font-size: 0.85rem; color: var(--text-secondary);">${count}</span>
                        </div>
                        <div style="background: var(--bg-tertiary); height: 8px; border-radius: 4px; overflow: hidden;">
                            <div style="background: ${color}; height: 100%; width: ${pct}%;"></div>
                        </div>
                    </div>
                `;
            }
            lifecycleContainer.innerHTML = html;
        } else {
            lifecycleContainer.innerHTML = '<div style="text-align: center; color: var(--text-secondary);">No data</div>';
        }
    }

    getInventoryStatusClass(status) {
        switch (status) {
            case 'active': return 'active';
            case 'inactive':
            case 'maintenance': return 'pending';
            case 'failed':
            case 'decommissioned': return 'error';
            default: return 'pending';
        }
    }

    getDeviceTypeColor(type) {
        switch (type) {
            case 'router': return '#22d3ee';
            case 'switch': return '#a855f7';
            case 'firewall': return '#ef4444';
            case 'load_balancer': return '#f59e0b';
            case 'server': return '#10b981';
            case 'virtual_machine': return '#3b82f6';
            case 'container': return '#8b5cf6';
            default: return 'var(--text-secondary)';
        }
    }

    getLifecycleColor(stage) {
        switch (stage) {
            case 'production': return '#10b981';
            case 'deployment': return '#3b82f6';
            case 'planning':
            case 'procurement': return '#f59e0b';
            case 'end_of_sale': return '#f97316';
            case 'end_of_support':
            case 'end_of_life': return '#ef4444';
            case 'retired': return '#6b7280';
            default: return '#8b5cf6';
        }
    }

    showAddDeviceModal() {
        document.getElementById('add-device-modal').style.display = 'flex';
    }

    hideAddDeviceModal() {
        document.getElementById('add-device-modal').style.display = 'none';
    }

    showImportModal() {
        document.getElementById('import-inventory-modal').style.display = 'flex';
    }

    hideImportModal() {
        document.getElementById('import-inventory-modal').style.display = 'none';
    }

    async addDevice() {
        const name = document.getElementById('device-name').value;
        if (!name) {
            alert('Please enter a device name');
            return;
        }

        const data = {
            name: name,
            hostname: document.getElementById('device-hostname').value,
            device_type: document.getElementById('device-type').value,
            status: document.getElementById('device-status').value,
            management_ip: document.getElementById('device-mgmt-ip').value,
            loopback_ip: document.getElementById('device-loopback-ip').value,
            owner: document.getElementById('device-owner').value,
            environment: document.getElementById('device-environment').value,
            notes: document.getElementById('device-notes').value,
            tags: document.getElementById('device-tags').value.split(',').map(t => t.trim()).filter(t => t),
            hardware: {
                manufacturer: document.getElementById('device-manufacturer').value,
                model: document.getElementById('device-model').value,
                serial_number: document.getElementById('device-serial').value,
                asset_tag: document.getElementById('device-asset-tag').value
            },
            location: {
                site: document.getElementById('device-site').value,
                rack: document.getElementById('device-rack').value,
                rack_position: parseInt(document.getElementById('device-rack-position').value) || 0
            }
        };

        try {
            const res = await fetch('/api/inventory/devices', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (res.ok) {
                this.hideAddDeviceModal();
                this.fetchInventoryData();
                // Clear form
                document.getElementById('device-name').value = '';
                document.getElementById('device-hostname').value = '';
                document.getElementById('device-mgmt-ip').value = '';
            } else {
                const error = await res.json();
                alert(`Error adding device: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error adding device:', error);
            alert('Error adding device');
        }
    }

    async deleteDevice(deviceId) {
        if (!confirm('Are you sure you want to delete this device?')) return;
        try {
            const res = await fetch(`/api/inventory/devices/${deviceId}`, { method: 'DELETE' });
            if (res.ok) {
                this.fetchInventoryData();
            }
        } catch (error) {
            console.error('Error deleting device:', error);
        }
    }

    async viewDevice(deviceId) {
        try {
            const res = await fetch(`/api/inventory/devices/${deviceId}`);
            if (res.ok) {
                const device = await res.json();
                alert(JSON.stringify(device, null, 2));
            }
        } catch (error) {
            console.error('Error viewing device:', error);
        }
    }

    async exportInventory() {
        try {
            const res = await fetch('/api/inventory/export');
            if (res.ok) {
                const data = await res.json();
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `inventory-export-${new Date().toISOString().split('T')[0]}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Error exporting inventory:', error);
        }
    }

    async importInventory() {
        const importData = document.getElementById('import-data').value;
        if (!importData) {
            alert('Please paste JSON data to import');
            return;
        }

        try {
            const parsed = JSON.parse(importData);
            const res = await fetch('/api/inventory/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(parsed)
            });

            if (res.ok) {
                const result = await res.json();
                alert(`Imported: ${result.imported}, Updated: ${result.updated}, Errors: ${result.errors}`);
                this.hideImportModal();
                this.fetchInventoryData();
            } else {
                const error = await res.json();
                alert(`Import error: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error importing inventory:', error);
            alert('Error parsing JSON data');
        }
    }

    filterInventory() {
        // Trigger re-fetch with filters
        const typeFilter = document.getElementById('inventory-filter-type')?.value || '';
        const statusFilter = document.getElementById('inventory-filter-status')?.value || '';
        const searchFilter = document.getElementById('inventory-search')?.value || '';

        let url = '/api/inventory/devices?';
        if (typeFilter) url += `device_type=${typeFilter}&`;
        if (statusFilter) url += `status=${statusFilter}&`;
        if (searchFilter) url += `search=${encodeURIComponent(searchFilter)}&`;

        fetch(url)
            .then(res => res.json())
            .then(data => {
                this.renderInventoryDevicesTable(data.devices || []);
            })
            .catch(err => console.error('Filter error:', err));
    }

    // ==================== CAPACITY METHODS ====================

    async fetchCapacityData() {
        try {
            const [statusRes, metricsRes, forecastsRes, recsRes] = await Promise.all([
                fetch('/api/capacity/status'),
                fetch('/api/capacity/metrics'),
                fetch('/api/capacity/forecasts'),
                fetch('/api/capacity/recommendations')
            ]);

            this.capacityData = {
                status: statusRes.ok ? await statusRes.json() : {},
                metrics: metricsRes.ok ? await metricsRes.json() : { metrics: [] },
                forecasts: forecastsRes.ok ? await forecastsRes.json() : { forecasts: [] },
                recommendations: recsRes.ok ? await recsRes.json() : { recommendations: [] }
            };

            this.renderCapacityData();
        } catch (error) {
            console.error('Error fetching capacity data:', error);
        }
    }

    renderCapacityData() {
        const data = this.capacityData || { status: {}, metrics: { metrics: [] }, forecasts: { forecasts: [] }, recommendations: { recommendations: [] } };

        const status = data.status || {};
        const metrics = data.metrics?.metrics || [];
        const forecasts = data.forecasts?.forecasts || [];
        const recommendations = data.recommendations?.recommendations || [];

        // Update main metrics
        document.getElementById('capacity-total').textContent = status.total_metrics || 0;
        document.getElementById('capacity-avg-util').innerHTML = `${status.average_utilization || 0}<span class="metric-unit">%</span>`;
        document.getElementById('capacity-critical').textContent = status.critical_metrics || 0;
        document.getElementById('capacity-recs').textContent = status.pending_recommendations || recommendations.length;

        // Status counts
        const byLevel = status.by_utilization_level || {};
        const healthy = (byLevel.idle || 0) + (byLevel.low || 0) + (byLevel.moderate || 0);
        const warning = byLevel.high || 0;

        document.getElementById('capacity-healthy').textContent = healthy;
        document.getElementById('capacity-warning').textContent = warning;
        document.getElementById('capacity-urgent').textContent = status.urgent_forecasts_30d || 0;
        document.getElementById('capacity-forecasts').textContent = status.total_forecasts || forecasts.length;

        // Render tables
        this.renderCapacityMetricsTable(metrics);
        this.renderCapacityForecastsTable(forecasts);
        this.renderCapacityRecommendations(recommendations);
    }

    renderCapacityMetricsTable(metrics) {
        const tbody = document.getElementById('capacity-metrics-table');

        if (!metrics.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No capacity metrics recorded</td></tr>';
            return;
        }

        let html = '';
        for (const metric of metrics.slice(0, 10)) {
            const utilPct = metric.utilization_pct || 0;
            const statusColor = this.getCapacityStatusColor(metric.utilization_level);
            const barColor = utilPct >= 90 ? '#ef4444' : (utilPct >= 70 ? '#f59e0b' : '#10b981');

            html += `
                <tr>
                    <td style="font-weight: 500;">${this.escapeHtml(metric.resource_name || '--')}</td>
                    <td>${this.escapeHtml(metric.device_name || '--')}</td>
                    <td><span style="color: #14b8a6; text-transform: capitalize;">${metric.resource_type || '--'}</span></td>
                    <td style="font-family: monospace;">${metric.current_value?.toFixed(1) || 0} ${metric.unit || ''}</td>
                    <td style="font-family: monospace;">${metric.max_capacity?.toFixed(1) || 0} ${metric.unit || ''}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="flex: 1; background: var(--bg-tertiary); height: 8px; border-radius: 4px; overflow: hidden;">
                                <div style="background: ${barColor}; height: 100%; width: ${Math.min(utilPct, 100)}%;"></div>
                            </div>
                            <span style="min-width: 45px; text-align: right;">${utilPct.toFixed(1)}%</span>
                        </div>
                    </td>
                    <td><span class="status-badge" style="background: ${statusColor}20; color: ${statusColor};">${metric.utilization_level || 'unknown'}</span></td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderCapacityForecastsTable(forecasts) {
        const tbody = document.getElementById('capacity-forecasts-table');
        const label = document.getElementById('capacity-forecasts-label');

        label.textContent = `${forecasts.length} forecast${forecasts.length !== 1 ? 's' : ''}`;

        if (!forecasts.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Generate forecasts to see predictions</td></tr>';
            return;
        }

        let html = '';
        for (const forecast of forecasts.slice(0, 10)) {
            const trendColor = this.getTrendColor(forecast.trend_direction);
            const trendIcon = this.getTrendIcon(forecast.trend_direction);
            const confidence = (forecast.trend_confidence * 100).toFixed(0);

            html += `
                <tr>
                    <td style="font-weight: 500;">${this.escapeHtml(forecast.resource_name || '--')}</td>
                    <td>${this.escapeHtml(forecast.device_name || '--')}</td>
                    <td><span style="color: ${trendColor};">${trendIcon} ${forecast.trend_direction || '--'}</span></td>
                    <td style="font-family: monospace;">${forecast.predicted_7d?.toFixed(1) || '--'}</td>
                    <td style="font-family: monospace;">${forecast.predicted_30d?.toFixed(1) || '--'}</td>
                    <td style="font-weight: bold; color: ${forecast.days_to_critical && forecast.days_to_critical < 30 ? '#ef4444' : 'inherit'};">
                        ${forecast.days_to_critical || '--'}
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 5px;">
                            <div style="width: 50px; background: var(--bg-tertiary); height: 6px; border-radius: 3px; overflow: hidden;">
                                <div style="background: #14b8a6; height: 100%; width: ${confidence}%;"></div>
                            </div>
                            <span style="font-size: 0.8rem;">${confidence}%</span>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderCapacityRecommendations(recommendations) {
        const container = document.getElementById('capacity-recommendations-container');
        const label = document.getElementById('capacity-recs-label');

        label.textContent = `${recommendations.length} recommendation${recommendations.length !== 1 ? 's' : ''}`;

        if (!recommendations.length) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">Generate recommendations to see planning suggestions</div>';
            return;
        }

        let html = '';
        for (const rec of recommendations.slice(0, 5)) {
            const priorityColor = this.getRecommendationPriorityColor(rec.priority);

            html += `
                <div style="background: var(--bg-tertiary); padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 3px solid ${priorityColor};">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                        <div>
                            <span style="background: ${priorityColor}20; color: ${priorityColor}; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase;">${rec.priority}</span>
                            <span style="margin-left: 8px; font-weight: 500;">${this.escapeHtml(rec.title || '')}</span>
                        </div>
                        <span style="color: var(--text-secondary); font-size: 0.8rem;">${rec.urgency_days} days</span>
                    </div>
                    <p style="margin: 0 0 10px 0; color: var(--text-secondary); font-size: 0.9rem;">${this.escapeHtml(rec.description || '')}</p>
                    <div style="display: flex; gap: 20px; font-size: 0.85rem;">
                        <div><strong>Impact:</strong> <span style="color: var(--text-secondary);">${this.escapeHtml(rec.impact || '--')}</span></div>
                    </div>
                    <div style="margin-top: 8px; font-size: 0.85rem;"><strong>Action:</strong> <span style="color: #14b8a6;">${this.escapeHtml(rec.action || '--')}</span></div>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    getCapacityStatusColor(level) {
        switch (level) {
            case 'idle': return '#6b7280';
            case 'low': return '#10b981';
            case 'moderate': return '#84cc16';
            case 'high': return '#f59e0b';
            case 'critical': return '#f97316';
            case 'exhausted': return '#ef4444';
            default: return '#6b7280';
        }
    }

    getTrendColor(direction) {
        switch (direction) {
            case 'decreasing': return '#10b981';
            case 'stable': return '#6b7280';
            case 'increasing': return '#f59e0b';
            case 'rapidly_increasing': return '#ef4444';
            default: return '#6b7280';
        }
    }

    getTrendIcon(direction) {
        switch (direction) {
            case 'decreasing': return '↓';
            case 'stable': return '→';
            case 'increasing': return '↑';
            case 'rapidly_increasing': return '⬆';
            default: return '-';
        }
    }

    getRecommendationPriorityColor(priority) {
        switch (priority) {
            case 'critical': return '#ef4444';
            case 'high': return '#f97316';
            case 'medium': return '#f59e0b';
            case 'low': return '#10b981';
            default: return '#6b7280';
        }
    }

    showRecordMetricModal() {
        document.getElementById('record-metric-modal').style.display = 'flex';
    }

    hideRecordMetricModal() {
        document.getElementById('record-metric-modal').style.display = 'none';
    }

    async recordMetric() {
        const data = {
            resource_type: document.getElementById('metric-resource-type').value,
            resource_name: document.getElementById('metric-resource-name').value,
            device_id: document.getElementById('metric-device-id').value,
            device_name: document.getElementById('metric-device-name').value,
            current_value: parseFloat(document.getElementById('metric-current-value').value),
            max_capacity: parseFloat(document.getElementById('metric-max-capacity').value),
            unit: document.getElementById('metric-unit').value
        };

        if (!data.resource_name || !data.device_id) {
            alert('Please fill in resource name and device ID');
            return;
        }

        try {
            const res = await fetch('/api/capacity/metrics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (res.ok) {
                this.hideRecordMetricModal();
                this.fetchCapacityData();
            } else {
                const error = await res.json();
                alert(`Error recording metric: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error recording metric:', error);
            alert('Error recording metric');
        }
    }

    async generateForecasts() {
        try {
            const res = await fetch('/api/capacity/forecasts/generate', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                alert(`Generated ${data.count || 0} forecasts`);
                this.fetchCapacityData();
            }
        } catch (error) {
            console.error('Error generating forecasts:', error);
        }
    }

    async generateCapacityRecommendations() {
        try {
            const res = await fetch('/api/capacity/recommendations/generate', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                alert(`Generated ${data.count || 0} recommendations`);
                this.fetchCapacityData();
            }
        } catch (error) {
            console.error('Error generating recommendations:', error);
        }
    }

    // ==================== SLA METHODS ====================

    async fetchSLAData() {
        try {
            const [statusRes, slasRes, violationsRes, reportsRes] = await Promise.all([
                fetch('/api/sla/status'),
                fetch('/api/sla/definitions'),
                fetch('/api/sla/violations?limit=20'),
                fetch('/api/sla/reports')
            ]);

            this.slaData = {
                status: statusRes.ok ? await statusRes.json() : {},
                slas: slasRes.ok ? await slasRes.json() : { slas: [] },
                violations: violationsRes.ok ? await violationsRes.json() : { violations: [] },
                reports: reportsRes.ok ? await reportsRes.json() : { reports: [] }
            };

            this.renderSLAData();
        } catch (error) {
            console.error('Error fetching SLA data:', error);
        }
    }

    refreshSLAData() {
        this.fetchSLAData();
    }

    renderSLAData() {
        const data = this.slaData || { status: {}, slas: { slas: [] }, violations: { violations: [] }, reports: { reports: [] } };

        const status = data.status || {};
        const slas = data.slas?.slas || [];
        const violations = data.violations?.violations || [];
        const reports = data.reports?.reports || [];

        // Update main metrics
        document.getElementById('sla-total').textContent = status.total_slas || slas.length;

        // Calculate compliance rate
        const byStatus = status.by_status || {};
        const compliant = byStatus.compliant || 0;
        const total = status.total_slas || slas.length || 1;
        const complianceRate = Math.round((compliant / total) * 100);
        document.getElementById('sla-compliance').innerHTML = `${complianceRate}<span class="metric-unit">%</span>`;

        document.getElementById('sla-violated').textContent = byStatus.violated || 0;
        document.getElementById('sla-active-violations').textContent = status.active_violations || 0;

        // Status counts
        document.getElementById('sla-compliant-count').textContent = compliant;
        document.getElementById('sla-at-risk-count').textContent = byStatus.at_risk || 0;
        document.getElementById('sla-total-violations').textContent = status.total_violations || violations.length;
        document.getElementById('sla-reports-count').textContent = status.total_reports || reports.length;

        // Render tables
        this.renderSLADefinitionsTable(slas);
        this.renderSLAViolationsTable(violations);
    }

    renderSLADefinitionsTable(slas) {
        const tbody = document.getElementById('sla-definitions-table');
        const label = document.getElementById('sla-definitions-label');

        label.textContent = `${slas.length} SLA${slas.length !== 1 ? 's' : ''}`;

        if (!slas.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No SLAs defined</td></tr>';
            return;
        }

        let html = '';
        for (const sla of slas) {
            const statusClass = this.getSLAStatusClass(sla.status);
            const statusColor = this.getSLAStatusColor(sla.status);
            const targets = (sla.targets || []).map(t => `${t.metric_type}: ${t.target_value}${t.unit}`).join(', ') || '--';

            html += `
                <tr>
                    <td style="font-weight: 500;">${this.escapeHtml(sla.name || '--')}</td>
                    <td>${this.escapeHtml(sla.service_name || '--')}</td>
                    <td style="text-transform: capitalize;">${sla.service_type || '--'}</td>
                    <td style="font-size: 0.85rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(targets)}</td>
                    <td><span class="status-badge" style="background: ${statusColor}20; color: ${statusColor};">${sla.status || 'unknown'}</span></td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button onclick="dashboard.generateSLAReport('${sla.id}')" title="Generate Report" style="padding: 4px 8px; background: #f43f5e; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Report</button>
                            <button onclick="dashboard.deleteSLA('${sla.id}')" title="Delete" style="padding: 4px 8px; background: #ef4444; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">X</button>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    renderSLAViolationsTable(violations) {
        const tbody = document.getElementById('sla-violations-table');
        const label = document.getElementById('sla-violations-label');

        label.textContent = `${violations.length} violation${violations.length !== 1 ? 's' : ''}`;

        if (!violations.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No violations recorded</td></tr>';
            return;
        }

        let html = '';
        for (const v of violations.slice(0, 10)) {
            const severityColor = this.getSeverityColor(v.severity);
            const startTime = v.start_time ? new Date(v.start_time).toLocaleString() : '--';

            html += `
                <tr>
                    <td style="font-weight: 500;">${this.escapeHtml(v.sla_name || '--')}</td>
                    <td style="text-transform: capitalize;">${v.metric_type || '--'}</td>
                    <td style="font-family: monospace;">${v.target_value || '--'}</td>
                    <td style="font-family: monospace; color: #ef4444;">${v.actual_value?.toFixed(2) || '--'}</td>
                    <td style="font-weight: bold; color: #ef4444;">${v.breach_percentage?.toFixed(1) || 0}%</td>
                    <td><span class="status-badge" style="background: ${severityColor}20; color: ${severityColor}; text-transform: uppercase;">${v.severity || '--'}</span></td>
                    <td style="font-size: 0.85rem;">${startTime}</td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            ${!v.acknowledged ?
                                `<button onclick="dashboard.acknowledgeSLAViolation('${v.id}')" title="Acknowledge" style="padding: 4px 8px; background: #3b82f6; border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 0.75rem;">Ack</button>` :
                                `<span style="color: var(--text-secondary); font-size: 0.75rem;">Acked</span>`
                            }
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }

    getSLAStatusClass(status) {
        switch (status) {
            case 'compliant': return 'active';
            case 'at_risk': return 'pending';
            case 'violated': return 'error';
            default: return 'pending';
        }
    }

    getSLAStatusColor(status) {
        switch (status) {
            case 'compliant': return '#10b981';
            case 'at_risk': return '#f59e0b';
            case 'violated': return '#ef4444';
            default: return '#6b7280';
        }
    }

    getSeverityColor(severity) {
        switch (severity) {
            case 'minor': return '#f59e0b';
            case 'moderate': return '#f97316';
            case 'major': return '#ef4444';
            case 'critical': return '#dc2626';
            default: return '#6b7280';
        }
    }

    showCreateSLAModal() {
        document.getElementById('create-sla-modal').style.display = 'flex';
    }

    hideCreateSLAModal() {
        document.getElementById('create-sla-modal').style.display = 'none';
    }

    async createSLA() {
        const name = document.getElementById('sla-name').value;
        if (!name) {
            alert('Please enter an SLA name');
            return;
        }

        const data = {
            name: name,
            service_name: document.getElementById('sla-service-name').value,
            service_type: document.getElementById('sla-service-type').value,
            description: document.getElementById('sla-description').value,
            targets: [
                {
                    metric_type: 'availability',
                    target_value: parseFloat(document.getElementById('sla-avail-target').value),
                    warning_threshold: parseFloat(document.getElementById('sla-avail-warning').value),
                    comparison: document.getElementById('sla-avail-comp').value,
                    unit: '%'
                },
                {
                    metric_type: 'latency',
                    target_value: parseFloat(document.getElementById('sla-latency-target').value),
                    warning_threshold: parseFloat(document.getElementById('sla-latency-warning').value),
                    comparison: document.getElementById('sla-latency-comp').value,
                    unit: 'ms'
                }
            ]
        };

        try {
            const res = await fetch('/api/sla/definitions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (res.ok) {
                this.hideCreateSLAModal();
                this.fetchSLAData();
            } else {
                const error = await res.json();
                alert(`Error creating SLA: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating SLA:', error);
            alert('Error creating SLA');
        }
    }

    async deleteSLA(slaId) {
        if (!confirm('Are you sure you want to delete this SLA?')) return;
        try {
            const res = await fetch(`/api/sla/definitions/${slaId}`, { method: 'DELETE' });
            if (res.ok) {
                this.fetchSLAData();
            }
        } catch (error) {
            console.error('Error deleting SLA:', error);
        }
    }

    async generateSLAReport(slaId) {
        try {
            const res = await fetch(`/api/sla/${slaId}/report`, { method: 'POST' });
            if (res.ok) {
                const report = await res.json();
                alert(`Report generated!\nCompliance: ${report.compliance_percentage}%\nStatus: ${report.overall_status}\nViolations: ${report.violation_count}`);
                this.fetchSLAData();
            } else {
                alert('Error generating report');
            }
        } catch (error) {
            console.error('Error generating SLA report:', error);
        }
    }

    async acknowledgeSLAViolation(violationId) {
        try {
            const res = await fetch(`/api/sla/violations/${violationId}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ acknowledged_by: 'Dashboard User' })
            });
            if (res.ok) {
                this.fetchSLAData();
            }
        } catch (error) {
            console.error('Error acknowledging violation:', error);
        }
    }

    // ==================== AUDIT LOG METHODS ====================
    async fetchAuditData() {
        try {
            const [eventsRes, statsRes] = await Promise.all([
                fetch('/api/audit/events?limit=100'),
                fetch('/api/audit/stats')
            ]);

            const events = eventsRes.ok ? await eventsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.auditEvents = events;
            this.auditStats = stats;
            this.renderAuditData(events, stats);
        } catch (error) {
            console.error('Error fetching audit data:', error);
        }
    }

    renderAuditData(events, stats) {
        // Update metric cards
        const totalEl = document.getElementById('audit-total');
        const securityEl = document.getElementById('audit-security');
        const todayEl = document.getElementById('audit-today');
        const exportsEl = document.getElementById('audit-exports');

        if (totalEl) totalEl.textContent = stats.total_events || events.length || 0;
        if (securityEl) securityEl.textContent = stats.security_events || 0;
        if (todayEl) todayEl.textContent = stats.today_events || 0;
        if (exportsEl) exportsEl.textContent = stats.exports || 0;

        // Update event type counts
        const typeCounters = {
            'audit-create-count': ['CREATE', 'create'],
            'audit-update-count': ['UPDATE', 'update'],
            'audit-delete-count': ['DELETE', 'delete'],
            'audit-login-count': ['LOGIN', 'login', 'LOGOUT', 'logout'],
            'audit-config-count': ['CONFIG_CHANGE', 'config_change', 'CONFIG', 'config']
        };

        for (const [elId, types] of Object.entries(typeCounters)) {
            const el = document.getElementById(elId);
            if (el) {
                let count = 0;
                for (const type of types) {
                    count += stats.event_type_counts?.[type] || 0;
                }
                // Also count from events if stats not available
                if (count === 0 && events.length > 0) {
                    count = events.filter(e => types.includes(e.event_type)).length;
                }
                el.textContent = count;
            }
        }

        // Update events count label
        const eventsLabel = document.getElementById('audit-events-label');
        if (eventsLabel) eventsLabel.textContent = `${events.length} events`;

        // Render events table
        this.renderAuditEventsTable(events);
    }

    renderAuditEventTypeBreakdown(eventTypeCounts) {
        const container = document.getElementById('audit-event-type-breakdown');
        if (!container) return;

        const eventTypes = Object.entries(eventTypeCounts);
        if (eventTypes.length === 0) {
            container.innerHTML = '<div class="empty-state">No events recorded</div>';
            return;
        }

        const total = eventTypes.reduce((sum, [_, count]) => sum + count, 0);

        let html = '<div class="event-type-grid">';
        for (const [type, count] of eventTypes.slice(0, 8)) {
            const percentage = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
            html += `
                <div class="event-type-card">
                    <div class="event-type-name">${this.escapeHtml(type)}</div>
                    <div class="event-type-count">${count}</div>
                    <div class="event-type-bar">
                        <div class="event-type-bar-fill" style="width: ${percentage}%"></div>
                    </div>
                    <div class="event-type-percentage">${percentage}%</div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    }

    renderAuditEventsTable(events) {
        const tableBody = document.getElementById('audit-events-table');
        if (!tableBody) return;

        if (!events || events.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No audit events recorded</td></tr>';
            return;
        }

        let html = '';
        for (const event of events.slice(0, 50)) {
            const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleString() : '-';
            const severityClass = this.getAuditSeverityClass(event.severity);

            html += `
                <tr>
                    <td>${timestamp}</td>
                    <td><span class="status-badge">${this.escapeHtml(event.event_type || '-')}</span></td>
                    <td><span class="status-badge ${severityClass}">${this.escapeHtml(event.severity || 'INFO')}</span></td>
                    <td>${this.escapeHtml(event.user_id || event.user || 'system')}</td>
                    <td>${this.escapeHtml(event.resource_type || '-')}${event.resource_id ? '/' + this.escapeHtml(event.resource_id) : ''}</td>
                    <td class="audit-message">${this.escapeHtml(event.description || event.message || '-')}</td>
                    <td>${this.escapeHtml(event.ip_address || event.source || '-')}</td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getAuditSeverityClass(severity) {
        const severityMap = {
            'critical': 'critical',
            'error': 'error',
            'warning': 'warning',
            'info': 'info',
            'debug': 'debug'
        };
        return severityMap[severity?.toLowerCase()] || 'info';
    }

    filterAuditEvents() {
        const eventType = document.getElementById('audit-filter-type')?.value || '';
        const severity = document.getElementById('audit-filter-severity')?.value || '';
        const user = document.getElementById('audit-filter-user')?.value || '';
        const resource = document.getElementById('audit-filter-resource')?.value || '';

        let filteredEvents = this.auditEvents || [];

        if (eventType) {
            filteredEvents = filteredEvents.filter(e => e.event_type === eventType);
        }
        if (severity) {
            filteredEvents = filteredEvents.filter(e => e.severity === severity);
        }
        if (user) {
            filteredEvents = filteredEvents.filter(e =>
                (e.user_id || e.user || '').toLowerCase().includes(user.toLowerCase())
            );
        }
        if (resource) {
            filteredEvents = filteredEvents.filter(e =>
                (e.resource_type || '').toLowerCase().includes(resource.toLowerCase()) ||
                (e.resource_id || '').toLowerCase().includes(resource.toLowerCase())
            );
        }

        this.renderAuditEventsTable(filteredEvents);
    }

    clearAuditFilters() {
        const filterIds = ['audit-filter-type', 'audit-filter-severity', 'audit-filter-user', 'audit-filter-resource'];
        filterIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        this.renderAuditEventsTable(this.auditEvents || []);
    }

    refreshAuditData() {
        this.fetchAuditData();
    }

    async exportAuditLog() {
        try {
            const res = await fetch('/api/audit/export');
            if (res.ok) {
                const data = await res.json();
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `audit-log-${new Date().toISOString().split('T')[0]}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Error exporting audit log:', error);
        }
    }

    showLogEventModal() {
        const modal = document.getElementById('log-event-modal');
        if (modal) {
            modal.style.display = 'flex';
            // Reset form
            const form = modal.querySelector('form');
            if (form) form.reset();
        }
    }

    hideLogEventModal() {
        const modal = document.getElementById('log-event-modal');
        if (modal) modal.style.display = 'none';
    }

    async logAuditEvent() {
        const eventType = document.getElementById('audit-event-type')?.value;
        const severity = document.getElementById('audit-event-severity')?.value;
        const userId = document.getElementById('audit-event-user')?.value;
        const resourceType = document.getElementById('audit-event-resource-type')?.value;
        const resourceId = document.getElementById('audit-event-resource-id')?.value;
        const description = document.getElementById('audit-event-description')?.value;

        if (!eventType || !description) {
            alert('Event type and description are required');
            return;
        }

        try {
            const res = await fetch('/api/audit/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_type: eventType,
                    severity: severity || 'INFO',
                    user_id: userId || 'dashboard_user',
                    resource_type: resourceType || '',
                    resource_id: resourceId || '',
                    description: description,
                    ip_address: 'dashboard',
                    details: {}
                })
            });

            if (res.ok) {
                this.hideLogEventModal();
                this.fetchAuditData();
            } else {
                const error = await res.json();
                alert(`Failed to log event: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error logging audit event:', error);
            alert('Failed to log event');
        }
    }

    async clearAuditHistory() {
        if (!confirm('Are you sure you want to clear all audit history? This action cannot be undone.')) {
            return;
        }

        try {
            const res = await fetch('/api/audit/clear', {
                method: 'POST'
            });
            if (res.ok) {
                this.fetchAuditData();
            }
        } catch (error) {
            console.error('Error clearing audit history:', error);
        }
    }

    // ==================== BACKUP & RESTORE METHODS ====================
    async fetchBackupData() {
        try {
            const [statusRes, backupsRes, schedulesRes] = await Promise.all([
                fetch('/api/backup/status'),
                fetch('/api/backups'),
                fetch('/api/backup/schedules')
            ]);

            const status = statusRes.ok ? await statusRes.json() : {};
            const backups = backupsRes.ok ? await backupsRes.json() : [];
            const schedules = schedulesRes.ok ? await schedulesRes.json() : [];

            this.backups = backups;
            this.backupSchedules = schedules;
            this.renderBackupData(status, backups, schedules);
        } catch (error) {
            console.error('Error fetching backup data:', error);
        }
    }

    renderBackupData(status, backups, schedules) {
        // Update metric cards
        const totalEl = document.getElementById('backup-total');
        const successfulEl = document.getElementById('backup-successful');
        const schedulesEl = document.getElementById('backup-schedules');
        const lastEl = document.getElementById('backup-last');

        if (totalEl) totalEl.textContent = status.total_backups || backups.length || 0;
        if (successfulEl) successfulEl.textContent = status.successful_backups || backups.filter(b => b.status === 'completed').length || 0;
        if (schedulesEl) schedulesEl.textContent = schedules.length || 0;

        // Last backup time
        if (lastEl) {
            const lastBackup = status.last_backup_time || (backups.length > 0 ? backups[0].created_at : null);
            if (lastBackup) {
                const date = new Date(lastBackup);
                lastEl.textContent = date.toLocaleDateString();
            } else {
                lastEl.textContent = 'Never';
            }
        }

        // Update type counts
        const typeCounts = { full: 0, incremental: 0, config: 0, topology: 0 };
        for (const backup of backups) {
            const type = (backup.backup_type || backup.type || '').toLowerCase();
            if (typeCounts[type] !== undefined) {
                typeCounts[type]++;
            }
        }

        const fullCountEl = document.getElementById('backup-full-count');
        const incCountEl = document.getElementById('backup-incremental-count');
        const configCountEl = document.getElementById('backup-config-count');
        const topoCountEl = document.getElementById('backup-topology-count');

        if (fullCountEl) fullCountEl.textContent = typeCounts.full;
        if (incCountEl) incCountEl.textContent = typeCounts.incremental;
        if (configCountEl) configCountEl.textContent = typeCounts.config;
        if (topoCountEl) topoCountEl.textContent = typeCounts.topology;

        // Update list label
        const listLabel = document.getElementById('backup-list-label');
        if (listLabel) listLabel.textContent = `${backups.length} backups`;

        // Render tables
        this.renderBackupsTable(backups);
        this.renderBackupSchedulesTable(schedules);
    }

    renderBackupsTable(backups) {
        const tableBody = document.getElementById('backup-table');
        if (!tableBody) return;

        if (!backups || backups.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No backups available</td></tr>';
            return;
        }

        let html = '';
        for (const backup of backups.slice(0, 20)) {
            const created = backup.created_at ? new Date(backup.created_at).toLocaleString() : '-';
            const statusClass = this.getBackupStatusClass(backup.status);
            const size = this.formatBackupSize(backup.size || backup.size_bytes || 0);

            html += `
                <tr>
                    <td>${this.escapeHtml(backup.name || backup.id || '-')}</td>
                    <td><span class="status-badge">${this.escapeHtml(backup.backup_type || backup.type || '-')}</span></td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(backup.status || 'unknown')}</span></td>
                    <td>${size}</td>
                    <td>${created}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.restoreBackup('${backup.id}')" title="Restore">Restore</button>
                        <button class="btn btn-sm" onclick="dashboard.verifyBackup('${backup.id}')" title="Verify">Verify</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteBackup('${backup.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderBackupSchedulesTable(schedules) {
        const tableBody = document.getElementById('backup-schedules-table');
        if (!tableBody) return;

        if (!schedules || schedules.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No schedules configured</td></tr>';
            return;
        }

        let html = '';
        for (const schedule of schedules) {
            const nextRun = schedule.next_run ? new Date(schedule.next_run).toLocaleString() : '-';
            const statusClass = schedule.enabled ? 'success' : 'warning';
            const statusText = schedule.enabled ? 'Active' : 'Disabled';

            html += `
                <tr>
                    <td>${this.escapeHtml(schedule.name || schedule.id || '-')}</td>
                    <td>${this.escapeHtml(schedule.frequency || '-')}</td>
                    <td><span class="status-badge">${this.escapeHtml(schedule.backup_type || '-')}</span></td>
                    <td>${schedule.retention_days || '-'} days</td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${nextRun}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.runScheduleNow('${schedule.id}')" title="Run Now">Run</button>
                        <button class="btn btn-sm" onclick="dashboard.toggleSchedule('${schedule.id}', ${!schedule.enabled})" title="${schedule.enabled ? 'Disable' : 'Enable'}">${schedule.enabled ? 'Disable' : 'Enable'}</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteSchedule('${schedule.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getBackupStatusClass(status) {
        const statusMap = {
            'completed': 'success',
            'success': 'success',
            'in_progress': 'warning',
            'pending': 'info',
            'failed': 'error',
            'error': 'error'
        };
        return statusMap[status?.toLowerCase()] || 'info';
    }

    formatBackupSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    refreshBackupData() {
        this.fetchBackupData();
    }

    showCreateBackupModal() {
        const modal = document.getElementById('create-backup-modal');
        if (modal) {
            modal.style.display = 'flex';
            // Reset form
            document.getElementById('backup-name').value = '';
            document.getElementById('backup-type').value = 'full';
            document.getElementById('backup-compression').value = 'gzip';
            document.getElementById('backup-description').value = '';
        }
    }

    hideCreateBackupModal() {
        const modal = document.getElementById('create-backup-modal');
        if (modal) modal.style.display = 'none';
    }

    async createBackup() {
        const name = document.getElementById('backup-name')?.value;
        const backupType = document.getElementById('backup-type')?.value;
        const compression = document.getElementById('backup-compression')?.value;
        const description = document.getElementById('backup-description')?.value;

        if (!name) {
            alert('Backup name is required');
            return;
        }

        try {
            const res = await fetch('/api/backups', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    backup_type: backupType,
                    compression: compression,
                    description: description
                })
            });

            if (res.ok) {
                this.hideCreateBackupModal();
                this.fetchBackupData();
            } else {
                const error = await res.json();
                alert(`Failed to create backup: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating backup:', error);
            alert('Failed to create backup');
        }
    }

    showScheduleBackupModal() {
        const modal = document.getElementById('schedule-backup-modal');
        if (modal) {
            modal.style.display = 'flex';
            // Reset form
            document.getElementById('schedule-name').value = '';
            document.getElementById('schedule-frequency').value = 'daily';
            document.getElementById('schedule-backup-type').value = 'full';
            document.getElementById('schedule-retention').value = '30';
            document.getElementById('schedule-max-backups').value = '10';
        }
    }

    hideScheduleBackupModal() {
        const modal = document.getElementById('schedule-backup-modal');
        if (modal) modal.style.display = 'none';
    }

    async createBackupSchedule() {
        const name = document.getElementById('schedule-name')?.value;
        const frequency = document.getElementById('schedule-frequency')?.value;
        const backupType = document.getElementById('schedule-backup-type')?.value;
        const retentionDays = parseInt(document.getElementById('schedule-retention')?.value) || 30;
        const maxBackups = parseInt(document.getElementById('schedule-max-backups')?.value) || 10;

        if (!name) {
            alert('Schedule name is required');
            return;
        }

        try {
            const res = await fetch('/api/backup/schedules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    frequency: frequency,
                    backup_type: backupType,
                    retention_days: retentionDays,
                    max_backups: maxBackups,
                    enabled: true
                })
            });

            if (res.ok) {
                this.hideScheduleBackupModal();
                this.fetchBackupData();
            } else {
                const error = await res.json();
                alert(`Failed to create schedule: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating backup schedule:', error);
            alert('Failed to create schedule');
        }
    }

    async restoreBackup(backupId) {
        if (!confirm('Are you sure you want to restore this backup? Current network state will be replaced.')) {
            return;
        }

        try {
            const res = await fetch(`/api/backups/${backupId}/restore`, {
                method: 'POST'
            });

            if (res.ok) {
                alert('Backup restored successfully');
                this.fetchBackupData();
            } else {
                const error = await res.json();
                alert(`Failed to restore backup: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error restoring backup:', error);
            alert('Failed to restore backup');
        }
    }

    async verifyBackup(backupId) {
        try {
            const res = await fetch(`/api/backups/${backupId}/verify`, {
                method: 'POST'
            });

            if (res.ok) {
                const result = await res.json();
                alert(`Backup verification: ${result.valid ? 'Valid' : 'Invalid'}\n${result.message || ''}`);
            } else {
                const error = await res.json();
                alert(`Verification failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error verifying backup:', error);
            alert('Failed to verify backup');
        }
    }

    async deleteBackup(backupId) {
        if (!confirm('Are you sure you want to delete this backup?')) {
            return;
        }

        try {
            const res = await fetch(`/api/backups/${backupId}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchBackupData();
            } else {
                const error = await res.json();
                alert(`Failed to delete backup: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting backup:', error);
        }
    }

    async runScheduleNow(scheduleId) {
        try {
            const res = await fetch(`/api/backup/schedules/${scheduleId}/run`, {
                method: 'POST'
            });

            if (res.ok) {
                alert('Backup started');
                this.fetchBackupData();
            } else {
                const error = await res.json();
                alert(`Failed to run schedule: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error running schedule:', error);
        }
    }

    async toggleSchedule(scheduleId, enable) {
        const endpoint = enable ? 'enable' : 'disable';
        try {
            const res = await fetch(`/api/backup/schedules/${scheduleId}/${endpoint}`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchBackupData();
            }
        } catch (error) {
            console.error('Error toggling schedule:', error);
        }
    }

    async deleteSchedule(scheduleId) {
        if (!confirm('Are you sure you want to delete this schedule?')) {
            return;
        }

        try {
            const res = await fetch(`/api/backup/schedules/${scheduleId}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchBackupData();
            }
        } catch (error) {
            console.error('Error deleting schedule:', error);
        }
    }

    // ==================== ALERTS MANAGEMENT METHODS ====================
    async fetchAlertsData() {
        try {
            const [alertsRes, rulesRes, channelsRes, statsRes] = await Promise.all([
                fetch('/api/alerts'),
                fetch('/api/alerts/rules'),
                fetch('/api/alerts/channels'),
                fetch('/api/alerts/statistics')
            ]);

            const alerts = alertsRes.ok ? await alertsRes.json() : [];
            const rules = rulesRes.ok ? await rulesRes.json() : [];
            const channels = channelsRes.ok ? await channelsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.alertsData = { alerts, rules, channels, stats };
            this.renderAlertsData(alerts, rules, channels, stats);
        } catch (error) {
            console.error('Error fetching alerts data:', error);
        }
    }

    renderAlertsData(alerts, rules, channels, stats) {
        // Handle both array and object responses
        const alertList = Array.isArray(alerts) ? alerts : (alerts.alerts || []);
        const ruleList = Array.isArray(rules) ? rules : (rules.rules || []);
        const channelList = Array.isArray(channels) ? channels : (channels.channels || []);

        // Update metric cards
        const activeEl = document.getElementById('alerts-active');
        const criticalEl = document.getElementById('alerts-critical');
        const warningEl = document.getElementById('alerts-warning');
        const channelsEl = document.getElementById('alerts-channels');

        const activeAlerts = alertList.filter(a => a.status === 'active' || a.status === 'firing');
        if (activeEl) activeEl.textContent = activeAlerts.length;
        if (channelsEl) channelsEl.textContent = channelList.length;

        // Count by severity
        const severityCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
        for (const alert of activeAlerts) {
            const sev = (alert.severity || '').toLowerCase();
            if (severityCounts[sev] !== undefined) {
                severityCounts[sev]++;
            }
        }

        if (criticalEl) criticalEl.textContent = severityCounts.critical;
        if (warningEl) warningEl.textContent = severityCounts.high + severityCounts.medium;

        // Update severity breakdown
        const critCountEl = document.getElementById('alerts-critical-count');
        const highCountEl = document.getElementById('alerts-high-count');
        const medCountEl = document.getElementById('alerts-medium-count');
        const lowCountEl = document.getElementById('alerts-low-count');
        const infoCountEl = document.getElementById('alerts-info-count');

        if (critCountEl) critCountEl.textContent = severityCounts.critical;
        if (highCountEl) highCountEl.textContent = severityCounts.high;
        if (medCountEl) medCountEl.textContent = severityCounts.medium;
        if (lowCountEl) lowCountEl.textContent = severityCounts.low;
        if (infoCountEl) infoCountEl.textContent = severityCounts.info;

        // Update list label
        const listLabel = document.getElementById('alerts-list-label');
        if (listLabel) listLabel.textContent = `${activeAlerts.length} alerts`;

        // Render tables
        this.renderAlertsTable(activeAlerts);
        this.renderAlertRulesTable(ruleList);
        this.renderAlertChannelsTable(channelList);
    }

    renderAlertsTable(alerts) {
        const tableBody = document.getElementById('alerts-table');
        if (!tableBody) return;

        if (!alerts || alerts.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No active alerts</td></tr>';
            return;
        }

        let html = '';
        for (const alert of alerts.slice(0, 20)) {
            const timestamp = alert.created_at || alert.timestamp ? new Date(alert.created_at || alert.timestamp).toLocaleString() : '-';
            const severityClass = this.getAlertSeverityClass(alert.severity);
            const statusClass = alert.status === 'acknowledged' ? 'warning' : (alert.status === 'resolved' ? 'success' : 'error');

            html += `
                <tr>
                    <td><span class="status-badge ${severityClass}">${this.escapeHtml(alert.severity || 'unknown')}</span></td>
                    <td>${this.escapeHtml(alert.message || alert.name || '-')}</td>
                    <td>${this.escapeHtml(alert.source || '-')}</td>
                    <td>${this.escapeHtml(alert.category || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(alert.status || 'active')}</span></td>
                    <td>${timestamp}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.acknowledgeAlert('${alert.id}')" title="Acknowledge">Ack</button>
                        <button class="btn btn-sm" onclick="dashboard.resolveAlert('${alert.id}')" title="Resolve">Resolve</button>
                        <button class="btn btn-sm" onclick="dashboard.silenceAlert('${alert.id}')" title="Silence">Silence</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderAlertRulesTable(rules) {
        const tableBody = document.getElementById('alert-rules-table');
        if (!tableBody) return;

        if (!rules || rules.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No alert rules configured</td></tr>';
            return;
        }

        let html = '';
        for (const rule of rules) {
            const statusClass = rule.enabled ? 'success' : 'warning';
            const statusText = rule.enabled ? 'Active' : 'Disabled';
            const severityClass = this.getAlertSeverityClass(rule.severity);

            html += `
                <tr>
                    <td>${this.escapeHtml(rule.name || '-')}</td>
                    <td>${this.escapeHtml(rule.condition || rule.expression || '-')}</td>
                    <td><span class="status-badge ${severityClass}">${this.escapeHtml(rule.severity || '-')}</span></td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${rule.trigger_count || 0}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.toggleAlertRule('${rule.id}', ${!rule.enabled})">${rule.enabled ? 'Disable' : 'Enable'}</button>
                        <button class="btn btn-sm" onclick="dashboard.evaluateRule('${rule.id}')" title="Test">Test</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteAlertRule('${rule.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderAlertChannelsTable(channels) {
        const tableBody = document.getElementById('alert-channels-table');
        if (!tableBody) return;

        if (!channels || channels.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No channels configured</td></tr>';
            return;
        }

        let html = '';
        for (const channel of channels) {
            const statusClass = channel.enabled ? 'success' : 'warning';
            const statusText = channel.enabled ? 'Active' : 'Disabled';
            const lastUsed = channel.last_used ? new Date(channel.last_used).toLocaleString() : 'Never';

            html += `
                <tr>
                    <td>${this.escapeHtml(channel.name || '-')}</td>
                    <td><span class="status-badge">${this.escapeHtml(channel.type || channel.channel_type || '-')}</span></td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${lastUsed}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.testChannel('${channel.id}')" title="Test">Test</button>
                        <button class="btn btn-sm" onclick="dashboard.toggleChannel('${channel.id}', ${!channel.enabled})">${channel.enabled ? 'Disable' : 'Enable'}</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteChannel('${channel.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getAlertSeverityClass(severity) {
        const severityMap = {
            'critical': 'critical',
            'high': 'error',
            'medium': 'warning',
            'low': 'info',
            'info': 'info'
        };
        return severityMap[severity?.toLowerCase()] || 'info';
    }

    refreshAlertsData() {
        this.fetchAlertsData();
    }

    showCreateAlertRuleModal() {
        const modal = document.getElementById('create-alert-rule-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('alert-rule-name').value = '';
            document.getElementById('alert-rule-condition').value = 'cpu_high';
            document.getElementById('alert-rule-severity').value = 'medium';
            document.getElementById('alert-rule-category').value = 'network';
            document.getElementById('alert-rule-description').value = '';
        }
    }

    hideCreateAlertRuleModal() {
        const modal = document.getElementById('create-alert-rule-modal');
        if (modal) modal.style.display = 'none';
    }

    async createAlertRule() {
        const name = document.getElementById('alert-rule-name')?.value;
        const condition = document.getElementById('alert-rule-condition')?.value;
        const severity = document.getElementById('alert-rule-severity')?.value;
        const category = document.getElementById('alert-rule-category')?.value;
        const description = document.getElementById('alert-rule-description')?.value;

        if (!name) {
            alert('Rule name is required');
            return;
        }

        try {
            const res = await fetch('/api/alerts/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    condition: condition,
                    severity: severity,
                    category: category,
                    description: description,
                    enabled: true
                })
            });

            if (res.ok) {
                this.hideCreateAlertRuleModal();
                this.fetchAlertsData();
            } else {
                const error = await res.json();
                alert(`Failed to create rule: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating alert rule:', error);
            alert('Failed to create rule');
        }
    }

    showAddChannelModal() {
        const modal = document.getElementById('add-channel-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('channel-name').value = '';
            document.getElementById('channel-type').value = 'email';
            document.getElementById('channel-min-severity').value = 'medium';
            document.getElementById('channel-email').value = '';
            document.getElementById('channel-webhook').value = '';
            this.updateChannelConfig();
        }
    }

    hideAddChannelModal() {
        const modal = document.getElementById('add-channel-modal');
        if (modal) modal.style.display = 'none';
    }

    updateChannelConfig() {
        const type = document.getElementById('channel-type')?.value;
        const emailConfig = document.getElementById('channel-config-email');
        const webhookConfig = document.getElementById('channel-config-webhook');

        if (emailConfig) emailConfig.style.display = (type === 'email') ? 'block' : 'none';
        if (webhookConfig) webhookConfig.style.display = (type === 'webhook' || type === 'slack') ? 'block' : 'none';
    }

    async createNotificationChannel() {
        const name = document.getElementById('channel-name')?.value;
        const type = document.getElementById('channel-type')?.value;
        const minSeverity = document.getElementById('channel-min-severity')?.value;
        const email = document.getElementById('channel-email')?.value;
        const webhook = document.getElementById('channel-webhook')?.value;

        if (!name) {
            alert('Channel name is required');
            return;
        }

        const config = {};
        if (type === 'email' && email) config.email = email;
        if ((type === 'webhook' || type === 'slack') && webhook) config.webhook_url = webhook;

        try {
            const res = await fetch('/api/alerts/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    channel_type: type,
                    min_severity: minSeverity,
                    config: config,
                    enabled: true
                })
            });

            if (res.ok) {
                this.hideAddChannelModal();
                this.fetchAlertsData();
            } else {
                const error = await res.json();
                alert(`Failed to add channel: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating channel:', error);
            alert('Failed to add channel');
        }
    }

    async acknowledgeAlert(alertId) {
        try {
            const res = await fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error acknowledging alert:', error);
        }
    }

    async resolveAlert(alertId) {
        try {
            const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: 'POST' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error resolving alert:', error);
        }
    }

    async silenceAlert(alertId) {
        try {
            const res = await fetch(`/api/alerts/${alertId}/suppress`, { method: 'POST' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error silencing alert:', error);
        }
    }

    async acknowledgeAllAlerts() {
        if (!confirm('Acknowledge all active alerts?')) return;
        try {
            const res = await fetch('/api/alerts/bulk/acknowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ all: true })
            });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error acknowledging all alerts:', error);
        }
    }

    async toggleAlertRule(ruleId, enable) {
        const endpoint = enable ? 'enable' : 'disable';
        try {
            const res = await fetch(`/api/alerts/rules/${ruleId}/${endpoint}`, { method: 'POST' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error toggling rule:', error);
        }
    }

    async evaluateRule(ruleId) {
        try {
            const res = await fetch(`/api/alerts/rules/${ruleId}/evaluate`, { method: 'POST' });
            if (res.ok) {
                const result = await res.json();
                alert(`Rule evaluation: ${result.triggered ? 'Would trigger' : 'Would not trigger'}`);
            }
        } catch (error) {
            console.error('Error evaluating rule:', error);
        }
    }

    async deleteAlertRule(ruleId) {
        if (!confirm('Delete this alert rule?')) return;
        try {
            const res = await fetch(`/api/alerts/rules/${ruleId}`, { method: 'DELETE' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error deleting rule:', error);
        }
    }

    async testChannel(channelId) {
        try {
            const res = await fetch(`/api/alerts/channels/${channelId}/test`, { method: 'POST' });
            if (res.ok) {
                alert('Test notification sent');
            } else {
                alert('Failed to send test notification');
            }
        } catch (error) {
            console.error('Error testing channel:', error);
        }
    }

    async toggleChannel(channelId, enable) {
        const endpoint = enable ? 'enable' : 'disable';
        try {
            const res = await fetch(`/api/alerts/channels/${channelId}/${endpoint}`, { method: 'POST' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error toggling channel:', error);
        }
    }

    async deleteChannel(channelId) {
        if (!confirm('Delete this notification channel?')) return;
        try {
            const res = await fetch(`/api/alerts/channels/${channelId}`, { method: 'DELETE' });
            if (res.ok) this.fetchAlertsData();
        } catch (error) {
            console.error('Error deleting channel:', error);
        }
    }

    // ==================== WORKFLOW AUTOMATION METHODS ====================
    async fetchWorkflowsData() {
        try {
            const [workflowsRes, runningRes, templatesRes, statsRes] = await Promise.all([
                fetch('/api/workflows'),
                fetch('/api/workflows/running'),
                fetch('/api/workflows/templates'),
                fetch('/api/workflows/statistics')
            ]);

            const workflows = workflowsRes.ok ? await workflowsRes.json() : [];
            const running = runningRes.ok ? await runningRes.json() : [];
            const templates = templatesRes.ok ? await templatesRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.workflowsData = { workflows, running, templates, stats };
            this.renderWorkflowsData(workflows, running, templates, stats);
        } catch (error) {
            console.error('Error fetching workflows data:', error);
        }
    }

    renderWorkflowsData(workflows, running, templates, stats) {
        // Handle array or object responses
        const workflowList = Array.isArray(workflows) ? workflows : (workflows.workflows || []);
        const runningList = Array.isArray(running) ? running : (running.workflows || []);
        const templateList = Array.isArray(templates) ? templates : (templates.templates || []);

        // Update metric cards
        const totalEl = document.getElementById('workflows-total');
        const runningEl = document.getElementById('workflows-running');
        const templatesEl = document.getElementById('workflows-templates');
        const successRateEl = document.getElementById('workflows-success-rate');

        if (totalEl) totalEl.textContent = workflowList.length;
        if (runningEl) runningEl.textContent = runningList.length;
        if (templatesEl) templatesEl.textContent = templateList.length;
        if (successRateEl) {
            const rate = stats.success_rate || 0;
            successRateEl.textContent = `${(rate * 100).toFixed(0)}%`;
        }

        // Count by status
        const statusCounts = { pending: 0, running: 0, completed: 0, failed: 0, paused: 0 };
        for (const wf of workflowList) {
            const status = (wf.status || '').toLowerCase();
            if (statusCounts[status] !== undefined) {
                statusCounts[status]++;
            }
        }

        // Update status breakdown
        const pendingEl = document.getElementById('workflows-pending-count');
        const runningCountEl = document.getElementById('workflows-running-count');
        const completedEl = document.getElementById('workflows-completed-count');
        const failedEl = document.getElementById('workflows-failed-count');
        const pausedEl = document.getElementById('workflows-paused-count');

        if (pendingEl) pendingEl.textContent = statusCounts.pending;
        if (runningCountEl) runningCountEl.textContent = statusCounts.running;
        if (completedEl) completedEl.textContent = statusCounts.completed;
        if (failedEl) failedEl.textContent = statusCounts.failed;
        if (pausedEl) pausedEl.textContent = statusCounts.paused;

        // Update list label
        const listLabel = document.getElementById('workflows-list-label');
        if (listLabel) listLabel.textContent = `${workflowList.length} workflows`;

        // Render tables
        this.renderWorkflowsTable(workflowList);
        this.renderRunningWorkflowsTable(runningList);
    }

    renderWorkflowsTable(workflows) {
        const tableBody = document.getElementById('workflows-table');
        if (!tableBody) return;

        if (!workflows || workflows.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No workflows defined</td></tr>';
            return;
        }

        let html = '';
        for (const wf of workflows.slice(0, 20)) {
            const created = wf.created_at ? new Date(wf.created_at).toLocaleString() : '-';
            const statusClass = this.getWorkflowStatusClass(wf.status);
            const steps = wf.steps || [];
            const completedSteps = steps.filter(s => s.status === 'completed').length;
            const progress = steps.length > 0 ? Math.round((completedSteps / steps.length) * 100) : 0;

            html += `
                <tr>
                    <td>${this.escapeHtml(wf.name || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(wf.status || 'pending')}</span></td>
                    <td>${steps.length}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 5px;">
                            <div style="flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px;">
                                <div style="width: ${progress}%; height: 100%; background: #8b5cf6; border-radius: 3px;"></div>
                            </div>
                            <span style="font-size: 0.8rem;">${progress}%</span>
                        </div>
                    </td>
                    <td>${created}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.startWorkflow('${wf.id}')" title="Start">Start</button>
                        <button class="btn btn-sm" onclick="dashboard.cloneWorkflow('${wf.id}')" title="Clone">Clone</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteWorkflow('${wf.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderRunningWorkflowsTable(workflows) {
        const tableBody = document.getElementById('workflows-running-table');
        if (!tableBody) return;

        if (!workflows || workflows.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No running workflows</td></tr>';
            return;
        }

        let html = '';
        for (const wf of workflows) {
            const started = wf.started_at ? new Date(wf.started_at).toLocaleString() : '-';
            const steps = wf.steps || [];
            const currentStep = steps.find(s => s.status === 'running');
            const completedSteps = steps.filter(s => s.status === 'completed').length;
            const progress = steps.length > 0 ? Math.round((completedSteps / steps.length) * 100) : 0;

            html += `
                <tr>
                    <td>${this.escapeHtml(wf.name || '-')}</td>
                    <td>${this.escapeHtml(currentStep?.name || '-')}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 5px;">
                            <div style="flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px;">
                                <div style="width: ${progress}%; height: 100%; background: #8b5cf6; border-radius: 3px;"></div>
                            </div>
                            <span style="font-size: 0.8rem;">${completedSteps}/${steps.length}</span>
                        </div>
                    </td>
                    <td>${started}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.pauseWorkflow('${wf.id}')" title="Pause">Pause</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.cancelWorkflow('${wf.id}')" title="Cancel">Cancel</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getWorkflowStatusClass(status) {
        const statusMap = {
            'pending': 'info',
            'running': 'warning',
            'completed': 'success',
            'failed': 'error',
            'paused': 'warning',
            'cancelled': 'error'
        };
        return statusMap[status?.toLowerCase()] || 'info';
    }

    refreshWorkflowsData() {
        this.fetchWorkflowsData();
    }

    showCreateWorkflowModal() {
        const modal = document.getElementById('create-workflow-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('workflow-name').value = '';
            document.getElementById('workflow-trigger').value = 'manual';
            document.getElementById('workflow-priority').value = 'normal';
            document.getElementById('workflow-description').value = '';
        }
    }

    hideCreateWorkflowModal() {
        const modal = document.getElementById('create-workflow-modal');
        if (modal) modal.style.display = 'none';
    }

    async createWorkflow() {
        const name = document.getElementById('workflow-name')?.value;
        const trigger = document.getElementById('workflow-trigger')?.value;
        const priority = document.getElementById('workflow-priority')?.value;
        const description = document.getElementById('workflow-description')?.value;

        if (!name) {
            alert('Workflow name is required');
            return;
        }

        try {
            const res = await fetch('/api/workflows', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    trigger: trigger,
                    priority: priority,
                    description: description,
                    steps: []
                })
            });

            if (res.ok) {
                this.hideCreateWorkflowModal();
                this.fetchWorkflowsData();
            } else {
                const error = await res.json();
                alert(`Failed to create workflow: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating workflow:', error);
            alert('Failed to create workflow');
        }
    }

    showWorkflowTemplatesModal() {
        alert('Workflow templates browser coming soon!');
    }

    async startWorkflow(workflowId) {
        try {
            const res = await fetch(`/api/workflows/${workflowId}/start`, { method: 'POST' });
            if (res.ok) {
                this.fetchWorkflowsData();
            } else {
                const error = await res.json();
                alert(`Failed to start workflow: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error starting workflow:', error);
        }
    }

    async pauseWorkflow(workflowId) {
        try {
            const res = await fetch(`/api/workflows/${workflowId}/pause`, { method: 'POST' });
            if (res.ok) this.fetchWorkflowsData();
        } catch (error) {
            console.error('Error pausing workflow:', error);
        }
    }

    async resumeWorkflow(workflowId) {
        try {
            const res = await fetch(`/api/workflows/${workflowId}/resume`, { method: 'POST' });
            if (res.ok) this.fetchWorkflowsData();
        } catch (error) {
            console.error('Error resuming workflow:', error);
        }
    }

    async cancelWorkflow(workflowId) {
        if (!confirm('Cancel this workflow?')) return;
        try {
            const res = await fetch(`/api/workflows/${workflowId}/cancel`, { method: 'POST' });
            if (res.ok) this.fetchWorkflowsData();
        } catch (error) {
            console.error('Error cancelling workflow:', error);
        }
    }

    async cloneWorkflow(workflowId) {
        try {
            const res = await fetch(`/api/workflows/${workflowId}/clone`, { method: 'POST' });
            if (res.ok) this.fetchWorkflowsData();
        } catch (error) {
            console.error('Error cloning workflow:', error);
        }
    }

    async deleteWorkflow(workflowId) {
        if (!confirm('Delete this workflow?')) return;
        try {
            const res = await fetch(`/api/workflows/${workflowId}`, { method: 'DELETE' });
            if (res.ok) this.fetchWorkflowsData();
        } catch (error) {
            console.error('Error deleting workflow:', error);
        }
    }

    // ==================== USERS/RBAC METHODS ====================
    async fetchUsersData() {
        try {
            const [usersRes, rolesRes, policiesRes, statusRes] = await Promise.all([
                fetch('/api/rbac/users'),
                fetch('/api/rbac/roles'),
                fetch('/api/rbac/policies'),
                fetch('/api/rbac/status')
            ]);

            const users = usersRes.ok ? await usersRes.json() : [];
            const roles = rolesRes.ok ? await rolesRes.json() : [];
            const policies = policiesRes.ok ? await policiesRes.json() : [];
            const status = statusRes.ok ? await statusRes.json() : {};

            this.usersData = { users, roles, policies, status };
            this.renderUsersData(users, roles, policies, status);
        } catch (error) {
            console.error('Error fetching users data:', error);
        }
    }

    renderUsersData(users, roles, policies, status) {
        // Handle array or object responses
        const userList = Array.isArray(users) ? users : (users.users || []);
        const roleList = Array.isArray(roles) ? roles : (roles.roles || []);
        const policyList = Array.isArray(policies) ? policies : (policies.policies || []);

        // Update metric cards
        const totalEl = document.getElementById('users-total');
        const activeEl = document.getElementById('users-active');
        const rolesEl = document.getElementById('users-roles');
        const policiesEl = document.getElementById('users-policies');

        if (totalEl) totalEl.textContent = userList.length;
        if (rolesEl) rolesEl.textContent = roleList.length;
        if (policiesEl) policiesEl.textContent = policyList.length;

        // Count by status
        const statusCounts = { active: 0, suspended: 0, locked: 0, pending: 0 };
        for (const user of userList) {
            const userStatus = (user.status || '').toLowerCase();
            if (statusCounts[userStatus] !== undefined) {
                statusCounts[userStatus]++;
            }
        }

        if (activeEl) activeEl.textContent = statusCounts.active;

        // Update status breakdown
        const activeCountEl = document.getElementById('users-active-count');
        const suspendedEl = document.getElementById('users-suspended-count');
        const lockedEl = document.getElementById('users-locked-count');
        const pendingEl = document.getElementById('users-pending-count');

        if (activeCountEl) activeCountEl.textContent = statusCounts.active;
        if (suspendedEl) suspendedEl.textContent = statusCounts.suspended;
        if (lockedEl) lockedEl.textContent = statusCounts.locked;
        if (pendingEl) pendingEl.textContent = statusCounts.pending;

        // Update list label
        const listLabel = document.getElementById('users-list-label');
        if (listLabel) listLabel.textContent = `${userList.length} users`;

        // Render tables
        this.renderUsersTable(userList);
        this.renderRolesTable(roleList);
    }

    renderUsersTable(users) {
        const tableBody = document.getElementById('users-table');
        if (!tableBody) return;

        if (!users || users.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No users configured</td></tr>';
            return;
        }

        let html = '';
        for (const user of users.slice(0, 20)) {
            const lastLogin = user.last_login ? new Date(user.last_login).toLocaleString() : 'Never';
            const statusClass = this.getUserStatusClass(user.status);
            const roles = user.roles?.join(', ') || '-';

            html += `
                <tr>
                    <td>${this.escapeHtml(user.username || '-')}</td>
                    <td>${this.escapeHtml(user.email || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(user.status || 'pending')}</span></td>
                    <td>${this.escapeHtml(roles)}</td>
                    <td>${lastLogin}</td>
                    <td>
                        ${user.status === 'suspended' ?
                            `<button class="btn btn-sm" onclick="dashboard.activateUser('${user.id}')" title="Activate">Activate</button>` :
                            `<button class="btn btn-sm" onclick="dashboard.suspendUser('${user.id}')" title="Suspend">Suspend</button>`
                        }
                        ${user.status === 'locked' ?
                            `<button class="btn btn-sm" onclick="dashboard.unlockUser('${user.id}')" title="Unlock">Unlock</button>` : ''
                        }
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderRolesTable(roles) {
        const tableBody = document.getElementById('roles-table');
        if (!tableBody) return;

        if (!roles || roles.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No roles defined</td></tr>';
            return;
        }

        let html = '';
        for (const role of roles) {
            const permissions = role.permissions?.join(', ') || '-';
            const userCount = role.user_count || 0;

            html += `
                <tr>
                    <td>${this.escapeHtml(role.name || '-')}</td>
                    <td>${this.escapeHtml(role.description || '-')}</td>
                    <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(permissions)}</td>
                    <td>${userCount}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.editRole('${role.id}')" title="Edit">Edit</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getUserStatusClass(status) {
        const statusMap = {
            'active': 'success',
            'suspended': 'warning',
            'locked': 'error',
            'pending': 'info'
        };
        return statusMap[status?.toLowerCase()] || 'info';
    }

    refreshUsersData() {
        this.fetchUsersData();
    }

    showCreateUserModal() {
        const modal = document.getElementById('create-user-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('user-username').value = '';
            document.getElementById('user-email').value = '';
            document.getElementById('user-fullname').value = '';
            document.getElementById('user-role').value = 'viewer';
        }
    }

    hideCreateUserModal() {
        const modal = document.getElementById('create-user-modal');
        if (modal) modal.style.display = 'none';
    }

    async createUser() {
        const username = document.getElementById('user-username')?.value;
        const email = document.getElementById('user-email')?.value;
        const fullname = document.getElementById('user-fullname')?.value;
        const role = document.getElementById('user-role')?.value;

        if (!username || !email) {
            alert('Username and email are required');
            return;
        }

        try {
            const res = await fetch('/api/rbac/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: username,
                    email: email,
                    full_name: fullname,
                    roles: [role],
                    status: 'active'
                })
            });

            if (res.ok) {
                this.hideCreateUserModal();
                this.fetchUsersData();
            } else {
                const error = await res.json();
                alert(`Failed to create user: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating user:', error);
            alert('Failed to create user');
        }
    }

    showCreateRoleModal() {
        const modal = document.getElementById('create-role-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('role-name').value = '';
            document.getElementById('role-description').value = '';
            document.getElementById('role-permissions').selectedIndex = -1;
        }
    }

    hideCreateRoleModal() {
        const modal = document.getElementById('create-role-modal');
        if (modal) modal.style.display = 'none';
    }

    async createRole() {
        const name = document.getElementById('role-name')?.value;
        const description = document.getElementById('role-description')?.value;
        const permSelect = document.getElementById('role-permissions');
        const permissions = Array.from(permSelect?.selectedOptions || []).map(o => o.value);

        if (!name) {
            alert('Role name is required');
            return;
        }

        try {
            const res = await fetch('/api/rbac/roles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    description: description,
                    permissions: permissions
                })
            });

            if (res.ok) {
                this.hideCreateRoleModal();
                this.fetchUsersData();
            } else {
                const error = await res.json();
                alert(`Failed to create role: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating role:', error);
            alert('Failed to create role');
        }
    }

    async activateUser(userId) {
        try {
            const res = await fetch(`/api/rbac/users/${userId}/activate`, { method: 'POST' });
            if (res.ok) this.fetchUsersData();
        } catch (error) {
            console.error('Error activating user:', error);
        }
    }

    async suspendUser(userId) {
        if (!confirm('Suspend this user?')) return;
        try {
            const res = await fetch(`/api/rbac/users/${userId}/suspend`, { method: 'POST' });
            if (res.ok) this.fetchUsersData();
        } catch (error) {
            console.error('Error suspending user:', error);
        }
    }

    async unlockUser(userId) {
        try {
            const res = await fetch(`/api/rbac/users/${userId}/unlock`, { method: 'POST' });
            if (res.ok) this.fetchUsersData();
        } catch (error) {
            console.error('Error unlocking user:', error);
        }
    }

    editRole(roleId) {
        alert('Role editor coming soon!');
    }

    // ==================== WEBHOOKS METHODS ====================
    async fetchWebhooksData() {
        try {
            const [webhooksRes, deliveriesRes, statusRes] = await Promise.all([
                fetch('/api/webhooks'),
                fetch('/api/webhooks/deliveries?limit=50'),
                fetch('/api/webhooks/status')
            ]);

            const webhooks = webhooksRes.ok ? await webhooksRes.json() : [];
            const deliveries = deliveriesRes.ok ? await deliveriesRes.json() : [];
            const status = statusRes.ok ? await statusRes.json() : {};

            this.webhooksData = { webhooks, deliveries, status };
            this.renderWebhooksData(webhooks, deliveries, status);
        } catch (error) {
            console.error('Error fetching webhooks data:', error);
        }
    }

    renderWebhooksData(webhooks, deliveries, status) {
        // Handle array or object responses
        const webhookList = Array.isArray(webhooks) ? webhooks : (webhooks.webhooks || []);
        const deliveryList = Array.isArray(deliveries) ? deliveries : (deliveries.deliveries || []);

        // Update metric cards
        const totalEl = document.getElementById('webhooks-total');
        const activeEl = document.getElementById('webhooks-active');
        const deliveriesEl = document.getElementById('webhooks-deliveries');
        const successRateEl = document.getElementById('webhooks-success-rate');

        if (totalEl) totalEl.textContent = webhookList.length;
        if (deliveriesEl) deliveriesEl.textContent = status.total_deliveries || deliveryList.length;

        // Count by status
        const statusCounts = { active: 0, paused: 0 };
        for (const wh of webhookList) {
            const whStatus = (wh.status || '').toLowerCase();
            if (whStatus === 'active') statusCounts.active++;
            else if (whStatus === 'paused') statusCounts.paused++;
        }

        if (activeEl) activeEl.textContent = statusCounts.active;

        // Count deliveries
        const deliveryCounts = { delivered: 0, failed: 0 };
        for (const d of deliveryList) {
            const dStatus = (d.status || '').toLowerCase();
            if (dStatus === 'delivered' || dStatus === 'success') deliveryCounts.delivered++;
            else if (dStatus === 'failed' || dStatus === 'error') deliveryCounts.failed++;
        }

        // Calculate success rate
        const totalDeliveries = deliveryCounts.delivered + deliveryCounts.failed;
        const rate = totalDeliveries > 0 ? (deliveryCounts.delivered / totalDeliveries) * 100 : 0;
        if (successRateEl) successRateEl.textContent = `${rate.toFixed(0)}%`;

        // Update breakdown
        const activeCountEl = document.getElementById('webhooks-active-count');
        const pausedEl = document.getElementById('webhooks-paused-count');
        const deliveredEl = document.getElementById('webhooks-delivered-count');
        const failedEl = document.getElementById('webhooks-failed-count');

        if (activeCountEl) activeCountEl.textContent = statusCounts.active;
        if (pausedEl) pausedEl.textContent = statusCounts.paused;
        if (deliveredEl) deliveredEl.textContent = deliveryCounts.delivered;
        if (failedEl) failedEl.textContent = deliveryCounts.failed;

        // Update list label
        const listLabel = document.getElementById('webhooks-list-label');
        if (listLabel) listLabel.textContent = `${webhookList.length} webhooks`;

        // Render tables
        this.renderWebhooksTable(webhookList);
        this.renderWebhookDeliveriesTable(deliveryList);
    }

    renderWebhooksTable(webhooks) {
        const tableBody = document.getElementById('webhooks-table');
        if (!tableBody) return;

        if (!webhooks || webhooks.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No webhooks configured</td></tr>';
            return;
        }

        let html = '';
        for (const wh of webhooks.slice(0, 20)) {
            const lastDelivery = wh.last_delivery ? new Date(wh.last_delivery).toLocaleString() : 'Never';
            const statusClass = wh.status === 'active' ? 'success' : 'warning';
            const events = wh.events?.join(', ') || '-';
            const urlDisplay = wh.url?.length > 40 ? wh.url.substring(0, 40) + '...' : wh.url;

            html += `
                <tr>
                    <td>${this.escapeHtml(wh.name || '-')}</td>
                    <td title="${this.escapeHtml(wh.url || '')}">${this.escapeHtml(urlDisplay || '-')}</td>
                    <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(events)}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(wh.status || 'active')}</span></td>
                    <td>${lastDelivery}</td>
                    <td>
                        ${wh.status === 'active' ?
                            `<button class="btn btn-sm" onclick="dashboard.pauseWebhook('${wh.id}')" title="Pause">Pause</button>` :
                            `<button class="btn btn-sm" onclick="dashboard.resumeWebhook('${wh.id}')" title="Resume">Resume</button>`
                        }
                        <button class="btn btn-sm btn-danger" onclick="dashboard.deleteWebhook('${wh.id}')" title="Delete">Delete</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderWebhookDeliveriesTable(deliveries) {
        const tableBody = document.getElementById('webhook-deliveries-table');
        if (!tableBody) return;

        if (!deliveries || deliveries.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">No deliveries</td></tr>';
            return;
        }

        let html = '';
        for (const d of deliveries.slice(0, 15)) {
            const timestamp = d.timestamp || d.created_at ? new Date(d.timestamp || d.created_at).toLocaleString() : '-';
            const statusClass = (d.status === 'delivered' || d.status === 'success') ? 'success' : 'error';
            const response = d.response_code ? `${d.response_code}` : '-';

            html += `
                <tr>
                    <td>${this.escapeHtml(d.webhook_name || d.webhook_id || '-')}</td>
                    <td>${this.escapeHtml(d.event_type || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(d.status || '-')}</span></td>
                    <td>${response}</td>
                    <td>${timestamp}</td>
                    <td>
                        ${d.status !== 'delivered' && d.status !== 'success' ?
                            `<button class="btn btn-sm" onclick="dashboard.retryDelivery('${d.id}')" title="Retry">Retry</button>` : ''
                        }
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    refreshWebhooksData() {
        this.fetchWebhooksData();
    }

    showCreateWebhookModal() {
        const modal = document.getElementById('create-webhook-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('webhook-name').value = '';
            document.getElementById('webhook-url').value = '';
            document.getElementById('webhook-events').selectedIndex = -1;
        }
    }

    hideCreateWebhookModal() {
        const modal = document.getElementById('create-webhook-modal');
        if (modal) modal.style.display = 'none';
    }

    async createWebhook() {
        const name = document.getElementById('webhook-name')?.value;
        const url = document.getElementById('webhook-url')?.value;
        const eventsSelect = document.getElementById('webhook-events');
        const events = Array.from(eventsSelect?.selectedOptions || []).map(o => o.value);

        if (!name || !url) {
            alert('Name and URL are required');
            return;
        }

        try {
            const res = await fetch('/api/webhooks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    url: url,
                    events: events.length > 0 ? events : ['*'],
                    status: 'active'
                })
            });

            if (res.ok) {
                this.hideCreateWebhookModal();
                this.fetchWebhooksData();
            } else {
                const error = await res.json();
                alert(`Failed to create webhook: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating webhook:', error);
            alert('Failed to create webhook');
        }
    }

    async testWebhook() {
        const url = prompt('Enter webhook URL to test:');
        if (!url) return;

        try {
            const res = await fetch('/api/webhooks/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });

            if (res.ok) {
                const result = await res.json();
                alert(`Test result: ${result.success ? 'Success' : 'Failed'}\nResponse: ${result.response_code || 'N/A'}`);
            } else {
                alert('Test failed');
            }
        } catch (error) {
            console.error('Error testing webhook:', error);
            alert('Test failed');
        }
    }

    async pauseWebhook(webhookId) {
        try {
            const res = await fetch(`/api/webhooks/${webhookId}/pause`, { method: 'POST' });
            if (res.ok) this.fetchWebhooksData();
        } catch (error) {
            console.error('Error pausing webhook:', error);
        }
    }

    async resumeWebhook(webhookId) {
        try {
            const res = await fetch(`/api/webhooks/${webhookId}/resume`, { method: 'POST' });
            if (res.ok) this.fetchWebhooksData();
        } catch (error) {
            console.error('Error resuming webhook:', error);
        }
    }

    async deleteWebhook(webhookId) {
        if (!confirm('Delete this webhook?')) return;
        try {
            const res = await fetch(`/api/webhooks/${webhookId}`, { method: 'DELETE' });
            if (res.ok) this.fetchWebhooksData();
        } catch (error) {
            console.error('Error deleting webhook:', error);
        }
    }

    async retryDelivery(deliveryId) {
        try {
            const res = await fetch(`/api/webhooks/deliveries/${deliveryId}/retry`, { method: 'POST' });
            if (res.ok) {
                this.fetchWebhooksData();
            }
        } catch (error) {
            console.error('Error retrying delivery:', error);
        }
    }

    // ==================== API KEYS METHODS ====================
    async fetchApiKeysData() {
        try {
            const [keysRes, statusRes] = await Promise.all([
                fetch('/api/apikeys'),
                fetch('/api/apikeys/status')
            ]);

            const keys = keysRes.ok ? await keysRes.json() : [];
            const status = statusRes.ok ? await statusRes.json() : {};

            this.apiKeysData = { keys, status };
            this.renderApiKeysData(keys, status);
        } catch (error) {
            console.error('Error fetching API keys data:', error);
        }
    }

    renderApiKeysData(keys, status) {
        // Handle array or object responses
        const keyList = Array.isArray(keys) ? keys : (keys.keys || []);

        // Update metric cards
        const totalEl = document.getElementById('apikeys-total');
        const activeEl = document.getElementById('apikeys-active');
        const requestsEl = document.getElementById('apikeys-requests');
        const expiringEl = document.getElementById('apikeys-expiring');

        if (totalEl) totalEl.textContent = keyList.length;
        if (requestsEl) requestsEl.textContent = status.total_requests || 0;

        // Count by status
        const statusCounts = { active: 0, suspended: 0, revoked: 0, expired: 0 };
        let expiringSoon = 0;
        const now = new Date();
        const sevenDays = 7 * 24 * 60 * 60 * 1000;

        for (const key of keyList) {
            const keyStatus = (key.status || '').toLowerCase();
            if (statusCounts[keyStatus] !== undefined) {
                statusCounts[keyStatus]++;
            }
            // Check expiring soon
            if (key.expires_at) {
                const expiryDate = new Date(key.expires_at);
                if (expiryDate > now && (expiryDate - now) < sevenDays) {
                    expiringSoon++;
                }
            }
        }

        if (activeEl) activeEl.textContent = statusCounts.active;
        if (expiringEl) expiringEl.textContent = expiringSoon;

        // Update breakdown
        const activeCountEl = document.getElementById('apikeys-active-count');
        const suspendedEl = document.getElementById('apikeys-suspended-count');
        const revokedEl = document.getElementById('apikeys-revoked-count');
        const expiredEl = document.getElementById('apikeys-expired-count');

        if (activeCountEl) activeCountEl.textContent = statusCounts.active;
        if (suspendedEl) suspendedEl.textContent = statusCounts.suspended;
        if (revokedEl) revokedEl.textContent = statusCounts.revoked;
        if (expiredEl) expiredEl.textContent = statusCounts.expired;

        // Update list label
        const listLabel = document.getElementById('apikeys-list-label');
        if (listLabel) listLabel.textContent = `${keyList.length} keys`;

        // Render table
        this.renderApiKeysTable(keyList);
    }

    renderApiKeysTable(keys) {
        const tableBody = document.getElementById('apikeys-table');
        if (!tableBody) return;

        if (!keys || keys.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No API keys configured</td></tr>';
            return;
        }

        let html = '';
        for (const key of keys.slice(0, 20)) {
            const expires = key.expires_at ? new Date(key.expires_at).toLocaleDateString() : 'Never';
            const statusClass = this.getApiKeyStatusClass(key.status);
            const scopes = key.scopes?.join(', ') || '-';
            const keyPrefix = key.key_prefix || (key.key ? key.key.substring(0, 8) + '...' : '-');

            html += `
                <tr>
                    <td>${this.escapeHtml(key.name || '-')}</td>
                    <td><code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">${this.escapeHtml(keyPrefix)}</code></td>
                    <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(scopes)}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(key.status || 'active')}</span></td>
                    <td>${key.request_count || 0}</td>
                    <td>${expires}</td>
                    <td>
                        ${key.status === 'active' ?
                            `<button class="btn btn-sm" onclick="dashboard.suspendApiKey('${key.id}')" title="Suspend">Suspend</button>` :
                            key.status === 'suspended' ?
                            `<button class="btn btn-sm" onclick="dashboard.reactivateApiKey('${key.id}')" title="Reactivate">Reactivate</button>` : ''
                        }
                        <button class="btn btn-sm" onclick="dashboard.rotateApiKey('${key.id}')" title="Rotate">Rotate</button>
                        <button class="btn btn-sm btn-danger" onclick="dashboard.revokeApiKey('${key.id}')" title="Revoke">Revoke</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getApiKeyStatusClass(status) {
        const statusMap = {
            'active': 'success',
            'suspended': 'warning',
            'revoked': 'error',
            'expired': 'info'
        };
        return statusMap[status?.toLowerCase()] || 'info';
    }

    refreshApiKeysData() {
        this.fetchApiKeysData();
    }

    showCreateApiKeyModal() {
        const modal = document.getElementById('create-apikey-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('apikey-name').value = '';
            document.getElementById('apikey-owner').value = '';
            document.getElementById('apikey-expiry').value = '90';
            document.getElementById('apikey-scopes').selectedIndex = -1;
        }
    }

    hideCreateApiKeyModal() {
        const modal = document.getElementById('create-apikey-modal');
        if (modal) modal.style.display = 'none';
    }

    async generateApiKey() {
        const name = document.getElementById('apikey-name')?.value;
        const owner = document.getElementById('apikey-owner')?.value;
        const expiryDays = parseInt(document.getElementById('apikey-expiry')?.value) || 90;
        const scopesSelect = document.getElementById('apikey-scopes');
        const scopes = Array.from(scopesSelect?.selectedOptions || []).map(o => o.value);

        if (!name) {
            alert('Key name is required');
            return;
        }

        try {
            const res = await fetch('/api/apikeys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    owner_id: owner || 'dashboard',
                    scopes: scopes.length > 0 ? scopes : ['read:agents'],
                    expires_in_days: expiryDays > 0 ? expiryDays : null
                })
            });

            if (res.ok) {
                const result = await res.json();
                this.hideCreateApiKeyModal();
                // Show the generated key
                if (result.key) {
                    alert(`API Key Generated!\n\nKey: ${result.key}\n\nSave this key - it won't be shown again!`);
                }
                this.fetchApiKeysData();
            } else {
                const error = await res.json();
                alert(`Failed to generate key: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error generating API key:', error);
            alert('Failed to generate key');
        }
    }

    async suspendApiKey(keyId) {
        try {
            const res = await fetch(`/api/apikeys/${keyId}/suspend`, { method: 'POST' });
            if (res.ok) this.fetchApiKeysData();
        } catch (error) {
            console.error('Error suspending key:', error);
        }
    }

    async reactivateApiKey(keyId) {
        try {
            const res = await fetch(`/api/apikeys/${keyId}/reactivate`, { method: 'POST' });
            if (res.ok) this.fetchApiKeysData();
        } catch (error) {
            console.error('Error reactivating key:', error);
        }
    }

    async rotateApiKey(keyId) {
        if (!confirm('Rotate this API key? The old key will be invalidated.')) return;
        try {
            const res = await fetch(`/api/apikeys/${keyId}/rotate`, { method: 'POST' });
            if (res.ok) {
                const result = await res.json();
                if (result.new_key) {
                    alert(`New API Key: ${result.new_key}\n\nSave this key - it won't be shown again!`);
                }
                this.fetchApiKeysData();
            }
        } catch (error) {
            console.error('Error rotating key:', error);
        }
    }

    async revokeApiKey(keyId) {
        if (!confirm('Revoke this API key? This action cannot be undone.')) return;
        try {
            const res = await fetch(`/api/apikeys/${keyId}/revoke`, { method: 'POST' });
            if (res.ok) this.fetchApiKeysData();
        } catch (error) {
            console.error('Error revoking key:', error);
        }
    }

    // ==================== SESSIONS METHODS ====================
    async fetchSessionsData() {
        try {
            const [statusRes, activitiesRes] = await Promise.all([
                fetch('/api/sessions/status'),
                fetch('/api/sessions/activities/recent?limit=20')
            ]);

            const status = statusRes.ok ? await statusRes.json() : {};
            const activities = activitiesRes.ok ? await activitiesRes.json() : [];

            this.sessionsData = { status, activities };
            this.renderSessionsData(status, activities);
        } catch (error) {
            console.error('Error fetching sessions data:', error);
        }
    }

    renderSessionsData(status, activities) {
        // Handle array or object responses
        const activityList = Array.isArray(activities) ? activities : (activities.activities || []);
        const sessions = status.sessions || [];

        // Update metric cards
        const activeEl = document.getElementById('sessions-active');
        const todayEl = document.getElementById('sessions-today');
        const usersEl = document.getElementById('sessions-users');
        const durationEl = document.getElementById('sessions-duration');

        const activeSessions = sessions.filter(s => s.status === 'active');
        if (activeEl) activeEl.textContent = status.active_sessions || activeSessions.length;
        if (todayEl) todayEl.textContent = status.sessions_today || 0;
        if (usersEl) usersEl.textContent = status.unique_users || 0;

        // Format average duration
        if (durationEl) {
            const avgMins = status.avg_duration_minutes || 0;
            if (avgMins < 60) {
                durationEl.textContent = `${Math.round(avgMins)}m`;
            } else {
                durationEl.textContent = `${Math.round(avgMins / 60)}h`;
            }
        }

        // Count by status
        const statusCounts = { active: 0, locked: 0, expired: 0, revoked: 0 };
        for (const session of sessions) {
            const sessionStatus = (session.status || '').toLowerCase();
            if (statusCounts[sessionStatus] !== undefined) {
                statusCounts[sessionStatus]++;
            }
        }

        // Update breakdown
        const activeCountEl = document.getElementById('sessions-active-count');
        const lockedEl = document.getElementById('sessions-locked-count');
        const expiredEl = document.getElementById('sessions-expired-count');
        const revokedEl = document.getElementById('sessions-revoked-count');

        if (activeCountEl) activeCountEl.textContent = statusCounts.active;
        if (lockedEl) lockedEl.textContent = statusCounts.locked;
        if (expiredEl) expiredEl.textContent = statusCounts.expired;
        if (revokedEl) revokedEl.textContent = statusCounts.revoked;

        // Update list label
        const listLabel = document.getElementById('sessions-list-label');
        if (listLabel) listLabel.textContent = `${activeSessions.length} sessions`;

        // Render tables
        this.renderSessionsTable(activeSessions);
        this.renderSessionActivitiesTable(activityList);
    }

    renderSessionsTable(sessions) {
        const tableBody = document.getElementById('sessions-table');
        if (!tableBody) return;

        if (!sessions || sessions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No active sessions</td></tr>';
            return;
        }

        let html = '';
        for (const session of sessions.slice(0, 20)) {
            const started = session.created_at ? new Date(session.created_at).toLocaleString() : '-';
            const lastActive = session.last_activity ? new Date(session.last_activity).toLocaleString() : '-';
            const statusClass = this.getSessionStatusClass(session.status);

            html += `
                <tr>
                    <td>${this.escapeHtml(session.user_id || session.username || '-')}</td>
                    <td>${this.escapeHtml(session.ip_address || '-')}</td>
                    <td>${this.escapeHtml(session.device || session.user_agent || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(session.status || 'active')}</span></td>
                    <td>${started}</td>
                    <td>${lastActive}</td>
                    <td>
                        ${session.status === 'active' ?
                            `<button class="btn btn-sm" onclick="dashboard.lockSession('${session.id}')" title="Lock">Lock</button>` :
                            session.status === 'locked' ?
                            `<button class="btn btn-sm" onclick="dashboard.unlockSession('${session.id}')" title="Unlock">Unlock</button>` : ''
                        }
                        <button class="btn btn-sm btn-danger" onclick="dashboard.revokeSession('${session.id}')" title="Revoke">Revoke</button>
                    </td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    renderSessionActivitiesTable(activities) {
        const tableBody = document.getElementById('session-activities-table');
        if (!tableBody) return;

        if (!activities || activities.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No recent activity</td></tr>';
            return;
        }

        let html = '';
        for (const activity of activities.slice(0, 15)) {
            const timestamp = activity.timestamp ? new Date(activity.timestamp).toLocaleString() : '-';
            const statusClass = activity.success ? 'success' : 'error';
            const statusText = activity.success ? 'Success' : 'Failed';

            html += `
                <tr>
                    <td>${this.escapeHtml(activity.user_id || '-')}</td>
                    <td>${this.escapeHtml(activity.action || activity.activity_type || '-')}</td>
                    <td>${this.escapeHtml(activity.resource || activity.endpoint || '-')}</td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${timestamp}</td>
                </tr>
            `;
        }
        tableBody.innerHTML = html;
    }

    getSessionStatusClass(status) {
        const statusMap = {
            'active': 'success',
            'locked': 'warning',
            'expired': 'info',
            'revoked': 'error'
        };
        return statusMap[status?.toLowerCase()] || 'info';
    }

    refreshSessionsData() {
        this.fetchSessionsData();
    }

    async lockSession(sessionId) {
        try {
            const res = await fetch(`/api/sessions/${sessionId}/lock`, { method: 'POST' });
            if (res.ok) this.fetchSessionsData();
        } catch (error) {
            console.error('Error locking session:', error);
        }
    }

    async unlockSession(sessionId) {
        try {
            const res = await fetch(`/api/sessions/${sessionId}/unlock`, { method: 'POST' });
            if (res.ok) this.fetchSessionsData();
        } catch (error) {
            console.error('Error unlocking session:', error);
        }
    }

    async revokeSession(sessionId) {
        if (!confirm('Revoke this session? The user will be logged out.')) return;
        try {
            const res = await fetch(`/api/sessions/${sessionId}/revoke`, { method: 'POST' });
            if (res.ok) this.fetchSessionsData();
        } catch (error) {
            console.error('Error revoking session:', error);
        }
    }

    async cleanupSessions() {
        try {
            const res = await fetch('/api/sessions/cleanup', { method: 'POST' });
            if (res.ok) {
                const result = await res.json();
                alert(`Cleaned up ${result.removed || 0} expired sessions`);
                this.fetchSessionsData();
            }
        } catch (error) {
            console.error('Error cleaning up sessions:', error);
        }
    }

    // ==================== TENANCY METHODS ====================
    async fetchTenancyData() {
        try {
            const [tenantsRes, statsRes] = await Promise.all([
                fetch('/api/tenancy/tenants'),
                fetch('/api/tenancy/statistics')
            ]);

            const tenants = tenantsRes.ok ? await tenantsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderTenancyData(tenants, stats);
        } catch (error) {
            console.error('Error fetching tenancy data:', error);
        }
    }

    renderTenancyData(tenants, stats) {
        // Update summary metrics
        document.getElementById('tenancy-total').textContent = stats.total_tenants || 0;
        document.getElementById('tenancy-active').textContent = stats.active_tenants || 0;

        const byStatus = stats.tenants_by_status || {};
        document.getElementById('tenancy-suspended').textContent = byStatus.suspended || 0;

        const byTier = stats.tenants_by_tier || {};
        document.getElementById('tenancy-enterprise').textContent = byTier.enterprise || 0;

        // Update tier breakdown
        document.getElementById('tenancy-tier-free').textContent = byTier.free || 0;
        document.getElementById('tenancy-tier-basic').textContent = byTier.basic || 0;
        document.getElementById('tenancy-tier-standard').textContent = byTier.standard || 0;
        document.getElementById('tenancy-tier-premium').textContent = byTier.premium || 0;
        document.getElementById('tenancy-tier-enterprise').textContent = byTier.enterprise || 0;

        // Update list label
        document.getElementById('tenancy-list-label').textContent = `${tenants.length} tenant${tenants.length !== 1 ? 's' : ''}`;

        // Render tenants table
        this.renderTenantsTable(tenants);
    }

    renderTenantsTable(tenants) {
        const tbody = document.getElementById('tenancy-table');
        if (!tenants || tenants.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No tenants found</td></tr>';
            return;
        }

        tbody.innerHTML = tenants.map(t => `
            <tr>
                <td><code style="font-size: 0.75rem;">${t.tenant_id}</code></td>
                <td><strong>${this.escapeHtml(t.name)}</strong></td>
                <td><span class="status-badge ${this.getTierBadgeClass(t.tier)}">${t.tier?.toUpperCase()}</span></td>
                <td><span class="status-badge ${this.getTenantStatusBadgeClass(t.status)}">${t.status?.toUpperCase()}</span></td>
                <td>${t.agent_count || 0} / ${t.config?.max_agents || '-'}</td>
                <td>${t.network_count || 0} / ${t.config?.max_networks || '-'}</td>
                <td>${t.owner_email || '-'}</td>
                <td>${t.created_at ? new Date(t.created_at).toLocaleDateString() : '-'}</td>
                <td>
                    ${t.status === 'pending' ? `<button class="btn btn-sm" onclick="dashboard.activateTenant('${t.tenant_id}')" style="background: #10b981; color: white; padding: 2px 8px; font-size: 0.75rem;">Activate</button>` : ''}
                    ${t.status === 'active' ? `<button class="btn btn-sm" onclick="dashboard.suspendTenant('${t.tenant_id}')" style="background: #f59e0b; color: white; padding: 2px 8px; font-size: 0.75rem;">Suspend</button>` : ''}
                    ${t.status === 'suspended' ? `<button class="btn btn-sm" onclick="dashboard.activateTenant('${t.tenant_id}')" style="background: #10b981; color: white; padding: 2px 8px; font-size: 0.75rem;">Reactivate</button>` : ''}
                    ${t.tenant_id !== 'tenant-default' ? `<button class="btn btn-sm" onclick="dashboard.deleteTenant('${t.tenant_id}')" style="background: #ef4444; color: white; padding: 2px 8px; font-size: 0.75rem;">Delete</button>` : ''}
                </td>
            </tr>
        `).join('');
    }

    getTierBadgeClass(tier) {
        const map = {
            'free': 'info',
            'basic': 'success',
            'standard': 'warning',
            'premium': 'warning',
            'enterprise': 'success'
        };
        return map[tier?.toLowerCase()] || 'info';
    }

    getTenantStatusBadgeClass(status) {
        const map = {
            'pending': 'warning',
            'active': 'success',
            'suspended': 'error',
            'disabled': 'error',
            'deleted': 'error'
        };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshTenancyData() {
        this.fetchTenancyData();
    }

    showCreateTenantModal() {
        document.getElementById('create-tenant-modal').style.display = 'flex';
    }

    hideCreateTenantModal() {
        document.getElementById('create-tenant-modal').style.display = 'none';
        // Clear form
        document.getElementById('tenant-name').value = '';
        document.getElementById('tenant-description').value = '';
        document.getElementById('tenant-tier').value = 'standard';
        document.getElementById('tenant-owner-email').value = '';
    }

    async createTenant() {
        const name = document.getElementById('tenant-name').value.trim();
        const description = document.getElementById('tenant-description').value.trim();
        const tier = document.getElementById('tenant-tier').value;
        const ownerEmail = document.getElementById('tenant-owner-email').value.trim();

        if (!name) {
            alert('Tenant name is required');
            return;
        }

        try {
            const res = await fetch('/api/tenancy/tenants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    description,
                    tier,
                    owner_email: ownerEmail
                })
            });

            if (res.ok) {
                this.hideCreateTenantModal();
                this.fetchTenancyData();
            } else {
                const error = await res.json();
                alert(`Failed to create tenant: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating tenant:', error);
            alert('Failed to create tenant');
        }
    }

    async activateTenant(tenantId) {
        try {
            const res = await fetch(`/api/tenancy/tenants/${tenantId}/activate`, { method: 'POST' });
            if (res.ok) this.fetchTenancyData();
            else alert('Failed to activate tenant');
        } catch (error) {
            console.error('Error activating tenant:', error);
        }
    }

    async suspendTenant(tenantId) {
        const reason = prompt('Enter suspension reason (optional):');
        try {
            const res = await fetch(`/api/tenancy/tenants/${tenantId}/suspend`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: reason || '' })
            });
            if (res.ok) this.fetchTenancyData();
            else alert('Failed to suspend tenant');
        } catch (error) {
            console.error('Error suspending tenant:', error);
        }
    }

    async deleteTenant(tenantId) {
        if (!confirm('Are you sure you want to delete this tenant? This cannot be undone.')) return;
        try {
            const res = await fetch(`/api/tenancy/tenants/${tenantId}`, { method: 'DELETE' });
            if (res.ok) this.fetchTenancyData();
            else alert('Failed to delete tenant');
        } catch (error) {
            console.error('Error deleting tenant:', error);
        }
    }

    async updateTenantTier(tenantId) {
        const newTier = prompt('Enter new tier (free, basic, standard, premium, enterprise):');
        if (!newTier) return;

        const validTiers = ['free', 'basic', 'standard', 'premium', 'enterprise'];
        if (!validTiers.includes(newTier.toLowerCase())) {
            alert('Invalid tier. Must be one of: ' + validTiers.join(', '));
            return;
        }

        try {
            const res = await fetch(`/api/tenancy/tenants/${tenantId}/tier`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: newTier.toLowerCase() })
            });
            if (res.ok) this.fetchTenancyData();
            else alert('Failed to update tenant tier');
        } catch (error) {
            console.error('Error updating tenant tier:', error);
        }
    }

    // ==================== PLUGINS METHODS ====================
    async fetchPluginsData() {
        try {
            const [pluginsRes, statsRes, registryRes] = await Promise.all([
                fetch('/api/plugins'),
                fetch('/api/plugins/statistics'),
                fetch('/api/plugins/registry')
            ]);

            const plugins = pluginsRes.ok ? await pluginsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};
            const registry = registryRes.ok ? await registryRes.json() : [];

            this.renderPluginsData(plugins, stats, registry);
        } catch (error) {
            console.error('Error fetching plugins data:', error);
        }
    }

    renderPluginsData(plugins, stats, registry) {
        // Update summary metrics
        document.getElementById('plugins-total').textContent = stats.total_plugins || 0;
        document.getElementById('plugins-enabled').textContent = stats.enabled_plugins || 0;
        document.getElementById('plugins-hooks').textContent = stats.hooks?.total_hooks || 0;
        document.getElementById('plugins-registry').textContent = stats.registry?.total_entries || 0;

        // Update type breakdown
        const byType = stats.by_type || {};
        document.getElementById('plugins-type-protocol').textContent = byType.protocol || 0;
        document.getElementById('plugins-type-integration').textContent = byType.integration || 0;
        document.getElementById('plugins-type-visualization').textContent = byType.visualization || 0;
        document.getElementById('plugins-type-utility').textContent = byType.utility || 0;

        // Update list labels
        document.getElementById('plugins-list-label').textContent = `${plugins.length} plugin${plugins.length !== 1 ? 's' : ''}`;
        document.getElementById('registry-list-label').textContent = `${registry.length} available`;

        // Render tables
        this.renderPluginsTable(plugins);
        this.renderRegistryTable(registry);

        // Update registry select dropdown
        this.populateRegistrySelect(registry);
    }

    renderPluginsTable(plugins) {
        const tbody = document.getElementById('plugins-table');
        if (!plugins || plugins.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No plugins installed</td></tr>';
            return;
        }

        tbody.innerHTML = plugins.map(p => `
            <tr>
                <td><code style="font-size: 0.75rem;">${p.id}</code></td>
                <td><strong>${this.escapeHtml(p.name || p.metadata?.name || '-')}</strong></td>
                <td>${p.version || p.metadata?.version || '-'}</td>
                <td><span class="status-badge ${this.getPluginTypeBadgeClass(p.metadata?.plugin_type)}">${p.metadata?.plugin_type?.toUpperCase() || '-'}</span></td>
                <td><span class="status-badge ${this.getPluginStatusBadgeClass(p.status)}">${p.status?.toUpperCase()}</span></td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(p.metadata?.description || '')}">${p.metadata?.description || '-'}</td>
                <td>
                    ${p.status === 'enabled' ?
                        `<button class="btn btn-sm" onclick="dashboard.disablePlugin('${p.id}')" style="background: #f59e0b; color: white; padding: 2px 8px; font-size: 0.75rem;">Disable</button>` :
                        `<button class="btn btn-sm" onclick="dashboard.enablePlugin('${p.id}')" style="background: #10b981; color: white; padding: 2px 8px; font-size: 0.75rem;">Enable</button>`
                    }
                    <button class="btn btn-sm" onclick="dashboard.uninstallPlugin('${p.id}')" style="background: #ef4444; color: white; padding: 2px 8px; font-size: 0.75rem;">Uninstall</button>
                </td>
            </tr>
        `).join('');
    }

    renderRegistryTable(registry) {
        const tbody = document.getElementById('registry-table');
        if (!registry || registry.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No plugins in registry</td></tr>';
            return;
        }

        tbody.innerHTML = registry.map(r => `
            <tr>
                <td><strong>${this.escapeHtml(r.metadata?.name || r.name || '-')}</strong></td>
                <td>${r.metadata?.version || r.version || '-'}</td>
                <td><span class="status-badge ${this.getPluginTypeBadgeClass(r.metadata?.plugin_type)}">${r.metadata?.plugin_type?.toUpperCase() || '-'}</span></td>
                <td>${r.metadata?.author || '-'}</td>
                <td>${r.downloads || 0}</td>
                <td>${r.rating ? `${r.rating.toFixed(1)} / 5` : '-'}</td>
                <td>
                    <button class="btn btn-sm" onclick="dashboard.installFromRegistry('${r.metadata?.id || r.id}')" style="background: #ec4899; color: white; padding: 2px 8px; font-size: 0.75rem;">Install</button>
                </td>
            </tr>
        `).join('');
    }

    populateRegistrySelect(registry) {
        const select = document.getElementById('install-plugin-registry');
        select.innerHTML = '<option value="">-- Select a plugin --</option>';
        registry.forEach(r => {
            const id = r.metadata?.id || r.id;
            const name = r.metadata?.name || r.name || id;
            select.innerHTML += `<option value="${id}">${name} (${r.metadata?.version || 'latest'})</option>`;
        });
    }

    getPluginTypeBadgeClass(type) {
        const map = {
            'protocol': 'info',
            'integration': 'warning',
            'visualization': 'success',
            'utility': 'warning'
        };
        return map[type?.toLowerCase()] || 'info';
    }

    getPluginStatusBadgeClass(status) {
        const map = {
            'installed': 'info',
            'enabled': 'success',
            'disabled': 'warning',
            'error': 'error'
        };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshPluginsData() {
        this.fetchPluginsData();
    }

    showInstallPluginModal() {
        document.getElementById('install-plugin-modal').style.display = 'flex';
    }

    hideInstallPluginModal() {
        document.getElementById('install-plugin-modal').style.display = 'none';
        document.getElementById('install-plugin-id').value = '';
        document.getElementById('install-plugin-registry').value = '';
    }

    async installPlugin() {
        const pluginId = document.getElementById('install-plugin-id').value.trim();
        const registryId = document.getElementById('install-plugin-registry').value;

        const idToInstall = pluginId || registryId;
        if (!idToInstall) {
            alert('Please enter a plugin ID or select from registry');
            return;
        }

        try {
            const res = await fetch('/api/plugins/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plugin_id: idToInstall })
            });

            if (res.ok) {
                this.hideInstallPluginModal();
                this.fetchPluginsData();
            } else {
                const error = await res.json();
                alert(`Failed to install plugin: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error installing plugin:', error);
            alert('Failed to install plugin');
        }
    }

    async installFromRegistry(pluginId) {
        try {
            const res = await fetch('/api/plugins/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plugin_id: pluginId })
            });

            if (res.ok) {
                this.fetchPluginsData();
            } else {
                const error = await res.json();
                alert(`Failed to install plugin: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error installing plugin:', error);
        }
    }

    async enablePlugin(pluginId) {
        try {
            const res = await fetch(`/api/plugins/${pluginId}/enable`, { method: 'POST' });
            if (res.ok) this.fetchPluginsData();
            else alert('Failed to enable plugin');
        } catch (error) {
            console.error('Error enabling plugin:', error);
        }
    }

    async disablePlugin(pluginId) {
        try {
            const res = await fetch(`/api/plugins/${pluginId}/disable`, { method: 'POST' });
            if (res.ok) this.fetchPluginsData();
            else alert('Failed to disable plugin');
        } catch (error) {
            console.error('Error disabling plugin:', error);
        }
    }

    async uninstallPlugin(pluginId) {
        if (!confirm('Are you sure you want to uninstall this plugin?')) return;
        try {
            const res = await fetch(`/api/plugins/${pluginId}`, { method: 'DELETE' });
            if (res.ok) this.fetchPluginsData();
            else alert('Failed to uninstall plugin');
        } catch (error) {
            console.error('Error uninstalling plugin:', error);
        }
    }

    // ==================== RATE LIMITING METHODS ====================
    async fetchRateLimitData() {
        try {
            const [statsRes, tiersRes, logRes] = await Promise.all([
                fetch('/api/ratelimit/statistics'),
                fetch('/api/ratelimit/tiers'),
                fetch('/api/ratelimit/log?limit=50')
            ]);

            const stats = statsRes.ok ? await statsRes.json() : {};
            const tiers = tiersRes.ok ? await tiersRes.json() : [];
            const log = logRes.ok ? await logRes.json() : [];

            this.renderRateLimitData(stats, tiers, log);
        } catch (error) {
            console.error('Error fetching rate limit data:', error);
        }
    }

    renderRateLimitData(stats, tiers, log) {
        // Update summary metrics
        document.getElementById('ratelimit-rpm').textContent = stats.requests_last_minute || 0;
        document.getElementById('ratelimit-allowed').textContent = stats.allowed_last_minute || 0;
        document.getElementById('ratelimit-denied').textContent = stats.denied_last_minute || 0;

        const denialRate = stats.denial_rate || 0;
        document.getElementById('ratelimit-denial-rate').textContent = `${(denialRate * 100).toFixed(1)}%`;

        // Update breakdown
        document.getElementById('ratelimit-buckets').textContent = stats.bucket_stats?.total_buckets || 0;
        document.getElementById('ratelimit-windows').textContent = stats.window_stats?.total_windows || 0;
        document.getElementById('ratelimit-tiers').textContent = stats.tiers || 0;
        document.getElementById('ratelimit-users').textContent = stats.user_assignments || 0;
        document.getElementById('ratelimit-blocked').textContent = stats.blocked_keys || 0;

        // Update list labels
        document.getElementById('tiers-list-label').textContent = `${tiers.length} tier${tiers.length !== 1 ? 's' : ''}`;
        document.getElementById('requests-list-label').textContent = `${log.length} request${log.length !== 1 ? 's' : ''}`;

        // Render tables
        this.renderRateLimitTiersTable(tiers);
        this.renderRateLimitLogTable(log);
    }

    renderRateLimitTiersTable(tiers) {
        const tbody = document.getElementById('ratelimit-tiers-table');
        if (!tiers || tiers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No rate limit tiers configured</td></tr>';
            return;
        }

        tbody.innerHTML = tiers.map(t => `
            <tr>
                <td><strong>${this.escapeHtml(t.name)}</strong></td>
                <td>${t.requests_per_second || 0}</td>
                <td>${t.requests_per_minute || 0}</td>
                <td>${t.requests_per_hour || 0}</td>
                <td>${t.burst_size || 0}</td>
                <td><span class="status-badge info">${t.algorithm?.toUpperCase() || 'SLIDING_WINDOW'}</span></td>
            </tr>
        `).join('');
    }

    renderRateLimitLogTable(log) {
        const tbody = document.getElementById('ratelimit-log-table');
        if (!log || log.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No recent requests</td></tr>';
            return;
        }

        tbody.innerHTML = log.slice().reverse().map(r => `
            <tr>
                <td><code style="font-size: 0.75rem;">${r.key}</code></td>
                <td><span class="status-badge info">${r.tier?.toUpperCase()}</span></td>
                <td><span class="status-badge ${r.allowed ? 'success' : 'error'}">${r.allowed ? 'ALLOWED' : 'DENIED'}</span></td>
                <td>${r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    refreshRateLimitData() {
        this.fetchRateLimitData();
    }

    // ==================== EVENTS METHODS ====================
    async fetchEventsData() {
        try {
            const [busRes, subscribersRes, historyRes] = await Promise.all([
                fetch('/api/events/statistics'),
                fetch('/api/events/subscribers'),
                fetch('/api/events/history?limit=50')
            ]);

            const stats = busRes.ok ? await busRes.json() : {};
            const subscribers = subscribersRes.ok ? await subscribersRes.json() : [];
            const history = historyRes.ok ? await historyRes.json() : [];

            this.renderEventsData(stats, subscribers, history);
        } catch (error) {
            console.error('Error fetching events data:', error);
        }
    }

    renderEventsData(stats, subscribers, history) {
        // Update summary metrics
        document.getElementById('events-published').textContent = stats.total_published || 0;
        document.getElementById('events-delivered').textContent = stats.total_delivered || 0;
        document.getElementById('events-subscribers').textContent = subscribers.length || 0;
        document.getElementById('events-channels').textContent = stats.channels || 0;

        // Count events by category
        const byType = stats.by_type || {};
        let systemCount = 0, protocolCount = 0, networkCount = 0, agentCount = 0;
        Object.keys(byType).forEach(type => {
            if (type.startsWith('system.')) systemCount += byType[type];
            else if (type.startsWith('ospf.') || type.startsWith('bgp.') || type.startsWith('isis.')) protocolCount += byType[type];
            else if (type.startsWith('network.')) networkCount += byType[type];
            else if (type.startsWith('agent.')) agentCount += byType[type];
        });

        document.getElementById('events-type-system').textContent = systemCount;
        document.getElementById('events-type-protocol').textContent = protocolCount;
        document.getElementById('events-type-network').textContent = networkCount;
        document.getElementById('events-type-agent').textContent = agentCount;

        // Update list labels
        document.getElementById('events-list-label').textContent = `${history.length} event${history.length !== 1 ? 's' : ''}`;
        document.getElementById('subscribers-list-label').textContent = `${subscribers.length} subscriber${subscribers.length !== 1 ? 's' : ''}`;

        // Render tables
        this.renderEventsTable(history);
        this.renderSubscribersTable(subscribers);
    }

    renderEventsTable(events) {
        const tbody = document.getElementById('events-table');
        if (!events || events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No events recorded</td></tr>';
            return;
        }

        tbody.innerHTML = events.slice().reverse().map(e => `
            <tr>
                <td><span class="status-badge info">${e.event_type}</span></td>
                <td>${e.source || '-'}</td>
                <td><span class="status-badge ${this.getEventPriorityBadgeClass(e.priority)}">${this.getEventPriorityLabel(e.priority)}</span></td>
                <td>${e.delivery_count || 0}</td>
                <td>${e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '-'}</td>
                <td>${e.tags?.length > 0 ? e.tags.join(', ') : '-'}</td>
            </tr>
        `).join('');
    }

    renderSubscribersTable(subscribers) {
        const tbody = document.getElementById('subscribers-table');
        if (!subscribers || subscribers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No subscribers registered</td></tr>';
            return;
        }

        tbody.innerHTML = subscribers.map(s => `
            <tr>
                <td><code style="font-size: 0.75rem;">${s.id || s.subscriber_id}</code></td>
                <td>${s.event_types?.slice(0, 3).join(', ') || '-'}${s.event_types?.length > 3 ? '...' : ''}</td>
                <td><span class="status-badge ${s.active ? 'success' : 'warning'}">${s.active ? 'ACTIVE' : 'INACTIVE'}</span></td>
                <td>${s.events_received || 0}</td>
            </tr>
        `).join('');
    }

    getEventPriorityBadgeClass(priority) {
        const map = { 1: 'info', 2: 'success', 3: 'warning', 4: 'error' };
        return map[priority] || 'info';
    }

    getEventPriorityLabel(priority) {
        const map = { 1: 'LOW', 2: 'NORMAL', 3: 'HIGH', 4: 'CRITICAL' };
        return map[priority] || 'NORMAL';
    }

    refreshEventsData() {
        this.fetchEventsData();
    }

    showPublishEventModal() {
        document.getElementById('publish-event-modal').style.display = 'flex';
    }

    hidePublishEventModal() {
        document.getElementById('publish-event-modal').style.display = 'none';
        document.getElementById('publish-event-source').value = '';
        document.getElementById('publish-event-tags').value = '';
    }

    async publishEvent() {
        const eventType = document.getElementById('publish-event-type').value;
        const source = document.getElementById('publish-event-source').value.trim();
        const priority = parseInt(document.getElementById('publish-event-priority').value);
        const tagsInput = document.getElementById('publish-event-tags').value.trim();
        const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()) : [];

        if (!source) {
            alert('Event source is required');
            return;
        }

        try {
            const res = await fetch('/api/events/publish', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_type: eventType,
                    source,
                    priority,
                    tags
                })
            });

            if (res.ok) {
                this.hidePublishEventModal();
                this.fetchEventsData();
            } else {
                const error = await res.json();
                alert(`Failed to publish event: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error publishing event:', error);
            alert('Failed to publish event');
        }
    }

    // ==================== RULES METHODS ====================
    async fetchRulesData() {
        try {
            const [statsRes, rulesRes, setsRes] = await Promise.all([
                fetch('/api/rules/statistics'),
                fetch('/api/rules'),
                fetch('/api/rules/sets')
            ]);

            const stats = statsRes.ok ? await statsRes.json() : {};
            const rules = rulesRes.ok ? await rulesRes.json() : [];
            const sets = setsRes.ok ? await setsRes.json() : [];

            this.renderRulesData(stats, rules, sets);
        } catch (error) {
            console.error('Error fetching rules data:', error);
        }
    }

    renderRulesData(stats, rules, sets) {
        // Update summary metrics
        document.getElementById('rules-total').textContent = stats.total_rules || rules.length || 0;
        document.getElementById('rules-enabled').textContent = stats.enabled_rules || rules.filter(r => r.enabled).length || 0;
        document.getElementById('rules-executions').textContent = stats.total_executions || 0;
        document.getElementById('rules-sets').textContent = stats.total_rule_sets || sets.length || 0;

        // Update breakdown
        document.getElementById('rules-conditions').textContent = stats.total_conditions || 0;
        document.getElementById('rules-actions').textContent = stats.total_actions || 0;
        document.getElementById('rules-matches').textContent = stats.total_matches || 0;
        document.getElementById('rules-failures').textContent = stats.total_failures || 0;

        // Update list labels
        document.getElementById('rules-list-label').textContent = `${rules.length} rule${rules.length !== 1 ? 's' : ''}`;
        document.getElementById('rulesets-list-label').textContent = `${sets.length} rule set${sets.length !== 1 ? 's' : ''}`;

        // Render tables
        this.renderRulesTable(rules);
        this.renderRuleSetsTable(sets);
    }

    renderRulesTable(rules) {
        const tbody = document.getElementById('rules-table');
        if (!rules || rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No rules defined</td></tr>';
            return;
        }

        tbody.innerHTML = rules.map(r => `
            <tr>
                <td><strong>${this.escapeHtml(r.name)}</strong></td>
                <td><span class="status-badge ${this.getRulePriorityBadgeClass(r.priority)}">${this.getRulePriorityLabel(r.priority)}</span></td>
                <td>${r.condition_ids?.length || 0}</td>
                <td>${r.action_ids?.length || 0}</td>
                <td>${r.execution_count || 0}</td>
                <td><span class="status-badge ${r.enabled ? 'success' : 'warning'}">${r.enabled ? 'ENABLED' : 'DISABLED'}</span></td>
                <td>
                    ${r.enabled ?
                        `<button class="btn btn-sm" onclick="dashboard.disableRule('${r.id}')" style="background: #f59e0b; color: white; padding: 2px 8px; font-size: 0.75rem;">Disable</button>` :
                        `<button class="btn btn-sm" onclick="dashboard.enableRule('${r.id}')" style="background: #10b981; color: white; padding: 2px 8px; font-size: 0.75rem;">Enable</button>`
                    }
                    <button class="btn btn-sm" onclick="dashboard.deleteRule('${r.id}')" style="background: #ef4444; color: white; padding: 2px 8px; font-size: 0.75rem;">Delete</button>
                </td>
            </tr>
        `).join('');
    }

    renderRuleSetsTable(sets) {
        const tbody = document.getElementById('rulesets-table');
        if (!sets || sets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No rule sets defined</td></tr>';
            return;
        }

        tbody.innerHTML = sets.map(s => `
            <tr>
                <td><strong>${this.escapeHtml(s.name)}</strong></td>
                <td>${s.rule_ids?.length || 0}</td>
                <td><span class="status-badge ${s.enabled ? 'success' : 'warning'}">${s.enabled ? 'ACTIVE' : 'INACTIVE'}</span></td>
                <td>${s.last_run_at ? new Date(s.last_run_at).toLocaleString() : 'Never'}</td>
            </tr>
        `).join('');
    }

    getRulePriorityBadgeClass(priority) {
        const map = { 1: 'info', 2: 'info', 3: 'success', 4: 'warning', 5: 'warning', 6: 'error' };
        return map[priority] || 'info';
    }

    getRulePriorityLabel(priority) {
        const map = { 1: 'LOWEST', 2: 'LOW', 3: 'NORMAL', 4: 'HIGH', 5: 'HIGHEST', 6: 'CRITICAL' };
        return map[priority] || 'NORMAL';
    }

    refreshRulesData() {
        this.fetchRulesData();
    }

    showCreateRuleModal() {
        document.getElementById('create-rule-modal').style.display = 'flex';
    }

    hideCreateRuleModal() {
        document.getElementById('create-rule-modal').style.display = 'none';
        document.getElementById('rule-name').value = '';
        document.getElementById('rule-description').value = '';
        document.getElementById('rule-tags').value = '';
    }

    async createRule() {
        const name = document.getElementById('rule-name').value.trim();
        const description = document.getElementById('rule-description').value.trim();
        const priority = parseInt(document.getElementById('rule-priority').value);
        const enabled = document.getElementById('rule-enabled').value === 'true';
        const tagsInput = document.getElementById('rule-tags').value.trim();
        const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()) : [];

        if (!name) {
            alert('Rule name is required');
            return;
        }

        try {
            const res = await fetch('/api/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, priority, enabled, tags })
            });

            if (res.ok) {
                this.hideCreateRuleModal();
                this.fetchRulesData();
            } else {
                const error = await res.json();
                alert(`Failed to create rule: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating rule:', error);
            alert('Failed to create rule');
        }
    }

    async enableRule(ruleId) {
        try {
            const res = await fetch(`/api/rules/${ruleId}/enable`, { method: 'POST' });
            if (res.ok) this.fetchRulesData();
            else alert('Failed to enable rule');
        } catch (error) {
            console.error('Error enabling rule:', error);
        }
    }

    async disableRule(ruleId) {
        try {
            const res = await fetch(`/api/rules/${ruleId}/disable`, { method: 'POST' });
            if (res.ok) this.fetchRulesData();
            else alert('Failed to disable rule');
        } catch (error) {
            console.error('Error disabling rule:', error);
        }
    }

    async deleteRule(ruleId) {
        if (!confirm('Are you sure you want to delete this rule?')) return;
        try {
            const res = await fetch(`/api/rules/${ruleId}`, { method: 'DELETE' });
            if (res.ok) this.fetchRulesData();
            else alert('Failed to delete rule');
        } catch (error) {
            console.error('Error deleting rule:', error);
        }
    }

    // ==================== MESSAGING METHODS ====================
    async fetchMessagingData() {
        try {
            const [statsRes, messagesRes, topicsRes] = await Promise.all([
                fetch('/api/messaging/statistics'),
                fetch('/api/messaging/history?limit=50'),
                fetch('/api/messaging/topics')
            ]);

            const stats = statsRes.ok ? await statsRes.json() : {};
            const messages = messagesRes.ok ? await messagesRes.json() : [];
            const topics = topicsRes.ok ? await topicsRes.json() : [];

            this.renderMessagingData(stats, messages, topics);
        } catch (error) {
            console.error('Error fetching messaging data:', error);
        }
    }

    renderMessagingData(stats, messages, topics) {
        // Update summary metrics
        document.getElementById('messaging-sent').textContent = stats.messages_sent || 0;
        document.getElementById('messaging-received').textContent = stats.messages_received || 0;
        document.getElementById('messaging-topics').textContent = stats.active_topics || topics.length || 0;
        document.getElementById('messaging-subs').textContent = stats.total_subscribers || 0;

        // Update breakdown by message type
        const byType = stats.by_type || {};
        document.getElementById('messaging-routes').textContent = byType.route_update || 0;
        document.getElementById('messaging-health').textContent = byType.health_status || 0;
        document.getElementById('messaging-alerts').textContent = byType.alert || 0;
        document.getElementById('messaging-pending').textContent = stats.pending_ack || 0;

        // Update list labels
        document.getElementById('messages-list-label').textContent = `${messages.length} message${messages.length !== 1 ? 's' : ''}`;
        document.getElementById('topics-list-label').textContent = `${topics.length} topic${topics.length !== 1 ? 's' : ''}`;

        // Render tables
        this.renderMessagesTable(messages);
        this.renderTopicsTable(topics);
    }

    renderMessagesTable(messages) {
        const tbody = document.getElementById('messages-table');
        if (!messages || messages.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No messages</td></tr>';
            return;
        }

        tbody.innerHTML = messages.slice().reverse().map(m => `
            <tr>
                <td><span class="status-badge info">${m.message_type}</span></td>
                <td><code style="font-size: 0.75rem;">${m.sender_id || '-'}</code></td>
                <td><code style="font-size: 0.75rem;">${m.recipient_id || 'broadcast'}</code></td>
                <td>${m.topic || '-'}</td>
                <td><span class="status-badge ${this.getMessagePriorityBadgeClass(m.priority)}">${this.getMessagePriorityLabel(m.priority)}</span></td>
                <td><span class="status-badge ${m.acknowledged ? 'success' : 'warning'}">${m.acknowledged ? 'ACK' : 'PENDING'}</span></td>
                <td>${m.timestamp ? new Date(m.timestamp).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    renderTopicsTable(topics) {
        const tbody = document.getElementById('topics-table');
        if (!topics || topics.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No active topics</td></tr>';
            return;
        }

        tbody.innerHTML = topics.map(t => `
            <tr>
                <td><strong>${this.escapeHtml(t.name || t.topic)}</strong></td>
                <td>${t.subscriber_count || 0}</td>
                <td>${t.message_count || 0}</td>
                <td>${t.last_activity ? new Date(t.last_activity).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getMessagePriorityBadgeClass(priority) {
        const map = { 0: 'info', 1: 'success', 2: 'warning', 3: 'error' };
        return map[priority] || 'info';
    }

    getMessagePriorityLabel(priority) {
        const map = { 0: 'LOW', 1: 'NORMAL', 2: 'HIGH', 3: 'CRITICAL' };
        return map[priority] || 'NORMAL';
    }

    refreshMessagingData() {
        this.fetchMessagingData();
    }

    showSendMessageModal() {
        document.getElementById('send-message-modal').style.display = 'flex';
    }

    hideSendMessageModal() {
        document.getElementById('send-message-modal').style.display = 'none';
        document.getElementById('message-recipient').value = '';
        document.getElementById('message-topic').value = '';
    }

    async sendMessage() {
        const messageType = document.getElementById('message-type').value;
        const recipientId = document.getElementById('message-recipient').value.trim() || null;
        const topic = document.getElementById('message-topic').value.trim() || null;
        const priority = parseInt(document.getElementById('message-priority').value);

        try {
            const res = await fetch('/api/messaging/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message_type: messageType,
                    recipient_id: recipientId,
                    topic,
                    priority,
                    payload: {}
                })
            });

            if (res.ok) {
                this.hideSendMessageModal();
                this.fetchMessagingData();
            } else {
                const error = await res.json();
                alert(`Failed to send message: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error sending message:', error);
            alert('Failed to send message');
        }
    }

    // ==================== HEALING METHODS ====================
    async fetchHealingData() {
        try {
            const [anomaliesRes, actionsRes, statsRes] = await Promise.all([
                fetch('/api/healing/anomalies?limit=50'),
                fetch('/api/healing/actions?limit=50'),
                fetch('/api/healing/statistics')
            ]);

            const anomalies = anomaliesRes.ok ? await anomaliesRes.json() : [];
            const actions = actionsRes.ok ? await actionsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderHealingData(anomalies, actions, stats);
        } catch (error) {
            console.error('Error fetching healing data:', error);
        }
    }

    renderHealingData(anomalies, actions, stats) {
        // Update summary metrics
        document.getElementById('healing-anomalies').textContent = stats.total_anomalies || anomalies.length || 0;
        document.getElementById('healing-actions').textContent = stats.total_actions || actions.length || 0;

        const successRate = stats.success_rate || 0;
        document.getElementById('healing-success-rate').textContent = `${(successRate * 100).toFixed(0)}%`;
        document.getElementById('healing-monitors').textContent = stats.active_monitors || 0;

        // Update breakdown by anomaly type
        const byType = stats.by_type || {};
        document.getElementById('healing-adjacency').textContent = byType.adjacency_loss || 0;
        document.getElementById('healing-route').textContent = byType.route_withdrawal || 0;
        document.getElementById('healing-protocol').textContent = byType.protocol_state || 0;
        document.getElementById('healing-remediated').textContent = stats.auto_remediated || 0;

        // Update list labels
        document.getElementById('anomalies-list-label').textContent = `${anomalies.length} anomal${anomalies.length !== 1 ? 'ies' : 'y'}`;
        document.getElementById('remediation-list-label').textContent = `${actions.length} action${actions.length !== 1 ? 's' : ''}`;

        // Render tables
        this.renderAnomaliesTable(anomalies);
        this.renderRemediationTable(actions);
    }

    renderAnomaliesTable(anomalies) {
        const tbody = document.getElementById('anomalies-table');
        if (!anomalies || anomalies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No anomalies detected</td></tr>';
            return;
        }

        tbody.innerHTML = anomalies.slice().reverse().map(a => `
            <tr>
                <td><span class="status-badge ${this.getAnomalyTypeBadgeClass(a.anomaly_type)}">${a.anomaly_type || a.type}</span></td>
                <td><code style="font-size: 0.75rem;">${a.agent_id || '-'}</code></td>
                <td><span class="status-badge ${this.getSeverityBadgeClass(a.severity)}">${a.severity || 'MEDIUM'}</span></td>
                <td><span class="status-badge ${a.resolved ? 'success' : 'warning'}">${a.resolved ? 'RESOLVED' : 'ACTIVE'}</span></td>
                <td>${a.detected_at || a.timestamp ? new Date(a.detected_at || a.timestamp).toLocaleTimeString() : '-'}</td>
                <td>
                    ${!a.resolved ? `<button class="btn btn-sm" onclick="dashboard.remediateAnomaly('${a.anomaly_id || a.id}')" style="background: #22c55e; color: white; padding: 2px 8px; font-size: 0.75rem;">Remediate</button>` : ''}
                </td>
            </tr>
        `).join('');
    }

    renderRemediationTable(actions) {
        const tbody = document.getElementById('remediation-table');
        if (!actions || actions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No remediation actions taken</td></tr>';
            return;
        }

        tbody.innerHTML = actions.slice().reverse().map(a => `
            <tr>
                <td><strong>${a.action_id || a.name || '-'}</strong></td>
                <td><code style="font-size: 0.75rem;">${a.agent_id || '-'}</code></td>
                <td>${a.event_type || '-'}</td>
                <td><span class="status-badge ${this.getActionStatusBadgeClass(a.status)}">${a.status?.toUpperCase()}</span></td>
                <td>${a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getAnomalyTypeBadgeClass(type) {
        const map = {
            'adjacency_loss': 'error',
            'route_withdrawal': 'warning',
            'protocol_state': 'warning',
            'metric_spike': 'info'
        };
        return map[type?.toLowerCase()] || 'info';
    }

    getSeverityBadgeClass(severity) {
        if (typeof severity === 'number') {
            if (severity >= 8) return 'error';
            if (severity >= 5) return 'warning';
            return 'info';
        }
        const map = { 'critical': 'error', 'high': 'error', 'medium': 'warning', 'low': 'info' };
        return map[severity?.toLowerCase()] || 'info';
    }

    getActionStatusBadgeClass(status) {
        const map = {
            'success': 'success',
            'pending': 'warning',
            'running': 'info',
            'failed': 'error',
            'rolled_back': 'warning'
        };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshHealingData() {
        this.fetchHealingData();
    }

    async remediateAnomaly(anomalyId) {
        try {
            const res = await fetch(`/api/healing/remediate/${anomalyId}`, { method: 'POST' });
            if (res.ok) this.fetchHealingData();
            else alert('Failed to remediate anomaly');
        } catch (error) {
            console.error('Error remediating anomaly:', error);
        }
    }

    // ==================== PIPELINES METHODS ====================
    async fetchPipelinesData() {
        try {
            const [pipelinesRes, statsRes] = await Promise.all([
                fetch('/api/pipelines'),
                fetch('/api/pipelines/statistics')
            ]);

            const pipelines = pipelinesRes.ok ? await pipelinesRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderPipelinesData(pipelines, stats);
        } catch (error) {
            console.error('Error fetching pipelines data:', error);
        }
    }

    renderPipelinesData(pipelines, stats) {
        // Update summary metrics
        document.getElementById('pipelines-total').textContent = stats.total_pipelines || pipelines.length || 0;
        document.getElementById('pipelines-running').textContent = stats.running_pipelines || pipelines.filter(p => p.status === 'running').length || 0;
        document.getElementById('pipelines-completed').textContent = stats.completed_today || 0;
        document.getElementById('pipelines-failed').textContent = stats.failed_today || 0;

        // Update breakdown
        document.getElementById('pipelines-sources').textContent = stats.total_sources || 0;
        document.getElementById('pipelines-transforms').textContent = stats.total_transforms || 0;
        document.getElementById('pipelines-sinks').textContent = stats.total_sinks || 0;
        document.getElementById('pipelines-throughput').textContent = stats.records_per_minute || 0;

        // Update list label
        document.getElementById('pipelines-list-label').textContent = `${pipelines.length} pipeline${pipelines.length !== 1 ? 's' : ''}`;

        // Render table
        this.renderPipelinesTable(pipelines);
    }

    renderPipelinesTable(pipelines) {
        const tbody = document.getElementById('pipelines-table');
        if (!pipelines || pipelines.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No pipelines configured</td></tr>';
            return;
        }

        tbody.innerHTML = pipelines.map(p => `
            <tr>
                <td><strong>${this.escapeHtml(p.name)}</strong></td>
                <td>${p.source_type || '-'}</td>
                <td>${p.transform_count || p.transforms?.length || 0}</td>
                <td>${p.sink_type || '-'}</td>
                <td><span class="status-badge ${this.getPipelineStatusBadgeClass(p.status)}">${p.status?.toUpperCase()}</span></td>
                <td>${p.last_run_at ? new Date(p.last_run_at).toLocaleString() : 'Never'}</td>
                <td>
                    ${p.status !== 'running' ?
                        `<button class="btn btn-sm" onclick="dashboard.startPipeline('${p.id}')" style="background: #10b981; color: white; padding: 2px 8px; font-size: 0.75rem;">Start</button>` :
                        `<button class="btn btn-sm" onclick="dashboard.stopPipeline('${p.id}')" style="background: #f59e0b; color: white; padding: 2px 8px; font-size: 0.75rem;">Stop</button>`
                    }
                    <button class="btn btn-sm" onclick="dashboard.deletePipeline('${p.id}')" style="background: #ef4444; color: white; padding: 2px 8px; font-size: 0.75rem;">Delete</button>
                </td>
            </tr>
        `).join('');
    }

    getPipelineStatusBadgeClass(status) {
        const map = {
            'running': 'success',
            'idle': 'info',
            'stopped': 'warning',
            'failed': 'error',
            'completed': 'success'
        };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshPipelinesData() {
        this.fetchPipelinesData();
    }

    showCreatePipelineModal() {
        document.getElementById('create-pipeline-modal').style.display = 'flex';
    }

    hideCreatePipelineModal() {
        document.getElementById('create-pipeline-modal').style.display = 'none';
        document.getElementById('pipeline-name').value = '';
        document.getElementById('pipeline-description').value = '';
    }

    async createPipeline() {
        const name = document.getElementById('pipeline-name').value.trim();
        const description = document.getElementById('pipeline-description').value.trim();
        const sourceType = document.getElementById('pipeline-source').value;
        const sinkType = document.getElementById('pipeline-sink').value;

        if (!name) {
            alert('Pipeline name is required');
            return;
        }

        try {
            const res = await fetch('/api/pipelines', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, source_type: sourceType, sink_type: sinkType })
            });

            if (res.ok) {
                this.hideCreatePipelineModal();
                this.fetchPipelinesData();
            } else {
                const error = await res.json();
                alert(`Failed to create pipeline: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating pipeline:', error);
            alert('Failed to create pipeline');
        }
    }

    async startPipeline(pipelineId) {
        try {
            const res = await fetch(`/api/pipelines/${pipelineId}/start`, { method: 'POST' });
            if (res.ok) this.fetchPipelinesData();
            else alert('Failed to start pipeline');
        } catch (error) {
            console.error('Error starting pipeline:', error);
        }
    }

    async stopPipeline(pipelineId) {
        try {
            const res = await fetch(`/api/pipelines/${pipelineId}/stop`, { method: 'POST' });
            if (res.ok) this.fetchPipelinesData();
            else alert('Failed to stop pipeline');
        } catch (error) {
            console.error('Error stopping pipeline:', error);
        }
    }

    async deletePipeline(pipelineId) {
        if (!confirm('Are you sure you want to delete this pipeline?')) return;
        try {
            const res = await fetch(`/api/pipelines/${pipelineId}`, { method: 'DELETE' });
            if (res.ok) this.fetchPipelinesData();
            else alert('Failed to delete pipeline');
        } catch (error) {
            console.error('Error deleting pipeline:', error);
        }
    }

    // ==================== NOTIFICATIONS METHODS ====================
    async fetchNotificationsData() {
        try {
            const [statsRes, historyRes] = await Promise.all([
                fetch('/api/notifications/statistics'),
                fetch('/api/notifications/history?limit=50')
            ]);

            const stats = statsRes.ok ? await statsRes.json() : {};
            const history = historyRes.ok ? await historyRes.json() : [];

            this.renderNotificationsData(stats, history);
        } catch (error) {
            console.error('Error fetching notifications data:', error);
        }
    }

    renderNotificationsData(stats, history) {
        // Update summary metrics
        document.getElementById('notifications-sent').textContent = stats.total_sent || 0;
        document.getElementById('notifications-delivered').textContent = stats.total_delivered || 0;
        document.getElementById('notifications-pending').textContent = stats.pending || 0;
        document.getElementById('notifications-channels').textContent = stats.active_channels || 0;

        // Update breakdown by channel
        const byChannel = stats.by_channel || {};
        document.getElementById('notifications-email').textContent = byChannel.email || 0;
        document.getElementById('notifications-slack').textContent = byChannel.slack || 0;
        document.getElementById('notifications-webhook').textContent = byChannel.webhook || 0;
        document.getElementById('notifications-sms').textContent = byChannel.sms || 0;

        // Update list label
        document.getElementById('notifications-list-label').textContent = `${history.length} notification${history.length !== 1 ? 's' : ''}`;

        // Render table
        this.renderNotificationsTable(history);
    }

    renderNotificationsTable(notifications) {
        const tbody = document.getElementById('notifications-table');
        if (!notifications || notifications.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No notifications sent</td></tr>';
            return;
        }

        tbody.innerHTML = notifications.slice().reverse().map(n => `
            <tr>
                <td><span class="status-badge ${this.getChannelBadgeClass(n.channel)}">${n.channel?.toUpperCase()}</span></td>
                <td>${n.recipient || '-'}</td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(n.subject || '')}">${n.subject || '-'}</td>
                <td><span class="status-badge ${this.getNotificationPriorityBadgeClass(n.priority)}">${n.priority?.toUpperCase()}</span></td>
                <td><span class="status-badge ${this.getNotificationStatusBadgeClass(n.status)}">${n.status?.toUpperCase()}</span></td>
                <td>${n.sent_at ? new Date(n.sent_at).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getChannelBadgeClass(channel) {
        const map = { 'email': 'info', 'slack': 'success', 'webhook': 'warning', 'sms': 'warning' };
        return map[channel?.toLowerCase()] || 'info';
    }

    getNotificationPriorityBadgeClass(priority) {
        const map = { 'low': 'info', 'normal': 'success', 'high': 'warning', 'critical': 'error' };
        return map[priority?.toLowerCase()] || 'info';
    }

    getNotificationStatusBadgeClass(status) {
        const map = { 'sent': 'success', 'delivered': 'success', 'pending': 'warning', 'failed': 'error' };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshNotificationsData() {
        this.fetchNotificationsData();
    }

    showSendNotificationModal() {
        document.getElementById('send-notification-modal').style.display = 'flex';
    }

    hideSendNotificationModal() {
        document.getElementById('send-notification-modal').style.display = 'none';
        document.getElementById('notification-recipient').value = '';
        document.getElementById('notification-subject').value = '';
    }

    async sendNotification() {
        const channel = document.getElementById('notification-channel').value;
        const recipient = document.getElementById('notification-recipient').value.trim();
        const subject = document.getElementById('notification-subject').value.trim();
        const priority = document.getElementById('notification-priority').value;

        if (!recipient || !subject) {
            alert('Recipient and subject are required');
            return;
        }

        try {
            const res = await fetch('/api/notifications/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel, recipient, subject, priority, body: '' })
            });

            if (res.ok) {
                this.hideSendNotificationModal();
                this.fetchNotificationsData();
            } else {
                const error = await res.json();
                alert(`Failed to send notification: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error sending notification:', error);
            alert('Failed to send notification');
        }
    }

    // ==================== FSM METHODS ====================
    async fetchFSMData() {
        const protocol = document.getElementById('fsm-protocol-filter')?.value || 'all';
        try {
            const [machinesRes, transitionsRes, statsRes] = await Promise.all([
                fetch(`/api/fsm/machines?protocol=${protocol}`),
                fetch('/api/fsm/transitions?limit=50'),
                fetch('/api/fsm/statistics')
            ]);

            const machines = machinesRes.ok ? await machinesRes.json() : [];
            const transitions = transitionsRes.ok ? await transitionsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderFSMData(machines, transitions, stats);
        } catch (error) {
            console.error('Error fetching FSM data:', error);
        }
    }

    renderFSMData(machines, transitions, stats) {
        // Update summary metrics
        document.getElementById('fsm-machines-count').textContent = machines.length || 0;
        document.getElementById('fsm-transitions-count').textContent = stats.transitions_per_hour || 0;
        document.getElementById('fsm-stable-count').textContent = machines.filter(m => !m.is_flapping).length || 0;
        document.getElementById('fsm-flapping-count').textContent = machines.filter(m => m.is_flapping).length || 0;

        // Render tables
        this.renderFSMMachinesTable(machines);
        this.renderFSMTransitionsTable(transitions);
    }

    renderFSMMachinesTable(machines) {
        const tbody = document.getElementById('fsm-machines-table');
        if (!machines || machines.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No state machines tracked</td></tr>';
            return;
        }

        tbody.innerHTML = machines.map(m => `
            <tr>
                <td><span class="status-badge ${this.getFSMProtocolBadgeClass(m.protocol)}">${m.protocol?.toUpperCase()}</span></td>
                <td>${m.peer || '-'}</td>
                <td><span class="status-badge ${this.getFSMStateBadgeClass(m.current_state)}">${m.current_state?.toUpperCase()}</span></td>
                <td>${m.previous_state?.toUpperCase() || '-'}</td>
                <td>${m.transition_count || 0}</td>
                <td>${m.last_change ? new Date(m.last_change).toLocaleTimeString() : '-'}</td>
                <td>${m.uptime || '-'}</td>
            </tr>
        `).join('');
    }

    renderFSMTransitionsTable(transitions) {
        const tbody = document.getElementById('fsm-transitions-table');
        if (!transitions || transitions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No recent transitions</td></tr>';
            return;
        }

        tbody.innerHTML = transitions.map(t => `
            <tr>
                <td>${t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : '-'}</td>
                <td><span class="status-badge ${this.getFSMProtocolBadgeClass(t.protocol)}">${t.protocol?.toUpperCase()}</span></td>
                <td>${t.peer || '-'}</td>
                <td>${t.from_state?.toUpperCase() || '-'}</td>
                <td><span class="status-badge ${this.getFSMStateBadgeClass(t.to_state)}">${t.to_state?.toUpperCase()}</span></td>
                <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(t.reason || '')}">${t.reason || '-'}</td>
            </tr>
        `).join('');
    }

    getFSMProtocolBadgeClass(protocol) {
        const map = { 'ospf': 'info', 'bgp': 'warning', 'isis': 'success', 'lacp': 'warning' };
        return map[protocol?.toLowerCase()] || 'info';
    }

    getFSMStateBadgeClass(state) {
        const fullStates = ['full', 'established', 'up', 'active'];
        const downStates = ['down', 'idle', 'init'];
        const s = state?.toLowerCase();
        if (fullStates.includes(s)) return 'success';
        if (downStates.includes(s)) return 'error';
        return 'warning';
    }

    filterFSMByProtocol() {
        this.fetchFSMData();
    }

    refreshFSMData() {
        this.fetchFSMData();
    }

    // ==================== ACTIONS METHODS ====================
    async fetchActionsData() {
        try {
            const [queueRes, safetyRes, statsRes] = await Promise.all([
                fetch('/api/actions/queue'),
                fetch('/api/actions/safety'),
                fetch('/api/actions/statistics')
            ]);

            const queue = queueRes.ok ? await queueRes.json() : [];
            const safety = safetyRes.ok ? await safetyRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderActionsData(queue, safety, stats);
        } catch (error) {
            console.error('Error fetching actions data:', error);
        }
    }

    renderActionsData(queue, safety, stats) {
        // Update summary metrics
        document.getElementById('actions-total-count').textContent = stats.total || 0;
        document.getElementById('actions-pending-count').textContent = stats.pending || 0;
        document.getElementById('actions-completed-count').textContent = stats.completed || 0;
        document.getElementById('actions-blocked-count').textContent = stats.blocked || 0;

        // Render tables
        this.renderActionsQueueTable(queue);
        this.renderSafetyConstraintsTable(safety);
    }

    renderActionsQueueTable(actions) {
        const tbody = document.getElementById('actions-queue-table');
        if (!actions || actions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No actions in queue</td></tr>';
            return;
        }

        tbody.innerHTML = actions.map(a => `
            <tr>
                <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(a.description || '')}">${a.description || '-'}</td>
                <td>${a.target || '-'}</td>
                <td><span class="status-badge ${this.getActionPriorityBadgeClass(a.priority)}">${a.priority?.toUpperCase()}</span></td>
                <td><span class="status-badge ${this.getActionStatusBadgeClass(a.status)}">${a.status?.toUpperCase()}</span></td>
                <td><span class="status-badge ${a.safety_check === 'passed' ? 'success' : 'error'}">${a.safety_check?.toUpperCase()}</span></td>
                <td>${a.created_at ? new Date(a.created_at).toLocaleTimeString() : '-'}</td>
                <td>
                    ${a.status === 'pending' ? `
                        <button class="btn btn-sm" onclick="dashboard.approveAction('${a.id}')" title="Approve" style="background: #10b981; border-color: #10b981;">
                            <i class="fas fa-check"></i>
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.rejectAction('${a.id}')" title="Reject">
                            <i class="fas fa-times"></i>
                        </button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    }

    renderSafetyConstraintsTable(constraints) {
        const tbody = document.getElementById('actions-safety-table');
        if (!constraints || constraints.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No safety constraints</td></tr>';
            return;
        }

        tbody.innerHTML = constraints.map(c => `
            <tr>
                <td>${c.name || '-'}</td>
                <td><span class="status-badge info">${c.type?.toUpperCase()}</span></td>
                <td>${c.violations || 0}</td>
                <td><span class="status-badge ${c.enabled ? 'success' : 'warning'}">${c.enabled ? 'ENABLED' : 'DISABLED'}</span></td>
                <td>${c.last_checked ? new Date(c.last_checked).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getActionPriorityBadgeClass(priority) {
        const map = { 'low': 'info', 'normal': 'success', 'high': 'warning', 'critical': 'error' };
        return map[priority?.toLowerCase()] || 'info';
    }

    getActionStatusBadgeClass(status) {
        const map = { 'pending': 'warning', 'approved': 'success', 'executing': 'info', 'completed': 'success', 'rejected': 'error', 'blocked': 'error' };
        return map[status?.toLowerCase()] || 'info';
    }

    async approveAction(id) {
        if (!confirm('Approve this action for execution?')) return;

        try {
            const res = await fetch(`/api/actions/${id}/approve`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchActionsData();
            } else {
                const error = await res.json();
                alert(`Failed to approve: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error approving action:', error);
            alert('Failed to approve action');
        }
    }

    async rejectAction(id) {
        if (!confirm('Reject this action?')) return;

        try {
            const res = await fetch(`/api/actions/${id}/reject`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchActionsData();
            } else {
                const error = await res.json();
                alert(`Failed to reject: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error rejecting action:', error);
            alert('Failed to reject action');
        }
    }

    refreshActionsData() {
        this.fetchActionsData();
    }

    // ==================== GRAPHQL METHODS ====================
    async fetchGraphQLData() {
        try {
            const [historyRes, statsRes] = await Promise.all([
                fetch('/api/graphql/history?limit=20'),
                fetch('/api/graphql/statistics')
            ]);

            const history = historyRes.ok ? await historyRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderGraphQLData(history, stats);
        } catch (error) {
            console.error('Error fetching GraphQL data:', error);
        }
    }

    renderGraphQLData(history, stats) {
        // Update summary metrics
        document.getElementById('graphql-queries-count').textContent = stats.queries_today || 0;
        document.getElementById('graphql-mutations-count').textContent = stats.mutations_today || 0;
        document.getElementById('graphql-errors-count').textContent = stats.errors_today || 0;
        document.getElementById('graphql-avg-time').textContent = stats.avg_response_ms ? `${stats.avg_response_ms.toFixed(0)} ms` : '-';

        // Render history table
        this.renderGraphQLHistoryTable(history);
    }

    renderGraphQLHistoryTable(history) {
        const tbody = document.getElementById('graphql-history-table');
        if (!history || history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No recent queries</td></tr>';
            return;
        }

        tbody.innerHTML = history.map(h => `
            <tr>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace;" title="${this.escapeHtml(h.operation || '')}">${h.operation || '-'}</td>
                <td><span class="status-badge ${h.type === 'mutation' ? 'warning' : 'info'}">${h.type?.toUpperCase()}</span></td>
                <td>${h.duration_ms ? `${h.duration_ms.toFixed(0)} ms` : '-'}</td>
                <td><span class="status-badge ${h.status === 'success' ? 'success' : 'error'}">${h.status?.toUpperCase()}</span></td>
                <td>${h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    async executeGraphQL() {
        const query = document.getElementById('graphql-query').value.trim();
        if (!query) {
            alert('Please enter a GraphQL query');
            return;
        }

        try {
            const res = await fetch('/api/graphql', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });

            const result = await res.json();
            document.getElementById('graphql-result').textContent = JSON.stringify(result, null, 2);
            this.fetchGraphQLData();
        } catch (error) {
            console.error('Error executing GraphQL query:', error);
            document.getElementById('graphql-result').textContent = `Error: ${error.message}`;
        }
    }

    refreshGraphQLData() {
        this.fetchGraphQLData();
    }

    // ==================== INTEGRATION METHODS ====================
    async fetchIntegrationData() {
        try {
            const [connectorsRes, eventsRes, statsRes] = await Promise.all([
                fetch('/api/integration/connectors'),
                fetch('/api/integration/events?limit=50'),
                fetch('/api/integration/statistics')
            ]);

            const connectors = connectorsRes.ok ? await connectorsRes.json() : [];
            const events = eventsRes.ok ? await eventsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderIntegrationData(connectors, events, stats);
        } catch (error) {
            console.error('Error fetching integration data:', error);
        }
    }

    renderIntegrationData(connectors, events, stats) {
        // Update summary metrics
        document.getElementById('integration-connectors-count').textContent = connectors.length || 0;
        document.getElementById('integration-active-count').textContent = connectors.filter(c => c.status === 'active').length || 0;
        document.getElementById('integration-events-count').textContent = stats.events_per_minute || 0;
        document.getElementById('integration-errors-count').textContent = stats.errors || 0;

        // Render tables
        this.renderConnectorsTable(connectors);
        this.renderIntegrationEventsTable(events);
    }

    renderConnectorsTable(connectors) {
        const tbody = document.getElementById('integration-connectors-table');
        if (!connectors || connectors.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No connectors configured</td></tr>';
            return;
        }

        tbody.innerHTML = connectors.map(c => `
            <tr>
                <td>${c.name || '-'}</td>
                <td><span class="status-badge ${this.getProtocolBadgeClass(c.protocol)}">${c.protocol?.toUpperCase()}</span></td>
                <td><span class="status-badge ${c.status === 'active' ? 'success' : 'warning'}">${c.status?.toUpperCase()}</span></td>
                <td>${c.event_count || 0}</td>
                <td>${c.last_sync ? new Date(c.last_sync).toLocaleTimeString() : '-'}</td>
                <td>${c.latency_ms ? `${c.latency_ms.toFixed(1)} ms` : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.syncConnector('${c.id}')" title="Sync">
                        <i class="fas fa-sync"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.toggleConnector('${c.id}')" title="${c.status === 'active' ? 'Disable' : 'Enable'}">
                        <i class="fas fa-${c.status === 'active' ? 'pause' : 'play'}"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderIntegrationEventsTable(events) {
        const tbody = document.getElementById('integration-events-table');
        if (!events || events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No recent events</td></tr>';
            return;
        }

        tbody.innerHTML = events.slice(0, 20).map(e => `
            <tr>
                <td>${e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '-'}</td>
                <td>${e.connector || '-'}</td>
                <td><span class="status-badge info">${e.event_type?.toUpperCase()}</span></td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(e.details || '')}">${e.details || '-'}</td>
                <td><span class="status-badge ${e.status === 'success' ? 'success' : 'error'}">${e.status?.toUpperCase()}</span></td>
            </tr>
        `).join('');
    }

    getProtocolBadgeClass(protocol) {
        const map = { 'ospf': 'error', 'bgp': 'info', 'vxlan': 'success', 'isis': 'warning' };
        return map[protocol?.toLowerCase()] || 'info';
    }

    async syncConnector(id) {
        try {
            const res = await fetch(`/api/integration/connectors/${id}/sync`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchIntegrationData();
            } else {
                const error = await res.json();
                alert(`Sync failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error syncing connector:', error);
            alert('Failed to sync connector');
        }
    }

    async toggleConnector(id) {
        try {
            const res = await fetch(`/api/integration/connectors/${id}/toggle`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchIntegrationData();
            } else {
                const error = await res.json();
                alert(`Toggle failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error toggling connector:', error);
            alert('Failed to toggle connector');
        }
    }

    refreshIntegrationData() {
        this.fetchIntegrationData();
    }

    // ==================== CERTIFICATION METHODS ====================
    async fetchCertificationData() {
        try {
            const [labsRes, examsRes, progressRes] = await Promise.all([
                fetch('/api/certification/labs'),
                fetch('/api/certification/exams'),
                fetch('/api/certification/progress')
            ]);

            const labs = labsRes.ok ? await labsRes.json() : [];
            const exams = examsRes.ok ? await examsRes.json() : [];
            const progress = progressRes.ok ? await progressRes.json() : {};

            this.renderCertificationData(labs, exams, progress);
        } catch (error) {
            console.error('Error fetching certification data:', error);
        }
    }

    renderCertificationData(labs, exams, progress) {
        // Update summary metrics
        document.getElementById('cert-labs-count').textContent = labs.length || 0;
        document.getElementById('cert-completed-count').textContent = progress.labs_completed || 0;
        document.getElementById('cert-exams-count').textContent = progress.exams_taken || 0;
        document.getElementById('cert-ready').textContent = progress.ready_for?.join(', ') || '-';

        // Render tables
        this.renderCertLabsTable(labs, progress);
        this.renderCertExamsTable(exams, progress);
    }

    renderCertLabsTable(labs, progress) {
        const tbody = document.getElementById('cert-labs-table');
        if (!labs || labs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No labs available</td></tr>';
            return;
        }

        tbody.innerHTML = labs.map(l => {
            const labProgress = progress.labs?.[l.id] || {};
            return `
                <tr>
                    <td>${l.name || '-'}</td>
                    <td><span class="status-badge ${this.getCertLevelBadgeClass(l.certification)}">${l.certification?.toUpperCase()}</span></td>
                    <td><span class="status-badge ${this.getDifficultyBadgeClass(l.difficulty)}">${l.difficulty?.toUpperCase()}</span></td>
                    <td>${l.tasks?.length || 0}</td>
                    <td>${l.time_limit || '-'}</td>
                    <td><span class="status-badge ${this.getLabStatusBadgeClass(labProgress.status)}">${labProgress.status?.toUpperCase() || 'NOT STARTED'}</span></td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.startCertLab('${l.id}')" title="Start Lab" style="background: #16a34a; border-color: #16a34a;">
                            <i class="fas fa-play"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    renderCertExamsTable(exams, progress) {
        const tbody = document.getElementById('cert-exams-table');
        if (!exams || exams.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No practice exams available</td></tr>';
            return;
        }

        tbody.innerHTML = exams.map(e => {
            const examProgress = progress.exams?.[e.id] || {};
            return `
                <tr>
                    <td>${e.name || '-'}</td>
                    <td><span class="status-badge ${this.getCertLevelBadgeClass(e.track)}">${e.track?.toUpperCase()}</span></td>
                    <td>${e.questions || 0}</td>
                    <td>${e.pass_score ? `${e.pass_score}%` : '-'}</td>
                    <td>${examProgress.best_score ? `${examProgress.best_score}%` : '-'}</td>
                    <td>${examProgress.attempts || 0}</td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.startCertExam('${e.id}')" title="Take Exam" style="background: #16a34a; border-color: #16a34a;">
                            <i class="fas fa-file-alt"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    getCertLevelBadgeClass(level) {
        const map = { 'ccna': 'success', 'ccnp': 'info', 'ccie': 'error', 'devnet': 'info' };
        return map[level?.toLowerCase()] || 'info';
    }

    getLabStatusBadgeClass(status) {
        const map = { 'completed': 'success', 'in_progress': 'warning', 'failed': 'error', 'not_started': 'info' };
        return map[status?.toLowerCase()] || 'info';
    }

    async startCertLab(id) {
        try {
            const res = await fetch(`/api/certification/labs/${id}/start`, {
                method: 'POST'
            });

            if (res.ok) {
                alert('Lab started! Check the lab environment for tasks.');
                this.fetchCertificationData();
            } else {
                const error = await res.json();
                alert(`Failed to start lab: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error starting lab:', error);
            alert('Failed to start lab');
        }
    }

    async startCertExam(id) {
        if (!confirm('Start this practice exam? Make sure you have enough time.')) return;

        try {
            const res = await fetch(`/api/certification/exams/${id}/start`, {
                method: 'POST'
            });

            if (res.ok) {
                alert('Exam started! Good luck!');
                this.fetchCertificationData();
            } else {
                const error = await res.json();
                alert(`Failed to start exam: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error starting exam:', error);
            alert('Failed to start exam');
        }
    }

    refreshCertificationData() {
        this.fetchCertificationData();
    }

    // ==================== TUTORIALS METHODS ====================
    async fetchTutorialsData() {
        try {
            const [tutorialsRes, assessmentsRes, progressRes] = await Promise.all([
                fetch('/api/tutorials'),
                fetch('/api/tutorials/assessments'),
                fetch('/api/tutorials/progress')
            ]);

            const tutorials = tutorialsRes.ok ? await tutorialsRes.json() : [];
            const assessments = assessmentsRes.ok ? await assessmentsRes.json() : [];
            const progress = progressRes.ok ? await progressRes.json() : {};

            this.renderTutorialsData(tutorials, assessments, progress);
        } catch (error) {
            console.error('Error fetching tutorials data:', error);
        }
    }

    renderTutorialsData(tutorials, assessments, progress) {
        // Update summary metrics
        document.getElementById('tutorials-available-count').textContent = tutorials.length || 0;
        document.getElementById('tutorials-completed-count').textContent = progress.completed || 0;
        document.getElementById('tutorials-in-progress-count').textContent = progress.in_progress || 0;
        document.getElementById('tutorials-score').textContent = progress.avg_score ? `${(progress.avg_score * 100).toFixed(0)}%` : '-';

        // Render tables
        this.renderTutorialsListTable(tutorials, progress);
        this.renderAssessmentsTable(assessments);
    }

    renderTutorialsListTable(tutorials, progress) {
        const tbody = document.getElementById('tutorials-list-table');
        if (!tutorials || tutorials.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No tutorials available</td></tr>';
            return;
        }

        tbody.innerHTML = tutorials.map(t => {
            const userProgress = progress.tutorials?.[t.id] || {};
            const progressPercent = userProgress.completed_steps ? Math.round((userProgress.completed_steps / t.steps?.length) * 100) : 0;

            return `
                <tr>
                    <td>${t.title || '-'}</td>
                    <td><span class="status-badge ${this.getTutorialCategoryBadgeClass(t.category)}">${t.category?.toUpperCase()}</span></td>
                    <td><span class="status-badge ${this.getDifficultyBadgeClass(t.difficulty)}">${t.difficulty?.toUpperCase()}</span></td>
                    <td>${t.steps?.length || 0}</td>
                    <td>${t.duration || '-'}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden;">
                                <div style="width: ${progressPercent}%; height: 100%; background: #ea580c;"></div>
                            </div>
                            <span style="font-size: 0.8rem;">${progressPercent}%</span>
                        </div>
                    </td>
                    <td>
                        <button class="btn btn-sm" onclick="dashboard.startTutorial('${t.id}')" title="${progressPercent > 0 ? 'Continue' : 'Start'}" style="background: #ea580c; border-color: #ea580c;">
                            <i class="fas fa-${progressPercent > 0 ? 'play-circle' : 'play'}"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    renderAssessmentsTable(assessments) {
        const tbody = document.getElementById('tutorials-assessments-table');
        if (!assessments || assessments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No assessments completed</td></tr>';
            return;
        }

        tbody.innerHTML = assessments.slice(0, 10).map(a => `
            <tr>
                <td>${a.tutorial_title || '-'}</td>
                <td><span class="status-badge ${this.getScoreBadgeClass(a.score)}">${a.score ? `${(a.score * 100).toFixed(0)}%` : '-'}</span></td>
                <td>${a.correct || 0} / ${a.total || 0}</td>
                <td>${a.time_spent || '-'}</td>
                <td>${a.completed_at ? new Date(a.completed_at).toLocaleString() : '-'}</td>
            </tr>
        `).join('');
    }

    getTutorialCategoryBadgeClass(category) {
        const map = { 'routing': 'warning', 'switching': 'info', 'security': 'success', 'automation': 'info' };
        return map[category?.toLowerCase()] || 'info';
    }

    getDifficultyBadgeClass(difficulty) {
        const map = { 'beginner': 'success', 'intermediate': 'warning', 'advanced': 'error', 'expert': 'error' };
        return map[difficulty?.toLowerCase()] || 'info';
    }

    getScoreBadgeClass(score) {
        if (!score && score !== 0) return 'info';
        if (score >= 0.9) return 'success';
        if (score >= 0.7) return 'warning';
        return 'error';
    }

    async startTutorial(id) {
        try {
            const res = await fetch(`/api/tutorials/${id}/start`, {
                method: 'POST'
            });

            if (res.ok) {
                const tutorial = await res.json();
                alert(`Tutorial started: ${tutorial.title}\n\nCheck the Tutorial tab for interactive guidance.`);
                this.fetchTutorialsData();
            } else {
                const error = await res.json();
                alert(`Failed to start tutorial: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error starting tutorial:', error);
            alert('Failed to start tutorial');
        }
    }

    refreshTutorialsData() {
        this.fetchTutorialsData();
    }

    // ==================== TRAFFIC METHODS ====================
    async fetchTrafficData() {
        try {
            const [flowsRes, iperfRes, statsRes] = await Promise.all([
                fetch('/api/traffic/flows'),
                fetch('/api/traffic/iperf/results'),
                fetch('/api/traffic/statistics')
            ]);

            const flows = flowsRes.ok ? await flowsRes.json() : [];
            const iperf = iperfRes.ok ? await iperfRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderTrafficData(flows, iperf, stats);
        } catch (error) {
            console.error('Error fetching traffic data:', error);
        }
    }

    renderTrafficData(flows, iperf, stats) {
        // Update summary metrics
        document.getElementById('traffic-flows-count').textContent = flows.filter(f => f.status === 'running').length || 0;
        document.getElementById('traffic-bandwidth').textContent = this.formatBandwidth(stats.total_bandwidth);
        document.getElementById('traffic-tests-count').textContent = stats.tests_run || 0;
        document.getElementById('traffic-avg-latency').textContent = stats.avg_latency_ms ? `${stats.avg_latency_ms.toFixed(1)} ms` : '-';

        // Render tables
        this.renderTrafficFlowsTable(flows);
        this.renderIPerfResultsTable(iperf);
    }

    renderTrafficFlowsTable(flows) {
        const tbody = document.getElementById('traffic-flows-table');
        if (!flows || flows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No traffic flows</td></tr>';
            return;
        }

        tbody.innerHTML = flows.map(f => `
            <tr>
                <td style="font-family: monospace;">${f.id?.substring(0, 8) || '-'}</td>
                <td>${f.source || 'local'}</td>
                <td>${f.destination || '-'}</td>
                <td><span class="status-badge ${f.protocol === 'tcp' ? 'info' : 'success'}">${f.protocol?.toUpperCase()}</span></td>
                <td>${this.formatBandwidth(f.bandwidth)}</td>
                <td>${f.duration ? `${f.duration}s` : '-'}</td>
                <td><span class="status-badge ${this.getFlowStatusBadgeClass(f.status)}">${f.status?.toUpperCase()}</span></td>
                <td>
                    ${f.status === 'running' ? `
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.stopTrafficFlow('${f.id}')" title="Stop">
                            <i class="fas fa-stop"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `).join('');
    }

    renderIPerfResultsTable(results) {
        const tbody = document.getElementById('traffic-iperf-table');
        if (!results || results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No iPerf results</td></tr>';
            return;
        }

        tbody.innerHTML = results.map(r => `
            <tr>
                <td style="font-family: monospace;">${r.id?.substring(0, 8) || '-'}</td>
                <td>${r.server || '-'}</td>
                <td>${r.client || 'local'}</td>
                <td><span class="status-badge ${r.protocol === 'tcp' ? 'info' : 'success'}">${r.protocol?.toUpperCase()}</span></td>
                <td>${this.formatBandwidth(r.throughput)}</td>
                <td>${r.jitter_ms ? `${r.jitter_ms.toFixed(2)} ms` : '-'}</td>
                <td>${r.loss_percent ? `${r.loss_percent.toFixed(2)}%` : '0%'}</td>
                <td>${r.completed_at ? new Date(r.completed_at).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getFlowStatusBadgeClass(status) {
        const map = { 'running': 'success', 'completed': 'info', 'stopped': 'warning', 'failed': 'error' };
        return map[status?.toLowerCase()] || 'info';
    }

    showStartTrafficModal() {
        document.getElementById('start-traffic-modal').style.display = 'flex';
    }

    hideStartTrafficModal() {
        document.getElementById('start-traffic-modal').style.display = 'none';
        document.getElementById('traffic-destination').value = '';
        document.getElementById('traffic-bandwidth-input').value = '';
        document.getElementById('traffic-duration').value = '';
    }

    async startTrafficFlow() {
        const destination = document.getElementById('traffic-destination').value.trim();
        const protocol = document.getElementById('traffic-protocol').value;
        const bandwidth = document.getElementById('traffic-bandwidth-input').value.trim();
        const duration = parseInt(document.getElementById('traffic-duration').value) || 10;

        if (!destination) {
            alert('Destination is required');
            return;
        }

        try {
            const res = await fetch('/api/traffic/flows', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ destination, protocol, bandwidth: bandwidth || '10M', duration })
            });

            if (res.ok) {
                this.hideStartTrafficModal();
                this.fetchTrafficData();
            } else {
                const error = await res.json();
                alert(`Failed to start traffic flow: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error starting traffic flow:', error);
            alert('Failed to start traffic flow');
        }
    }

    async stopTrafficFlow(id) {
        try {
            const res = await fetch(`/api/traffic/flows/${id}/stop`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchTrafficData();
            } else {
                const error = await res.json();
                alert(`Failed to stop flow: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error stopping traffic flow:', error);
            alert('Failed to stop traffic flow');
        }
    }

    refreshTrafficData() {
        this.fetchTrafficData();
    }

    // ==================== REASONING METHODS ====================
    async fetchReasoningData() {
        try {
            const [historyRes, statsRes] = await Promise.all([
                fetch('/api/reasoning/history?limit=50'),
                fetch('/api/reasoning/statistics')
            ]);

            const history = historyRes.ok ? await historyRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderReasoningData(history, stats);
        } catch (error) {
            console.error('Error fetching reasoning data:', error);
        }
    }

    renderReasoningData(history, stats) {
        // Update summary metrics
        document.getElementById('reasoning-decisions-count').textContent = stats.decisions_made || 0;
        document.getElementById('reasoning-intents-count').textContent = stats.intents_parsed || 0;
        document.getElementById('reasoning-accuracy').textContent = stats.accuracy ? `${(stats.accuracy * 100).toFixed(1)}%` : '-';
        document.getElementById('reasoning-avg-time').textContent = stats.avg_decision_time_ms ? `${stats.avg_decision_time_ms.toFixed(0)} ms` : '-';

        // Render history table
        this.renderReasoningHistoryTable(history);
    }

    renderReasoningHistoryTable(decisions) {
        const tbody = document.getElementById('reasoning-history-table');
        if (!decisions || decisions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No decisions recorded yet</td></tr>';
            return;
        }

        tbody.innerHTML = decisions.map(d => `
            <tr>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(d.input || '')}">${d.input || '-'}</td>
                <td><span class="status-badge ${this.getIntentTypeBadgeClass(d.intent_type)}">${d.intent_type?.toUpperCase()}</span></td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(d.decision || '')}">${d.decision || '-'}</td>
                <td><span class="status-badge ${this.getConfidenceBadgeClass(d.confidence)}">${d.confidence ? `${(d.confidence * 100).toFixed(0)}%` : '-'}</span></td>
                <td>${d.processing_time_ms ? `${d.processing_time_ms.toFixed(0)} ms` : '-'}</td>
                <td>${d.timestamp ? new Date(d.timestamp).toLocaleString() : '-'}</td>
            </tr>
        `).join('');
    }

    getConfidenceBadgeClass(confidence) {
        if (!confidence && confidence !== 0) return 'info';
        if (confidence >= 0.9) return 'success';
        if (confidence >= 0.7) return 'warning';
        return 'error';
    }

    async runReasoning() {
        const input = document.getElementById('reasoning-input').value.trim();
        if (!input) {
            alert('Please enter input for reasoning');
            return;
        }

        try {
            const res = await fetch('/api/reasoning/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input })
            });

            if (res.ok) {
                const result = await res.json();
                document.getElementById('reasoning-output').style.display = 'block';
                document.getElementById('reasoning-result').textContent = JSON.stringify(result, null, 2);
                this.fetchReasoningData();
            } else {
                const error = await res.json();
                alert(`Reasoning failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error running reasoning:', error);
            alert('Failed to run reasoning');
        }
    }

    refreshReasoningData() {
        this.fetchReasoningData();
    }

    // ==================== MULTI-AGENT METHODS ====================
    async fetchMultiAgentData() {
        try {
            const [peersRes, consensusRes, statsRes] = await Promise.all([
                fetch('/api/multiagent/peers'),
                fetch('/api/multiagent/consensus'),
                fetch('/api/multiagent/statistics')
            ]);

            const peers = peersRes.ok ? await peersRes.json() : [];
            const consensus = consensusRes.ok ? await consensusRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderMultiAgentData(peers, consensus, stats);
        } catch (error) {
            console.error('Error fetching multi-agent data:', error);
        }
    }

    renderMultiAgentData(peers, consensus, stats) {
        // Update summary metrics
        document.getElementById('multiagent-peers-count').textContent = peers.length || 0;
        document.getElementById('multiagent-active-count').textContent = peers.filter(p => p.status === 'active').length || 0;
        document.getElementById('multiagent-messages-count').textContent = stats.messages_per_minute || 0;
        document.getElementById('multiagent-consensus-count').textContent = stats.consensus_rounds || 0;

        // Render tables
        this.renderPeersTable(peers);
        this.renderConsensusTable(consensus);
    }

    renderPeersTable(peers) {
        const tbody = document.getElementById('multiagent-peers-table');
        if (!peers || peers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No peer agents connected</td></tr>';
            return;
        }

        tbody.innerHTML = peers.map(p => `
            <tr>
                <td style="font-family: monospace;">${p.agent_id?.substring(0, 12) || '-'}</td>
                <td>${p.address || '-'}</td>
                <td><span class="status-badge ${this.getPeerStatusBadgeClass(p.status)}">${p.status?.toUpperCase()}</span></td>
                <td>${p.last_seen ? new Date(p.last_seen).toLocaleTimeString() : '-'}</td>
                <td>${p.message_count || 0}</td>
                <td>${p.latency_ms ? `${p.latency_ms.toFixed(1)} ms` : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.pingPeer('${p.agent_id}')" title="Ping">
                        <i class="fas fa-satellite-dish"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.removePeer('${p.agent_id}')" title="Remove">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderConsensusTable(proposals) {
        const tbody = document.getElementById('multiagent-consensus-table');
        if (!proposals || proposals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No consensus proposals</td></tr>';
            return;
        }

        tbody.innerHTML = proposals.map(p => `
            <tr>
                <td style="font-family: monospace;">${p.id?.substring(0, 8) || '-'}</td>
                <td><span class="status-badge info">${p.type?.toUpperCase()}</span></td>
                <td>${p.proposer?.substring(0, 12) || '-'}</td>
                <td>${p.votes || 0} / ${p.required || 0}</td>
                <td><span class="status-badge ${this.getConsensusStatusBadgeClass(p.status)}">${p.status?.toUpperCase()}</span></td>
                <td>${p.created_at ? new Date(p.created_at).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getPeerStatusBadgeClass(status) {
        const map = { 'active': 'success', 'inactive': 'warning', 'unreachable': 'error', 'connecting': 'info' };
        return map[status?.toLowerCase()] || 'info';
    }

    getConsensusStatusBadgeClass(status) {
        const map = { 'pending': 'warning', 'approved': 'success', 'rejected': 'error', 'expired': 'info' };
        return map[status?.toLowerCase()] || 'info';
    }

    showAddPeerModal() {
        document.getElementById('add-peer-modal').style.display = 'flex';
    }

    hideAddPeerModal() {
        document.getElementById('add-peer-modal').style.display = 'none';
        document.getElementById('peer-address').value = '';
        document.getElementById('peer-name').value = '';
    }

    async addPeer() {
        const address = document.getElementById('peer-address').value.trim();
        const name = document.getElementById('peer-name').value.trim();

        if (!address) {
            alert('Address is required');
            return;
        }

        try {
            const res = await fetch('/api/multiagent/peers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address, name: name || null })
            });

            if (res.ok) {
                this.hideAddPeerModal();
                this.fetchMultiAgentData();
            } else {
                const error = await res.json();
                alert(`Failed to add peer: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error adding peer:', error);
            alert('Failed to add peer');
        }
    }

    async pingPeer(agentId) {
        try {
            const res = await fetch(`/api/multiagent/peers/${agentId}/ping`, {
                method: 'POST'
            });

            if (res.ok) {
                const result = await res.json();
                alert(`Ping successful: ${result.latency_ms?.toFixed(1) || '?'} ms`);
            } else {
                alert('Ping failed');
            }
        } catch (error) {
            console.error('Error pinging peer:', error);
            alert('Failed to ping peer');
        }
    }

    async removePeer(agentId) {
        if (!confirm('Remove this peer agent?')) return;

        try {
            const res = await fetch(`/api/multiagent/peers/${agentId}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchMultiAgentData();
            } else {
                const error = await res.json();
                alert(`Failed to remove peer: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error removing peer:', error);
            alert('Failed to remove peer');
        }
    }

    refreshMultiAgentData() {
        this.fetchMultiAgentData();
    }

    // ==================== WHATIF METHODS ====================
    async fetchWhatIfData() {
        try {
            const [historyRes, statsRes] = await Promise.all([
                fetch('/api/whatif/history?limit=50'),
                fetch('/api/whatif/statistics')
            ]);

            const history = historyRes.ok ? await historyRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderWhatIfData(history, stats);
        } catch (error) {
            console.error('Error fetching what-if data:', error);
        }
    }

    renderWhatIfData(history, stats) {
        // Update summary metrics
        document.getElementById('whatif-scenarios-count').textContent = stats.total_scenarios || 0;
        document.getElementById('whatif-simulations-count').textContent = stats.simulations_run || 0;
        document.getElementById('whatif-high-impact-count').textContent = stats.high_impact || 0;
        document.getElementById('whatif-avg-recovery').textContent = stats.avg_recovery_time || '-';

        // Render history table
        this.renderWhatIfHistoryTable(history);
    }

    renderWhatIfHistoryTable(simulations) {
        const tbody = document.getElementById('whatif-history-table');
        if (!simulations || simulations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No simulations run yet</td></tr>';
            return;
        }

        tbody.innerHTML = simulations.map(s => `
            <tr>
                <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(s.description || '')}">${s.description || '-'}</td>
                <td><span class="status-badge ${this.getScenarioTypeBadgeClass(s.type)}">${s.type?.toUpperCase().replace('_', ' ')}</span></td>
                <td>${s.target || '-'}</td>
                <td><span class="status-badge ${this.getImpactBadgeClass(s.impact)}">${s.impact?.toUpperCase()}</span></td>
                <td>${s.affected_paths || 0}</td>
                <td>${s.recovery_estimate || '-'}</td>
                <td>${s.simulated_at ? new Date(s.simulated_at).toLocaleString() : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.viewWhatIfDetails('${s.id}')" title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.rerunWhatIf('${s.id}')" title="Re-run">
                        <i class="fas fa-redo"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    getScenarioTypeBadgeClass(type) {
        const map = { 'link_failure': 'info', 'node_failure': 'error', 'config_change': 'warning', 'traffic_spike': 'info' };
        return map[type?.toLowerCase()] || 'info';
    }

    getImpactBadgeClass(impact) {
        const map = { 'low': 'success', 'medium': 'warning', 'high': 'error', 'critical': 'error' };
        return map[impact?.toLowerCase()] || 'info';
    }

    async runWhatIfSimulation() {
        const type = document.getElementById('whatif-scenario-type').value;
        const target = document.getElementById('whatif-target').value.trim();
        const description = document.getElementById('whatif-description').value.trim();

        if (!target) {
            alert('Please specify a target');
            return;
        }

        try {
            const res = await fetch('/api/whatif/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, target, description: description || `${type} simulation on ${target}` })
            });

            if (res.ok) {
                const result = await res.json();
                document.getElementById('whatif-target').value = '';
                document.getElementById('whatif-description').value = '';
                this.fetchWhatIfData();
                alert(`Simulation complete!\n\nImpact: ${result.impact}\nAffected Paths: ${result.affected_paths || 0}\nRecovery Est: ${result.recovery_estimate || 'N/A'}`);
            } else {
                const error = await res.json();
                alert(`Simulation failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error running simulation:', error);
            alert('Failed to run simulation');
        }
    }

    async viewWhatIfDetails(id) {
        try {
            const res = await fetch(`/api/whatif/${id}`);
            if (res.ok) {
                const sim = await res.json();
                const details = [
                    `Description: ${sim.description}`,
                    `Type: ${sim.type}`,
                    `Target: ${sim.target}`,
                    `Impact: ${sim.impact}`,
                    `Affected Paths: ${sim.affected_paths || 0}`,
                    `Recovery Estimate: ${sim.recovery_estimate || 'N/A'}`,
                    `Simulated: ${sim.simulated_at ? new Date(sim.simulated_at).toLocaleString() : 'N/A'}`
                ].join('\n');
                alert(details);
            }
        } catch (error) {
            console.error('Error fetching simulation details:', error);
        }
    }

    async rerunWhatIf(id) {
        try {
            const res = await fetch(`/api/whatif/${id}/rerun`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchWhatIfData();
                alert('Simulation re-run complete');
            } else {
                const error = await res.json();
                alert(`Failed to re-run simulation: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error re-running simulation:', error);
            alert('Failed to re-run simulation');
        }
    }

    refreshWhatIfData() {
        this.fetchWhatIfData();
    }

    // ==================== HEATMAP METHODS ====================
    async fetchHeatmapData() {
        const type = document.getElementById('heatmap-type')?.value || 'utilization';
        try {
            const [dataRes, hotspotsRes, statsRes] = await Promise.all([
                fetch(`/api/heatmap/data?type=${type}`),
                fetch('/api/heatmap/hotspots'),
                fetch('/api/heatmap/statistics')
            ]);

            const data = dataRes.ok ? await dataRes.json() : [];
            const hotspots = hotspotsRes.ok ? await hotspotsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderHeatmapData(data, hotspots, stats);
        } catch (error) {
            console.error('Error fetching heatmap data:', error);
        }
    }

    renderHeatmapData(data, hotspots, stats) {
        // Update summary metrics
        document.getElementById('heatmap-links-count').textContent = stats.monitored_links || 0;
        document.getElementById('heatmap-hotspots-count').textContent = hotspots.length || 0;
        document.getElementById('heatmap-avg-utilization').textContent = `${(stats.avg_utilization || 0).toFixed(1)}%`;
        document.getElementById('heatmap-peak-utilization').textContent = `${(stats.peak_utilization || 0).toFixed(1)}%`;

        // Render heatmap grid
        this.renderHeatmapGrid(data);
        this.renderHotspotsTable(hotspots);
    }

    renderHeatmapGrid(data) {
        const grid = document.getElementById('heatmap-grid');
        if (!data || data.length === 0) {
            grid.innerHTML = '<div style="text-align: center; color: var(--text-secondary); grid-column: 1 / -1;">No heatmap data available</div>';
            return;
        }

        grid.innerHTML = data.map(cell => {
            const color = this.getHeatmapColor(cell.value);
            return `
                <div style="background: ${color}; padding: 8px; border-radius: 4px; text-align: center; font-size: 0.75rem; color: white; cursor: pointer;"
                     title="${cell.label || cell.link}: ${cell.value?.toFixed(1)}%"
                     onclick="dashboard.showHeatmapCellDetails('${cell.id}')">
                    <div style="font-weight: bold;">${cell.value?.toFixed(0) || 0}%</div>
                    <div style="font-size: 0.65rem; opacity: 0.8;">${cell.label?.substring(0, 8) || '-'}</div>
                </div>
            `;
        }).join('');
    }

    getHeatmapColor(value) {
        if (!value && value !== 0) return '#374151';
        if (value >= 75) return '#ef4444';
        if (value >= 50) return '#f97316';
        if (value >= 25) return '#eab308';
        return '#22c55e';
    }

    renderHotspotsTable(hotspots) {
        const tbody = document.getElementById('heatmap-hotspots-table');
        if (!hotspots || hotspots.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No traffic hotspots detected</td></tr>';
            return;
        }

        tbody.innerHTML = hotspots.map(h => `
            <tr>
                <td>${h.link_name || '-'}</td>
                <td>${h.source || '-'}</td>
                <td>${h.destination || '-'}</td>
                <td><span class="status-badge ${this.getUtilizationBadgeClass(h.utilization)}">${h.utilization?.toFixed(1)}%</span></td>
                <td>${this.formatBandwidth(h.bandwidth)}</td>
                <td><span class="status-badge ${this.getTrendBadgeClass(h.trend)}">${h.trend?.toUpperCase()}</span></td>
                <td>${h.duration || '-'}</td>
            </tr>
        `).join('');
    }

    getUtilizationBadgeClass(util) {
        if (!util && util !== 0) return 'info';
        if (util >= 75) return 'error';
        if (util >= 50) return 'warning';
        return 'success';
    }

    showHeatmapCellDetails(id) {
        // Could open a modal with detailed cell info
        console.log('Showing details for cell:', id);
    }

    refreshHeatmapData() {
        this.fetchHeatmapData();
    }

    // ==================== KNOWLEDGE METHODS ====================
    async fetchKnowledgeData() {
        try {
            const [snapshotsRes, analyticsRes, statsRes] = await Promise.all([
                fetch('/api/knowledge/snapshots'),
                fetch('/api/knowledge/analytics'),
                fetch('/api/knowledge/statistics')
            ]);

            const snapshots = snapshotsRes.ok ? await snapshotsRes.json() : [];
            const analytics = analyticsRes.ok ? await analyticsRes.json() : {};
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderKnowledgeData(snapshots, analytics, stats);
        } catch (error) {
            console.error('Error fetching knowledge data:', error);
        }
    }

    renderKnowledgeData(snapshots, analytics, stats) {
        // Update summary metrics
        document.getElementById('knowledge-snapshots-count').textContent = snapshots.length || 0;
        document.getElementById('knowledge-devices-count').textContent = stats.devices_tracked || 0;
        document.getElementById('knowledge-changes-count').textContent = stats.changes_24h || 0;
        document.getElementById('knowledge-queries-count').textContent = stats.queries_today || 0;

        // Update analytics
        document.getElementById('knowledge-device-distribution').textContent = analytics.device_distribution || '-';
        document.getElementById('knowledge-protocol-coverage').textContent = analytics.protocol_coverage || '-';
        document.getElementById('knowledge-state-consistency').textContent = analytics.state_consistency || '-';
        document.getElementById('knowledge-last-sync').textContent = analytics.last_sync ? new Date(analytics.last_sync).toLocaleString() : '-';

        // Render snapshots table
        this.renderKnowledgeSnapshotsTable(snapshots);
    }

    renderKnowledgeSnapshotsTable(snapshots) {
        const tbody = document.getElementById('knowledge-snapshots-table');
        if (!snapshots || snapshots.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No snapshots available</td></tr>';
            return;
        }

        tbody.innerHTML = snapshots.map(s => `
            <tr>
                <td style="font-family: monospace;">${s.id?.substring(0, 8) || '-'}</td>
                <td><span class="status-badge ${this.getSnapshotTypeBadgeClass(s.type)}">${s.type?.toUpperCase()}</span></td>
                <td>${s.device_count || 0}</td>
                <td>${s.protocol_count || 0}</td>
                <td>${this.formatBytes(s.size)}</td>
                <td>${s.created_at ? new Date(s.created_at).toLocaleString() : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.viewSnapshot('${s.id}')" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.exportSnapshot('${s.id}')" title="Export">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.deleteSnapshot('${s.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    getSnapshotTypeBadgeClass(type) {
        const map = { 'full': 'success', 'incremental': 'info', 'partial': 'warning', 'auto': 'info' };
        return map[type?.toLowerCase()] || 'info';
    }

    formatBytes(bytes) {
        if (!bytes && bytes !== 0) return '-';
        if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GB`;
        if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
        if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${bytes} B`;
    }

    async createKnowledgeSnapshot() {
        try {
            const res = await fetch('/api/knowledge/snapshots', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'full' })
            });

            if (res.ok) {
                this.fetchKnowledgeData();
            } else {
                const error = await res.json();
                alert(`Failed to create snapshot: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating snapshot:', error);
            alert('Failed to create snapshot');
        }
    }

    async viewSnapshot(id) {
        try {
            const res = await fetch(`/api/knowledge/snapshots/${id}`);
            if (res.ok) {
                const snapshot = await res.json();
                const details = [
                    `ID: ${snapshot.id}`,
                    `Type: ${snapshot.type}`,
                    `Devices: ${snapshot.device_count}`,
                    `Protocols: ${snapshot.protocol_count}`,
                    `Size: ${this.formatBytes(snapshot.size)}`,
                    `Created: ${snapshot.created_at ? new Date(snapshot.created_at).toLocaleString() : 'N/A'}`
                ].join('\n');
                alert(details);
            }
        } catch (error) {
            console.error('Error viewing snapshot:', error);
        }
    }

    async exportSnapshot(id) {
        window.open(`/api/knowledge/snapshots/${id}/export`, '_blank');
    }

    async deleteSnapshot(id) {
        if (!confirm('Delete this snapshot?')) return;

        try {
            const res = await fetch(`/api/knowledge/snapshots/${id}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchKnowledgeData();
            } else {
                const error = await res.json();
                alert(`Failed to delete snapshot: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting snapshot:', error);
            alert('Failed to delete snapshot');
        }
    }

    refreshKnowledgeData() {
        this.fetchKnowledgeData();
    }

    // ==================== INTENT METHODS ====================
    async fetchIntentData() {
        try {
            const [historyRes, statsRes] = await Promise.all([
                fetch('/api/intent/history?limit=50'),
                fetch('/api/intent/statistics')
            ]);

            const history = historyRes.ok ? await historyRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderIntentData(history, stats);
        } catch (error) {
            console.error('Error fetching intent data:', error);
        }
    }

    renderIntentData(history, stats) {
        // Update summary metrics
        document.getElementById('intent-total-count').textContent = stats.total || history.length || 0;
        document.getElementById('intent-executed-count').textContent = stats.executed || 0;
        document.getElementById('intent-pending-count').textContent = stats.pending || 0;
        document.getElementById('intent-failed-count').textContent = stats.failed || 0;

        // Render history table
        this.renderIntentHistoryTable(history);
    }

    renderIntentHistoryTable(intents) {
        const tbody = document.getElementById('intent-history-table');
        if (!intents || intents.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No intents executed yet</td></tr>';
            return;
        }

        tbody.innerHTML = intents.map(i => `
            <tr>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(i.description || '')}">${i.description || '-'}</td>
                <td><span class="status-badge ${this.getIntentTypeBadgeClass(i.type)}">${i.type?.toUpperCase()}</span></td>
                <td>${i.target || '-'}</td>
                <td>${i.steps?.length || 0}</td>
                <td><span class="status-badge ${this.getIntentStatusBadgeClass(i.status)}">${i.status?.toUpperCase()}</span></td>
                <td>${i.created_at ? new Date(i.created_at).toLocaleString() : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.viewIntentDetails('${i.id}')" title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${i.status === 'failed' ? `
                        <button class="btn btn-sm" onclick="dashboard.retryIntent('${i.id}')" title="Retry" style="background: #f43f5e; border-color: #f43f5e;">
                            <i class="fas fa-redo"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `).join('');
    }

    getIntentTypeBadgeClass(type) {
        const map = { 'configuration': 'error', 'connectivity': 'info', 'security': 'warning', 'optimization': 'success' };
        return map[type?.toLowerCase()] || 'info';
    }

    getIntentStatusBadgeClass(status) {
        const map = { 'pending': 'warning', 'executing': 'info', 'executed': 'success', 'completed': 'success', 'failed': 'error', 'validated': 'success' };
        return map[status?.toLowerCase()] || 'info';
    }

    async validateIntent() {
        const intentText = document.getElementById('intent-input').value.trim();
        if (!intentText) {
            alert('Please enter an intent description');
            return;
        }

        try {
            const res = await fetch('/api/intent/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ description: intentText })
            });

            const result = await res.json();
            if (res.ok && result.valid) {
                alert(`Intent is valid!\n\nType: ${result.type}\nTarget: ${result.target}\nSteps: ${result.steps?.length || 0}`);
            } else {
                alert(`Intent validation failed: ${result.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error validating intent:', error);
            alert('Failed to validate intent');
        }
    }

    async executeIntent() {
        const intentText = document.getElementById('intent-input').value.trim();
        if (!intentText) {
            alert('Please enter an intent description');
            return;
        }

        if (!confirm('Execute this intent? This may make changes to your network configuration.')) {
            return;
        }

        try {
            const res = await fetch('/api/intent/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ description: intentText })
            });

            if (res.ok) {
                document.getElementById('intent-input').value = '';
                this.fetchIntentData();
                alert('Intent execution started');
            } else {
                const error = await res.json();
                alert(`Failed to execute intent: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error executing intent:', error);
            alert('Failed to execute intent');
        }
    }

    async viewIntentDetails(id) {
        try {
            const res = await fetch(`/api/intent/${id}`);
            if (res.ok) {
                const intent = await res.json();
                const details = [
                    `Description: ${intent.description}`,
                    `Type: ${intent.type}`,
                    `Status: ${intent.status}`,
                    `Target: ${intent.target || 'N/A'}`,
                    `Steps: ${intent.steps?.length || 0}`,
                    `Created: ${intent.created_at ? new Date(intent.created_at).toLocaleString() : 'N/A'}`,
                    intent.error ? `Error: ${intent.error}` : ''
                ].filter(Boolean).join('\n');
                alert(details);
            }
        } catch (error) {
            console.error('Error fetching intent details:', error);
        }
    }

    async retryIntent(id) {
        if (!confirm('Retry this failed intent?')) return;

        try {
            const res = await fetch(`/api/intent/${id}/retry`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchIntentData();
            } else {
                const error = await res.json();
                alert(`Failed to retry intent: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error retrying intent:', error);
            alert('Failed to retry intent');
        }
    }

    refreshIntentData() {
        this.fetchIntentData();
    }

    // ==================== DISCOVERY METHODS ====================
    async fetchDiscoveryData() {
        try {
            const [servicesRes, loadbalancersRes] = await Promise.all([
                fetch('/api/discovery/services'),
                fetch('/api/discovery/loadbalancers')
            ]);

            const services = servicesRes.ok ? await servicesRes.json() : [];
            const loadbalancers = loadbalancersRes.ok ? await loadbalancersRes.json() : [];

            this.renderDiscoveryData(services, loadbalancers);
        } catch (error) {
            console.error('Error fetching discovery data:', error);
        }
    }

    renderDiscoveryData(services, loadbalancers) {
        // Update summary metrics
        document.getElementById('discovery-services-count').textContent = services.length || 0;

        const healthy = services.filter(s => s.status === 'healthy' || s.status === 'active').length;
        const unhealthy = services.filter(s => s.status === 'unhealthy' || s.status === 'inactive').length;
        const endpoints = services.reduce((sum, s) => sum + (s.instances?.length || 0), 0);

        document.getElementById('discovery-healthy-count').textContent = healthy;
        document.getElementById('discovery-unhealthy-count').textContent = unhealthy;
        document.getElementById('discovery-endpoints-count').textContent = endpoints;

        // Render tables
        this.renderDiscoveryServicesTable(services);
        this.renderLoadBalancersTable(loadbalancers);
    }

    renderDiscoveryServicesTable(services) {
        const tbody = document.getElementById('discovery-services-table');
        if (!services || services.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No services registered</td></tr>';
            return;
        }

        tbody.innerHTML = services.map(s => `
            <tr>
                <td>${s.name || '-'}</td>
                <td><span class="status-badge ${this.getServiceTypeBadgeClass(s.type)}">${s.type?.toUpperCase()}</span></td>
                <td>${s.host || '-'}</td>
                <td>${s.port || '-'}</td>
                <td><span class="status-badge ${this.getServiceStatusBadgeClass(s.status)}">${s.status?.toUpperCase()}</span></td>
                <td>${s.instances?.length || 0}</td>
                <td>${s.last_check ? new Date(s.last_check).toLocaleTimeString() : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.deregisterService('${s.id}')" title="Deregister">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderLoadBalancersTable(loadbalancers) {
        const tbody = document.getElementById('discovery-loadbalancers-table');
        if (!loadbalancers || loadbalancers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No load balancers configured</td></tr>';
            return;
        }

        tbody.innerHTML = loadbalancers.map(lb => `
            <tr>
                <td>${lb.service_name || '-'}</td>
                <td><span class="status-badge info">${lb.strategy?.toUpperCase()}</span></td>
                <td>${lb.active_endpoints || 0}</td>
                <td>${lb.requests_per_sec?.toFixed(1) || '0.0'}</td>
                <td>${lb.avg_latency_ms?.toFixed(1) || '0.0'} ms</td>
                <td><span class="status-badge ${lb.active_endpoints > 0 ? 'success' : 'warning'}">${lb.active_endpoints > 0 ? 'ACTIVE' : 'IDLE'}</span></td>
            </tr>
        `).join('');
    }

    getServiceTypeBadgeClass(type) {
        const map = { 'http': 'success', 'grpc': 'info', 'tcp': 'warning', 'udp': 'warning' };
        return map[type?.toLowerCase()] || 'info';
    }

    getServiceStatusBadgeClass(status) {
        const map = { 'healthy': 'success', 'active': 'success', 'unhealthy': 'error', 'inactive': 'warning', 'unknown': 'info' };
        return map[status?.toLowerCase()] || 'info';
    }

    refreshDiscoveryData() {
        this.fetchDiscoveryData();
    }

    showRegisterServiceModal() {
        document.getElementById('register-service-modal').style.display = 'flex';
    }

    hideRegisterServiceModal() {
        document.getElementById('register-service-modal').style.display = 'none';
        document.getElementById('service-name').value = '';
        document.getElementById('service-host').value = '';
        document.getElementById('service-port').value = '';
        document.getElementById('service-health-path').value = '';
    }

    async registerService() {
        const name = document.getElementById('service-name').value.trim();
        const type = document.getElementById('service-type').value;
        const host = document.getElementById('service-host').value.trim();
        const port = parseInt(document.getElementById('service-port').value);
        const healthPath = document.getElementById('service-health-path').value.trim();

        if (!name || !host || !port) {
            alert('Name, host, and port are required');
            return;
        }

        try {
            const res = await fetch('/api/discovery/services', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, type, host, port, health_check_path: healthPath || null })
            });

            if (res.ok) {
                this.hideRegisterServiceModal();
                this.fetchDiscoveryData();
            } else {
                const error = await res.json();
                alert(`Failed to register service: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error registering service:', error);
            alert('Failed to register service');
        }
    }

    async deregisterService(id) {
        if (!confirm('Deregister this service?')) return;

        try {
            const res = await fetch(`/api/discovery/services/${id}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchDiscoveryData();
            } else {
                const error = await res.json();
                alert(`Failed to deregister service: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deregistering service:', error);
            alert('Failed to deregister service');
        }
    }

    // ==================== OPTIMIZATION METHODS ====================
    async fetchOptimizationData() {
        try {
            const [recommendationsRes, patternsRes] = await Promise.all([
                fetch('/api/optimization/recommendations'),
                fetch('/api/optimization/patterns')
            ]);

            const recommendations = recommendationsRes.ok ? await recommendationsRes.json() : [];
            const patterns = patternsRes.ok ? await patternsRes.json() : [];

            this.renderOptimizationData(recommendations, patterns);
        } catch (error) {
            console.error('Error fetching optimization data:', error);
        }
    }

    renderOptimizationData(recommendations, patterns) {
        // Update summary metrics
        document.getElementById('optimization-recommendations-count').textContent = recommendations.length || 0;
        document.getElementById('optimization-patterns-count').textContent = patterns.length || 0;

        const pending = recommendations.filter(r => r.status === 'pending').length;
        const applied = recommendations.filter(r => r.status === 'applied').length;
        document.getElementById('optimization-pending-count').textContent = pending;
        document.getElementById('optimization-applied-count').textContent = applied;

        // Render tables
        this.renderRecommendationsTable(recommendations);
        this.renderTrafficPatternsTable(patterns);
    }

    renderRecommendationsTable(recommendations) {
        const tbody = document.getElementById('optimization-recommendations-table');
        if (!recommendations || recommendations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No optimization recommendations</td></tr>';
            return;
        }

        tbody.innerHTML = recommendations.map(r => `
            <tr>
                <td><span class="status-badge ${this.getRecommendationTypeBadgeClass(r.type)}">${r.type?.toUpperCase()}</span></td>
                <td>${r.target || '-'}</td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.description || '')}">${r.description || '-'}</td>
                <td><span class="status-badge ${this.getRecommendationPriorityBadgeClass(r.priority)}">${r.priority?.toUpperCase()}</span></td>
                <td>${r.estimated_impact || '-'}</td>
                <td><span class="status-badge ${this.getRecommendationStatusBadgeClass(r.status)}">${r.status?.toUpperCase()}</span></td>
                <td>
                    ${r.status === 'pending' ? `
                        <button class="btn btn-sm" onclick="dashboard.applyRecommendation('${r.id}')" title="Apply" style="background: #14b8a6; border-color: #14b8a6;">
                            <i class="fas fa-check"></i>
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="dashboard.dismissRecommendation('${r.id}')" title="Dismiss">
                            <i class="fas fa-times"></i>
                        </button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    }

    renderTrafficPatternsTable(patterns) {
        const tbody = document.getElementById('optimization-patterns-table');
        if (!patterns || patterns.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No traffic patterns detected</td></tr>';
            return;
        }

        tbody.innerHTML = patterns.map(p => `
            <tr>
                <td>${p.name || '-'}</td>
                <td>${p.source || '-'}</td>
                <td>${p.destination || '-'}</td>
                <td>${this.formatBandwidth(p.avg_bandwidth)}</td>
                <td>${this.formatPercent(p.peak_usage)}</td>
                <td><span class="status-badge ${this.getTrendBadgeClass(p.trend)}">${p.trend?.toUpperCase()}</span></td>
                <td>${p.last_updated ? new Date(p.last_updated).toLocaleString() : '-'}</td>
            </tr>
        `).join('');
    }

    getRecommendationTypeBadgeClass(type) {
        const map = { 'ospf': 'success', 'bgp': 'info', 'vxlan': 'warning', 'path': 'info' };
        return map[type?.toLowerCase()] || 'info';
    }

    getRecommendationPriorityBadgeClass(priority) {
        const map = { 'low': 'info', 'medium': 'warning', 'high': 'error', 'critical': 'error' };
        return map[priority?.toLowerCase()] || 'info';
    }

    getRecommendationStatusBadgeClass(status) {
        const map = { 'pending': 'warning', 'applied': 'success', 'dismissed': 'info', 'failed': 'error' };
        return map[status?.toLowerCase()] || 'info';
    }

    getTrendBadgeClass(trend) {
        const map = { 'increasing': 'warning', 'decreasing': 'success', 'stable': 'info', 'volatile': 'error' };
        return map[trend?.toLowerCase()] || 'info';
    }

    formatBandwidth(bw) {
        if (!bw && bw !== 0) return '-';
        if (bw >= 1000000000) return `${(bw / 1000000000).toFixed(1)} Gbps`;
        if (bw >= 1000000) return `${(bw / 1000000).toFixed(1)} Mbps`;
        if (bw >= 1000) return `${(bw / 1000).toFixed(1)} Kbps`;
        return `${bw} bps`;
    }

    formatPercent(val) {
        if (!val && val !== 0) return '-';
        return `${(val * 100).toFixed(1)}%`;
    }

    refreshOptimizationData() {
        this.fetchOptimizationData();
    }

    showAnalyzeTrafficModal() {
        document.getElementById('analyze-traffic-modal').style.display = 'flex';
    }

    hideAnalyzeTrafficModal() {
        document.getElementById('analyze-traffic-modal').style.display = 'none';
        document.getElementById('analysis-scope').value = '';
    }

    async runTrafficAnalysis() {
        const type = document.getElementById('analysis-type').value;
        const scope = document.getElementById('analysis-scope').value.trim();
        const window = document.getElementById('analysis-window').value;

        try {
            const res = await fetch('/api/optimization/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ analysis_type: type, scope: scope || null, time_window: window })
            });

            if (res.ok) {
                this.hideAnalyzeTrafficModal();
                this.fetchOptimizationData();
            } else {
                const error = await res.json();
                alert(`Failed to run analysis: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error running traffic analysis:', error);
            alert('Failed to run traffic analysis');
        }
    }

    async applyRecommendation(id) {
        if (!confirm('Apply this optimization recommendation?')) return;

        try {
            const res = await fetch(`/api/optimization/recommendations/${id}/apply`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchOptimizationData();
            } else {
                const error = await res.json();
                alert(`Failed to apply recommendation: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error applying recommendation:', error);
            alert('Failed to apply recommendation');
        }
    }

    async dismissRecommendation(id) {
        if (!confirm('Dismiss this recommendation?')) return;

        try {
            const res = await fetch(`/api/optimization/recommendations/${id}/dismiss`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchOptimizationData();
            } else {
                const error = await res.json();
                alert(`Failed to dismiss recommendation: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error dismissing recommendation:', error);
            alert('Failed to dismiss recommendation');
        }
    }

    // ==================== STATEMACHINE METHODS ====================
    async fetchStateMachineData() {
        try {
            const [machinesRes, statesRes, transitionsRes, statsRes] = await Promise.all([
                fetch('/api/statemachine/machines'),
                fetch('/api/statemachine/states'),
                fetch('/api/statemachine/transitions?limit=50'),
                fetch('/api/statemachine/statistics')
            ]);

            const machines = machinesRes.ok ? await machinesRes.json() : [];
            const states = statesRes.ok ? await statesRes.json() : [];
            const transitions = transitionsRes.ok ? await transitionsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderStateMachineData(machines, states, transitions, stats);
        } catch (error) {
            console.error('Error fetching state machine data:', error);
        }
    }

    renderStateMachineData(machines, states, transitions, stats) {
        // Update summary metrics
        document.getElementById('statemachine-machines-count').textContent = machines.length || 0;
        document.getElementById('statemachine-states-count').textContent = stats.total_states || 0;
        document.getElementById('statemachine-transitions-count').textContent = stats.transitions_today || 0;
        document.getElementById('statemachine-active-count').textContent = machines.filter(m => m.status === 'active').length || 0;

        // Render tables
        this.renderStateMachinesTable(machines);
        this.renderStateTransitionsTable(transitions);
    }

    renderStateMachinesTable(machines) {
        const tbody = document.getElementById('statemachine-machines-table');
        if (!machines || machines.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No state machines defined</td></tr>';
            return;
        }

        tbody.innerHTML = machines.map(m => `
            <tr>
                <td>${m.name || '-'}</td>
                <td><span class="status-badge info">${m.type?.toUpperCase()}</span></td>
                <td><span class="status-badge ${this.getStateBadgeClass(m.current_state)}">${m.current_state?.toUpperCase()}</span></td>
                <td>${m.states?.length || 0}</td>
                <td>${m.transitions_count || 0}</td>
                <td><span class="status-badge ${m.status === 'active' ? 'success' : 'warning'}">${m.status?.toUpperCase()}</span></td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.viewStateMachine('${m.id}')" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.triggerTransition('${m.id}')" title="Trigger Transition">
                        <i class="fas fa-arrow-right"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.resetStateMachine('${m.id}')" title="Reset">
                        <i class="fas fa-redo"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderStateTransitionsTable(transitions) {
        const tbody = document.getElementById('statemachine-transitions-table');
        if (!transitions || transitions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No recent transitions</td></tr>';
            return;
        }

        tbody.innerHTML = transitions.map(t => `
            <tr>
                <td>${t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : '-'}</td>
                <td>${t.machine_name || '-'}</td>
                <td><span class="status-badge warning">${t.from_state?.toUpperCase()}</span></td>
                <td><span class="status-badge success">${t.to_state?.toUpperCase()}</span></td>
                <td>${t.trigger || '-'}</td>
                <td><span class="status-badge ${t.result === 'success' ? 'success' : 'error'}">${t.result?.toUpperCase()}</span></td>
            </tr>
        `).join('');
    }

    getStateBadgeClass(state) {
        const map = { 'idle': 'info', 'active': 'success', 'waiting': 'warning', 'error': 'error', 'completed': 'success' };
        return map[state?.toLowerCase()] || 'info';
    }

    async viewStateMachine(id) {
        try {
            const res = await fetch(`/api/statemachine/machines/${id}`);
            if (res.ok) {
                const machine = await res.json();
                const details = [
                    `Name: ${machine.name}`,
                    `Type: ${machine.type}`,
                    `Current State: ${machine.current_state}`,
                    `Available States: ${machine.states?.join(', ') || 'N/A'}`,
                    `Total Transitions: ${machine.transitions_count || 0}`,
                    `Created: ${machine.created_at ? new Date(machine.created_at).toLocaleString() : 'N/A'}`
                ].join('\n');
                alert(details);
            }
        } catch (error) {
            console.error('Error viewing state machine:', error);
        }
    }

    async triggerTransition(machineId) {
        const event = prompt('Enter transition event/trigger:');
        if (!event) return;

        try {
            const res = await fetch(`/api/statemachine/machines/${machineId}/trigger`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ event })
            });

            if (res.ok) {
                const result = await res.json();
                this.fetchStateMachineData();
                alert(`Transition complete!\nNew state: ${result.new_state}`);
            } else {
                const error = await res.json();
                alert(`Transition failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error triggering transition:', error);
            alert('Failed to trigger transition');
        }
    }

    async resetStateMachine(id) {
        if (!confirm('Reset this state machine to initial state?')) return;

        try {
            const res = await fetch(`/api/statemachine/machines/${id}/reset`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchStateMachineData();
            } else {
                const error = await res.json();
                alert(`Reset failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error resetting state machine:', error);
            alert('Failed to reset state machine');
        }
    }

    async createStateMachine() {
        const name = prompt('Enter state machine name:');
        if (!name) return;

        try {
            const res = await fetch('/api/statemachine/machines', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    type: 'protocol',
                    states: ['idle', 'active', 'waiting', 'completed'],
                    initial_state: 'idle'
                })
            });

            if (res.ok) {
                this.fetchStateMachineData();
            } else {
                const error = await res.json();
                alert(`Failed to create state machine: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating state machine:', error);
            alert('Failed to create state machine');
        }
    }

    refreshStateMachineData() {
        this.fetchStateMachineData();
    }

    // ==================== RBAC METHODS ====================
    async fetchRBACData() {
        try {
            const [rolesRes, permissionsRes, policiesRes, statsRes] = await Promise.all([
                fetch('/api/rbac/roles'),
                fetch('/api/rbac/permissions'),
                fetch('/api/rbac/policies'),
                fetch('/api/rbac/statistics')
            ]);

            const roles = rolesRes.ok ? await rolesRes.json() : [];
            const permissions = permissionsRes.ok ? await permissionsRes.json() : [];
            const policies = policiesRes.ok ? await policiesRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderRBACData(roles, permissions, policies, stats);
        } catch (error) {
            console.error('Error fetching RBAC data:', error);
        }
    }

    renderRBACData(roles, permissions, policies, stats) {
        // Update summary metrics
        document.getElementById('rbac-users-count').textContent = stats.users || 0;
        document.getElementById('rbac-roles-count').textContent = roles.length || 0;
        document.getElementById('rbac-permissions-count').textContent = permissions.length || 0;
        document.getElementById('rbac-policies-count').textContent = policies.length || 0;

        // Render tables
        this.renderRBACRolesTable(roles);
        this.renderRBACPermissionsTable(permissions);
        this.renderRBACPoliciesTable(policies);
    }

    renderRBACRolesTable(roles) {
        const tbody = document.getElementById('rbac-roles-table');
        if (!roles || roles.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No roles defined</td></tr>';
            return;
        }

        tbody.innerHTML = roles.map(r => `
            <tr>
                <td><strong>${r.name || '-'}</strong></td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.description || '')}">${r.description || '-'}</td>
                <td>${r.permissions?.length || 0}</td>
                <td>${r.user_count || 0}</td>
                <td><span class="status-badge ${r.active ? 'success' : 'warning'}">${r.active ? 'ACTIVE' : 'INACTIVE'}</span></td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.viewRole('${r.id}')" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.editRole('${r.id}')" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.deleteRole('${r.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderRBACPermissionsTable(permissions) {
        const tbody = document.getElementById('rbac-permissions-table');
        if (!permissions || permissions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No permissions defined</td></tr>';
            return;
        }

        tbody.innerHTML = permissions.map(p => `
            <tr>
                <td><strong>${p.name || '-'}</strong></td>
                <td>${p.resource || '*'}</td>
                <td><span class="status-badge ${this.getActionBadgeClass(p.action)}">${p.action?.toUpperCase()}</span></td>
                <td>${p.scope || 'global'}</td>
                <td>${p.roles?.join(', ') || '-'}</td>
            </tr>
        `).join('');
    }

    renderRBACPoliciesTable(policies) {
        const tbody = document.getElementById('rbac-policies-table');
        if (!policies || policies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No policies defined</td></tr>';
            return;
        }

        tbody.innerHTML = policies.map(p => `
            <tr>
                <td><strong>${p.name || '-'}</strong></td>
                <td><span class="status-badge ${p.effect === 'allow' ? 'success' : 'error'}">${p.effect?.toUpperCase()}</span></td>
                <td>${p.resources?.join(', ') || '*'}</td>
                <td>${p.actions?.join(', ') || '*'}</td>
                <td>${p.conditions?.length || 0}</td>
                <td><span class="status-badge ${p.enabled ? 'success' : 'warning'}">${p.enabled ? 'ENABLED' : 'DISABLED'}</span></td>
            </tr>
        `).join('');
    }

    getActionBadgeClass(action) {
        const map = { 'read': 'success', 'write': 'info', 'execute': 'warning', 'delete': 'error', 'admin': 'error' };
        return map[action?.toLowerCase()] || 'info';
    }

    async viewRole(id) {
        try {
            const res = await fetch(`/api/rbac/roles/${id}`);
            if (res.ok) {
                const role = await res.json();
                const details = [
                    `Name: ${role.name}`,
                    `Description: ${role.description || 'N/A'}`,
                    `Permissions: ${role.permissions?.join(', ') || 'None'}`,
                    `Users: ${role.user_count || 0}`,
                    `Active: ${role.active ? 'Yes' : 'No'}`,
                    `Created: ${role.created_at ? new Date(role.created_at).toLocaleString() : 'N/A'}`
                ].join('\n');
                alert(details);
            }
        } catch (error) {
            console.error('Error viewing role:', error);
        }
    }

    async editRole(id) {
        const name = prompt('Enter new role name:');
        if (!name) return;

        try {
            const res = await fetch(`/api/rbac/roles/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });

            if (res.ok) {
                this.fetchRBACData();
            } else {
                const error = await res.json();
                alert(`Failed to update role: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error editing role:', error);
            alert('Failed to update role');
        }
    }

    async deleteRole(id) {
        if (!confirm('Delete this role?')) return;

        try {
            const res = await fetch(`/api/rbac/roles/${id}`, {
                method: 'DELETE'
            });

            if (res.ok) {
                this.fetchRBACData();
            } else {
                const error = await res.json();
                alert(`Failed to delete role: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error deleting role:', error);
            alert('Failed to delete role');
        }
    }

    showCreateRoleModal() {
        const name = prompt('Enter role name:');
        if (!name) return;

        const description = prompt('Enter role description:');

        this.createRole(name, description);
    }

    async createRole(name, description) {
        try {
            const res = await fetch('/api/rbac/roles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, permissions: [] })
            });

            if (res.ok) {
                this.fetchRBACData();
            } else {
                const error = await res.json();
                alert(`Failed to create role: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error creating role:', error);
            alert('Failed to create role');
        }
    }

    refreshRBACData() {
        this.fetchRBACData();
    }

    // ==================== LLM METHODS ====================
    async fetchLLMData() {
        try {
            const [providersRes, conversationsRes, statsRes] = await Promise.all([
                fetch('/api/llm/providers'),
                fetch('/api/llm/conversations?limit=20'),
                fetch('/api/llm/statistics')
            ]);

            const providers = providersRes.ok ? await providersRes.json() : [];
            const conversations = conversationsRes.ok ? await conversationsRes.json() : [];
            const stats = statsRes.ok ? await statsRes.json() : {};

            this.renderLLMData(providers, conversations, stats);
        } catch (error) {
            console.error('Error fetching LLM data:', error);
        }
    }

    renderLLMData(providers, conversations, stats) {
        // Update summary metrics
        document.getElementById('llm-providers-count').textContent = providers.length || 0;
        document.getElementById('llm-conversations-count').textContent = stats.conversations_today || 0;
        document.getElementById('llm-tokens-count').textContent = this.formatNumber(stats.tokens_today || 0);
        document.getElementById('llm-active-provider').textContent = stats.active_provider || '-';

        // Render tables
        this.renderLLMProvidersTable(providers);
        this.renderLLMConversationsTable(conversations);
    }

    renderLLMProvidersTable(providers) {
        const tbody = document.getElementById('llm-providers-table');
        if (!providers || providers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No providers configured</td></tr>';
            return;
        }

        tbody.innerHTML = providers.map(p => `
            <tr>
                <td><strong>${p.name || '-'}</strong></td>
                <td>${p.model || '-'}</td>
                <td><span class="status-badge ${p.status === 'active' ? 'success' : 'warning'}">${p.status?.toUpperCase()}</span></td>
                <td><span class="status-badge ${p.api_key_configured ? 'success' : 'error'}">${p.api_key_configured ? 'CONFIGURED' : 'MISSING'}</span></td>
                <td>${p.requests_today || 0}</td>
                <td>${p.avg_latency_ms ? `${p.avg_latency_ms.toFixed(0)} ms` : '-'}</td>
                <td>
                    <button class="btn btn-sm" onclick="dashboard.setActiveProvider('${p.id}')" title="Set Active" style="background: #0ea5e9; border-color: #0ea5e9;">
                        <i class="fas fa-check"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.testProvider('${p.id}')" title="Test">
                        <i class="fas fa-vial"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="dashboard.configureProvider('${p.id}')" title="Configure">
                        <i class="fas fa-cog"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderLLMConversationsTable(conversations) {
        const tbody = document.getElementById('llm-conversations-table');
        if (!conversations || conversations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No recent conversations</td></tr>';
            return;
        }

        tbody.innerHTML = conversations.map(c => `
            <tr>
                <td style="font-family: monospace;">${c.id?.substring(0, 8) || '-'}</td>
                <td><span class="status-badge ${this.getProviderBadgeClass(c.provider)}">${c.provider?.toUpperCase()}</span></td>
                <td>${c.turns || 0} / 75</td>
                <td>${this.formatNumber(c.tokens || 0)}</td>
                <td><span class="status-badge ${c.status === 'active' ? 'success' : 'info'}">${c.status?.toUpperCase()}</span></td>
                <td>${c.started_at ? new Date(c.started_at).toLocaleTimeString() : '-'}</td>
            </tr>
        `).join('');
    }

    getProviderBadgeClass(provider) {
        const map = { 'openai': 'success', 'anthropic': 'warning', 'google': 'info', 'local': 'info' };
        return map[provider?.toLowerCase()] || 'info';
    }

    formatNumber(num) {
        if (!num && num !== 0) return '-';
        if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
        if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
        return num.toString();
    }

    async setActiveProvider(id) {
        try {
            const res = await fetch(`/api/llm/providers/${id}/activate`, {
                method: 'POST'
            });

            if (res.ok) {
                this.fetchLLMData();
            } else {
                const error = await res.json();
                alert(`Failed to set active provider: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error setting active provider:', error);
            alert('Failed to set active provider');
        }
    }

    async testProvider(id) {
        try {
            const res = await fetch(`/api/llm/providers/${id}/test`, {
                method: 'POST'
            });

            if (res.ok) {
                const result = await res.json();
                alert(`Provider test ${result.success ? 'successful' : 'failed'}!\nLatency: ${result.latency_ms || 'N/A'} ms\nMessage: ${result.message || 'N/A'}`);
            } else {
                const error = await res.json();
                alert(`Test failed: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error testing provider:', error);
            alert('Failed to test provider');
        }
    }

    async configureProvider(id) {
        const apiKey = prompt('Enter API key (leave empty to keep current):');
        if (apiKey === null) return;

        try {
            const body = {};
            if (apiKey) body.api_key = apiKey;

            const res = await fetch(`/api/llm/providers/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (res.ok) {
                this.fetchLLMData();
                alert('Provider configured successfully');
            } else {
                const error = await res.json();
                alert(`Failed to configure provider: ${error.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error configuring provider:', error);
            alert('Failed to configure provider');
        }
    }

    refreshLLMData() {
        this.fetchLLMData();
    }

    // ==================== UTILITY METHODS ====================
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.agentDashboard = new AgentDashboard();
    window.dashboard = window.agentDashboard;  // Alias for onclick handlers
});
