/**
 * RubberBand Network Builder Wizard
 *
 * JavaScript logic for the 6-step network builder wizard
 */

// State
let sessionId = null;
let currentStep = 1;
let wizardState = {
    docker_config: null,
    mcp_selection: { selected: [], custom: [] },
    agents: [],
    network_type: { mode: 'manual' },
    topology: { links: [], auto_generate: false },
    llm_config: { provider: 'claude', api_key: null }
};

// Default MCPs
let defaultMcps = [];

// Current agent's protocols being configured
let currentAgentProtocols = [];

// Current agent's interfaces being configured
let currentAgentInterfaces = [];

// Interface counters by type
let interfaceCounters = {
    eth: 1,   // Start at 1 since eth0 is default
    lo: 1,    // Start at 1 since lo0 is default
    vlan: 0,
    tun: 0,
    sub: 0    // Sub-interface counter
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await createSession();
    await checkDocker();
    await loadDefaultMcps();
    await loadAgentTemplates();
});

// Import Network Template
async function importNetworkTemplate() {
    const jsonText = document.getElementById('import-template-json').value.trim();
    const statusSpan = document.getElementById('import-status');

    if (!jsonText) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Please paste a network template JSON</span>';
        return;
    }

    let networkData;
    try {
        networkData = JSON.parse(jsonText);
    } catch (e) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Invalid JSON format</span>';
        return;
    }

    statusSpan.innerHTML = '<span style="color: #00d9ff;">Importing...</span>';

    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/import-network`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(networkData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        const result = await response.json();

        // Update local wizard state from imported data
        if (networkData.docker) {
            wizardState.docker_config = {
                name: networkData.docker.n || networkData.id,
                subnet: networkData.docker.subnet,
                gateway: networkData.docker.gw,
                driver: networkData.docker.driver || 'bridge'
            };
        }

        // Import agents into local state
        wizardState.agents = [];
        for (const agent of networkData.agents || []) {
            wizardState.agents.push({
                id: agent.id,
                name: agent.n || agent.id,
                router_id: agent.r,
                protocols: agent.protos || [],
                protocol: agent.protos?.[0]?.p || 'ospf',
                interfaces: agent.ifs || [],
                protocol_config: agent.protos?.[0] || {}
            });
        }

        // Import topology
        if (networkData.topo && networkData.topo.links) {
            wizardState.topology = {
                links: networkData.topo.links.map(l => ({
                    id: l.id,
                    agent1_id: l.a1,
                    interface1: l.i1,
                    agent2_id: l.a2,
                    interface2: l.i2,
                    link_type: l.t || 'ethernet',
                    cost: l.c || 10
                })),
                auto_generate: false
            };
        }

        statusSpan.innerHTML = `<span style="color: #4ade80;">Imported ${result.imported.agents} agents, ${result.imported.links} links</span>`;

        // Show success alert
        showAlert(`Network template imported! ${result.imported.agents} agents, ${result.imported.links} links. Skipping to deployment...`, 'success');

        // Skip to step 5 (LLM Provider / Deploy)
        setTimeout(() => {
            goToStep(5);
            updatePreview();
        }, 1500);

    } catch (error) {
        statusSpan.innerHTML = `<span style="color: #ef4444;">Import failed: ${error.message}</span>`;
        showAlert(`Import failed: ${error.message}`, 'error');
    }
}

// Session Management

async function createSession() {
    try {
        const response = await fetch('/api/wizard/session/create', { method: 'POST' });
        const data = await response.json();
        sessionId = data.session_id;
        console.log('Wizard session created:', sessionId);
    } catch (error) {
        console.error('Failed to create session:', error);
        showAlert('Failed to initialize wizard session', 'error');
    }
}

// Docker Check

async function checkDocker() {
    const statusDiv = document.getElementById('docker-status');
    try {
        const response = await fetch('/api/wizard/check-docker');
        const data = await response.json();

        if (data.available) {
            statusDiv.innerHTML = `
                <div class="status-dot available"></div>
                <span>Docker is available: ${data.message}</span>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="status-dot unavailable"></div>
                <span>Docker unavailable: ${data.message}</span>
            `;
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="status-dot unavailable"></div>
            <span>Error checking Docker: ${error.message}</span>
        `;
    }
}

// MCP Loading

async function loadDefaultMcps() {
    try {
        const response = await fetch('/api/wizard/mcps/default');
        defaultMcps = await response.json();
        renderMcpGrid();
    } catch (error) {
        console.error('Failed to load MCPs:', error);
    }
}

// Current MCP being configured
let currentMcpConfig = null;

// MCP configurations (stored separately from selection)
let mcpConfigurations = {};

function renderMcpGrid() {
    const grid = document.getElementById('mcp-grid');
    grid.innerHTML = defaultMcps.map(mcp => {
        const isSelected = wizardState.mcp_selection.selected.includes(mcp.id);
        const requiresConfig = mcp.c?._requires_config;
        const hasConfig = mcpConfigurations[mcp.id] && Object.keys(mcpConfigurations[mcp.id]).length > 0;
        const configFields = mcp.c?._config_fields || [];

        return `
            <div class="mcp-card ${isSelected ? 'selected' : ''}"
                 data-mcp-id="${mcp.id}">
                <div onclick="toggleMcp('${mcp.id}')" style="cursor: pointer;">
                    <h4>${mcp.n}</h4>
                    <p>${mcp.d || 'No description'}</p>
                </div>
                ${configFields.length > 0 ? `
                    <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #2a2a4e;">
                        <button class="btn btn-secondary" onclick="event.stopPropagation(); openMcpConfig('${mcp.id}')"
                                style="padding: 5px 10px; font-size: 0.8rem; width: 100%;">
                            ${hasConfig ? '✓ Configured' : (requiresConfig ? '⚠ Configure' : 'Configure')}
                        </button>
                    </div>
                ` : `
                    <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #2a2a4e; text-align: center;">
                        <span style="color: #4ade80; font-size: 0.75rem;">✓ No config needed</span>
                    </div>
                `}
            </div>
        `;
    }).join('');
}

function toggleMcp(mcpId) {
    const mcp = defaultMcps.find(m => m.id === mcpId);
    const requiresConfig = mcp?.c?._requires_config;
    const hasConfig = mcpConfigurations[mcpId] && Object.keys(mcpConfigurations[mcpId]).length > 0;

    const index = wizardState.mcp_selection.selected.indexOf(mcpId);
    if (index > -1) {
        // Deselecting
        wizardState.mcp_selection.selected.splice(index, 1);
    } else {
        // Selecting - check if config is required
        if (requiresConfig && !hasConfig) {
            openMcpConfig(mcpId);
            return;  // Don't select until configured
        }
        wizardState.mcp_selection.selected.push(mcpId);
    }
    renderMcpGrid();
}

function openMcpConfig(mcpId) {
    const mcp = defaultMcps.find(m => m.id === mcpId);
    if (!mcp) return;

    currentMcpConfig = mcp;
    const configFields = mcp.c?._config_fields || [];
    const savedConfig = mcpConfigurations[mcpId] || {};

    // Set modal title and description
    document.getElementById('mcp-modal-title').textContent = `Configure ${mcp.n}`;
    document.getElementById('mcp-modal-description').textContent = mcp.d;
    document.getElementById('mcp-docs-url').href = mcp.url;

    // Build config fields
    const fieldsContainer = document.getElementById('mcp-config-fields');

    if (configFields.length === 0) {
        fieldsContainer.innerHTML = '<p style="color: #4ade80;">This MCP does not require additional configuration.</p>';
    } else {
        fieldsContainer.innerHTML = configFields.map(field => `
            <div class="form-group" style="margin-bottom: 15px;">
                <label for="mcp-field-${field.id}">${field.label}${field.required ? ' *' : ''}</label>
                <input type="${field.type}"
                       id="mcp-field-${field.id}"
                       placeholder="${field.placeholder || ''}"
                       value="${savedConfig[field.id] || ''}"
                       ${field.required ? 'required' : ''}
                       style="width: 100%; padding: 10px; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px; color: #eee;">
                ${field.hint ? `<div class="hint" style="font-size: 0.8rem; color: #666; margin-top: 4px;">${field.hint}</div>` : ''}
            </div>
        `).join('');
    }

    // Show modal
    document.getElementById('mcp-config-modal').style.display = 'flex';
}

function closeMcpModal() {
    document.getElementById('mcp-config-modal').style.display = 'none';
    currentMcpConfig = null;
}

function saveMcpConfig() {
    if (!currentMcpConfig) return;

    const mcpId = currentMcpConfig.id;
    const configFields = currentMcpConfig.c?._config_fields || [];

    // Collect values
    const config = {};
    let hasError = false;

    for (const field of configFields) {
        const input = document.getElementById(`mcp-field-${field.id}`);
        const value = input?.value?.trim() || '';

        if (field.required && !value) {
            input.style.borderColor = '#ef4444';
            hasError = true;
        } else {
            input.style.borderColor = '#2a2a4e';
            if (value) {
                config[field.id] = value;
            }
        }
    }

    if (hasError) {
        showAlert('Please fill in all required fields', 'error');
        return;
    }

    // Save config
    mcpConfigurations[mcpId] = config;

    // Auto-select the MCP if not already selected
    if (!wizardState.mcp_selection.selected.includes(mcpId)) {
        wizardState.mcp_selection.selected.push(mcpId);
    }

    // Store in wizard state for backend
    wizardState.mcp_selection.custom = wizardState.mcp_selection.custom || [];
    const existingIndex = wizardState.mcp_selection.custom.findIndex(c => c.id === mcpId);
    if (existingIndex >= 0) {
        wizardState.mcp_selection.custom[existingIndex] = { id: mcpId, config };
    } else {
        wizardState.mcp_selection.custom.push({ id: mcpId, config });
    }

    closeMcpModal();
    renderMcpGrid();
    showAlert(`${currentMcpConfig.n} configured and enabled!`, 'success');
}

// Agent Templates

async function loadAgentTemplates() {
    try {
        const response = await fetch('/api/wizard/libraries/agents');
        const templates = await response.json();
        const select = document.getElementById('template-select');

        templates.forEach(t => {
            const option = document.createElement('option');
            option.value = t.id;
            option.textContent = `${t.n} (${t.r})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load templates:', error);
    }
}

// Agent Management

function showAgentTab(tab) {
    document.querySelectorAll('#step-3 .tabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`#step-3 .tabs .tab[onclick*="${tab}"]`).classList.add('active');

    document.getElementById('agent-tab-new').style.display = tab === 'new' ? 'block' : 'none';
    document.getElementById('agent-tab-template').style.display = tab === 'template' ? 'block' : 'none';
    document.getElementById('agent-tab-nl').style.display = tab === 'nl' ? 'block' : 'none';
    document.getElementById('agent-tab-bulk').style.display = tab === 'bulk' ? 'block' : 'none';
}

function updateProtocolConfig() {
    const protocol = document.getElementById('protocol').value;
    const configDiv = document.getElementById('protocol-config');

    if (protocol === 'ospf' || protocol === 'ospfv3') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="ospf-area">OSPF Area</label>
                <input type="text" id="ospf-area" placeholder="0.0.0.0" value="0.0.0.0">
                <div class="hint">Use 0.0.0.0 for backbone area</div>
            </div>
            <div class="form-group">
                <label for="ospf-interface">OSPF Interface</label>
                <input type="text" id="ospf-interface" placeholder="eth0" value="eth0">
                <div class="hint">Interface to run OSPF on</div>
            </div>
            <div class="form-group">
                <label for="ospf-loopback">Loopback IP Address</label>
                <input type="text" id="ospf-loopback" placeholder="e.g., 10.255.255.1">
                <div class="hint">Loopback IP for testing connectivity (will be added to lo0 interface)</div>
            </div>
        `;
    } else if (protocol === 'ibgp') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="bgp-asn">AS Number</label>
                <input type="number" id="bgp-asn" placeholder="65001" value="65001">
                <div class="hint">All iBGP peers must share the same AS number</div>
            </div>
            <div class="form-group">
                <label for="bgp-peer-ip">Peer IP Address</label>
                <input type="text" id="bgp-peer-ip" placeholder="e.g., 192.168.1.2">
                <div class="hint">IP address of iBGP peer (same AS)</div>
            </div>
            <div class="form-group">
                <label for="bgp-network">Advertised Networks (comma-separated)</label>
                <input type="text" id="bgp-network" placeholder="e.g., 10.0.0.0/8, 172.16.0.0/16">
                <div class="hint">Networks to advertise via BGP</div>
            </div>
        `;
    } else if (protocol === 'ebgp') {
        configDiv.innerHTML = `
            <div class="form-row">
                <div class="form-group">
                    <label for="bgp-asn">Local AS Number</label>
                    <input type="number" id="bgp-asn" placeholder="65001" value="65001">
                    <div class="hint">Your autonomous system number</div>
                </div>
                <div class="form-group">
                    <label for="bgp-peer-asn">Peer AS Number</label>
                    <input type="number" id="bgp-peer-asn" placeholder="65002">
                    <div class="hint">Neighbor's AS (must be different for eBGP)</div>
                </div>
            </div>
            <div class="form-group">
                <label for="bgp-peer-ip">Peer IP Address</label>
                <input type="text" id="bgp-peer-ip" placeholder="e.g., 192.168.1.2">
                <div class="hint">IP address of eBGP peer</div>
            </div>
            <div class="form-group">
                <label for="bgp-network">Advertised Networks (comma-separated)</label>
                <input type="text" id="bgp-network" placeholder="e.g., 10.0.0.0/8">
                <div class="hint">Enter your networks to advertise (leave empty if none)</div>
            </div>
            <div class="form-group">
                <label for="bgp-loopback">Loopback IP Address</label>
                <input type="text" id="bgp-loopback" placeholder="e.g., 10.255.255.1">
                <div class="hint">Loopback IP for testing connectivity (will be added to lo0 interface)</div>
            </div>
        `;
    } else if (protocol === 'isis') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="isis-system-id">System ID</label>
                <input type="text" id="isis-system-id" placeholder="0000.0000.0001">
                <div class="hint">IS-IS System ID (e.g., 0000.0000.0001). Leave empty to auto-generate from Router ID.</div>
            </div>
            <div class="form-group">
                <label for="isis-area">Area Address</label>
                <input type="text" id="isis-area" placeholder="49.0001" value="49.0001">
                <div class="hint">IS-IS area address (e.g., 49.0001 for area 1)</div>
            </div>
            <div class="form-group">
                <label for="isis-level">IS-IS Level</label>
                <select id="isis-level">
                    <option value="1">Level 1 (Intra-area)</option>
                    <option value="2">Level 2 (Inter-area)</option>
                    <option value="3" selected>Level 1-2 (Both)</option>
                </select>
                <div class="hint">Level 1 = intra-area, Level 2 = inter-area backbone</div>
            </div>
            <div class="form-group">
                <label for="isis-interface">IS-IS Interface</label>
                <input type="text" id="isis-interface" placeholder="eth0" value="eth0">
                <div class="hint">Interface to run IS-IS on</div>
            </div>
            <div class="form-group">
                <label for="isis-metric">Interface Metric</label>
                <input type="number" id="isis-metric" placeholder="10" value="10">
                <div class="hint">IS-IS metric for the interface (default: 10)</div>
            </div>
        `;
    } else if (protocol === 'mpls') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="mpls-router-id">MPLS Router ID</label>
                <input type="text" id="mpls-router-id" placeholder="Leave empty to use agent Router ID">
                <div class="hint">MPLS/LDP Router ID. Leave empty to use the agent's Router ID.</div>
            </div>
            <div class="form-group">
                <label for="ldp-interfaces">LDP Interfaces (comma-separated)</label>
                <input type="text" id="ldp-interfaces" placeholder="eth0, eth1" value="eth0">
                <div class="hint">Interfaces to enable LDP on</div>
            </div>
            <div class="form-group">
                <label for="ldp-neighbors">LDP Neighbor IPs (comma-separated)</label>
                <input type="text" id="ldp-neighbors" placeholder="e.g., 10.0.0.2, 10.0.0.3">
                <div class="hint">IP addresses of LDP neighbors (optional - uses discovery if empty)</div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="label-range-start">Label Range Start</label>
                    <input type="number" id="label-range-start" placeholder="16" value="16">
                </div>
                <div class="form-group">
                    <label for="label-range-end">Label Range End</label>
                    <input type="number" id="label-range-end" placeholder="1048575" value="1048575">
                </div>
            </div>
            <div class="hint">MPLS label range (default: 16-1048575)</div>
        `;
    } else if (protocol === 'vxlan') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="vtep-ip">VTEP IP Address</label>
                <input type="text" id="vtep-ip" placeholder="Leave empty to use Router ID">
                <div class="hint">VXLAN Tunnel Endpoint IP. Leave empty to use Router ID.</div>
            </div>
            <div class="form-group">
                <label for="vxlan-vnis">VNIs (comma-separated)</label>
                <input type="text" id="vxlan-vnis" placeholder="e.g., 10001, 10002, 10003">
                <div class="hint">VXLAN Network Identifiers to configure</div>
            </div>
            <div class="form-group">
                <label for="vxlan-remote-vteps">Remote VTEP IPs (comma-separated)</label>
                <input type="text" id="vxlan-remote-vteps" placeholder="e.g., 10.0.0.2, 10.0.0.3">
                <div class="hint">IP addresses of remote VTEPs (for static tunnels)</div>
            </div>
            <div class="form-group">
                <label for="vxlan-udp-port">UDP Port</label>
                <input type="number" id="vxlan-udp-port" placeholder="4789" value="4789">
                <div class="hint">VXLAN UDP port (default: 4789)</div>
            </div>
        `;
    } else if (protocol === 'evpn') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="evpn-rd">Route Distinguisher</label>
                <input type="text" id="evpn-rd" placeholder="e.g., 65001:100">
                <div class="hint">EVPN Route Distinguisher (format: ASN:NN or IP:NN)</div>
            </div>
            <div class="form-group">
                <label for="evpn-rt-import">Import Route Targets (comma-separated)</label>
                <input type="text" id="evpn-rt-import" placeholder="e.g., 65001:100">
                <div class="hint">Route targets to import</div>
            </div>
            <div class="form-group">
                <label for="evpn-rt-export">Export Route Targets (comma-separated)</label>
                <input type="text" id="evpn-rt-export" placeholder="e.g., 65001:100">
                <div class="hint">Route targets to export</div>
            </div>
            <div class="form-group">
                <label for="evpn-vnis">EVPN VNIs (comma-separated)</label>
                <input type="text" id="evpn-vnis" placeholder="e.g., 10001, 10002">
                <div class="hint">VNIs to associate with this EVPN instance</div>
            </div>
            <div class="form-group">
                <label for="evpn-type">EVPN Instance Type</label>
                <select id="evpn-type">
                    <option value="vlan-based">VLAN-Based</option>
                    <option value="vlan-bundle">VLAN Bundle</option>
                    <option value="vlan-aware">VLAN-Aware Bundle</option>
                </select>
            </div>
        `;
    } else if (protocol === 'dhcp') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="dhcp-pool-name">Pool Name</label>
                <input type="text" id="dhcp-pool-name" placeholder="default" value="default">
                <div class="hint">Name for this DHCP pool</div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="dhcp-pool-start">Pool Start IP</label>
                    <input type="text" id="dhcp-pool-start" placeholder="e.g., 192.168.1.100">
                </div>
                <div class="form-group">
                    <label for="dhcp-pool-end">Pool End IP</label>
                    <input type="text" id="dhcp-pool-end" placeholder="e.g., 192.168.1.200">
                </div>
            </div>
            <div class="form-group">
                <label for="dhcp-gateway">Default Gateway</label>
                <input type="text" id="dhcp-gateway" placeholder="e.g., 192.168.1.1">
                <div class="hint">Gateway IP to provide to clients</div>
            </div>
            <div class="form-group">
                <label for="dhcp-dns">DNS Servers (comma-separated)</label>
                <input type="text" id="dhcp-dns" placeholder="e.g., 8.8.8.8, 8.8.4.4">
                <div class="hint">DNS servers to provide to clients</div>
            </div>
            <div class="form-group">
                <label for="dhcp-lease-time">Lease Time (seconds)</label>
                <input type="number" id="dhcp-lease-time" placeholder="86400" value="86400">
                <div class="hint">DHCP lease duration (default: 86400 = 24 hours)</div>
            </div>
            <div class="form-group">
                <label for="dhcp-domain">Domain Name</label>
                <input type="text" id="dhcp-domain" placeholder="e.g., example.local">
                <div class="hint">Domain name to provide to clients (optional)</div>
            </div>
        `;
    } else if (protocol === 'dns') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="dns-zone">Primary Zone</label>
                <input type="text" id="dns-zone" placeholder="e.g., example.local">
                <div class="hint">DNS zone this server is authoritative for</div>
            </div>
            <div class="form-group">
                <label for="dns-records">DNS Records (one per line: name TYPE value)</label>
                <textarea id="dns-records" rows="4" placeholder="www A 192.168.1.10&#10;mail A 192.168.1.20&#10;@ MX mail.example.local"></textarea>
                <div class="hint">Format: name TYPE value (A, AAAA, CNAME, MX, PTR, TXT)</div>
            </div>
            <div class="form-group">
                <label for="dns-forwarders">Forwarders (comma-separated)</label>
                <input type="text" id="dns-forwarders" placeholder="e.g., 8.8.8.8, 1.1.1.1">
                <div class="hint">Upstream DNS servers for recursive queries</div>
            </div>
            <div class="form-group">
                <label for="dns-listen-port">Listen Port</label>
                <input type="number" id="dns-listen-port" placeholder="53" value="53">
                <div class="hint">DNS server port (default: 53)</div>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="dns-recursion" checked> Enable Recursion
                </label>
                <div class="hint">Allow recursive queries for non-authoritative zones</div>
            </div>
        `;
    } else if (protocol === 'ntp') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="ntp-mode">NTP Mode</label>
                <select id="ntp-mode">
                    <option value="server">Server (provides time to clients)</option>
                    <option value="client">Client (syncs from server)</option>
                    <option value="peer">Peer (bidirectional sync)</option>
                </select>
                <div class="hint">Role of this NTP instance</div>
            </div>
            <div class="form-group">
                <label for="ntp-servers">Upstream NTP Servers (comma-separated)</label>
                <input type="text" id="ntp-servers" placeholder="e.g., 0.pool.ntp.org, 1.pool.ntp.org">
                <div class="hint">NTP servers to synchronize with (for client/peer mode)</div>
            </div>
            <div class="form-group">
                <label for="ntp-stratum">Stratum Level</label>
                <input type="number" id="ntp-stratum" placeholder="2" value="2" min="1" max="15">
                <div class="hint">Time source accuracy level (1=highest, 15=lowest)</div>
            </div>
            <div class="form-group">
                <label for="ntp-interface">Listen Interface</label>
                <input type="text" id="ntp-interface" placeholder="eth0" value="eth0">
                <div class="hint">Interface to listen on (server mode)</div>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="ntp-broadcast" > Enable Broadcast Mode
                </label>
                <div class="hint">Broadcast time to subnet (server mode)</div>
            </div>
        `;
    } else if (protocol === 'ptp') {
        configDiv.innerHTML = `
            <div class="form-group">
                <label for="ptp-mode">PTP Mode</label>
                <select id="ptp-mode">
                    <option value="grandmaster">Grandmaster Clock (primary time source)</option>
                    <option value="boundary">Boundary Clock (master + slave)</option>
                    <option value="slave">Slave Clock (syncs from master)</option>
                </select>
                <div class="hint">PTP clock role in the network</div>
            </div>
            <div class="form-group">
                <label for="ptp-domain">PTP Domain</label>
                <input type="number" id="ptp-domain" placeholder="0" value="0" min="0" max="127">
                <div class="hint">PTP domain number (0-127)</div>
            </div>
            <div class="form-group">
                <label for="ptp-profile">PTP Profile</label>
                <select id="ptp-profile">
                    <option value="default">IEEE 1588 Default Profile</option>
                    <option value="g8275.1">ITU-T G.8275.1 (Telecom)</option>
                    <option value="g8275.2">ITU-T G.8275.2 (Telecom Assisted)</option>
                    <option value="power">IEEE C37.238 (Power Industry)</option>
                </select>
                <div class="hint">PTP profile for specific use cases</div>
            </div>
            <div class="form-group">
                <label for="ptp-transport">Transport</label>
                <select id="ptp-transport">
                    <option value="udp-ipv4">UDP over IPv4</option>
                    <option value="udp-ipv6">UDP over IPv6</option>
                    <option value="ethernet">Ethernet (Layer 2)</option>
                </select>
                <div class="hint">PTP message transport mechanism</div>
            </div>
            <div class="form-group">
                <label for="ptp-interface">PTP Interface</label>
                <input type="text" id="ptp-interface" placeholder="eth0" value="eth0">
                <div class="hint">Network interface for PTP messages</div>
            </div>
            <div class="form-group">
                <label for="ptp-priority1">Priority 1</label>
                <input type="number" id="ptp-priority1" placeholder="128" value="128" min="0" max="255">
                <div class="hint">Clock selection priority (0=highest, 255=lowest)</div>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="ptp-delay-mechanism" checked> Use E2E Delay Mechanism
                </label>
                <div class="hint">End-to-End (checked) vs Peer-to-Peer delay measurement</div>
            </div>
        `;
    } else {
        configDiv.innerHTML = '<div class="alert alert-info">Select a protocol to configure.</div>';
    }
}

// Multi-protocol management functions

function showAddProtocolForm() {
    document.getElementById('add-protocol-form').style.display = 'block';
    updateProtocolConfig();  // Initialize with current selection
}

function hideAddProtocolForm() {
    document.getElementById('add-protocol-form').style.display = 'none';
}

function addProtocolToAgent() {
    const protocol = document.getElementById('protocol').value;
    const routerId = document.getElementById('router-id').value.trim();

    if (!routerId) {
        showAlert('Please enter a Router ID first', 'error');
        return;
    }

    // Build protocol config
    const protocolConfig = {
        p: protocol,
        r: routerId
    };

    if (protocol === 'ospf' || protocol === 'ospfv3') {
        protocolConfig.a = document.getElementById('ospf-area')?.value || '0.0.0.0';
        const ospfInterface = document.getElementById('ospf-interface')?.value;
        if (ospfInterface) {
            protocolConfig.interface = ospfInterface;
        }
        const loopbackIp = document.getElementById('ospf-loopback')?.value?.trim();
        if (loopbackIp) {
            protocolConfig.loopback_ip = loopbackIp;
        }
    } else if (protocol === 'ibgp') {
        protocolConfig.asn = parseInt(document.getElementById('bgp-asn')?.value || '65001');

        const networksStr = document.getElementById('bgp-network')?.value || '';
        if (networksStr.trim()) {
            protocolConfig.nets = networksStr.split(',').map(n => n.trim()).filter(n => n);
        } else {
            protocolConfig.nets = [];
        }

        const peerIp = document.getElementById('bgp-peer-ip')?.value?.trim();
        if (peerIp) {
            protocolConfig.peers = [{
                ip: peerIp,
                asn: protocolConfig.asn
            }];
        }
    } else if (protocol === 'ebgp') {
        protocolConfig.asn = parseInt(document.getElementById('bgp-asn')?.value || '65001');

        const networksStr = document.getElementById('bgp-network')?.value || '';
        if (networksStr.trim()) {
            protocolConfig.nets = networksStr.split(',').map(n => n.trim()).filter(n => n);
        } else {
            protocolConfig.nets = [];
        }

        const peerIp = document.getElementById('bgp-peer-ip')?.value?.trim();
        const peerAsn = document.getElementById('bgp-peer-asn')?.value;
        if (peerIp && peerAsn) {
            protocolConfig.peers = [{
                ip: peerIp,
                asn: parseInt(peerAsn)
            }];
        }
        const loopbackIp = document.getElementById('bgp-loopback')?.value?.trim();
        if (loopbackIp) {
            protocolConfig.loopback_ip = loopbackIp;
        }
    } else if (protocol === 'isis') {
        // IS-IS protocol config
        const systemId = document.getElementById('isis-system-id')?.value?.trim();
        if (systemId) {
            protocolConfig.system_id = systemId;
        }
        protocolConfig.area = document.getElementById('isis-area')?.value || '49.0001';
        protocolConfig.level = parseInt(document.getElementById('isis-level')?.value || '3');
        const isisInterface = document.getElementById('isis-interface')?.value;
        if (isisInterface) {
            protocolConfig.interface = isisInterface;
        }
        protocolConfig.metric = parseInt(document.getElementById('isis-metric')?.value || '10');
    } else if (protocol === 'mpls') {
        // MPLS/LDP protocol config
        const mplsRouterId = document.getElementById('mpls-router-id')?.value?.trim();
        if (mplsRouterId) {
            protocolConfig.mpls_router_id = mplsRouterId;
        }
        const ldpInterfaces = document.getElementById('ldp-interfaces')?.value || '';
        if (ldpInterfaces.trim()) {
            protocolConfig.ldp_interfaces = ldpInterfaces.split(',').map(i => i.trim()).filter(i => i);
        }
        const ldpNeighbors = document.getElementById('ldp-neighbors')?.value || '';
        if (ldpNeighbors.trim()) {
            protocolConfig.ldp_neighbors = ldpNeighbors.split(',').map(n => n.trim()).filter(n => n);
        }
        protocolConfig.label_range_start = parseInt(document.getElementById('label-range-start')?.value || '16');
        protocolConfig.label_range_end = parseInt(document.getElementById('label-range-end')?.value || '1048575');
    } else if (protocol === 'vxlan') {
        // VXLAN protocol config
        const vtepIp = document.getElementById('vtep-ip')?.value?.trim();
        if (vtepIp) {
            protocolConfig.vtep_ip = vtepIp;
        }
        const vnis = document.getElementById('vxlan-vnis')?.value || '';
        if (vnis.trim()) {
            protocolConfig.vnis = vnis.split(',').map(v => parseInt(v.trim())).filter(v => !isNaN(v));
        }
        const remoteVteps = document.getElementById('vxlan-remote-vteps')?.value || '';
        if (remoteVteps.trim()) {
            protocolConfig.remote_vteps = remoteVteps.split(',').map(v => v.trim()).filter(v => v);
        }
        protocolConfig.udp_port = parseInt(document.getElementById('vxlan-udp-port')?.value || '4789');
    } else if (protocol === 'evpn') {
        // EVPN protocol config
        protocolConfig.rd = document.getElementById('evpn-rd')?.value?.trim() || '';
        const rtImport = document.getElementById('evpn-rt-import')?.value || '';
        if (rtImport.trim()) {
            protocolConfig.rt_import = rtImport.split(',').map(r => r.trim()).filter(r => r);
        }
        const rtExport = document.getElementById('evpn-rt-export')?.value || '';
        if (rtExport.trim()) {
            protocolConfig.rt_export = rtExport.split(',').map(r => r.trim()).filter(r => r);
        }
        const evpnVnis = document.getElementById('evpn-vnis')?.value || '';
        if (evpnVnis.trim()) {
            protocolConfig.vnis = evpnVnis.split(',').map(v => parseInt(v.trim())).filter(v => !isNaN(v));
        }
        protocolConfig.evpn_type = document.getElementById('evpn-type')?.value || 'vlan-based';
    } else if (protocol === 'dhcp') {
        // DHCP server config
        protocolConfig.pool_name = document.getElementById('dhcp-pool-name')?.value?.trim() || 'default';
        protocolConfig.pool_start = document.getElementById('dhcp-pool-start')?.value?.trim() || '';
        protocolConfig.pool_end = document.getElementById('dhcp-pool-end')?.value?.trim() || '';
        protocolConfig.gateway = document.getElementById('dhcp-gateway')?.value?.trim() || '';
        const dnsServers = document.getElementById('dhcp-dns')?.value || '';
        if (dnsServers.trim()) {
            protocolConfig.dns_servers = dnsServers.split(',').map(d => d.trim()).filter(d => d);
        }
        protocolConfig.lease_time = parseInt(document.getElementById('dhcp-lease-time')?.value || '86400');
        const domain = document.getElementById('dhcp-domain')?.value?.trim();
        if (domain) {
            protocolConfig.domain = domain;
        }
    } else if (protocol === 'dns') {
        // DNS server config
        protocolConfig.zone = document.getElementById('dns-zone')?.value?.trim() || '';
        const recordsText = document.getElementById('dns-records')?.value || '';
        if (recordsText.trim()) {
            // Parse DNS records from text format
            protocolConfig.records = recordsText.split('\n')
                .map(line => line.trim())
                .filter(line => line)
                .map(line => {
                    const parts = line.split(/\s+/);
                    if (parts.length >= 3) {
                        return {
                            name: parts[0],
                            type: parts[1].toUpperCase(),
                            value: parts.slice(2).join(' ')
                        };
                    }
                    return null;
                })
                .filter(r => r !== null);
        }
        const forwarders = document.getElementById('dns-forwarders')?.value || '';
        if (forwarders.trim()) {
            protocolConfig.forwarders = forwarders.split(',').map(f => f.trim()).filter(f => f);
        }
        protocolConfig.port = parseInt(document.getElementById('dns-listen-port')?.value || '53');
        protocolConfig.recursion = document.getElementById('dns-recursion')?.checked ?? true;
    } else if (protocol === 'ntp') {
        // NTP server/client config
        protocolConfig.mode = document.getElementById('ntp-mode')?.value || 'client';
        const ntpServers = document.getElementById('ntp-servers')?.value || '';
        if (ntpServers.trim()) {
            protocolConfig.servers = ntpServers.split(',').map(s => s.trim()).filter(s => s);
        }
        protocolConfig.stratum = parseInt(document.getElementById('ntp-stratum')?.value || '2');
        protocolConfig.interface = document.getElementById('ntp-interface')?.value?.trim() || 'eth0';
        protocolConfig.broadcast = document.getElementById('ntp-broadcast')?.checked ?? false;
    } else if (protocol === 'ptp') {
        // PTP (Precision Time Protocol) config
        protocolConfig.mode = document.getElementById('ptp-mode')?.value || 'slave';
        protocolConfig.domain = parseInt(document.getElementById('ptp-domain')?.value || '0');
        protocolConfig.profile = document.getElementById('ptp-profile')?.value || 'default';
        protocolConfig.transport = document.getElementById('ptp-transport')?.value || 'udp-ipv4';
        protocolConfig.interface = document.getElementById('ptp-interface')?.value?.trim() || 'eth0';
        protocolConfig.priority1 = parseInt(document.getElementById('ptp-priority1')?.value || '128');
        protocolConfig.delay_mechanism = document.getElementById('ptp-delay-mechanism')?.checked ? 'e2e' : 'p2p';
    }

    // Check if this protocol type already exists
    const existingIndex = currentAgentProtocols.findIndex(p => p.p === protocol);
    if (existingIndex >= 0) {
        // Replace existing
        currentAgentProtocols[existingIndex] = protocolConfig;
        showAlert(`Updated ${protocol.toUpperCase()} configuration`, 'info');
    } else {
        currentAgentProtocols.push(protocolConfig);
        showAlert(`Added ${protocol.toUpperCase()} protocol`, 'success');
    }

    renderConfiguredProtocols();
    hideAddProtocolForm();
}

function removeProtocolFromAgent(index) {
    currentAgentProtocols.splice(index, 1);
    renderConfiguredProtocols();
}

function renderConfiguredProtocols() {
    const container = document.getElementById('configured-protocols');

    if (currentAgentProtocols.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No protocols configured. Add at least one protocol.</div>';
        return;
    }

    container.innerHTML = currentAgentProtocols.map((proto, index) => {
        let details = '';
        if (proto.p === 'ospf' || proto.p === 'ospfv3') {
            details = `Area: ${proto.a || '0.0.0.0'}`;
        } else if (proto.p === 'ibgp' || proto.p === 'ebgp') {
            details = `AS: ${proto.asn}`;
            if (proto.peers && proto.peers.length > 0) {
                details += `, Peer: ${proto.peers[0].ip} (AS ${proto.peers[0].asn})`;
            }
            if (proto.nets && proto.nets.length > 0) {
                details += `, Networks: ${proto.nets.length}`;
            }
        } else if (proto.p === 'isis') {
            details = `Area: ${proto.area || '49.0001'}, Level: ${proto.level === 3 ? '1-2' : proto.level}`;
            if (proto.system_id) {
                details += `, SysID: ${proto.system_id}`;
            }
        } else if (proto.p === 'mpls') {
            details = 'MPLS/LDP';
            if (proto.ldp_interfaces && proto.ldp_interfaces.length > 0) {
                details += `, Interfaces: ${proto.ldp_interfaces.join(', ')}`;
            }
            if (proto.ldp_neighbors && proto.ldp_neighbors.length > 0) {
                details += `, Neighbors: ${proto.ldp_neighbors.length}`;
            }
        } else if (proto.p === 'vxlan') {
            details = 'VXLAN';
            if (proto.vtep_ip) {
                details += `, VTEP: ${proto.vtep_ip}`;
            }
            if (proto.vnis && proto.vnis.length > 0) {
                details += `, VNIs: ${proto.vnis.join(', ')}`;
            }
        } else if (proto.p === 'evpn') {
            details = 'EVPN';
            if (proto.rd) {
                details += `, RD: ${proto.rd}`;
            }
            if (proto.vnis && proto.vnis.length > 0) {
                details += `, VNIs: ${proto.vnis.length}`;
            }
        } else if (proto.p === 'dhcp') {
            details = `Pool: ${proto.pool_name || 'default'}`;
            if (proto.pool_start && proto.pool_end) {
                details += `, Range: ${proto.pool_start} - ${proto.pool_end}`;
            }
        } else if (proto.p === 'dns') {
            details = 'DNS Server';
            if (proto.zone) {
                details += `, Zone: ${proto.zone}`;
            }
            if (proto.records && proto.records.length > 0) {
                details += `, Records: ${proto.records.length}`;
            }
        } else if (proto.p === 'ntp') {
            details = `NTP ${proto.mode || 'client'}`;
            if (proto.stratum) {
                details += `, Stratum: ${proto.stratum}`;
            }
            if (proto.servers && proto.servers.length > 0) {
                details += `, Servers: ${proto.servers.length}`;
            }
        } else if (proto.p === 'ptp') {
            details = `PTP ${proto.mode || 'slave'}`;
            if (proto.profile) {
                details += `, Profile: ${proto.profile}`;
            }
            if (proto.domain !== undefined) {
                details += `, Domain: ${proto.domain}`;
            }
        }

        return `
            <div class="agent-item" style="margin-bottom: 10px;">
                <div class="agent-info">
                    <h4 style="color: #00d9ff;">${proto.p.toUpperCase()}</h4>
                    <span>${details}</span>
                </div>
                <div class="agent-actions">
                    <button class="btn btn-danger" onclick="removeProtocolFromAgent(${index})" style="padding: 5px 10px;">Remove</button>
                </div>
            </div>
        `;
    }).join('');
}

function clearAgentProtocols() {
    currentAgentProtocols = [];
    renderConfiguredProtocols();
}

// Multi-interface management functions

function showAddInterfaceForm() {
    document.getElementById('add-interface-form').style.display = 'block';
    updateInterfaceName();
}

function hideAddInterfaceForm() {
    document.getElementById('add-interface-form').style.display = 'none';
    // Clear form
    document.getElementById('if-address').value = '';
    document.getElementById('if-mtu').value = '1500';
    document.getElementById('if-description').value = '';
}

function updateInterfaceName() {
    const ifType = document.getElementById('if-type').value;
    const subParentGroup = document.getElementById('sub-interface-parent-group');
    const subVlanGroup = document.getElementById('sub-interface-vlan-group');

    if (ifType === 'sub') {
        // Show sub-interface configuration
        subParentGroup.style.display = 'block';
        subVlanGroup.style.display = 'block';

        // Populate parent interface dropdown with available interfaces
        const parentSelect = document.getElementById('sub-parent');
        parentSelect.innerHTML = '<option value="eth0">eth0 (default)</option>';

        // Add configured ethernet interfaces
        currentAgentInterfaces.forEach(iface => {
            if (iface.t === 'eth') {
                parentSelect.innerHTML += `<option value="${iface.n}">${iface.n}</option>`;
            }
        });

        // Generate sub-interface name
        updateSubInterfaceName();
    } else {
        // Hide sub-interface configuration
        subParentGroup.style.display = 'none';
        subVlanGroup.style.display = 'none';

        // Generate normal interface name
        const counter = interfaceCounters[ifType];
        document.getElementById('if-name').value = `${ifType}${counter}`;
    }
}

function updateSubInterfaceName() {
    const parent = document.getElementById('sub-parent').value;
    const vlanId = document.getElementById('sub-vlan').value || '100';
    document.getElementById('if-name').value = `${parent}.${vlanId}`;
}

function addInterfaceToAgent() {
    const ifType = document.getElementById('if-type').value;
    const ifName = document.getElementById('if-name').value;
    const ifAddress = document.getElementById('if-address').value.trim();
    const ifMtu = parseInt(document.getElementById('if-mtu').value) || 1500;
    const ifDescription = document.getElementById('if-description').value.trim();

    // Build interface config
    const interfaceConfig = {
        id: ifName,
        n: ifName,
        t: ifType,
        a: ifAddress ? [ifAddress] : [],
        s: 'up',
        mtu: ifMtu
    };

    if (ifDescription) {
        interfaceConfig.description = ifDescription;
    }

    // Handle sub-interface specific fields
    if (ifType === 'sub') {
        const parentIf = document.getElementById('sub-parent').value;
        const vlanId = parseInt(document.getElementById('sub-vlan').value) || 100;
        interfaceConfig.parent = parentIf;
        interfaceConfig.vlan_id = vlanId;
        // Don't increment counter for sub-interfaces since name is based on parent.vlan
    } else {
        // Increment counter for this type
        interfaceCounters[ifType]++;
    }

    // Add to list
    currentAgentInterfaces.push(interfaceConfig);

    renderConfiguredInterfaces();
    hideAddInterfaceForm();
    showAlert(`Added interface ${ifName}`, 'success');
}

function removeInterfaceFromAgent(index) {
    currentAgentInterfaces.splice(index, 1);
    renderConfiguredInterfaces();
}

function renderConfiguredInterfaces() {
    const container = document.getElementById('configured-interfaces');

    if (currentAgentInterfaces.length === 0) {
        container.innerHTML = '<div class="alert alert-info">Default interfaces (eth0, lo0) will be created automatically. Add more if needed.</div>';
        return;
    }

    container.innerHTML = `
        <div class="alert alert-info" style="margin-bottom: 10px;">
            Default interfaces (eth0, lo0) + ${currentAgentInterfaces.length} additional interface(s)
        </div>
        ${currentAgentInterfaces.map((iface, index) => {
            const addressDisplay = iface.a && iface.a.length > 0 ? iface.a.join(', ') : 'No IP';
            let typeDisplay = iface.t;
            if (iface.t === 'sub') {
                typeDisplay = `sub-if (parent: ${iface.parent}, VLAN: ${iface.vlan_id})`;
            }
            return `
                <div class="agent-item" style="margin-bottom: 10px;">
                    <div class="agent-info">
                        <h4 style="color: #00d9ff;">${iface.n}</h4>
                        <span>Type: ${typeDisplay} | IP: ${addressDisplay} | MTU: ${iface.mtu}${iface.description ? ' | ' + iface.description : ''}</span>
                    </div>
                    <div class="agent-actions">
                        <button class="btn btn-danger" onclick="removeInterfaceFromAgent(${index})" style="padding: 5px 10px;">Remove</button>
                    </div>
                </div>
            `;
        }).join('')}
    `;
}

function clearAgentInterfaces() {
    currentAgentInterfaces = [];
    // Reset counters (keeping eth0 and lo0 as defaults)
    interfaceCounters = { eth: 1, lo: 1, vlan: 0, tun: 0 };
    renderConfiguredInterfaces();
}

async function addAgent() {
    const id = document.getElementById('agent-id').value.trim();
    const name = document.getElementById('agent-name').value.trim();
    const routerId = document.getElementById('router-id').value.trim();

    if (!id || !name || !routerId) {
        showAlert('Please fill in all required fields', 'error');
        return;
    }

    // Check for duplicate
    if (wizardState.agents.find(a => a.id === id)) {
        showAlert('Agent ID already exists', 'error');
        return;
    }

    // Check that at least one protocol is configured
    if (currentAgentProtocols.length === 0) {
        showAlert('Please add at least one protocol to the agent', 'error');
        return;
    }

    // Build default interfaces (eth0 + lo0)
    // Check if any protocol has a loopback_ip configured
    const loopbackIps = [`${routerId}/32`];  // Router ID always on loopback
    for (const proto of currentAgentProtocols) {
        if (proto.loopback_ip) {
            // Add loopback IP with /32 if not already specified
            const loopIp = proto.loopback_ip.includes('/') ? proto.loopback_ip : `${proto.loopback_ip}/32`;
            if (!loopbackIps.includes(loopIp)) {
                loopbackIps.push(loopIp);
            }
        }
    }

    const defaultInterfaces = [
        { id: 'eth0', n: 'eth0', t: 'eth', a: [], s: 'up', mtu: 1500 },
        { id: 'lo0', n: 'lo0', t: 'lo', a: loopbackIps, s: 'up', mtu: 65535 }
    ];

    // Combine default + additional interfaces
    const allInterfaces = [...defaultInterfaces, ...currentAgentInterfaces.map(i => ({ ...i }))];

    // Build agent with multiple protocols
    const agent = {
        id,
        name,
        router_id: routerId,
        protocols: currentAgentProtocols.map(p => ({ ...p })),  // Copy the protocols array
        // For backwards compatibility, set primary protocol
        protocol: currentAgentProtocols[0].p,
        interfaces: allInterfaces,
        protocol_config: currentAgentProtocols[0]  // Primary protocol config
    };

    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/step3/agent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(agent)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        wizardState.agents.push(agent);
        renderAgentList();
        clearAgentForm();
        updateLinkAgentSelects();

    } catch (error) {
        showAlert(`Failed to add agent: ${error.message}`, 'error');
    }
}

async function addAgentFromTemplate() {
    const templateId = document.getElementById('template-select').value;
    const newId = document.getElementById('template-new-id').value.trim();
    const newName = document.getElementById('template-new-name').value.trim();

    if (!templateId || !newId) {
        showAlert('Please select a template and provide a new ID', 'error');
        return;
    }

    try {
        const params = new URLSearchParams({
            template_id: templateId,
            new_id: newId,
            ...(newName && { new_name: newName })
        });

        const response = await fetch(
            `/api/wizard/session/${sessionId}/step3/from-template?${params}`,
            { method: 'POST' }
        );

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        const data = await response.json();
        wizardState.agents.push(data.agent);
        renderAgentList();
        updateLinkAgentSelects();

    } catch (error) {
        showAlert(`Failed to add agent from template: ${error.message}`, 'error');
    }
}

function clearAgentForm() {
    document.getElementById('agent-id').value = '';
    document.getElementById('agent-name').value = '';
    document.getElementById('router-id').value = '';
    clearAgentProtocols();
    clearAgentInterfaces();
    hideAddProtocolForm();
    hideAddInterfaceForm();
}

// Natural Language Agent Configuration
let nlConvertedAgent = null;

async function convertNLToAgent() {
    const description = document.getElementById('nl-description').value.trim();
    const agentId = document.getElementById('nl-agent-id').value.trim();
    const agentName = document.getElementById('nl-agent-name').value.trim();
    const statusDiv = document.getElementById('nl-status');
    const convertBtn = document.getElementById('nl-convert-btn');

    if (!description) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter an agent description</div>';
        return;
    }

    if (!agentId) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter an Agent ID</div>';
        return;
    }

    // Check for duplicate ID
    if (wizardState.agents.find(a => a.id === agentId)) {
        statusDiv.innerHTML = '<div class="alert alert-error">Agent ID already exists</div>';
        return;
    }

    convertBtn.disabled = true;
    convertBtn.textContent = 'Converting...';
    statusDiv.innerHTML = '<div class="alert alert-info">Analyzing description with LLM...</div>';

    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/nl-to-agent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                description,
                agent_id: agentId,
                agent_name: agentName || null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Conversion failed');
        }

        const data = await response.json();
        nlConvertedAgent = data.agent;

        // Show preview
        statusDiv.innerHTML = '<div class="alert alert-success">Conversion successful! Review the configuration below.</div>';
        document.getElementById('nl-preview').style.display = 'block';
        document.getElementById('nl-preview-content').textContent = JSON.stringify(nlConvertedAgent, null, 2);

    } catch (error) {
        statusDiv.innerHTML = `<div class="alert alert-error">Conversion failed: ${error.message}</div>`;
        document.getElementById('nl-preview').style.display = 'none';
    } finally {
        convertBtn.disabled = false;
        convertBtn.textContent = 'Convert to Agent';
    }
}

async function addNLAgent() {
    if (!nlConvertedAgent) {
        showAlert('No converted agent to add', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/step3/agent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(nlConvertedAgent)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        wizardState.agents.push(nlConvertedAgent);
        renderAgentList();
        updateLinkAgentSelects();
        clearNLForm();
        showAlert('Agent added successfully!', 'success');

    } catch (error) {
        showAlert(`Failed to add agent: ${error.message}`, 'error');
    }
}

function clearNLPreview() {
    document.getElementById('nl-preview').style.display = 'none';
    nlConvertedAgent = null;
}

function clearNLForm() {
    document.getElementById('nl-description').value = '';
    document.getElementById('nl-agent-id').value = '';
    document.getElementById('nl-agent-name').value = '';
    document.getElementById('nl-status').innerHTML = '';
    clearNLPreview();
}

function removeAgent(agentId) {
    wizardState.agents = wizardState.agents.filter(a => a.id !== agentId);
    renderAgentList();
    updateLinkAgentSelects();

    // Remove links involving this agent
    wizardState.topology.links = wizardState.topology.links.filter(
        l => l.agent1_id !== agentId && l.agent2_id !== agentId
    );
    renderLinkList();
}

// Bulk Import Functions

let bulkAgentsParsed = [];

function bulkImportAgents() {
    let jsonText = document.getElementById('bulk-agents-json').value.trim();
    const statusSpan = document.getElementById('bulk-import-status');

    if (!jsonText) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Please paste agent JSON</span>';
        return;
    }

    let agents;
    try {
        // Try to parse as-is first (could be an array)
        const parsed = JSON.parse(jsonText);

        // If it's an array, use it directly
        if (Array.isArray(parsed)) {
            agents = parsed;
        } else if (parsed.id || parsed.n) {
            // Single agent object
            agents = [parsed];
        } else if (parsed.agents && Array.isArray(parsed.agents)) {
            // Network template format - extract agents
            agents = parsed.agents;
        } else {
            throw new Error('Unrecognized format');
        }
    } catch (e) {
        // Try to fix common issue: multiple objects without array wrapper
        // Pattern: {...}, {...}, {...} or {...}\n{...}\n{...}
        try {
            // Look for pattern of consecutive objects: },{ or }\n{ or }\r\n{
            if (jsonText.match(/\}\s*,?\s*\{/)) {
                // Wrap in array brackets and ensure commas between objects
                const fixed = '[' + jsonText.replace(/\}\s*,?\s*\{/g, '},{') + ']';
                const parsed = JSON.parse(fixed);
                if (Array.isArray(parsed)) {
                    agents = parsed;
                    statusSpan.innerHTML = '<span style="color: #f59e0b;">Auto-wrapped objects in array format</span>';
                }
            }
        } catch (e2) {
            // Still failed
        }

        if (!agents) {
            statusSpan.innerHTML = `<span style="color: #ef4444;">Invalid JSON: ${e.message}<br><br>Tip: Wrap multiple objects in [ ] brackets</span>`;
            return;
        }
    }

    if (agents.length === 0) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">No agents found in JSON</span>';
        return;
    }

    // Validate agents
    const validationErrors = [];
    const seenIds = new Set(wizardState.agents.map(a => a.id));

    agents.forEach((agent, idx) => {
        if (!agent.id && !agent.n) {
            validationErrors.push(`Agent ${idx + 1}: Missing id and name`);
            return;
        }

        // Normalize to internal format
        const id = agent.id || agent.n.toLowerCase().replace(/\s+/g, '-');
        if (seenIds.has(id)) {
            validationErrors.push(`Agent ${idx + 1}: ID '${id}' already exists`);
            return;
        }
        seenIds.add(id);

        // Router ID is required
        if (!agent.r && !agent.router_id) {
            validationErrors.push(`Agent ${idx + 1} (${id}): Missing router ID`);
        }
    });

    if (validationErrors.length > 0) {
        statusSpan.innerHTML = `<span style="color: #ef4444;">Validation errors:<br>${validationErrors.join('<br>')}</span>`;
        return;
    }

    // Store parsed agents for confirmation
    bulkAgentsParsed = agents;

    // Show preview
    document.getElementById('bulk-count').textContent = agents.length;
    document.getElementById('bulk-preview-list').innerHTML = agents.map(agent => {
        const id = agent.id || agent.n.toLowerCase().replace(/\s+/g, '-');
        const name = agent.n || agent.name || id;
        const routerId = agent.r || agent.router_id;
        const protocols = agent.protos || agent.protocols || [];
        const protoDisplay = protocols.length > 0
            ? protocols.map(p => (p.p || p.protocol || '').toUpperCase()).join(' + ')
            : 'None';

        return `
            <div class="agent-item" style="margin-bottom: 8px;">
                <div class="agent-info">
                    <h4>${name}</h4>
                    <span>ID: ${id} | Router ID: ${routerId} | Protocols: ${protoDisplay}</span>
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('bulk-import-preview').style.display = 'block';
    statusSpan.innerHTML = `<span style="color: #4ade80;">Found ${agents.length} valid agents. Review and confirm.</span>`;
}

async function confirmBulkImport() {
    if (bulkAgentsParsed.length === 0) {
        showAlert('No agents to import', 'error');
        return;
    }

    let addedCount = 0;

    for (const agent of bulkAgentsParsed) {
        // Normalize TOON format to internal format
        const normalizedAgent = {
            id: agent.id || agent.n.toLowerCase().replace(/\s+/g, '-'),
            name: agent.n || agent.name || agent.id,
            router_id: agent.r || agent.router_id,
            protocols: (agent.protos || agent.protocols || []).map(p => ({
                p: p.p || p.protocol,
                r: p.r || p.router_id || agent.r || agent.router_id,
                a: p.a || p.area,
                asn: p.asn,
                nets: p.nets || p.networks,
                peers: p.peers,
                loopback_ip: p.loopback_ip  // Preserve loopback IP for lo0 interface
            })),
            interfaces: (agent.ifs || agent.interfaces || []).map(iface => ({
                id: iface.id || iface.n,
                n: iface.n || iface.id,
                t: iface.t || iface.type || 'eth',
                a: iface.a || iface.addresses || [],
                s: iface.s || iface.status || 'up',
                mtu: iface.mtu || 1500,
                l1: iface.l1  // Preserve L1 link info
            }))
        };

        // Set primary protocol for backwards compatibility
        if (normalizedAgent.protocols.length > 0) {
            normalizedAgent.protocol = normalizedAgent.protocols[0].p;
            normalizedAgent.protocol_config = normalizedAgent.protocols[0];
        }

        // Collect loopback IPs from protocols
        const loopbackIps = [`${normalizedAgent.router_id}/32`];  // Router ID always on loopback
        for (const proto of normalizedAgent.protocols) {
            if (proto.loopback_ip) {
                const loopIp = proto.loopback_ip.includes('/') ? proto.loopback_ip : `${proto.loopback_ip}/32`;
                if (!loopbackIps.includes(loopIp)) {
                    loopbackIps.push(loopIp);
                }
            }
        }

        // Add default interfaces if none specified
        if (normalizedAgent.interfaces.length === 0) {
            normalizedAgent.interfaces = [
                { id: 'eth0', n: 'eth0', t: 'eth', a: [], s: 'up', mtu: 1500 },
                { id: 'lo0', n: 'lo0', t: 'lo', a: loopbackIps, s: 'up', mtu: 65535 }
            ];
        } else {
            // Update existing lo0 interface with loopback IPs from protocols
            const lo0 = normalizedAgent.interfaces.find(iface => iface.id === 'lo0' || iface.n === 'lo0');
            if (lo0) {
                // Merge loopback IPs, avoiding duplicates
                for (const loopIp of loopbackIps) {
                    if (!lo0.a.includes(loopIp)) {
                        lo0.a.push(loopIp);
                    }
                }
            }
        }

        try {
            const response = await fetch(`/api/wizard/session/${sessionId}/step3/agent`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(normalizedAgent)
            });

            if (response.ok) {
                wizardState.agents.push(normalizedAgent);
                addedCount++;
            }
        } catch (error) {
            console.error(`Failed to add agent ${normalizedAgent.id}:`, error);
        }
    }

    renderAgentList();
    updateLinkAgentSelects();
    cancelBulkImport();
    showAlert(`Imported ${addedCount} of ${bulkAgentsParsed.length} agents`, 'success');
}

function cancelBulkImport() {
    bulkAgentsParsed = [];
    document.getElementById('bulk-import-preview').style.display = 'none';
    document.getElementById('bulk-import-status').innerHTML = '';
}

// File Import Functions

function loadAgentFile(input) {
    const file = input.files[0];
    if (!file) return;

    document.getElementById('bulk-file-name').textContent = file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('bulk-agents-json').value = e.target.result;
        document.getElementById('bulk-import-status').innerHTML = '<span style="color: #4ade80;">File loaded</span>';
    };
    reader.onerror = () => {
        document.getElementById('bulk-import-status').innerHTML = '<span style="color: #ef4444;">Failed to read file</span>';
    };
    reader.readAsText(file);
}

function loadTopologyFile(input) {
    const file = input.files[0];
    if (!file) return;

    document.getElementById('topology-file-name').textContent = file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('import-topology-json').value = e.target.result;
        document.getElementById('topology-import-status').innerHTML = '<span style="color: #4ade80;">File loaded</span>';
    };
    reader.onerror = () => {
        document.getElementById('topology-import-status').innerHTML = '<span style="color: #ef4444;">Failed to read file</span>';
    };
    reader.readAsText(file);
}

function renderAgentList() {
    const list = document.getElementById('agent-list');
    const count = document.getElementById('agent-count');

    count.textContent = wizardState.agents.length;

    if (wizardState.agents.length === 0) {
        list.innerHTML = '<div class="alert alert-info">No agents configured yet. Add at least one agent to continue.</div>';
        document.getElementById('step3-next').disabled = true;
        return;
    }

    document.getElementById('step3-next').disabled = false;

    list.innerHTML = wizardState.agents.map(agent => {
        // Handle both old single-protocol and new multi-protocol format
        let protocolsDisplay = '';
        if (agent.protocols && agent.protocols.length > 0) {
            protocolsDisplay = agent.protocols.map(p => p.p.toUpperCase()).join(' + ');
        } else {
            protocolsDisplay = agent.protocol ? agent.protocol.toUpperCase() : 'None';
        }

        // Count interfaces
        const ifCount = agent.interfaces ? agent.interfaces.length : 2;

        return `
            <div class="agent-item">
                <div class="agent-info">
                    <h4>${agent.name}</h4>
                    <span>ID: ${agent.id} | Router ID: ${agent.router_id} | Protocols: ${protocolsDisplay} | Interfaces: ${ifCount}</span>
                </div>
                <div class="agent-actions">
                    <button class="btn btn-danger" onclick="removeAgent('${agent.id}')">Remove</button>
                </div>
            </div>
        `;
    }).join('');
}

// Topology & Links

function toggleAutoGenerate() {
    wizardState.topology.auto_generate = document.getElementById('auto-generate').checked;
    document.getElementById('manual-links').style.display = wizardState.topology.auto_generate ? 'none' : 'block';
}

function updateLinkAgentSelects() {
    const select1 = document.getElementById('link-agent1');
    const select2 = document.getElementById('link-agent2');

    const options = wizardState.agents.map(a => `<option value="${a.id}">${a.name} (${a.id})</option>`).join('');

    select1.innerHTML = options;
    select2.innerHTML = options;

    // Also populate interface selects for the first agents
    if (wizardState.agents.length > 0) {
        updateInterfaceSelect('link-agent1', 'link-if1');
        updateInterfaceSelect('link-agent2', 'link-if2');
    }
}

function updateInterfaceSelect(agentSelectId, interfaceSelectId) {
    const agentSelect = document.getElementById(agentSelectId);
    const interfaceSelect = document.getElementById(interfaceSelectId);

    if (!agentSelect || !interfaceSelect) return;

    const agentId = agentSelect.value;
    const agent = wizardState.agents.find(a => a.id === agentId);

    if (!agent) {
        interfaceSelect.innerHTML = '<option value="eth0">eth0 (default)</option>';
        return;
    }

    // Get all interfaces for this agent
    const interfaces = agent.interfaces || [];

    // Build interface options
    let options = '';

    // Always include default interfaces (eth0, lo0) at minimum
    const hasEth0 = interfaces.some(i => i.n === 'eth0' || i.id === 'eth0');
    const hasLo0 = interfaces.some(i => i.n === 'lo0' || i.id === 'lo0');

    if (!hasEth0) {
        options += '<option value="eth0">eth0 (default)</option>';
    }

    // Add all configured interfaces
    interfaces.forEach(iface => {
        const ifName = iface.n || iface.id;
        const ifType = iface.t || 'eth';
        const addresses = iface.a && iface.a.length > 0 ? ` - ${iface.a[0]}` : '';
        const desc = iface.description ? ` (${iface.description})` : '';

        // Skip loopback interfaces for link connections
        if (ifType === 'lo') return;

        options += `<option value="${ifName}">${ifName}${addresses}${desc}</option>`;
    });

    // If no non-loopback interfaces, add default eth0
    if (!options) {
        options = '<option value="eth0">eth0 (default)</option>';
    }

    interfaceSelect.innerHTML = options;
}

function addLink() {
    const agent1 = document.getElementById('link-agent1').value;
    const if1 = document.getElementById('link-if1').value;
    const agent2 = document.getElementById('link-agent2').value;
    const if2 = document.getElementById('link-if2').value;
    const cost = parseInt(document.getElementById('link-cost').value) || 10;

    if (!agent1 || !agent2 || agent1 === agent2) {
        showAlert('Please select two different agents', 'error');
        return;
    }

    const linkId = `link-${wizardState.topology.links.length + 1}`;

    wizardState.topology.links.push({
        id: linkId,
        agent1_id: agent1,
        interface1: if1,
        agent2_id: agent2,
        interface2: if2,
        link_type: 'ethernet',
        cost
    });

    renderLinkList();
}

function removeLink(linkId) {
    wizardState.topology.links = wizardState.topology.links.filter(l => l.id !== linkId);
    renderLinkList();
}

function renderLinkList() {
    const list = document.getElementById('link-list');
    const count = document.getElementById('link-count');

    count.textContent = wizardState.topology.links.length;

    if (wizardState.topology.links.length === 0) {
        list.innerHTML = '<div class="alert alert-info">No links configured. Add links or enable auto-generation.</div>';
        return;
    }

    list.innerHTML = wizardState.topology.links.map(link => {
        const agent1 = wizardState.agents.find(a => a.id === link.agent1_id);
        const agent2 = wizardState.agents.find(a => a.id === link.agent2_id);
        return `
            <div class="link-item">
                <span>${agent1?.name || link.agent1_id}:${link.interface1}</span>
                <span>---</span>
                <span>${agent2?.name || link.agent2_id}:${link.interface2}</span>
                <span>(cost: ${link.cost})</span>
                <button class="btn btn-danger" onclick="removeLink('${link.id}')">X</button>
            </div>
        `;
    }).join('');
}

// Import Topology Links from JSON

function importTopologyLinks() {
    const jsonText = document.getElementById('import-topology-json').value.trim();
    const statusSpan = document.getElementById('topology-import-status');

    if (!jsonText) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Please paste topology JSON</span>';
        return;
    }

    let links;
    try {
        const parsed = JSON.parse(jsonText);

        // Handle different formats
        if (Array.isArray(parsed)) {
            // Direct array of links
            links = parsed;
        } else if (parsed.links && Array.isArray(parsed.links)) {
            // Object with links property
            links = parsed.links;
        } else if (parsed.topo && parsed.topo.links) {
            // Full network format
            links = parsed.topo.links;
        } else {
            throw new Error('No links array found');
        }
    } catch (e) {
        statusSpan.innerHTML = `<span style="color: #ef4444;">Invalid JSON: ${e.message}</span>`;
        return;
    }

    if (links.length === 0) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">No links found in JSON</span>';
        return;
    }

    // Get available agent IDs
    const agentIds = new Set(wizardState.agents.map(a => a.id));

    // Validate and normalize links
    const validationWarnings = [];
    const normalizedLinks = [];

    links.forEach((link, idx) => {
        // Normalize TOON format to internal format
        const agent1 = link.a1 || link.agent1_id || link.agent1;
        const agent2 = link.a2 || link.agent2_id || link.agent2;
        const if1 = link.i1 || link.interface1 || link.if1 || 'eth0';
        const if2 = link.i2 || link.interface2 || link.if2 || 'eth0';
        const cost = link.c || link.cost || 10;
        const linkType = link.t || link.link_type || 'ethernet';

        // Check if agents exist
        if (!agentIds.has(agent1)) {
            validationWarnings.push(`Link ${idx + 1}: Agent '${agent1}' not found`);
        }
        if (!agentIds.has(agent2)) {
            validationWarnings.push(`Link ${idx + 1}: Agent '${agent2}' not found`);
        }

        normalizedLinks.push({
            id: link.id || `link-${wizardState.topology.links.length + normalizedLinks.length + 1}`,
            agent1_id: agent1,
            interface1: if1,
            agent2_id: agent2,
            interface2: if2,
            link_type: linkType,
            cost: cost
        });
    });

    // Add all links (even if some agents are missing - they might be added later)
    wizardState.topology.links = [...wizardState.topology.links, ...normalizedLinks];
    renderLinkList();

    // Clear input
    document.getElementById('import-topology-json').value = '';

    // Show result
    if (validationWarnings.length > 0) {
        statusSpan.innerHTML = `<span style="color: #f59e0b;">Imported ${normalizedLinks.length} links with warnings:<br>${validationWarnings.slice(0, 3).join('<br>')}${validationWarnings.length > 3 ? '<br>...' : ''}</span>`;
    } else {
        statusSpan.innerHTML = `<span style="color: #4ade80;">Imported ${normalizedLinks.length} links successfully</span>`;
    }

    showAlert(`Imported ${normalizedLinks.length} topology links`, 'success');
}

// LLM Provider

function updateApiKeyPlaceholder() {
    const provider = document.getElementById('llm-provider').value;
    const input = document.getElementById('api-key');

    const placeholders = {
        'claude': 'sk-ant-...',
        'openai': 'sk-...',
        'gemini': 'AIza...'
    };

    input.placeholder = placeholders[provider] || '';
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('api-key');
    const toggleIcon = document.getElementById('api-key-toggle-icon');

    if (input.type === 'password') {
        input.type = 'text';
        toggleIcon.textContent = 'Hide';
    } else {
        input.type = 'password';
        toggleIcon.textContent = 'Show';
    }
}

async function validateApiKey() {
    const provider = document.getElementById('llm-provider').value;
    const apiKey = document.getElementById('api-key').value;
    const statusDiv = document.getElementById('api-key-status');

    if (!apiKey) {
        statusDiv.innerHTML = '<div class="alert alert-error">Please enter an API key</div>';
        return;
    }

    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/validate-api-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: apiKey })
        });

        const data = await response.json();

        if (data.valid) {
            statusDiv.innerHTML = '<div class="alert alert-success">API key format valid</div>';
        } else {
            statusDiv.innerHTML = `<div class="alert alert-error">${data.message}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div class="alert alert-error">Validation failed: ${error.message}</div>`;
    }
}

// Navigation

async function nextStep(currentStep) {
    // Validate and save current step
    switch (currentStep) {
        case 1:
            const networkName = document.getElementById('network-name').value.trim();
            if (!networkName) {
                showAlert('Please enter a network name', 'error');
                return;
            }

            wizardState.docker_config = {
                name: networkName,
                subnet: document.getElementById('subnet').value || null,
                gateway: document.getElementById('gateway').value || null,
                driver: document.getElementById('driver').value
            };

            await saveStep1();
            break;

        case 2:
            await saveStep2();
            break;

        case 3:
            if (wizardState.agents.length === 0) {
                showAlert('Please add at least one agent', 'error');
                return;
            }
            await saveStep3();
            break;

        case 4:
            // Topology step - save links
            await saveStep4();
            break;
    }

    goToStep(currentStep + 1);
}

function prevStep(currentStep) {
    goToStep(currentStep - 1);
}

function goToStep(step) {
    currentStep = step;

    // Update progress
    document.querySelectorAll('.progress-container .step').forEach((s, i) => {
        s.classList.remove('active', 'completed');
        if (i + 1 < step) s.classList.add('completed');
        if (i + 1 === step) s.classList.add('active');
    });

    // Show correct step content
    document.querySelectorAll('.wizard-step').forEach(s => s.classList.remove('active'));
    document.getElementById(`step-${step}`).classList.add('active');

    // Update preview on last step (now step 5)
    if (step === 5) {
        updatePreview();
    }
}

// Step Savers

async function saveStep1() {
    try {
        await fetch(`/api/wizard/session/${sessionId}/step1`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(wizardState.docker_config)
        });
    } catch (error) {
        console.error('Failed to save step 1:', error);
    }
}

async function saveStep2() {
    try {
        await fetch(`/api/wizard/session/${sessionId}/step2`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(wizardState.mcp_selection)
        });
    } catch (error) {
        console.error('Failed to save step 2:', error);
    }
}

async function saveStep3() {
    try {
        await fetch(`/api/wizard/session/${sessionId}/step3/complete`, { method: 'POST' });
    } catch (error) {
        console.error('Failed to save step 3:', error);
    }
}

async function saveStep4() {
    // Step 4 is now Topology
    try {
        await fetch(`/api/wizard/session/${sessionId}/step5`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(wizardState.topology)
        });
    } catch (error) {
        console.error('Failed to save step 4 (topology):', error);
    }
}

// Preview

async function updatePreview() {
    try {
        // First save LLM config
        wizardState.llm_config = {
            provider: document.getElementById('llm-provider').value,
            api_key: document.getElementById('api-key').value
        };

        await fetch(`/api/wizard/session/${sessionId}/step6`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(wizardState.llm_config)
        });

        // Get preview
        const response = await fetch(`/api/wizard/session/${sessionId}/preview`);
        const data = await response.json();

        document.getElementById('preview-agents').textContent = data.agent_count;
        document.getElementById('preview-links').textContent = data.link_count;
        document.getElementById('preview-mcps').textContent = data.mcp_count;
        document.getElementById('preview-containers').textContent = data.estimated_containers;

        document.getElementById('preview-details').innerHTML = `
            <p><strong>Network:</strong> ${data.network.n}</p>
            <p><strong>Docker Network:</strong> ${data.network.docker?.n || 'N/A'}</p>
            <p><strong>Subnet:</strong> ${data.network.docker?.subnet || 'Auto'}</p>
        `;

    } catch (error) {
        console.error('Failed to get preview:', error);
    }
}

// Save & Launch

async function saveNetwork() {
    try {
        const response = await fetch(`/api/wizard/session/${sessionId}/save`, { method: 'POST' });
        const data = await response.json();

        showAlert(`Network saved successfully! ID: ${data.network_id}`, 'success');

    } catch (error) {
        showAlert(`Failed to save network: ${error.message}`, 'error');
    }
}

async function launchNetwork() {
    const apiKey = document.getElementById('api-key').value;
    const provider = document.getElementById('llm-provider').value;

    if (!apiKey) {
        showAlert('Please enter an API key to launch the network', 'error');
        return;
    }

    const apiKeys = {};
    if (provider === 'claude') apiKeys.anthropic = apiKey;
    else if (provider === 'openai') apiKeys.openai = apiKey;
    else if (provider === 'gemini') apiKeys.google = apiKey;

    try {
        showAlert('Launching network...', 'info');

        const response = await fetch(`/api/wizard/session/${sessionId}/launch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                network_id: wizardState.docker_config.name,
                api_keys: apiKeys
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        const data = await response.json();

        if (data.status === 'running') {
            showAlert('Network launched successfully! Opening agent dashboards...', 'success');

            // Show agent details
            let details = '<h4>Agent Status:</h4><ul>';
            for (const [agentId, agent] of Object.entries(data.agents)) {
                details += `<li>${agentId}: ${agent.status} (IP: ${agent.ip_address || 'N/A'}, WebUI: ${agent.webui_port || 'N/A'})</li>`;
            }
            details += '</ul>';

            document.getElementById('preview-details').innerHTML += details;

            // Collect agents with WebUI ports
            const agentsWithWebUI = Object.entries(data.agents)
                .filter(([_, agent]) => agent.webui_port)
                .map(([agentId, agent]) => ({
                    id: agentId,
                    port: agent.webui_port,
                    url: `http://localhost:${agent.webui_port}/dashboard`
                }));

            if (agentsWithWebUI.length > 0) {
                // Wait a moment for containers to fully start
                setTimeout(async () => {
                    // Open all agents in new tabs with staggered delays to avoid popup blocking
                    // Don't redirect current page - open ALL agents in new tabs
                    for (let i = 0; i < agentsWithWebUI.length; i++) {
                        const agent = agentsWithWebUI[i];
                        // Stagger each window.open by 500ms to avoid popup blockers
                        await new Promise(resolve => setTimeout(resolve, i * 500));

                        const newWindow = window.open(agent.url, `rubberband_${agent.id}`);

                        // Check if popup was blocked
                        if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
                            console.warn(`Popup blocked for ${agent.id}. User may need to allow popups.`);
                            // Add a clickable link as fallback
                            const fallbackLink = document.createElement('div');
                            fallbackLink.innerHTML = `
                                <p style="margin-top: 10px;">
                                    <a href="${agent.url}" target="_blank" style="color: #00d9ff; text-decoration: underline;">
                                        Click here to open ${agent.id} dashboard
                                    </a>
                                </p>
                            `;
                            document.getElementById('preview-details').appendChild(fallbackLink);
                        }
                    }
                }, 2000);  // 2 second delay for containers to initialize

                details += `<p style="margin-top: 15px; color: #4ade80;">Opening ${agentsWithWebUI.length} agent dashboard(s) in new tabs...</p>`;
                details += `<p style="color: #888; font-size: 0.9rem;">If tabs don't open automatically, please allow popups for this site.</p>`;
                document.getElementById('preview-details').innerHTML = details;
            }
        } else if (data.status === 'error') {
            showAlert('Network launch failed. Check Docker availability.', 'error');
        }

    } catch (error) {
        showAlert(`Failed to launch network: ${error.message}`, 'error');
    }
}

// Utility

function showAlert(message, type) {
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.position = 'fixed';
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '1000';
    alert.style.maxWidth = '400px';

    document.body.appendChild(alert);

    // Auto remove after 5 seconds
    setTimeout(() => {
        alert.remove();
    }, 5000);
}
