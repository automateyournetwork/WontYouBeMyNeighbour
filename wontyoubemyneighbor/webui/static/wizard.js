/**
 * ASI Network Builder Wizard
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
    llm_config: { provider: 'claude', api_key: null },
    // Network Foundation (3-layer architecture)
    network_foundation: {
        underlay_protocol: 'ipv6',  // 'ipv4', 'ipv6', or 'dual'
        overlay: {
            enabled: true,
            subnet: 'fd00:a510::/48',
            enable_nd: true,
            enable_routes: true
        },
        docker_ipv6: {
            enabled: true,
            subnet: 'fd00:d0c:1::/64',
            gateway: 'fd00:d0c:1::1'
        }
    }
};

// Default MCPs
let defaultMcps = [];

// Current agent's protocols being configured
let currentAgentProtocols = [];

// Current agent's interfaces being configured
let currentAgentInterfaces = [];

// Interface counters by type
let interfaceCounters = {
    eth: 1,       // Start at 1 since eth0 is default
    lo: 1,        // Start at 1 since lo0 is default
    bond: 0,      // Bond/LACP interfaces
    vlan: 0,      // VLAN SVIs
    vxlan: 0,     // VXLAN VTEPs
    gre: 0,       // GRE tunnels
    tun: 0,       // Generic tunnels
    bridge: 0     // Bridge interfaces
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await createSession();
    await checkDocker();
    await loadDefaultMcps();
    await loadAgentTemplates();
    initializeProtocolSelection();
    initializeNetworkNameDisplay();
});

// Initialize network name display in header
function initializeNetworkNameDisplay() {
    const networkNameInput = document.getElementById('network-name');
    const networkNameBadge = document.getElementById('network-name-badge');

    if (networkNameInput && networkNameBadge) {
        // Update on input change
        networkNameInput.addEventListener('input', () => {
            updateNetworkNameBadge();
        });

        // Update on blur (when user leaves the field)
        networkNameInput.addEventListener('blur', () => {
            updateNetworkNameBadge();
        });

        // Show initial value if present
        updateNetworkNameBadge();
    }
}

// Update the network name badge in the header
function updateNetworkNameBadge() {
    const networkNameInput = document.getElementById('network-name');
    const networkNameBadge = document.getElementById('network-name-badge');

    if (networkNameInput && networkNameBadge) {
        const name = networkNameInput.value.trim();
        if (name) {
            networkNameBadge.textContent = `Network: ${name}`;
            networkNameBadge.style.display = 'inline-block';
        } else {
            networkNameBadge.style.display = 'none';
        }
    }
}

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

// Network Foundation - Underlay Protocol Selection

function selectUnderlayProtocol(protocol) {
    // Update radio button
    document.querySelectorAll('input[name="underlay-protocol"]').forEach(radio => {
        radio.checked = (radio.value === protocol);
    });

    // Update visual selection
    document.querySelectorAll('.protocol-option').forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        if (radio.value === protocol) {
            option.style.borderColor = '#00d9ff';
            option.style.background = 'rgba(0, 217, 255, 0.1)';
        } else {
            option.style.borderColor = '#2a2a4e';
            option.style.background = '#16213e';
        }
    });

    // Update wizard state
    wizardState.network_foundation.underlay_protocol = protocol;

    // Update agent protocol availability based on underlay selection
    updateAgentProtocolAvailability(protocol);

    console.log(`[Wizard] Underlay protocol set to: ${protocol}`);
}

// Update which protocols are available for agents based on underlay selection
function updateAgentProtocolAvailability(underlayProtocol) {
    // Store in global state for use in agent builder
    window.underlayProtocol = underlayProtocol;

    // Update the protocol dropdown in the agent builder if it exists
    const protocolSelect = document.getElementById('agent-protocol');
    if (protocolSelect) {
        // Get all options
        const options = protocolSelect.querySelectorAll('option');
        options.forEach(option => {
            const value = option.value;

            // OSPFv3 is IPv6 only - hide if pure IPv4 underlay
            if (value === 'ospfv3') {
                option.style.display = (underlayProtocol === 'ipv4') ? 'none' : '';
                option.disabled = (underlayProtocol === 'ipv4');
            }

            // OSPFv2 (ospf) is IPv4 only - hide if pure IPv6 underlay
            if (value === 'ospf') {
                option.style.display = (underlayProtocol === 'ipv6') ? 'none' : '';
                option.disabled = (underlayProtocol === 'ipv6');
            }
        });

        // If current selection is now invalid, switch to a valid one
        const currentValue = protocolSelect.value;
        if ((currentValue === 'ospfv3' && underlayProtocol === 'ipv4') ||
            (currentValue === 'ospf' && underlayProtocol === 'ipv6')) {
            // Switch to BGP as a safe default
            protocolSelect.value = 'ibgp';
        }
    }

    console.log(`[Wizard] Agent protocols updated for ${underlayProtocol} underlay`);
}

// Initialize protocol selection visual on page load
function initializeProtocolSelection() {
    // Set default selection (IPv6)
    selectUnderlayProtocol('ipv6');
    // Initialize Docker network fields
    updateDockerNetworkFields();
}

// Docker Network IP Version Toggle
function updateDockerNetworkFields() {
    const ipVersion = document.getElementById('docker-ip-version').value;
    const subnetInput = document.getElementById('subnet');
    const gatewayInput = document.getElementById('gateway');

    if (ipVersion === 'ipv6') {
        // IPv6 defaults
        subnetInput.value = 'fd00:d0c:1::/64';
        subnetInput.placeholder = 'e.g., fd00:d0c:1::/64';
        gatewayInput.value = 'fd00:d0c:1::1';
        gatewayInput.placeholder = 'e.g., fd00:d0c:1::1';
        wizardState.network_foundation.docker_ipv6.enabled = true;
    } else {
        // IPv4 defaults
        subnetInput.value = '172.20.0.0/16';
        subnetInput.placeholder = 'e.g., 172.20.0.0/16';
        gatewayInput.value = '172.20.0.1';
        gatewayInput.placeholder = 'e.g., 172.20.0.1';
        wizardState.network_foundation.docker_ipv6.enabled = false;
    }

    console.log(`[Wizard] Docker network IP version set to: ${ipVersion}`);
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
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        defaultMcps = await response.json();
        console.log('Loaded MCPs:', defaultMcps.length, defaultMcps.map(m => `${m.id}(${m.t})`));
        renderMcpGrid();
    } catch (error) {
        console.error('Failed to load MCPs:', error);
        // Show error in UI
        const mandatoryGrid = document.getElementById('mandatory-mcp-grid');
        const optionalGrid = document.getElementById('optional-mcp-grid');
        if (mandatoryGrid) mandatoryGrid.innerHTML = `<div class="alert alert-error">Failed to load MCPs: ${error.message}</div>`;
        if (optionalGrid) optionalGrid.innerHTML = '';
    }
}

// Current MCP being configured
let currentMcpConfig = null;

// MCP configurations (stored separately from selection)
let mcpConfigurations = {};

// Custom MCPs added by user
let customMcps = [];

// Mandatory MCP types (always included, can't be deselected)
const MANDATORY_MCP_TYPES = ['gait', 'pyats', 'rfc', 'markmap', 'prometheus', 'grafana', 'subnet'];

// Optional MCP types (can be enabled/disabled)
const OPTIONAL_MCP_TYPES = ['servicenow', 'netbox', 'slack', 'github', 'smtp'];

function renderMcpGrid() {
    console.log('renderMcpGrid called, defaultMcps:', defaultMcps.length);
    console.log('MANDATORY_MCP_TYPES:', MANDATORY_MCP_TYPES);
    console.log('OPTIONAL_MCP_TYPES:', OPTIONAL_MCP_TYPES);

    // Separate mandatory and optional MCPs
    const mandatoryMcps = defaultMcps.filter(mcp => MANDATORY_MCP_TYPES.includes(mcp.t));
    const optionalMcps = defaultMcps.filter(mcp => OPTIONAL_MCP_TYPES.includes(mcp.t));

    console.log('Mandatory MCPs found:', mandatoryMcps.length, mandatoryMcps.map(m => m.id));
    console.log('Optional MCPs found:', optionalMcps.length, optionalMcps.map(m => m.id));

    // Ensure all mandatory MCPs are in the selected list
    mandatoryMcps.forEach(mcp => {
        if (!wizardState.mcp_selection.selected.includes(mcp.id)) {
            wizardState.mcp_selection.selected.push(mcp.id);
        }
    });

    // Render mandatory MCPs (locked)
    const mandatoryGrid = document.getElementById('mandatory-mcp-grid');
    console.log('mandatory-mcp-grid element:', mandatoryGrid);
    if (mandatoryGrid) {
        if (mandatoryMcps.length === 0) {
            mandatoryGrid.innerHTML = '<div class="alert alert-info">No mandatory MCPs found in API response</div>';
        } else {
            mandatoryGrid.innerHTML = mandatoryMcps.map(mcp => {
                return `
                    <div class="mcp-card mandatory selected" data-mcp-id="${mcp.id}">
                        <h4>${mcp.n}</h4>
                        <p>${mcp.d || 'No description'}</p>
                        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #2a4a2a; text-align: center;">
                            <span style="color: #4ade80; font-size: 0.75rem;">✓ Always enabled</span>
                        </div>
                    </div>
                `;
            }).join('');
        }
    } else {
        console.error('mandatory-mcp-grid element not found!');
    }

    // Render optional MCPs (toggleable)
    const optionalGrid = document.getElementById('optional-mcp-grid');
    console.log('optional-mcp-grid element:', optionalGrid);
    if (optionalGrid) {
        if (optionalMcps.length === 0) {
            optionalGrid.innerHTML = '<div class="alert alert-info">No optional MCPs found in API response</div>';
        } else {
            optionalGrid.innerHTML = optionalMcps.map(mcp => {
            const isSelected = wizardState.mcp_selection.selected.includes(mcp.id);
            const requiresConfig = mcp.c?._requires_config;
            const hasConfig = mcpConfigurations[mcp.id] && Object.keys(mcpConfigurations[mcp.id]).length > 0;
            const configFields = mcp.c?._config_fields || [];

            return `
                <div class="mcp-card ${isSelected ? 'selected' : ''}" data-mcp-id="${mcp.id}">
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
                            <span style="color: #888; font-size: 0.75rem;">Click to ${isSelected ? 'disable' : 'enable'}</span>
                        </div>
                    `}
                </div>
            `;
            }).join('');
        }
    } else {
        console.error('optional-mcp-grid element not found!');
    }

    // Render custom MCPs list
    renderCustomMcpList();
}

function renderCustomMcpList() {
    const listDiv = document.getElementById('custom-mcp-list');
    if (!listDiv) return;

    if (customMcps.length === 0) {
        listDiv.innerHTML = '';
        return;
    }

    listDiv.innerHTML = `
        <h4 style="color: #9333ea; margin-bottom: 10px;">Added Custom MCPs (${customMcps.length})</h4>
        <div class="mcp-grid">
            ${customMcps.map((mcp, idx) => `
                <div class="mcp-card custom selected" data-mcp-id="${mcp.id}">
                    <h4>${mcp.n || mcp.id}</h4>
                    <p>${mcp.d || 'Custom MCP'}</p>
                    <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #4a2a4e;">
                        <button class="btn btn-danger" onclick="removeCustomMcp(${idx})"
                                style="padding: 5px 10px; font-size: 0.8rem; width: 100%;">
                            Remove
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function loadCustomMcpFile(input) {
    const file = input.files[0];
    if (!file) return;

    document.getElementById('custom-mcp-file-name').textContent = file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('custom-mcp-json').value = e.target.result;
    };
    reader.readAsText(file);
}

function importCustomMcp() {
    const jsonText = document.getElementById('custom-mcp-json').value.trim();
    const statusSpan = document.getElementById('custom-mcp-status');

    if (!jsonText) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Please provide MCP configuration</span>';
        return;
    }

    let mcpConfig;
    try {
        mcpConfig = JSON.parse(jsonText);
    } catch (e) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">Invalid JSON format</span>';
        return;
    }

    // Validate required fields
    if (!mcpConfig.id) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">MCP must have an "id" field</span>';
        return;
    }

    // Check for duplicate
    if (customMcps.some(m => m.id === mcpConfig.id) ||
        defaultMcps.some(m => m.id === mcpConfig.id)) {
        statusSpan.innerHTML = '<span style="color: #ef4444;">MCP with this ID already exists</span>';
        return;
    }

    // Add defaults
    mcpConfig.t = mcpConfig.t || 'custom';
    mcpConfig.n = mcpConfig.n || mcpConfig.id;
    mcpConfig.e = mcpConfig.e !== false;
    mcpConfig.c = mcpConfig.c || {};

    // Add to custom MCPs and selected list
    customMcps.push(mcpConfig);
    wizardState.mcp_selection.custom.push(mcpConfig);
    wizardState.mcp_selection.selected.push(mcpConfig.id);

    // Clear form
    document.getElementById('custom-mcp-json').value = '';
    document.getElementById('custom-mcp-file-name').textContent = '';

    statusSpan.innerHTML = `<span style="color: #4ade80;">Added "${mcpConfig.n}"</span>`;
    setTimeout(() => { statusSpan.innerHTML = ''; }, 3000);

    renderCustomMcpList();
}

function removeCustomMcp(index) {
    const mcp = customMcps[index];
    if (!mcp) return;

    // Remove from arrays
    customMcps.splice(index, 1);
    wizardState.mcp_selection.custom = wizardState.mcp_selection.custom.filter(m => m.id !== mcp.id);
    wizardState.mcp_selection.selected = wizardState.mcp_selection.selected.filter(id => id !== mcp.id);

    renderCustomMcpList();
}

function toggleMcp(mcpId) {
    const mcp = defaultMcps.find(m => m.id === mcpId);
    if (!mcp) return;

    // Prevent toggling mandatory MCPs
    if (MANDATORY_MCP_TYPES.includes(mcp.t)) {
        console.log(`Cannot toggle mandatory MCP: ${mcp.n}`);
        return;
    }

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
    if (!mcp) {
        console.error('[Wizard] MCP not found:', mcpId);
        return;
    }

    currentMcpConfig = mcp;
    const configFields = mcp.c?._config_fields || [];
    const savedConfig = mcpConfigurations[mcpId] || {};

    // Debug logging
    console.log('[Wizard] Opening config for MCP:', mcpId);
    console.log('[Wizard] MCP config object:', mcp.c);
    console.log('[Wizard] Config fields count:', configFields.length);
    console.log('[Wizard] Config fields:', configFields);

    // Set modal title and description
    document.getElementById('mcp-modal-title').textContent = `Configure ${mcp.n}`;
    document.getElementById('mcp-modal-description').textContent = mcp.d;
    document.getElementById('mcp-docs-url').href = mcp.url;

    // Build config fields
    const fieldsContainer = document.getElementById('mcp-config-fields');

    if (configFields.length === 0) {
        fieldsContainer.innerHTML = '<p style="color: #4ade80;">This MCP does not require additional configuration.</p>';
    } else {
        fieldsContainer.innerHTML = configFields.map(field => {
            // Handle separator type - visual divider with label
            if (field.type === 'separator') {
                return `
                    <div style="margin: 20px 0 15px 0; padding-top: 15px; border-top: 1px solid #2a2a4e;">
                        <h4 style="color: #00d9ff; font-size: 0.9rem; margin: 0;">${field.label || ''}</h4>
                    </div>
                `;
            }
            // Handle checkbox type
            if (field.type === 'checkbox') {
                const isChecked = savedConfig[field.id] !== undefined
                    ? savedConfig[field.id]
                    : (field.default !== undefined ? field.default : false);
                return `
                    <div class="form-group" style="margin-bottom: 15px;">
                        <label style="display: flex; align-items: center; cursor: pointer;">
                            <input type="checkbox"
                                   id="mcp-field-${field.id}"
                                   ${isChecked ? 'checked' : ''}
                                   onchange="toggleDependentFields('${field.id}')"
                                   style="width: auto; margin-right: 10px; transform: scale(1.2);">
                            <span>${field.label}</span>
                        </label>
                        ${field.hint ? `<div class="hint" style="font-size: 0.8rem; color: #666; margin-top: 4px;">${field.hint}</div>` : ''}
                    </div>
                `;
            }
            // Handle select type - dropdown menu
            if (field.type === 'select') {
                const options = field.options || [];
                const currentValue = savedConfig[field.id] || field.default || '';
                const dependsOn = field.depends_on ? `data-depends-on="${field.depends_on}"` : '';
                return `
                    <div class="form-group mcp-dependent-field" ${dependsOn} style="margin-bottom: 15px;">
                        <label for="mcp-field-${field.id}">${field.label}${field.required ? ' *' : ''}</label>
                        <select id="mcp-field-${field.id}"
                                ${field.required ? 'required' : ''}
                                style="width: 100%; padding: 10px; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px; color: #eee;">
                            ${options.map(opt => `<option value="${opt}" ${opt === currentValue ? 'selected' : ''}>${opt}</option>`).join('')}
                        </select>
                        ${field.hint ? `<div class="hint" style="font-size: 0.8rem; color: #666; margin-top: 4px;">${field.hint}</div>` : ''}
                    </div>
                `;
            }
            // Handle number type
            if (field.type === 'number') {
                const dependsOn = field.depends_on ? `data-depends-on="${field.depends_on}"` : '';
                return `
                    <div class="form-group mcp-dependent-field" ${dependsOn} style="margin-bottom: 15px;">
                        <label for="mcp-field-${field.id}">${field.label}${field.required ? ' *' : ''}</label>
                        <input type="number"
                               id="mcp-field-${field.id}"
                               placeholder="${field.placeholder || ''}"
                               value="${savedConfig[field.id] || field.placeholder || ''}"
                               ${field.required ? 'required' : ''}
                               style="width: 100%; padding: 10px; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px; color: #eee;">
                        ${field.hint ? `<div class="hint" style="font-size: 0.8rem; color: #666; margin-top: 4px;">${field.hint}</div>` : ''}
                    </div>
                `;
            }
            // Handle button type - action buttons within MCP config
            if (field.type === 'button') {
                const dependsOn = field.depends_on ? `data-depends-on="${field.depends_on}"` : '';
                const action = field.action || '';
                return `
                    <div class="form-group mcp-dependent-field" ${dependsOn} style="margin-bottom: 15px;">
                        <button type="button"
                                id="mcp-field-${field.id}"
                                onclick="${action}()"
                                class="btn btn-primary"
                                style="width: 100%; padding: 12px; font-size: 1rem;">
                            ${field.label}
                        </button>
                        ${field.hint ? `<div class="hint" style="font-size: 0.8rem; color: #666; margin-top: 4px;">${field.hint}</div>` : ''}
                    </div>
                `;
            }
            // Default: text, password, email, url types
            // Check if this is a credential field that needs emphasis
            const isCredentialField = field.type === 'password' || field.id.includes('username') || field.id.includes('email');
            const isUrlField = field.type === 'url';
            const hintStyle = isCredentialField
                ? 'font-size: 0.8rem; color: #f59e0b; margin-top: 4px; padding: 6px 8px; background: rgba(245, 158, 11, 0.1); border-radius: 4px; border-left: 3px solid #f59e0b;'
                : 'font-size: 0.8rem; color: #666; margin-top: 4px;';
            const dependsOn = field.depends_on ? `data-depends-on="${field.depends_on}"` : '';
            const defaultValue = savedConfig[field.id] || field.default || '';
            // Disable browser autofill for sensitive/URL fields to prevent wrong values
            const autocomplete = (isCredentialField || isUrlField) ? 'autocomplete="off"' : '';
            // URL fields get a special warning
            const urlWarning = isUrlField ? `<div style="font-size: 0.75rem; color: #06b6d4; margin-top: 2px;">Include https:// (e.g., https://demo.netbox.dev)</div>` : '';
            return `
                <div class="form-group mcp-dependent-field" ${dependsOn} style="margin-bottom: 15px;">
                    <label for="mcp-field-${field.id}">${field.label}${field.required ? ' *' : ''}</label>
                    <input type="${isUrlField ? 'text' : field.type}"
                           id="mcp-field-${field.id}"
                           placeholder="${field.placeholder || ''}"
                           value="${defaultValue}"
                           ${field.required ? 'required' : ''}
                           ${autocomplete}
                           style="width: 100%; padding: 10px; background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px; color: #eee;">
                    ${urlWarning}
                    ${field.hint ? `<div class="hint" style="${hintStyle}">${field.hint}</div>` : ''}
                </div>
            `;
        }).join('');

        // Initialize dependent field visibility
        initializeDependentFields();
    }

    // Show modal
    document.getElementById('mcp-config-modal').style.display = 'flex';
}

function closeMcpModal() {
    document.getElementById('mcp-config-modal').style.display = 'none';
    currentMcpConfig = null;
}

// Toggle visibility of fields that depend on a checkbox
function toggleDependentFields(checkboxId) {
    const checkbox = document.getElementById(`mcp-field-${checkboxId}`);
    if (!checkbox) return;

    const isChecked = checkbox.checked;
    const dependentFields = document.querySelectorAll(`[data-depends-on="${checkboxId}"]`);

    dependentFields.forEach(field => {
        if (isChecked) {
            field.style.display = 'block';
            field.style.opacity = '1';
        } else {
            field.style.display = 'none';
            field.style.opacity = '0';
        }
    });
}

// Initialize dependent field visibility on modal open
function initializeDependentFields() {
    // Find all checkboxes that have dependent fields
    const checkboxes = document.querySelectorAll('[id^="mcp-field-"][type="checkbox"]');
    checkboxes.forEach(checkbox => {
        const fieldId = checkbox.id.replace('mcp-field-', '');
        toggleDependentFields(fieldId);
    });
}

function saveMcpConfig() {
    if (!currentMcpConfig) return;

    const mcpId = currentMcpConfig.id;
    const configFields = currentMcpConfig.c?._config_fields || [];

    // Collect values
    const config = {};
    let hasError = false;

    for (const field of configFields) {
        // Skip separator and button fields - they are just UI elements
        if (field.type === 'separator' || field.type === 'button') {
            continue;
        }

        const input = document.getElementById(`mcp-field-${field.id}`);

        // Handle checkbox type differently
        if (field.type === 'checkbox') {
            config[field.id] = input?.checked || false;
            continue;
        }

        // Check if this field is hidden (depends on unchecked checkbox)
        if (field.depends_on) {
            const dependsCheckbox = document.getElementById(`mcp-field-${field.depends_on}`);
            if (dependsCheckbox && !dependsCheckbox.checked) {
                // Field is hidden, skip validation but still save any value
                const value = input?.value?.trim() || field.default || '';
                if (value) {
                    config[field.id] = value;
                }
                continue;
            }
        }

        // Handle select type
        if (field.type === 'select') {
            const value = input?.value || field.default || '';
            if (value) {
                config[field.id] = value;
            }
            continue;
        }

        let value = input?.value?.trim() || '';

        // Validate URL fields have a protocol
        if (field.type === 'url' && value && !value.startsWith('http://') && !value.startsWith('https://')) {
            // Try to fix by prepending https://
            value = 'https://' + value;
            if (input) input.value = value;
            console.log(`[Wizard] Auto-fixed URL field ${field.id}: added https:// prefix`);
        }

        if (field.required && !value) {
            input.style.borderColor = '#ef4444';
            hasError = true;
        } else {
            if (input) input.style.borderColor = '#2a2a4e';
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

    // Update NetBox quick build section if we just configured NetBox
    if (mcpId === 'netbox') {
        updateNetBoxQuickBuild();
    }

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
    document.getElementById('agent-tab-netbox').style.display = tab === 'netbox' ? 'block' : 'none';
    document.getElementById('agent-tab-bulk').style.display = tab === 'bulk' ? 'block' : 'none';
}

// ========== NetBox Import Functions ==========

// Store loaded devices and current preview
let netboxDevices = [];
let netboxImportConfig = null;

// Build agents from NetBox site (PULL operation)
// Queries all devices in a site and creates agent configs for each
// NOW INCLUDES TOPOLOGY - links/cables between devices!
async function buildAgentsFromNetBoxSite() {
    const netboxConfig = mcpConfigurations['netbox'];
    if (!netboxConfig) {
        alert('Please configure NetBox MCP first (URL, Token, Site)');
        return;
    }

    const url = netboxConfig.netbox_url;
    const token = netboxConfig.api_token;
    const site = netboxConfig.site_name;

    if (!url || !token || !site) {
        alert('Please configure NetBox URL, API Token, and Site in the NetBox MCP settings');
        return;
    }

    // Show loading state
    const statusDiv = document.getElementById('netbox-build-status') || document.getElementById('netbox-connection-status');
    if (statusDiv) {
        statusDiv.innerHTML = '<span style="color: #888;"><span class="spinner" style="display: inline-block; width: 12px; height: 12px; margin-right: 8px;"></span>Querying NetBox site topology (devices + links)...</span>';
        statusDiv.style.display = 'block';
    }

    try {
        // Use the TOPOLOGY endpoint to get devices AND their interconnections
        const response = await fetch(`/api/wizard/mcps/netbox/site/${encodeURIComponent(site)}/topology?netbox_url=${encodeURIComponent(url)}&api_token=${encodeURIComponent(token)}`);
        const result = await response.json();

        if (result.status !== 'ok') {
            if (statusDiv) {
                statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${result.error}</span>`;
            }
            return;
        }

        if (!result.devices || result.devices.length === 0) {
            if (statusDiv) {
                statusDiv.innerHTML = `<span style="color: #f59e0b;">⚠ No devices found in site '${site}'</span>`;
            }
            return;
        }

        // Initialize wizard state if needed
        if (!wizardState.agents) {
            wizardState.agents = [];
        }
        if (!wizardState.topology) {
            wizardState.topology = { links: [], auto_generate: false };
        }
        if (!wizardState.topology.links) {
            wizardState.topology.links = [];
        }

        // Build a map of device names to agent IDs
        const deviceToAgentId = {};

        // Add each device as an agent
        for (const agentConfig of result.devices) {
            const agentId = `netbox-${agentConfig.netbox_id || agentConfig.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
            deviceToAgentId[agentConfig.name] = agentId;

            // Convert NetBox interfaces to wizard format
            const wizardInterfaces = (agentConfig.interfaces || []).map(iface => {
                // Extract first IP address
                const ipAddresses = iface.ip_addresses || [];
                const firstIp = ipAddresses.length > 0 ? ipAddresses[0].address : '';

                return {
                    id: iface.name.toLowerCase().replace(/[^a-z0-9]/g, ''),
                    n: iface.name,
                    t: iface.type || 'ethernet',
                    a: ipAddresses.map(ip => ip.address),  // addresses array
                    s: iface.enabled ? 'up' : 'down',
                    e: iface.enabled,
                    mac: iface.mac_address || '',
                    mtu: iface.mtu || 1500,
                    desc: iface.description || ''
                };
            });

            // Convert protocols to wizard format
            const wizardProtocols = (agentConfig.protocols || []).map(proto => ({
                p: proto.type,  // protocol type
                a: proto.area || '0.0.0.0',  // OSPF area
                asn: proto.local_as || '',  // BGP AS number
                enabled: proto.enabled !== false
            }));

            wizardState.agents.push({
                id: agentId,
                name: agentConfig.name,
                router_id: agentConfig.router_id || '',
                ifs: wizardInterfaces,  // wizard uses 'ifs' for interfaces
                interfaces: wizardInterfaces,  // also keep as 'interfaces' for compatibility
                protos: wizardProtocols,  // wizard uses 'protos' for protocols
                protocols: wizardProtocols,  // also keep as 'protocols' for compatibility
                source: 'netbox',
                netbox_url: agentConfig.netbox_url,
                netbox_id: agentConfig.netbox_id,
                neighbors: result.neighbors ? result.neighbors[agentConfig.name] || [] : []
            });
        }

        // Process links/connections from topology
        if (result.links && result.links.length > 0) {
            console.log(`[NetBox PULL] Processing ${result.links.length} links from topology`);

            for (const link of result.links) {
                const sourceAgentId = deviceToAgentId[link.source_device];
                const targetAgentId = deviceToAgentId[link.target_device];

                if (sourceAgentId && targetAgentId) {
                    // Add to topology.links using the wizard's format
                    wizardState.topology.links.push({
                        id: `link-${link.cable_id || Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
                        agent1_id: sourceAgentId,
                        interface1: link.source_interface,
                        agent2_id: targetAgentId,
                        interface2: link.target_interface,
                        link_type: 'ethernet',
                        status: link.status || 'connected',
                        label: link.label || '',
                        source: 'netbox'
                    });

                    // Also annotate the interfaces with their connection info
                    const sourceAgent = wizardState.agents.find(a => a.id === sourceAgentId);
                    const targetAgent = wizardState.agents.find(a => a.id === targetAgentId);

                    if (sourceAgent) {
                        const srcIface = (sourceAgent.ifs || sourceAgent.interfaces || [])
                            .find(i => i.n === link.source_interface || i.name === link.source_interface);
                        if (srcIface) {
                            srcIface.connected_to = {
                                agent: targetAgentId,
                                agent_name: link.target_device,
                                interface: link.target_interface
                            };
                        }
                    }

                    if (targetAgent) {
                        const tgtIface = (targetAgent.ifs || targetAgent.interfaces || [])
                            .find(i => i.n === link.target_interface || i.name === link.target_interface);
                        if (tgtIface) {
                            tgtIface.connected_to = {
                                agent: sourceAgentId,
                                agent_name: link.source_device,
                                interface: link.source_interface
                            };
                        }
                    }
                }
            }
        }

        // Update the agent list display
        if (typeof renderAgentList === 'function') {
            renderAgentList();
        }

        // Build summary message
        const linkInfo = result.link_count > 0 ? `, ${result.link_count} links` : ' (no cable data)';
        const successMsg = `✓ Imported ${result.device_count} devices${linkInfo} from site '${site}'`;

        if (statusDiv) {
            statusDiv.innerHTML = `<span style="color: #4ade80;">${successMsg}</span>`;
        }

        // Build detailed alert message
        let alertMsg = `Successfully imported from NetBox site '${site}'!\n\n`;
        alertMsg += `📦 Devices: ${result.device_count}\n`;
        alertMsg += `🔗 Links/Cables: ${result.link_count || 0}\n\n`;
        alertMsg += `Agents created:\n${result.devices.map(a => '• ' + a.name).join('\n')}`;

        if (result.links && result.links.length > 0) {
            alertMsg += `\n\nConnections:\n`;
            alertMsg += result.links.slice(0, 10).map(l =>
                `• ${l.source_device}:${l.source_interface} ↔ ${l.target_device}:${l.target_interface}`
            ).join('\n');
            if (result.links.length > 10) {
                alertMsg += `\n... and ${result.links.length - 10} more`;
            }
        }

        alert(alertMsg);

        // Update the link list display if on topology step
        if (typeof renderLinkList === 'function') {
            renderLinkList();
        }

        // IMPORTANT: Also save agents to the backend session so launch knows about them
        console.log('[NetBox PULL] Saving agents to backend session...');
        for (const agent of wizardState.agents.filter(a => a.source === 'netbox')) {
            try {
                const saveResponse = await fetch(`/api/wizard/session/${sessionId}/step3/agent`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: agent.id,
                        name: agent.name,
                        router_id: agent.router_id,
                        protocols: agent.protocols || agent.protos || [],
                        interfaces: agent.interfaces || agent.ifs || [],
                        source: 'netbox',
                        netbox_id: agent.netbox_id,
                        netbox_url: agent.netbox_url
                    })
                });
                if (saveResponse.ok) {
                    console.log(`[NetBox PULL] Saved agent ${agent.name} to session`);
                } else {
                    console.warn(`[NetBox PULL] Failed to save agent ${agent.name}: ${saveResponse.status}`);
                }
            } catch (err) {
                console.warn(`[NetBox PULL] Error saving agent ${agent.name}:`, err);
            }
        }

        // Mark that this network was pulled from NetBox (skip duplicate check on deploy)
        wizardState.pulledFromNetBox = true;

        console.log('[NetBox PULL] Import complete:', {
            devices: result.device_count,
            links: result.link_count,
            agents: wizardState.agents.length,
            wizardLinks: wizardState.topology.links.length
        });

    } catch (e) {
        console.error('[NetBox PULL] Error:', e);
        if (statusDiv) {
            statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${e.message}</span>`;
        }
    }
}

// Check if NetBox auto-build is enabled and trigger it
function checkNetBoxAutoBuild() {
    const netboxConfig = mcpConfigurations['netbox'];
    if (netboxConfig && netboxConfig.auto_build) {
        console.log('[Wizard] NetBox auto-build enabled, building agents from site...');
        buildAgentsFromNetBoxSite();
    }
}

async function testNetBoxConnection() {
    const url = document.getElementById('netbox-import-url').value.trim();
    const token = document.getElementById('netbox-import-token').value.trim();
    const statusDiv = document.getElementById('netbox-connection-status');

    if (!url || !token) {
        statusDiv.innerHTML = '<span style="color: #ef4444;">Please enter both URL and API token</span>';
        return;
    }

    statusDiv.innerHTML = '<span style="color: #888;"><span class="spinner" style="display: inline-block; width: 12px; height: 12px; margin-right: 8px;"></span>Testing connection...</span>';

    try {
        const response = await fetch('/api/wizard/mcps/netbox/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ netbox_url: url, api_token: token })
        });
        const result = await response.json();

        if (result.connected) {
            statusDiv.innerHTML = `<span style="color: #4ade80;">✓ Connected to NetBox ${result.netbox_version || ''}</span>`;
        } else {
            statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Connection failed: ${result.error || 'Unknown error'}</span>`;
        }
    } catch (e) {
        statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${e.message}</span>`;
    }
}

async function loadNetBoxDevices() {
    const url = document.getElementById('netbox-import-url').value.trim();
    const token = document.getElementById('netbox-import-token').value.trim();
    const statusDiv = document.getElementById('netbox-connection-status');

    if (!url || !token) {
        statusDiv.innerHTML = '<span style="color: #ef4444;">Please enter both URL and API token</span>';
        return;
    }

    statusDiv.innerHTML = '<span style="color: #888;"><span class="spinner" style="display: inline-block; width: 12px; height: 12px; margin-right: 8px;"></span>Loading devices...</span>';

    try {
        // Load devices
        const devicesResponse = await fetch(`/api/wizard/mcps/netbox/devices?netbox_url=${encodeURIComponent(url)}&api_token=${encodeURIComponent(token)}`);
        const devicesResult = await devicesResponse.json();

        if (devicesResult.status !== 'ok') {
            statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${devicesResult.error}</span>`;
            return;
        }

        netboxDevices = devicesResult.devices;

        // Load sites for filter
        const sitesResponse = await fetch(`/api/wizard/mcps/netbox/sites?netbox_url=${encodeURIComponent(url)}&api_token=${encodeURIComponent(token)}`);
        const sitesResult = await sitesResponse.json();
        populateSiteFilter(sitesResult.sites || []);

        // Load roles for filter
        const rolesResponse = await fetch(`/api/wizard/mcps/netbox/device-roles?netbox_url=${encodeURIComponent(url)}&api_token=${encodeURIComponent(token)}`);
        const rolesResult = await rolesResponse.json();
        populateRoleFilter(rolesResult.roles || []);

        // Show devices section
        document.getElementById('netbox-devices-section').style.display = 'block';
        renderNetBoxDevices(netboxDevices);

        statusDiv.innerHTML = `<span style="color: #4ade80;">✓ Loaded ${netboxDevices.length} devices</span>`;
    } catch (e) {
        statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${e.message}</span>`;
    }
}

function populateSiteFilter(sites) {
    const select = document.getElementById('netbox-filter-site');
    select.innerHTML = '<option value="">All Sites</option>' +
        sites.map(s => `<option value="${s.name}">${s.name}</option>`).join('');
}

function populateRoleFilter(roles) {
    const select = document.getElementById('netbox-filter-role');
    select.innerHTML = '<option value="">All Roles</option>' +
        roles.map(r => `<option value="${r.name}">${r.name}</option>`).join('');
}

function filterNetBoxDevices() {
    const siteFilter = document.getElementById('netbox-filter-site').value;
    const roleFilter = document.getElementById('netbox-filter-role').value;

    let filtered = netboxDevices;
    if (siteFilter) {
        filtered = filtered.filter(d => d.site === siteFilter);
    }
    if (roleFilter) {
        filtered = filtered.filter(d => d.role === roleFilter);
    }

    renderNetBoxDevices(filtered);
}

function renderNetBoxDevices(devices) {
    const tbody = document.getElementById('netbox-devices-list');

    if (devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="padding: 20px; text-align: center; color: #888;">No devices found</td></tr>';
        return;
    }

    tbody.innerHTML = devices.map(d => `
        <tr style="border-bottom: 1px solid #2a2a4e;">
            <td style="padding: 10px;">
                <strong style="color: #06b6d4;">${d.name}</strong>
                <div style="font-size: 0.8rem; color: #888;">${d.device_type} (${d.manufacturer})</div>
            </td>
            <td style="padding: 10px;">${d.site || '-'}</td>
            <td style="padding: 10px;">${d.role || '-'}</td>
            <td style="padding: 10px; font-family: monospace;">${d.primary_ip || '-'}</td>
            <td style="padding: 10px; text-align: center;">
                <button class="btn btn-secondary" onclick="previewNetBoxDevice(${d.id})" style="padding: 5px 15px;">Import</button>
            </td>
        </tr>
    `).join('');
}

async function previewNetBoxDevice(deviceId) {
    const url = document.getElementById('netbox-import-url').value.trim();
    const token = document.getElementById('netbox-import-token').value.trim();
    const statusDiv = document.getElementById('netbox-connection-status');

    statusDiv.innerHTML = '<span style="color: #888;"><span class="spinner" style="display: inline-block; width: 12px; height: 12px; margin-right: 8px;"></span>Fetching device details...</span>';

    try {
        const response = await fetch(`/api/wizard/mcps/netbox/devices/${deviceId}/import?netbox_url=${encodeURIComponent(url)}&api_token=${encodeURIComponent(token)}`);
        const result = await response.json();

        if (result.status !== 'ok') {
            statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${result.error}</span>`;
            return;
        }

        netboxImportConfig = result.agent_config;
        statusDiv.innerHTML = `<span style="color: #4ade80;">✓ ${result.message}</span>`;

        // Populate preview
        document.getElementById('netbox-preview-name').value = netboxImportConfig.name || '';
        document.getElementById('netbox-preview-router-id').value = netboxImportConfig.router_id || '';
        document.getElementById('netbox-preview-site').value = netboxImportConfig.site || '';
        document.getElementById('netbox-preview-role').value = netboxImportConfig.role || '';

        // Interfaces
        const ifaces = netboxImportConfig.interfaces || [];
        document.getElementById('netbox-preview-if-count').textContent = ifaces.length;
        document.getElementById('netbox-preview-interfaces').innerHTML = ifaces.map(i => {
            const ips = (i.ip_addresses || []).map(ip => ip.address).join(', ');
            return `<div style="padding: 4px 0; border-bottom: 1px solid #2a2a4e;">${i.name}${ips ? ': ' + ips : ''}</div>`;
        }).join('') || '<span style="color: #888;">No interfaces</span>';

        // Protocols
        const protocols = netboxImportConfig.protocols || [];
        document.getElementById('netbox-preview-protocols').innerHTML = protocols.map(p =>
            `<span style="background: #2a2a4e; padding: 4px 12px; border-radius: 4px;">${p.type.toUpperCase()}</span>`
        ).join('') || '<span style="color: #888;">No protocols suggested</span>';

        // Show preview
        document.getElementById('netbox-import-preview').style.display = 'block';

    } catch (e) {
        statusDiv.innerHTML = `<span style="color: #ef4444;">✗ Error: ${e.message}</span>`;
    }
}

function clearNetBoxPreview() {
    document.getElementById('netbox-import-preview').style.display = 'none';
    netboxImportConfig = null;
}

function importNetBoxDevice() {
    if (!netboxImportConfig) {
        showAlert('No device selected for import', 'error');
        return;
    }

    // Generate agent ID from device name
    const agentId = netboxImportConfig.name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-');

    // Build agent object compatible with wizard state
    const agent = {
        id: agentId,
        name: netboxImportConfig.name,
        router_id: netboxImportConfig.router_id || '',
        interfaces: (netboxImportConfig.interfaces || []).map(i => ({
            n: i.name,
            t: i.type || 'ethernet',
            ip: (i.ip_addresses && i.ip_addresses[0]) ? i.ip_addresses[0].address : '',
            e: i.enabled !== false
        })),
        protocols: (netboxImportConfig.protocols || []).map(p => ({
            t: p.type,
            ...p
        })),
        // Store NetBox reference
        netbox: {
            id: netboxImportConfig.netbox_id,
            url: netboxImportConfig.netbox_url,
            site: netboxImportConfig.site
        }
    };

    // Add to wizard state
    wizardState.agents.push(agent);
    renderAgentList();

    // Clear and hide preview
    clearNetBoxPreview();
    showAlert(`Imported agent "${agent.name}" from NetBox`, 'success');
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

    // Get all optional field groups
    const parentGroup = document.getElementById('parent-interface-group');
    const bondSelectGroup = document.getElementById('bond-select-group');
    const lacpModeGroup = document.getElementById('lacp-mode-group');
    const vlanIdGroup = document.getElementById('vlan-id-group');
    const subifIndexGroup = document.getElementById('subif-index-group');
    const interfaceModeGroup = document.getElementById('interface-mode-group');
    const allowedVlansGroup = document.getElementById('allowed-vlans-group');
    const greConfigGroup = document.getElementById('gre-config-group');
    const parentHint = document.getElementById('parent-hint');
    const ifAddressHint = document.getElementById('if-address-hint');

    // Hide all optional groups by default
    [parentGroup, bondSelectGroup, lacpModeGroup, vlanIdGroup, subifIndexGroup, interfaceModeGroup, allowedVlansGroup, greConfigGroup].forEach(g => {
        if (g) g.style.display = 'none';
    });

    // Reset address hint
    if (ifAddressHint) ifAddressHint.textContent = '';

    // Populate parent interface dropdown
    const parentSelect = document.getElementById('parent-interface');
    if (parentSelect) {
        parentSelect.innerHTML = '<option value="eth0">eth0 (default)</option>';
        currentAgentInterfaces.forEach(iface => {
            if (iface.t === 'eth' || iface.t === 'bond') {
                parentSelect.innerHTML += `<option value="${iface.n}">${iface.n}</option>`;
            }
        });
    }

    // Populate bond dropdown
    const bondSelect = document.getElementById('bond-select');
    if (bondSelect) {
        bondSelect.innerHTML = '<option value="">-- Select Bond --</option>';
        currentAgentInterfaces.forEach(iface => {
            if (iface.t === 'bond') {
                bondSelect.innerHTML += `<option value="${iface.n}">${iface.n}</option>`;
            }
        });
    }

    // Configure fields based on interface type
    switch (ifType) {
        case 'eth':
        case 'lo':
            // Simple interfaces - just counter-based naming
            const counter = interfaceCounters[ifType] || 0;
            document.getElementById('if-name').value = `${ifType}${counter}`;
            break;

        case 'bond':
            // Bond interface
            if (lacpModeGroup) lacpModeGroup.style.display = 'block';
            const bondCounter = interfaceCounters['bond'] || 0;
            document.getElementById('if-name').value = `bond${bondCounter}`;
            break;

        case 'bond-member':
            // Bond member - select parent and bond to join
            if (parentGroup) {
                parentGroup.style.display = 'block';
                if (parentHint) parentHint.textContent = 'Physical interface to add to bond';
            }
            if (bondSelectGroup) bondSelectGroup.style.display = 'block';
            document.getElementById('if-name').value = '(member)';
            break;

        case 'sub-l2':
            // L2 subinterface with VLAN tag
            if (parentGroup) {
                parentGroup.style.display = 'block';
                if (parentHint) parentHint.textContent = 'Parent interface (e.g., eth0.100)';
            }
            if (vlanIdGroup) vlanIdGroup.style.display = 'block';
            updateSubInterfaceName();
            break;

        case 'sub-l2-trunk':
            // L2 trunk subinterface
            if (parentGroup) {
                parentGroup.style.display = 'block';
                if (parentHint) parentHint.textContent = 'Parent interface for trunk';
            }
            if (vlanIdGroup) vlanIdGroup.style.display = 'block';
            if (allowedVlansGroup) allowedVlansGroup.style.display = 'block';
            updateSubInterfaceName();
            break;

        case 'sub-l3':
            // L3 routed subinterface
            if (parentGroup) {
                parentGroup.style.display = 'block';
                if (parentHint) parentHint.textContent = 'Parent L3 interface (e.g., eth0:0)';
            }
            if (subifIndexGroup) subifIndexGroup.style.display = 'block';
            updateL3SubInterfaceName();
            break;

        case 'vxlan':
            const vxlanCounter = interfaceCounters['vxlan'] || 0;
            document.getElementById('if-name').value = `vxlan${vxlanCounter}`;
            break;

        case 'gre':
            // GRE Tunnel interface - show tunnel config
            if (greConfigGroup) greConfigGroup.style.display = 'block';
            if (ifAddressHint) ifAddressHint.textContent = 'Tunnel interface IP (e.g., 10.0.0.1/30 for P2P)';
            const greCounter = interfaceCounters['gre'] || 0;
            document.getElementById('if-name').value = `gre${greCounter}`;
            // Set default MTU for GRE (1400 to account for overhead)
            document.getElementById('if-mtu').value = '1400';
            break;

        case 'tun':
            const tunCounter = interfaceCounters['tun'] || 0;
            document.getElementById('if-name').value = `tun${tunCounter}`;
            break;

        case 'vlan':
            if (vlanIdGroup) vlanIdGroup.style.display = 'block';
            const vlanId = document.getElementById('sub-vlan')?.value || '100';
            document.getElementById('if-name').value = `vlan${vlanId}`;
            break;

        case 'bridge':
            const bridgeCounter = interfaceCounters['bridge'] || 0;
            document.getElementById('if-name').value = `br${bridgeCounter}`;
            break;

        default:
            document.getElementById('if-name').value = ifType + '0';
    }
}

function updateSubInterfaceName() {
    const parent = document.getElementById('parent-interface')?.value || 'eth0';
    const vlanId = document.getElementById('sub-vlan')?.value || '100';
    document.getElementById('if-name').value = `${parent}.${vlanId}`;
}

function updateL3SubInterfaceName() {
    const parent = document.getElementById('parent-interface')?.value || 'eth0';
    const subifIndex = document.getElementById('subif-index')?.value || '0';
    document.getElementById('if-name').value = `${parent}:${subifIndex}`;
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

    // Handle type-specific fields
    switch (ifType) {
        case 'bond':
            // LACP Bond interface
            const lacpMode = document.getElementById('lacp-mode')?.value || 'active';
            interfaceConfig.lacp_mode = lacpMode;
            interfaceConfig.members = [];
            if (!interfaceCounters['bond']) interfaceCounters['bond'] = 0;
            interfaceCounters['bond']++;
            break;

        case 'bond-member':
            // Adding an interface to a bond
            const parentIf = document.getElementById('parent-interface')?.value;
            const bondIf = document.getElementById('bond-select')?.value;
            if (!bondIf) {
                showAlert('Please select a bond interface to join', 'error');
                return;
            }
            // Find the bond and add this member
            const bond = currentAgentInterfaces.find(i => i.n === bondIf && i.t === 'bond');
            if (bond) {
                bond.members = bond.members || [];
                bond.members.push(parentIf);
                showAlert(`Added ${parentIf} to ${bondIf}`, 'success');
                hideAddInterfaceForm();
                renderConfiguredInterfaces();
                return; // Don't add as separate interface
            }
            break;

        case 'sub-l2':
            // L2 802.1Q subinterface
            const l2Parent = document.getElementById('parent-interface')?.value || 'eth0';
            const l2VlanId = parseInt(document.getElementById('sub-vlan')?.value) || 100;
            interfaceConfig.parent = l2Parent;
            interfaceConfig.vlan_id = l2VlanId;
            interfaceConfig.encapsulation = 'dot1q';
            interfaceConfig.mode = 'access';
            break;

        case 'sub-l2-trunk':
            // L2 trunk subinterface
            const trunkParent = document.getElementById('parent-interface')?.value || 'eth0';
            const trunkVlanId = parseInt(document.getElementById('sub-vlan')?.value) || 100;
            const allowedVlans = document.getElementById('allowed-vlans')?.value || '';
            interfaceConfig.parent = trunkParent;
            interfaceConfig.vlan_id = trunkVlanId;
            interfaceConfig.encapsulation = 'dot1q';
            interfaceConfig.mode = 'trunk';
            interfaceConfig.allowed_vlans = allowedVlans;
            break;

        case 'sub-l3':
            // L3 routed subinterface
            const l3Parent = document.getElementById('parent-interface')?.value || 'eth0';
            const subifIndex = parseInt(document.getElementById('subif-index')?.value) || 0;
            interfaceConfig.parent = l3Parent;
            interfaceConfig.subif_index = subifIndex;
            interfaceConfig.encapsulation = 'none';
            interfaceConfig.mode = 'routed';
            break;

        case 'vlan':
            // VLAN SVI
            const sviVlanId = parseInt(document.getElementById('sub-vlan')?.value) || 100;
            interfaceConfig.vlan_id = sviVlanId;
            if (!interfaceCounters['vlan']) interfaceCounters['vlan'] = 0;
            interfaceCounters['vlan']++;
            break;

        case 'vxlan':
        case 'tun':
        case 'bridge':
            // Increment counters for these types
            if (!interfaceCounters[ifType]) interfaceCounters[ifType] = 0;
            interfaceCounters[ifType]++;
            break;

        case 'gre':
            // GRE Tunnel interface with tunnel configuration
            const greLocalIp = document.getElementById('gre-local-ip')?.value?.trim() || '';
            const greRemoteIp = document.getElementById('gre-remote-ip')?.value?.trim() || '';
            const greKey = document.getElementById('gre-key')?.value?.trim();
            const greKeepalive = parseInt(document.getElementById('gre-keepalive')?.value) || 10;
            const greChecksum = document.getElementById('gre-checksum')?.checked || false;
            const greSequence = document.getElementById('gre-sequence')?.checked || false;

            // Validate required fields
            if (!greRemoteIp) {
                showAlert('Remote endpoint IP is required for GRE tunnel', 'error');
                return;
            }

            // Add tunnel configuration to interface
            interfaceConfig.tun = {
                tt: 'gre',                           // tunnel type
                src: greLocalIp,                     // source/local IP
                dst: greRemoteIp,                    // destination/remote IP
                key: greKey ? parseInt(greKey) : null,  // GRE key
                csum: greChecksum,                   // checksum
                seq: greSequence,                    // sequence numbers
                ka: greKeepalive,                    // keepalive interval
                ttl: 255,                            // outer TTL
                tos: 192                             // CS6 for network control
            };

            if (!interfaceCounters['gre']) interfaceCounters['gre'] = 0;
            interfaceCounters['gre']++;
            break;

        default:
            // Standard interfaces (eth, lo)
            if (!interfaceCounters[ifType]) interfaceCounters[ifType] = 0;
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
            let typeDisplay = getInterfaceTypeDisplay(iface);
            let typeColor = getInterfaceTypeColor(iface.t);
            return `
                <div class="agent-item" style="margin-bottom: 10px;">
                    <div class="agent-info">
                        <h4 style="color: ${typeColor};">${iface.n}</h4>
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

function getInterfaceTypeDisplay(iface) {
    switch (iface.t) {
        case 'eth': return 'Ethernet';
        case 'lo': return 'Loopback';
        case 'bond':
            const members = iface.members?.length || 0;
            return `Bond/LACP (${iface.lacp_mode}, ${members} members)`;
        case 'sub-l2':
            return `L2 Subif (parent: ${iface.parent}, VLAN: ${iface.vlan_id})`;
        case 'sub-l2-trunk':
            return `L2 Trunk (parent: ${iface.parent}, native: ${iface.vlan_id}, allowed: ${iface.allowed_vlans || 'all'})`;
        case 'sub-l3':
            return `L3 Routed Subif (parent: ${iface.parent}:${iface.subif_index})`;
        case 'vlan':
            return `VLAN SVI (VLAN ${iface.vlan_id})`;
        case 'vxlan':
            return 'VXLAN VTEP';
        case 'gre':
            if (iface.tun) {
                const dst = iface.tun.dst || 'N/A';
                const key = iface.tun.key ? `, key=${iface.tun.key}` : '';
                return `GRE Tunnel (→ ${dst}${key})`;
            }
            return 'GRE Tunnel';
        case 'tun':
            return 'Tunnel';
        case 'bridge':
            return 'Bridge';
        default:
            return iface.t;
    }
}

function getInterfaceTypeColor(type) {
    const colors = {
        'eth': '#00d9ff',
        'lo': '#4ade80',
        'bond': '#a855f7',
        'sub-l2': '#f97316',
        'sub-l2-trunk': '#f97316',
        'sub-l3': '#ec4899',
        'vlan': '#22d3ee',
        'vxlan': '#fbbf24',
        'gre': '#06b6d4',
        'tun': '#06b6d4',
        'bridge': '#14b8a6'
    };
    return colors[type] || '#00d9ff';
}

function clearAgentInterfaces() {
    currentAgentInterfaces = [];
    // Reset counters (keeping eth0 and lo0 as defaults)
    interfaceCounters = { eth: 1, lo: 1, bond: 0, vlan: 0, vxlan: 0, gre: 0, tun: 0, bridge: 0 };
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
    const modelSelect = document.getElementById('llm-model');

    const placeholders = {
        'claude': 'sk-ant-...',
        'openai': 'sk-...',
        'gemini': 'AIza...'
    };

    input.placeholder = placeholders[provider] || '';

    // Show/hide appropriate model optgroups
    const optgroups = {
        'claude': 'claude-models',
        'openai': 'openai-models',
        'gemini': 'gemini-models'
    };

    // Hide all optgroups
    document.querySelectorAll('#llm-model optgroup').forEach(group => {
        group.style.display = 'none';
    });

    // Show the selected provider's models
    if (optgroups[provider]) {
        const targetGroup = document.getElementById(optgroups[provider]);
        if (targetGroup) {
            targetGroup.style.display = 'block';
            // Select the first option in the visible group
            const firstOption = targetGroup.querySelector('option');
            if (firstOption) {
                modelSelect.value = firstOption.value;
            }
        }
    }
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

            // Get underlay protocol selection
            const underlayRadio = document.querySelector('input[name="underlay-protocol"]:checked');
            const underlayProtocol = underlayRadio ? underlayRadio.value : 'ipv6';

            // Get Docker network IP version from dropdown
            const dockerIpVersion = document.getElementById('docker-ip-version').value;
            const isDockerIpv6 = dockerIpVersion === 'ipv6';

            wizardState.docker_config = {
                name: networkName,
                ip_version: dockerIpVersion,
                subnet: document.getElementById('subnet').value || null,
                gateway: document.getElementById('gateway').value || null,
                driver: document.getElementById('driver').value,
                enable_ipv6: isDockerIpv6
            };

            // Save network foundation settings
            wizardState.network_foundation = {
                underlay_protocol: underlayProtocol,
                overlay: {
                    enabled: true,
                    subnet: 'fd00:a510::/48',
                    enable_nd: true,  // Always enabled - SLAAC automatic
                    enable_routes: true  // Always enabled - SLAAC automatic
                },
                docker_ipv6: {
                    enabled: isDockerIpv6,
                    subnet: isDockerIpv6 ? document.getElementById('subnet').value : 'fd00:d0c:1::/64',
                    gateway: isDockerIpv6 ? document.getElementById('gateway').value : 'fd00:d0c:1::1'
                }
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

    // Update network name badge (ensure it shows on all steps)
    updateNetworkNameBadge();

    // Step 3 (Agent Builder) - check NetBox quick build
    if (step === 3) {
        updateNetBoxQuickBuild();
    }

    // Update preview on last step (now step 5)
    if (step === 5) {
        updatePreview();
    }
}

// Show/hide NetBox Quick Build section based on MCP config
// ONLY shows when user explicitly checks "Pull: Build agents from NetBox"
function updateNetBoxQuickBuild() {
    const quickBuildDiv = document.getElementById('netbox-quick-build');
    const siteDisplay = document.getElementById('netbox-site-display');

    if (!quickBuildDiv) return;

    const netboxConfig = mcpConfigurations['netbox'];

    // ONLY show if auto_build is explicitly enabled (user checked the checkbox)
    if (netboxConfig && netboxConfig.auto_build === true && netboxConfig.site_name && netboxConfig.netbox_url) {
        quickBuildDiv.style.display = 'block';
        if (siteDisplay) {
            siteDisplay.textContent = netboxConfig.site_name;
        }
    } else {
        quickBuildDiv.style.display = 'none';
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
        // Show deployment progress overlay
        showDeployProgress();
        setDeployStatus('Deploying Network...', 'Starting containers and configuring agents...');
        updateDeployStep('containers', 'active');

        showAlert('Launching network... Please wait for containers to start.', 'info');
        console.log('Launching network with session:', sessionId);

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
            hideDeployProgress();  // Hide progress overlay on error
            throw new Error(error.detail || 'Launch failed');
        }

        const data = await response.json();
        console.log('Launch response:', JSON.stringify(data, null, 2));

        // Containers launched successfully
        updateDeployStep('containers', 'complete');
        showAlert('Network launched! Showing results...', 'success');

        // NetBox Auto-Registration (PUSH) - if enabled
        let netboxResults = [];
        const netboxConfig = mcpConfigurations['netbox'];
        console.log('[NetBox] MCP Configuration:', JSON.stringify(netboxConfig, null, 2));
        if (netboxConfig && netboxConfig.auto_register === true && netboxConfig.netbox_url && netboxConfig.api_token && netboxConfig.site_name) {
            console.log('[NetBox] Auto-register enabled, registering agents in NetBox...');
            console.log('[NetBox] Using URL:', netboxConfig.netbox_url);
            console.log('[NetBox] Using Site:', netboxConfig.site_name);

            // Check if network was pulled from NetBox - if so, skip duplicate check and just sync
            const pulledFromNetBox = wizardState.pulledFromNetBox ||
                wizardState.agents.every(a => a.source === 'netbox');

            // Update progress overlay for NetBox
            if (pulledFromNetBox) {
                setDeployStatus('Syncing with NetBox...', 'Verifying devices match...');
                updateDeployStep('netbox-check', 'skipped');
            } else {
                setDeployStatus('Registering in NetBox...', 'Checking for existing devices...');
                updateDeployStep('netbox-check', 'active');
            }

            // Build list of agents to check
            const agentsToRegister = [];
            for (const agentId of Object.keys(data.agents || {})) {
                const agentConfig = wizardState.agents.find(a => a.id === agentId);
                if (agentConfig) {
                    agentsToRegister.push({ id: agentId, name: agentConfig.name || agentId, config: agentConfig });
                }
            }

            let agentsToSkip = new Set();
            let shouldProceed = true;

            // Skip duplicate check if pulled from NetBox - devices already exist there
            if (pulledFromNetBox) {
                console.log('[NetBox] Skipping duplicate check - network was pulled from NetBox');
                showAlert('Syncing with NetBox (pulled from existing site)...', 'info');
                updateDeployStep('netbox-register', 'active');
            } else {
                // Check for duplicates first (only for manually created networks)
                showAlert('Checking for existing devices in NetBox...', 'info');
                const duplicateCheck = await checkNetBoxDuplicates(netboxConfig, agentsToRegister);

                if (duplicateCheck.status === 'ok' && duplicateCheck.duplicates_found > 0) {
                    console.log('[NetBox] Found duplicates:', duplicateCheck.duplicates);
                    const userChoice = await showNetBoxDuplicateModal(duplicateCheck.duplicates);
                    console.log('[NetBox] User choice for duplicates:', userChoice);

                    if (userChoice === 'cancel') {
                        shouldProceed = false;
                        showAlert('NetBox registration cancelled. Network still launched.', 'warning');
                        // Progress overlay is already hidden, no need to update steps
                    } else if (userChoice === 'skip') {
                        // Mark duplicate device names to skip
                        duplicateCheck.duplicates.forEach(d => agentsToSkip.add(d.name));
                        showAlert(`Skipping ${agentsToSkip.size} existing device(s)...`, 'info');
                        // Steps already updated by closeNetBoxDuplicateModal
                    } else if (userChoice === 'update') {
                        // User chose to update existing
                        // Steps already updated by closeNetBoxDuplicateModal
                    }
                    // 'update' - proceed with registration (will update existing)
                } else {
                    // No duplicates found
                    updateDeployStep('netbox-check', 'complete');
                    updateDeployStep('netbox-register', 'active');
                }
            }

            if (shouldProceed) {
                showAlert('Registering agents in NetBox...', 'info');
                setDeployStatus('Registering in NetBox...', `Processing ${agentsToRegister.length} agent(s)...`);

                // Register each agent in NetBox using the wizard session endpoint
                let processedCount = 0;
                for (const agent of agentsToRegister) {
                    const agentId = agent.id;
                    const agentConfig = agent.config;
                    const agentName = agentConfig.name || agentId;
                    processedCount++;

                    // Update current agent being processed
                    setDeployCurrentAgent(agentName);
                    setDeployStatus('Registering in NetBox...', `Processing agent ${processedCount} of ${agentsToRegister.length}...`);

                    // Skip if user chose to skip duplicates
                    if (agentsToSkip.has(agentName)) {
                        console.log(`[NetBox] Skipping duplicate: ${agentName}`);
                        netboxResults.push({
                            agent_id: agentId,
                            success: true,
                            skipped: true,
                            device_name: agentName,
                            device_url: duplicateCheck.duplicates.find(d => d.name === agentName)?.device_url
                        });
                        continue;
                    }

                    try {
                        const regResponse = await fetch(`/api/wizard/session/${sessionId}/agents/${agentId}/mcps/netbox/register`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                netbox_url: netboxConfig.netbox_url,
                                api_token: netboxConfig.api_token,
                                site_name: netboxConfig.site_name,
                                agent_name: agentName,
                                agent_config: agentConfig
                            })
                        });
                        const regResult = await regResponse.json();
                        netboxResults.push({
                            agent_id: agentId,
                            success: regResult.success || regResult.status === 'ok',
                            device_url: regResult.device_url,
                            device_name: regResult.device_name || agentName,
                            error: regResult.errors?.join(', ') || (regResult.detail ? regResult.detail : null)
                        });
                        console.log(`[NetBox] Registered ${agentId}:`, regResult.success ? 'SUCCESS' : 'FAILED', regResult.device_url);
                    } catch (err) {
                        console.error(`[NetBox] Failed to register ${agentId}:`, err);
                        netboxResults.push({
                            agent_id: agentId,
                            success: false,
                            error: err.message
                        });
                    }
                }
                console.log('[NetBox] Registration complete:', netboxResults);
                setDeployCurrentAgent(null);
                updateDeployStep('netbox-register', 'complete');

                // Now register cables/topology links if we have any
                const topologyLinks = wizardState.topology?.links || [];
                if (topologyLinks.length > 0) {
                    console.log(`[NetBox] Registering ${topologyLinks.length} topology cables...`);
                    showAlert(`Registering ${topologyLinks.length} cable connections...`, 'info');
                    updateDeployStep('cables', 'active');
                    setDeployStatus('Registering Cables...', `Creating ${topologyLinks.length} cable connection(s)...`);

                    try {
                        // Build links array with device names (not agent IDs)
                        const cablesPayload = topologyLinks.map(link => {
                            // Get device names from agent IDs
                            const agent1 = wizardState.agents.find(a => a.id === link.agent1_id);
                            const agent2 = wizardState.agents.find(a => a.id === link.agent2_id);

                            return {
                                a_device: agent1?.name || link.agent1_id,
                                a_interface: link.interface1,
                                b_device: agent2?.name || link.agent2_id,
                                b_interface: link.interface2,
                                status: link.status || 'connected',
                                label: link.label || ''
                            };
                        });

                        const cablesResponse = await fetch('/api/wizard/mcps/netbox/register-cables', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                netbox_url: netboxConfig.netbox_url,
                                api_token: netboxConfig.api_token,
                                site_name: netboxConfig.site_name,
                                links: cablesPayload
                            })
                        });

                        const cablesResult = await cablesResponse.json();
                        console.log('[NetBox] Cables registration result:', cablesResult);

                        // Store cable results for display
                        window.netboxCablesResult = cablesResult;

                        if (cablesResult.created > 0) {
                            showAlert(`Created ${cablesResult.created} cable connections in NetBox`, 'success');
                            updateDeployStep('cables', 'complete');
                        }
                        if (cablesResult.failed > 0) {
                            console.warn('[NetBox] Some cables failed:', cablesResult.errors);
                            updateDeployStep('cables', cablesResult.created > 0 ? 'complete' : 'error');
                        }
                        if (cablesResult.created === 0 && cablesResult.failed === 0) {
                            updateDeployStep('cables', 'complete');
                        }
                    } catch (cableErr) {
                        console.error('[NetBox] Failed to register cables:', cableErr);
                        updateDeployStep('cables', 'error');
                    }
                } else {
                    // No cables to register
                    updateDeployStep('cables', 'skipped');
                }
            }
        } else {
            // NetBox not enabled - mark all NetBox steps as skipped
            updateDeployStep('netbox-check', 'skipped');
            updateDeployStep('netbox-register', 'skipped');
            updateDeployStep('cables', 'skipped');
        }

        // Hide deployment progress overlay before showing summary
        setDeployStatus('Complete!', 'Preparing summary...');
        hideDeployProgress();

        // Build launch summary page - include ALL agents (even without ports for debugging)
        const allAgents = Object.entries(data.agents || {});
        console.log('All agents in response:', allAgents.length);

        // Build NetBox config hash for URL (avoids CORS issues)
        let netboxHash = '';
        if (netboxConfig && netboxConfig.netbox_url && netboxConfig.api_token) {
            const nbConfig = {
                u: netboxConfig.netbox_url,
                t: netboxConfig.api_token,
                s: netboxConfig.site_name || ''
            };
            netboxHash = '#nb=' + btoa(JSON.stringify(nbConfig));
        }

        const agentsWithWebUI = allAgents
            .filter(([_, agent]) => agent.webui_port)
            .map(([agentId, agent]) => {
                const agentConfig = wizardState.agents.find(a => a.id === agentId);
                const deviceName = agentConfig?.name || agentId;
                // Include device name in the hash
                let hash = netboxHash;
                if (hash && deviceName) {
                    const nbConfig = JSON.parse(atob(hash.replace('#nb=', '')));
                    nbConfig.d = deviceName;  // device name
                    hash = '#nb=' + btoa(JSON.stringify(nbConfig));
                }
                return {
                    id: agentId,
                    port: agent.webui_port,
                    ip: agent.ip_address,
                    status: agent.status,
                    url: `http://localhost:${agent.webui_port}/dashboard?agent_id=${encodeURIComponent(agentId)}${hash}`
                };
            });

        console.log('Agents with WebUI ports:', agentsWithWebUI.length, agentsWithWebUI);

        // If no agents have ports, still show what we have
        if (agentsWithWebUI.length === 0 && allAgents.length > 0) {
            console.warn('No agents have webui_port! Raw agents:', allAgents);
            // Create entries anyway for display
            allAgents.forEach(([agentId, agent]) => {
                const agentConfig = wizardState.agents.find(a => a.id === agentId);
                const deviceName = agentConfig?.name || agentId;
                let hash = netboxHash;
                if (hash && deviceName) {
                    const nbConfig = JSON.parse(atob(hash.replace('#nb=', '')));
                    nbConfig.d = deviceName;
                    hash = '#nb=' + btoa(JSON.stringify(nbConfig));
                }
                agentsWithWebUI.push({
                    id: agentId,
                    port: agent.webui_port || 'N/A',
                    ip: agent.ip_address || 'N/A',
                    status: agent.status || 'unknown',
                    url: agent.webui_port ? `http://localhost:${agent.webui_port}/dashboard?agent_id=${encodeURIComponent(agentId)}${hash}` : '#'
                });
            });
        }

            // Store agents globally for the open all function
            window.launchedAgents = agentsWithWebUI;

            // Push NetBox config to each agent's API for dashboard auto-sync
            // (localStorage doesn't work across different ports/origins)
            if (netboxConfig && netboxConfig.netbox_url && netboxConfig.api_token) {
                console.log('[NetBox] Pushing config to', agentsWithWebUI.length, 'agents...');
                for (const agent of agentsWithWebUI) {
                    if (!agent.port || agent.port === 'N/A') continue;

                    const agentConfig = wizardState.agents.find(a => a.id === agent.id);
                    const agentName = agentConfig?.name || agent.id;

                    try {
                        const pushResponse = await fetch(`http://localhost:${agent.port}/api/config/netbox`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                netbox_url: netboxConfig.netbox_url,
                                api_token: netboxConfig.api_token,
                                site_name: netboxConfig.site_name,
                                device_name: agentName
                            })
                        });
                        if (pushResponse.ok) {
                            console.log(`[NetBox] Config pushed to ${agentName} (port ${agent.port})`);
                        } else {
                            console.warn(`[NetBox] Failed to push config to ${agentName}: ${pushResponse.status}`);
                        }
                    } catch (err) {
                        console.warn(`[NetBox] Could not push config to ${agentName}:`, err.message);
                    }
                }
                // Also save to localStorage as fallback (for wizard's own port)
                localStorage.setItem('netbox_config', JSON.stringify({
                    netbox_url: netboxConfig.netbox_url,
                    api_token: netboxConfig.api_token,
                    site_name: netboxConfig.site_name
                }));
                console.log('[NetBox] Config pushed to all agents');
            }

            // Log detailed info for debugging
            console.log('=== LAUNCH SUMMARY ===');
            console.log('Total agents in response:', allAgents.length);
            console.log('Agents with WebUI ports:', agentsWithWebUI.length);
            agentsWithWebUI.forEach(a => {
                console.log(`  - ${a.id}: port=${a.port}, url=${a.url}, status=${a.status}`);
            });
            console.log('window.launchedAgents set to:', window.launchedAgents);
            console.log('======================');

            // Create launch summary HTML
            let summaryHTML = `
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #4ade80; margin-bottom: 10px;">🎉 Network Deployed Successfully!</h2>
                    <p style="color: #888; margin-bottom: 20px;">${agentsWithWebUI.length} agent(s) are now running</p>
                    <button onclick="openAllAgentDashboards()" style="background: linear-gradient(135deg, #4ade80, #00d9ff); color: #1a1a2e; padding: 15px 30px; border: none; border-radius: 8px; cursor: pointer; font-size: 1.1rem; font-weight: bold; box-shadow: 0 4px 15px rgba(0,217,255,0.3);">
                        🚀 Open All ${agentsWithWebUI.length} Agent Dashboards
                    </button>
                    <p style="color: #666; font-size: 0.8rem; margin-top: 10px;">Click the button above or click individual agents below</p>
                </div>

                <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                    <h3 style="color: #00d9ff; margin-bottom: 15px;">Agent Dashboards</h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px;">
            `;

            for (const agent of agentsWithWebUI) {
                const statusColor = agent.status === 'running' ? '#4ade80' : '#facc15';
                summaryHTML += `
                    <a href="${agent.url}" target="_blank" style="text-decoration: none;">
                        <div style="background: #16213e; border: 2px solid ${statusColor}; border-radius: 8px; padding: 15px; transition: all 0.3s; cursor: pointer;"
                             onmouseover="this.style.borderColor='#00d9ff'; this.style.transform='translateY(-2px)';"
                             onmouseout="this.style.borderColor='${statusColor}'; this.style.transform='translateY(0)';">
                            <div style="font-weight: bold; color: #00d9ff; margin-bottom: 5px;">${agent.id}</div>
                            <div style="font-family: monospace; color: #4ade80; font-size: 1.1rem;">localhost:${agent.port}</div>
                            <div style="font-family: monospace; color: #888; font-size: 0.8rem;">Container IP: ${agent.ip || 'N/A'}</div>
                            <div style="color: ${statusColor}; font-size: 0.75rem; margin-top: 8px; text-transform: uppercase;">${agent.status}</div>
                        </div>
                    </a>
                `;
            }

            summaryHTML += `
                    </div>
                </div>
            `;

            // Add NetBox Registration Results section (if registration was performed)
            if (netboxResults.length > 0) {
                const registeredCount = netboxResults.filter(r => r.success && !r.skipped).length;
                const skippedCount = netboxResults.filter(r => r.skipped).length;
                const failCount = netboxResults.filter(r => !r.success).length;

                // Determine overall status color
                let statusColor = '#4ade80'; // green
                if (failCount > 0 && registeredCount === 0 && skippedCount === 0) {
                    statusColor = '#ef4444'; // red - all failed
                } else if (failCount > 0) {
                    statusColor = '#facc15'; // yellow - partial
                }

                // Build status text
                let statusText = `${registeredCount}/${netboxResults.length} REGISTERED`;
                if (skippedCount > 0) {
                    statusText = `${registeredCount} NEW, ${skippedCount} SKIPPED`;
                }

                // Store results globally for verification
                window.netboxRegistrationResults = netboxResults;
                window.netboxConfig = netboxConfig;

                summaryHTML += `
                <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 1px solid #06b6d4;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3 style="color: #06b6d4; display: flex; align-items: center; gap: 10px; margin: 0;">
                            📦 NetBox Registration
                            <span style="background: ${statusColor}; color: #1a1a2e; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: bold;">
                                ${statusText}
                            </span>
                            <span id="netbox-verify-status" style="font-size: 0.8rem; color: #888;"></span>
                        </h3>
                        <button onclick="verifyAllNetBoxDevices()" id="verify-all-btn" style="background: #06b6d4; color: #1a1a2e; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 0.85rem;">
                            🔍 Verify All in NetBox
                        </button>
                    </div>
                    <div id="netbox-results-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px;">
                `;

                for (const result of netboxResults) {
                    const isSuccess = result.success;
                    const isSkipped = result.skipped;

                    // Determine colors and status text based on state
                    let borderColor, statusIcon, statusLabel;
                    if (isSkipped) {
                        borderColor = '#6b7280'; // gray
                        statusIcon = '⏭️';
                        statusLabel = 'SKIPPED (exists)';
                    } else if (isSuccess) {
                        borderColor = '#4ade80'; // green
                        statusIcon = '✅';
                        statusLabel = 'REGISTERED';
                    } else {
                        borderColor = '#ef4444'; // red
                        statusIcon = '❌';
                        statusLabel = 'FAILED';
                    }

                    const cardId = `netbox-card-${result.agent_id.replace(/[^a-zA-Z0-9]/g, '-')}`;

                    summaryHTML += `
                        <div id="${cardId}" style="background: #16213e; border: 2px solid ${borderColor}; border-radius: 8px; padding: 12px;" data-device-url="${result.device_url || ''}" data-agent-id="${result.agent_id}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-weight: bold; color: #00d9ff;">${result.device_name || result.agent_id}</span>
                                <span class="reg-status" style="color: ${borderColor}; font-size: 0.75rem;">${statusIcon} ${statusLabel}</span>
                            </div>
                    `;

                    if ((isSuccess || isSkipped) && result.device_url) {
                        summaryHTML += `
                            <div style="display: flex; gap: 10px; align-items: center;">
                                <a href="${result.device_url}" target="_blank" style="display: inline-flex; align-items: center; gap: 5px; color: #06b6d4; text-decoration: none; font-size: 0.85rem;">
                                    🔗 View in NetBox
                                </a>
                                <span class="verify-status" style="font-size: 0.75rem; color: #888;"></span>
                            </div>
                        `;
                    } else if (result.error) {
                        summaryHTML += `
                            <div style="color: #ef4444; font-size: 0.8rem; word-break: break-word;">${result.error}</div>
                        `;
                    }

                    summaryHTML += `</div>`;
                }

                summaryHTML += `
                    </div>
                </div>
                `;

                // Add cables/topology section if cables were registered
                const cablesResult = window.netboxCablesResult;
                if (cablesResult && cablesResult.total > 0) {
                    const cableStatusColor = cablesResult.failed === 0 ? '#4ade80' :
                                             (cablesResult.created > 0 ? '#facc15' : '#ef4444');
                    summaryHTML += `
                    <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 1px solid #9333ea;">
                        <h3 style="color: #9333ea; display: flex; align-items: center; gap: 10px; margin: 0 0 15px 0;">
                            🔗 NetBox Topology (Cables)
                            <span style="background: ${cableStatusColor}; color: #1a1a2e; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: bold;">
                                ${cablesResult.created} CREATED, ${cablesResult.existing} EXISTING
                            </span>
                        </h3>
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 10px;">
                    `;

                    // Show created cables
                    for (const cable of (cablesResult.cables || []).slice(0, 10)) {
                        const statusIcon = cable.action === 'created' ? '✅' : '📎';
                        const statusText = cable.action === 'created' ? 'NEW' : 'EXISTS';
                        const cableLink = cable.url ? `<a href="${cable.url}" target="_blank" style="color: #06b6d4; font-size: 0.7rem; text-decoration: none; margin-left: 8px;" title="View in NetBox">🔗 NetBox</a>` : '';
                        summaryHTML += `
                            <div style="background: #16213e; border: 1px solid #9333ea; border-radius: 6px; padding: 10px;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-family: monospace; color: #00d9ff; font-size: 0.85rem;">
                                        ${cable.a_device}:${cable.a_interface}
                                        <span style="color: #9333ea;"> ↔ </span>
                                        ${cable.b_device}:${cable.b_interface}
                                    </span>
                                    <span style="font-size: 0.7rem; color: ${cable.action === 'created' ? '#4ade80' : '#888'};">
                                        ${statusIcon} ${statusText}${cableLink}
                                    </span>
                                </div>
                            </div>
                        `;
                    }

                    if ((cablesResult.cables || []).length > 10) {
                        summaryHTML += `
                            <div style="color: #888; font-size: 0.85rem; padding: 10px;">
                                ... and ${cablesResult.cables.length - 10} more cables
                            </div>
                        `;
                    }

                    // Show errors if any
                    if (cablesResult.failed > 0 && cablesResult.errors?.length > 0) {
                        summaryHTML += `
                            <div style="grid-column: 1 / -1; background: #2d1f1f; border: 1px solid #ef4444; border-radius: 6px; padding: 10px; margin-top: 10px;">
                                <div style="color: #ef4444; font-weight: bold; margin-bottom: 5px;">⚠️ ${cablesResult.failed} cables failed:</div>
                                <div style="color: #f87171; font-size: 0.8rem;">
                                    ${cablesResult.errors.slice(0, 3).join('<br>')}
                                    ${cablesResult.errors.length > 3 ? '<br>...' : ''}
                                </div>
                            </div>
                        `;
                    }

                    summaryHTML += `
                        </div>
                    </div>
                    `;
                }
            }

            summaryHTML += `
                <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                    <h3 style="color: #00d9ff; margin-bottom: 15px;">Quick Links</h3>
                    <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                        <a href="/monitor" target="_blank" style="background: #00d9ff; color: #1a1a2e; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">
                            📊 Full Agent Topology
                        </a>
                        <a href="/topology3d" target="_blank" style="background: #9333ea; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">
                            🌐 3D Network View
                        </a>
                    </div>
                </div>

                <div style="border-top: 1px solid #2a2a4e; padding-top: 20px; margin-top: 20px; text-align: center;">
                    <p style="color: #888; margin-bottom: 15px;">
                        The Network Builder is no longer needed. You can close it to free up port 8000.
                    </p>
                    <button onclick="closeBuilder()" style="background: #ef4444; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 1rem; font-weight: bold;">
                        🛑 Close Network Builder
                    </button>
                </div>
            `;

            // Replace step-5 content with summary (this is the active step when launching)
            const step5 = document.getElementById('step-5');
            console.log('step-5 element found:', !!step5);

            if (step5) {
                // Ensure step-5 is active/visible
                step5.classList.add('active');
                step5.innerHTML = `<div class="wizard-content">${summaryHTML}</div>`;
                console.log('Updated step-5 with launch summary');

                // Scroll to top so user sees the summary
                window.scrollTo(0, 0);
            } else {
                // Fallback: find the active wizard step
                const activeStep = document.querySelector('.wizard-step.active');
                console.log('Active step found:', !!activeStep);

                if (activeStep) {
                    activeStep.innerHTML = `<div class="wizard-content">${summaryHTML}</div>`;
                    console.log('Updated active wizard step with summary');
                } else {
                    // Last resort: create a modal/overlay
                    console.error('Could not find any wizard step to update');
                    const overlay = document.createElement('div');
                    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:#1a1a2e;z-index:9999;overflow:auto;padding:40px;';
                    overlay.innerHTML = summaryHTML;
                    document.body.appendChild(overlay);
                    console.log('Created overlay with summary');
                }
            }

            // Hide the wizard navigation at bottom
            const step5Nav = document.querySelector('#step-5 .wizard-nav');
            if (step5Nav) step5Nav.style.display = 'none';

            // Mark all progress steps as complete
            document.querySelectorAll('.step').forEach(step => step.classList.add('completed'));

            console.log('Summary page should now be visible');

    } catch (error) {
        console.error('Launch exception:', error);
        hideDeployProgress();  // Hide progress overlay on error
        showAlert(`Failed to launch network: ${error.message}`, 'error');
    }
}

// Open all agent dashboards function
function openAllAgentDashboards() {
    const agents = window.launchedAgents || [];
    if (agents.length === 0) {
        alert('No agents to open');
        return;
    }

    console.log(`Opening ${agents.length} agent dashboards...`);

    // Open each agent with a slight delay to avoid popup blockers
    agents.forEach((agent, index) => {
        setTimeout(() => {
            console.log(`Opening ${agent.id} at ${agent.url}`);
            const win = window.open(agent.url, `agent_${agent.id}`);
            if (!win) {
                console.warn(`Popup blocked for ${agent.id}. Please allow popups.`);
                if (index === 0) {
                    alert('Popup blocked! Please allow popups for this site, then click the button again.');
                }
            }
        }, index * 500); // 500ms between each to avoid blocking
    });
}

// Verify all NetBox device registrations
async function verifyAllNetBoxDevices() {
    const results = window.netboxRegistrationResults || [];
    const config = window.netboxConfig;

    if (results.length === 0 || !config) {
        alert('No NetBox registrations to verify');
        return;
    }

    const verifyBtn = document.getElementById('verify-all-btn');
    const statusSpan = document.getElementById('netbox-verify-status');

    if (verifyBtn) {
        verifyBtn.disabled = true;
        verifyBtn.textContent = '⏳ Verifying...';
    }
    if (statusSpan) {
        statusSpan.textContent = '';
    }

    console.log('[NetBox Verify] Starting verification of', results.length, 'devices');

    let verifiedCount = 0;
    let failedCount = 0;

    for (const result of results) {
        if (!result.success || !result.device_url) {
            // Skip failed registrations
            failedCount++;
            continue;
        }

        const cardId = `netbox-card-${result.agent_id.replace(/[^a-zA-Z0-9]/g, '-')}`;
        const card = document.getElementById(cardId);
        const verifyStatus = card?.querySelector('.verify-status');

        if (verifyStatus) {
            verifyStatus.textContent = '⏳ Checking...';
            verifyStatus.style.color = '#facc15';
        }

        try {
            const response = await fetch('/api/wizard/mcps/netbox/verify-device', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    device_url: result.device_url,
                    netbox_url: config.netbox_url,
                    api_token: config.api_token
                })
            });

            const verifyResult = await response.json();
            console.log(`[NetBox Verify] ${result.agent_id}:`, verifyResult);

            if (verifyResult.verified) {
                verifiedCount++;
                if (verifyStatus) {
                    verifyStatus.textContent = `✅ Verified (${verifyResult.status_label || 'Active'})`;
                    verifyStatus.style.color = '#4ade80';
                }
                if (card) {
                    card.style.borderColor = '#4ade80';
                }
            } else {
                failedCount++;
                if (verifyStatus) {
                    verifyStatus.textContent = `❌ ${verifyResult.error || 'Not found'}`;
                    verifyStatus.style.color = '#ef4444';
                }
                if (card) {
                    card.style.borderColor = '#ef4444';
                }
            }
        } catch (err) {
            console.error(`[NetBox Verify] Error verifying ${result.agent_id}:`, err);
            failedCount++;
            if (verifyStatus) {
                verifyStatus.textContent = `❌ ${err.message}`;
                verifyStatus.style.color = '#ef4444';
            }
        }

        // Small delay between requests to be nice to NetBox
        await new Promise(r => setTimeout(r, 200));
    }

    // Update summary
    if (verifyBtn) {
        verifyBtn.disabled = false;
        verifyBtn.textContent = '🔍 Verify All in NetBox';
    }
    if (statusSpan) {
        const totalChecked = verifiedCount + failedCount;
        if (failedCount === 0) {
            statusSpan.textContent = `✅ All ${verifiedCount} verified!`;
            statusSpan.style.color = '#4ade80';
        } else if (verifiedCount === 0) {
            statusSpan.textContent = `❌ ${failedCount} failed verification`;
            statusSpan.style.color = '#ef4444';
        } else {
            statusSpan.textContent = `⚠️ ${verifiedCount}/${totalChecked} verified`;
            statusSpan.style.color = '#facc15';
        }
    }

    console.log(`[NetBox Verify] Complete: ${verifiedCount} verified, ${failedCount} failed`);
}

// Close builder function
async function closeBuilder() {
    if (confirm('Close the Network Builder?\n\nYour deployed agents will continue running on their respective ports.')) {
        // Show shutdown message immediately
        const container = document.querySelector('.wizard-content') || document.querySelector('.container');
        if (container) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px 20px;">
                    <h2 style="color: #4ade80; margin-bottom: 20px;">✅ Builder Shutdown Initiated</h2>
                    <p style="color: #888; margin-bottom: 20px;">
                        The Network Builder is shutting down. Your agents are still running.
                    </p>
                    <p style="color: #00d9ff; margin-bottom: 20px;">
                        Closing browser tab...
                    </p>
                    <p style="color: #888; font-size: 0.9rem;">
                        To start the builder again later, run:<br>
                        <code style="background: #1a1a2e; padding: 8px 12px; border-radius: 4px; display: inline-block; margin-top: 10px; color: #4ade80;">
                            python3 wontyoubemyneighbor.py
                        </code>
                    </p>
                </div>
            `;
        }

        // Hide progress and buttons
        const progressContainer = document.querySelector('.progress-container');
        if (progressContainer) progressContainer.style.display = 'none';
        const buttonGroup = document.querySelector('.button-group');
        if (buttonGroup) buttonGroup.style.display = 'none';

        try {
            // Call shutdown endpoint
            await fetch('/api/wizard/shutdown', { method: 'POST' });
            console.log('Shutdown request sent successfully');
        } catch (error) {
            // Server may have already shut down, which is expected
            console.log('Shutdown in progress (connection closed as expected)');
        }

        // Attempt to close the browser tab/window after a short delay
        setTimeout(() => {
            closeBrowserTab();
        }, 1000);
    }
}

// Attempt to close the browser tab/window
function closeBrowserTab() {
    // Try multiple methods to close the tab
    try {
        // Method 1: Standard window.close() - works if page was opened by script
        window.close();

        // Method 2: For some browsers, opening about:blank then closing works
        setTimeout(() => {
            // If we're still here, try alternative approach
            window.open('about:blank', '_self');
            window.close();
        }, 500);

        // Method 3: If still open after 1 second, update message
        setTimeout(() => {
            const container = document.querySelector('.wizard-content') || document.querySelector('.container');
            if (container && document.visibilityState !== 'hidden') {
                container.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px;">
                        <h2 style="color: #4ade80; margin-bottom: 20px;">✅ Builder Shutdown Complete</h2>
                        <p style="color: #888; margin-bottom: 20px;">
                            The Network Builder has been shut down. Your agents are still running.
                        </p>
                        <p style="color: #facc15; margin-bottom: 20px;">
                            Please close this browser tab manually (Cmd+W / Ctrl+W)
                        </p>
                        <p style="color: #888; font-size: 0.9rem;">
                            To start the builder again later, run:<br>
                            <code style="background: #1a1a2e; padding: 8px 12px; border-radius: 4px; display: inline-block; margin-top: 10px; color: #4ade80;">
                                python3 wontyoubemyneighbor.py
                            </code>
                        </p>
                    </div>
                `;
            }
        }, 1500);

    } catch (e) {
        console.log('Could not close tab automatically:', e);
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

// =============================================================================
// NetBox Duplicate Detection
// =============================================================================

let netboxDuplicateResolver = null;

/**
 * Check for duplicate devices in NetBox before registration
 * @param {Object} netboxConfig - NetBox MCP configuration
 * @param {Array} agents - Array of agent objects with names
 * @returns {Promise<Object>} - Result with duplicates array
 */
async function checkNetBoxDuplicates(netboxConfig, agents) {
    const deviceNames = agents.map(a => a.name || a.id);
    console.log('[NetBox] Checking for duplicates:', deviceNames);

    try {
        const response = await fetch('/api/wizard/mcps/netbox/check-duplicates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                netbox_url: netboxConfig.netbox_url,
                api_token: netboxConfig.api_token,
                device_names: deviceNames
            })
        });

        const result = await response.json();
        console.log('[NetBox] Duplicate check result:', result);
        return result;
    } catch (err) {
        console.error('[NetBox] Error checking duplicates:', err);
        return { status: 'error', error: err.message, duplicates: [] };
    }
}

/**
 * Show the duplicate detection modal and wait for user choice
 * @param {Array} duplicates - Array of duplicate device info
 * @returns {Promise<string>} - User choice: 'cancel', 'skip', or 'update'
 */
function showNetBoxDuplicateModal(duplicates) {
    return new Promise((resolve) => {
        // Store resolver for use in closeNetBoxDuplicateModal
        netboxDuplicateResolver = resolve;

        // Hide the progress overlay so modal is clickable
        hideDeployProgress();

        // Populate the duplicates list
        const listEl = document.getElementById('duplicate-devices-list');
        listEl.innerHTML = duplicates.map(d => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #2a2a4e;">
                <div>
                    <strong style="color: #ffc107;">${d.name}</strong>
                    <div style="font-size: 0.85rem; color: #888;">
                        Site: ${d.site || 'Unknown'} | Status: ${d.status || 'unknown'}
                    </div>
                </div>
                <a href="${d.device_url}" target="_blank" style="color: #00d9ff; font-size: 0.85rem;">
                    View in NetBox &#8599;
                </a>
            </div>
        `).join('');

        // Show modal
        const modal = document.getElementById('netbox-duplicate-modal');
        modal.style.display = 'flex';
    });
}

/**
 * Close the duplicate modal and resolve with user choice
 * @param {string} choice - 'cancel', 'skip', or 'update'
 */
function closeNetBoxDuplicateModal(choice) {
    const modal = document.getElementById('netbox-duplicate-modal');
    modal.style.display = 'none';

    // Show progress overlay again (unless cancelled - it will be hidden at summary)
    if (choice !== 'cancel') {
        showDeployProgress();
        // Update status based on choice
        if (choice === 'skip') {
            setDeployStatus('Registering in NetBox...', 'Skipping existing devices...');
        } else if (choice === 'update') {
            setDeployStatus('Updating Devices...', 'Syncing existing devices with new configuration...');
        }
        updateDeployStep('netbox-check', 'complete');
        updateDeployStep('netbox-register', 'active');
    }

    if (netboxDuplicateResolver) {
        netboxDuplicateResolver(choice);
        netboxDuplicateResolver = null;
    }
}

// ============================================================================
// Deployment Progress Overlay Functions
// ============================================================================

/**
 * Show the deployment progress overlay
 */
function showDeployProgress() {
    const overlay = document.getElementById('deploy-progress-overlay');
    if (overlay) {
        overlay.style.display = 'flex';
        // Reset all steps to initial state
        updateDeployStep('containers', 'active');
        updateDeployStep('netbox-check', 'pending');
        updateDeployStep('netbox-register', 'pending');
        updateDeployStep('cables', 'pending');
        setDeployCurrentAgent(null);
    }
}

/**
 * Hide the deployment progress overlay
 */
function hideDeployProgress() {
    const overlay = document.getElementById('deploy-progress-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

/**
 * Update deployment status message
 * @param {string} title - Main status title
 * @param {string} message - Detailed status message
 */
function setDeployStatus(title, message) {
    const titleEl = document.getElementById('deploy-status-title');
    const messageEl = document.getElementById('deploy-status-message');
    if (titleEl) titleEl.textContent = title;
    if (messageEl) messageEl.textContent = message;
}

/**
 * Update a deployment step's visual state
 * @param {string} stepId - Step identifier (containers, netbox-check, netbox-register, cables)
 * @param {string} state - State: 'pending', 'active', 'complete', 'error', 'skipped'
 */
function updateDeployStep(stepId, state) {
    const step = document.getElementById(`deploy-step-${stepId}`);
    if (!step) return;

    const iconSpan = step.querySelector('.step-icon span');
    const textSpan = step.querySelector('span:last-child');

    // Reset opacity
    step.style.opacity = state === 'pending' ? '0.5' : '1';

    // Update icon and colors based on state
    switch (state) {
        case 'pending':
            iconSpan.textContent = '○';
            iconSpan.style.color = '#666';
            textSpan.style.color = '#888';
            break;
        case 'active':
            iconSpan.textContent = '⏳';
            iconSpan.style.color = '#ffc107';
            textSpan.style.color = '#ccc';
            break;
        case 'complete':
            iconSpan.textContent = '✓';
            iconSpan.style.color = '#4ade80';
            textSpan.style.color = '#4ade80';
            break;
        case 'error':
            iconSpan.textContent = '✗';
            iconSpan.style.color = '#ef4444';
            textSpan.style.color = '#ef4444';
            break;
        case 'skipped':
            iconSpan.textContent = '–';
            iconSpan.style.color = '#6c757d';
            textSpan.style.color = '#6c757d';
            break;
    }
}

/**
 * Show the current agent being processed
 * @param {string|null} agentName - Agent name or null to hide
 */
function setDeployCurrentAgent(agentName) {
    const container = document.getElementById('deploy-current-agent');
    const nameSpan = document.getElementById('deploy-agent-name');
    if (container && nameSpan) {
        if (agentName) {
            nameSpan.textContent = agentName;
            container.style.display = 'block';
        } else {
            container.style.display = 'none';
        }
    }
}
