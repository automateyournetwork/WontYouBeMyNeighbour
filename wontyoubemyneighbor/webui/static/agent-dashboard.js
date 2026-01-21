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

        this.init();
    }

    init() {
        // Get agent ID from URL params or use default
        const urlParams = new URLSearchParams(window.location.search);
        this.agentId = urlParams.get('agent') || 'local';

        this.connectWebSocket();
        this.setupEventListeners();
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

        // Auto-select Interfaces tab if none selected, otherwise first protocol
        if (!this.activeProtocol) {
            this.selectProtocol('interfaces');
        }
    }

    updateInterfacesData(interfaces) {
        if (!interfaces || !Array.isArray(interfaces)) {
            interfaces = [];
        }

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

        let html = '';

        // Always add Interfaces tab first (always active since every agent has interfaces)
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

        tabsContainer.innerHTML = html;

        // Add click handlers (including interfaces)
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
    }

    updateOSPFData(ospf) {
        if (!ospf) return;

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
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.agentDashboard = new AgentDashboard();
});
