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

        // Agentic info
        if (status.agentic) {
            document.getElementById('llm-provider').textContent = status.agentic.provider || '--';
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

        const protocolNames = {
            interfaces: 'Interfaces',
            ospf: 'OSPF',
            bgp: 'BGP',
            isis: 'IS-IS',
            mpls: 'MPLS',
            vxlan: 'VXLAN/EVPN',
            dhcp: 'DHCP',
            dns: 'DNS'
        };

        // MCP tabs (always available)
        const mcpTabs = {
            testing: 'Testing',
            gait: 'GAIT',
            markmap: 'Markmap',
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

        // Add inactive tabs for protocols not running (skip interfaces since it's always shown)
        for (const [proto, name] of Object.entries(protocolNames)) {
            if (proto !== 'interfaces' && !this.protocols[proto]) {
                html += `
                    <button class="protocol-tab ${proto}" data-protocol="${proto}" disabled style="opacity: 0.3;">
                        <span class="protocol-indicator inactive"></span>
                        ${name}
                    </button>
                `;
            }
        }

        // Add MCP tabs (Testing, GAIT, Markmap) - always available
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

        // Request data for specific tabs that need it
        if (protocol === 'gait') {
            // Request GAIT history when GAIT tab is selected
            this.send({ type: 'get_gait', agent_id: this.agentId });
        } else if (protocol === 'markmap') {
            // Request markmap data when Markmap tab is selected
            this.send({ type: 'get_markmap', agent_id: this.agentId });
        } else if (protocol === 'testing') {
            // Fetch previous test results when Testing tab is selected
            this.fetchPreviousTestResults();
        }
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

        // OSPF routes
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

        // BGP routes
        const bgpRoutesTable = document.getElementById('bgp-routes-table');
        if (bgpRoutesTable && routes.bgp) {
            if (routes.bgp.length === 0) {
                bgpRoutesTable.innerHTML = '<tr><td colspan="5" class="empty-state">No routes</td></tr>';
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
    }

    // ==================== TESTING TAB ====================
    setupTestingEvents() {
        // Run all tests button
        const runAllBtn = document.getElementById('run-all-tests-btn');
        if (runAllBtn) {
            runAllBtn.addEventListener('click', () => this.runAllTests());
        }

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

        // Fetch previous test results on page load for persistence
        this.fetchPreviousTestResults();
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
        // Load markmap-common first (required dependency)
        const commonScript = document.createElement('script');
        commonScript.src = 'https://cdn.jsdelivr.net/npm/markmap-common@0.15.4/dist/index.js';
        commonScript.onload = () => {
            // Load markmap-lib
            const libScript = document.createElement('script');
            libScript.src = 'https://cdn.jsdelivr.net/npm/markmap-lib@0.15.4/dist/browser/index.js';
            libScript.onload = () => {
                // Then load markmap-view
                const viewScript = document.createElement('script');
                viewScript.src = 'https://cdn.jsdelivr.net/npm/markmap-view@0.15.4/dist/browser/index.js';
                viewScript.onload = () => {
                    // Give scripts time to initialize globals
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
        };
        commonScript.onerror = () => {
            console.warn('markmap-common failed, trying direct fallback');
            this.loadMarkmapFallback(resolve, reject);
        };
        document.head.appendChild(commonScript);
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

    renderMarkmap(markdown) {
        const svgElement = document.getElementById('markmap-svg');
        if (!svgElement) return;

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
});
