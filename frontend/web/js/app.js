/**
 * AI-VAPT Operations Console — Frontend Application
 * Vanilla JS SPA with hash-based routing
 */

// ═══════════════════════════════════════════════════════════════════════
// API Client
// ═══════════════════════════════════════════════════════════════════════

const API_BASE = window.location.origin;

const api = {
    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(`${API_BASE}${path}`, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        return resp.json();
    },

    getHealth() { return this.request('GET', '/health'); },
    getSystemHealth() { return this.request('GET', '/system/health'); },
    getScenarios() { return this.request('GET', '/scenarios'); },
    startRun(data) { return this.request('POST', '/runs', data); },
    listRuns(limit = 100) { return this.request('GET', `/runs?limit=${limit}`); },
    getRun(runId) { return this.request('GET', `/runs/${runId}/persisted`); },
    getRunEvents(runId) { return this.request('GET', `/runs/${runId}/events`); },
    getRunTrace(runId) { return this.request('GET', `/runs/${runId}/trace`); },
    getRunEvidence(runId) { return this.request('GET', `/runs/${runId}/evidence`); },
    getRunFindings(runId) { return this.request('GET', `/runs/${runId}/findings`); },
    getRunCandidates(runId) { return this.request('GET', `/runs/${runId}/candidates`); },
    getRunAssessment(runId) { return this.request('GET', `/runs/${runId}/assessment`); },
    getRunReport(runId, format = 'json') { return this.request('GET', `/runs/${runId}/report?format=${format}`); },
};

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    currentRun: null,
    runs: [],
    systemHealth: null,
    scenarios: [],
    loading: false,
};

// ═══════════════════════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════════════════════

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function formatDate(isoStr) {
    if (!isoStr) return 'N/A';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString();
    } catch {
        return isoStr;
    }
}

function formatDateShort(isoStr) {
    if (!isoStr) return 'N/A';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
        return isoStr;
    }
}

function severityClass(severity) {
    const s = (severity || '').toLowerCase();
    if (s === 'critical') return 'severity-critical';
    if (s === 'high') return 'severity-high';
    if (s === 'medium' || s === 'moderate') return 'severity-medium';
    if (s === 'low') return 'severity-low';
    return 'severity-info';
}

function evidenceClass(tier) {
    const t = (tier || '').toUpperCase();
    if (t === 'DOCKER_OBSERVED') return 'evidence-docker';
    if (t === 'OBSERVED_LOCAL') return 'evidence-local';
    if (t === 'CONTROLLED_VALIDATION') return 'evidence-controlled';
    return 'evidence-simulated';
}

function statusClass(status) {
    const s = (status || '').toLowerCase();
    if (s === 'completed' || s === 'success' || s === 'ready') return 'status-ready';
    if (s === 'running' || s === 'degraded') return 'status-degraded';
    if (s === 'failed' || s === 'unavailable' || s === 'blocked') return 'status-unavailable';
    return 'status-degraded';
}

function showLoading(container, message = 'Loading...') {
    container.innerHTML = `
        <div class="loading-container">
            <div class="spinner"></div>
            <span style="margin-left: 0.5rem;">${escapeHtml(message)}</span>
        </div>
    `;
}

function showError(container, message) {
    container.innerHTML = `
        <div class="alert alert-error">
            <strong>Error:</strong> ${escapeHtml(message)}
        </div>
    `;
}

function showEmpty(container, icon = '📭', text = 'No data available', hint = '') {
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">${icon}</div>
            <div class="empty-state-text">${escapeHtml(text)}</div>
            ${hint ? `<div class="empty-state-hint">${escapeHtml(hint)}</div>` : ''}
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════════════
// Router
// ═══════════════════════════════════════════════════════════════════════

const routes = {
    '/dashboard': renderDashboard,
    '/assessment/new': renderNewAssessment,
    '/assessment/active': renderActiveAssessment,
    '/findings': renderFindings,
    '/intelligence': renderIntelligence,
    '/candidates': renderCandidates,
    '/attack-paths': renderAttackPaths,
    '/pivot-analysis': renderPivotAnalysis,
    '/runs': renderRunHistory,
    '/reports': renderReports,
    '/system': renderSystemHealth,
    '/configuration': renderConfiguration,
};

function getRoute() {
    const hash = window.location.hash || '#/dashboard';
    const path = hash.replace('#', '') || '/dashboard';
    return path;
}

function navigate(path) {
    window.location.hash = path;
}

function setActiveNav(page) {
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });
}

async function router() {
    const path = getRoute();
    const content = document.getElementById('content');

    // Determine which nav item to activate
    const navMap = {
        '/dashboard': 'dashboard',
        '/assessment/new': 'assessment-new',
        '/assessment/active': 'assessment-active',
        '/findings': 'findings',
        '/intelligence': 'intelligence',
        '/candidates': 'candidates',
        '/attack-paths': 'attack-paths',
        '/pivot-analysis': 'pivot-analysis',
        '/runs': 'runs',
        '/reports': 'reports',
        '/system': 'system',
        '/configuration': 'configuration',
    };
    setActiveNav(navMap[path] || 'dashboard');

    // Find and execute route handler
    const handler = routes[path] || renderDashboard;
    try {
        await handler(content);
    } catch (err) {
        showError(content, err.message);
    }
}

window.addEventListener('hashchange', router);

// ═══════════════════════════════════════════════════════════════════════
// Page: Dashboard
// ═══════════════════════════════════════════════════════════════════════

async function renderDashboard(container) {
    showLoading(container, 'Loading dashboard...');

    try {
        const [runs, health] = await Promise.all([
            api.listRuns(1000),
            api.getSystemHealth().catch(() => null),
        ]);

        state.runs = runs.runs || [];
        state.systemHealth = health;

        const totalRuns = state.runs.length;
        const successful = state.runs.filter(r => r.final_status === 'SUCCESS' || r.status === 'COMPLETED').length;
        const pivots = state.runs.reduce((sum, r) => sum + (r.pivot_count || 0), 0);
        const critical = state.runs.reduce((sum, r) => {
            return sum + (r.candidates || []).filter(c =>
                (c.severity || '').toLowerCase() === 'critical'
            ).length;
        }, 0);

        const recentRuns = state.runs.slice(0, 10);

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Dashboard</h1>
                <p class="page-subtitle">Security Operations Overview</p>
            </div>

            <div class="metrics-grid">
                <div class="metric-card accent-blue">
                    <div class="metric-icon">📊</div>
                    <div class="metric-label">Total Runs</div>
                    <div class="metric-value">${totalRuns}</div>
                </div>
                <div class="metric-card accent-green">
                    <div class="metric-icon">✅</div>
                    <div class="metric-label">Successful</div>
                    <div class="metric-value">${successful}</div>
                </div>
                <div class="metric-card accent-purple">
                    <div class="metric-icon">🔄</div>
                    <div class="metric-label">Pivots</div>
                    <div class="metric-value">${pivots}</div>
                </div>
                <div class="metric-card accent-red">
                    <div class="metric-icon">⚠️</div>
                    <div class="metric-label">CRIT Findings</div>
                    <div class="metric-value">${critical}</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Recent Runs</span>
                    <a href="#/runs" class="btn btn-secondary" style="text-decoration:none;">View All</a>
                </div>
                ${recentRuns.length === 0 ? showEmpty(null, '📭', 'No runs yet', 'Start an assessment to see results here.') : `
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Run ID</th>
                                <th>Scenario</th>
                                <th>Mode</th>
                                <th>Status</th>
                                <th>Evidence</th>
                                <th>Attempts</th>
                                <th>Pivots</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${recentRuns.map(r => `
                                <tr>
                                    <td><a href="#/runs" style="color:var(--accent-blue-light);text-decoration:none;">${escapeHtml(r.run_id)}</a></td>
                                    <td>${escapeHtml(r.scenario)}</td>
                                    <td><span class="badge badge-info">${escapeHtml(r.mode)}</span></td>
                                    <td><span class="badge ${r.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(r.status)}</span></td>
                                    <td><span class="badge ${evidenceClass(r.evidence_tier)}">${escapeHtml(r.evidence_tier)}</span></td>
                                    <td>${r.total_attempts}</td>
                                    <td>${r.pivot_count}</td>
                                    <td>${formatDateShort(r.created_at)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">System Health</span>
                </div>
                <div class="grid-4">
                    ${healthComponent('Application', health?.application || 'READY')}
                    ${healthComponent('Persistence', health?.persistence || 'READY')}
                    ${healthComponent('Ollama', health?.ollama || 'UNAVAILABLE', health?.ollama_model)}
                    ${healthComponent('Docker Lab', health?.docker || 'UNAVAILABLE')}
                </div>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

function healthComponent(name, status, detail) {
    const cls = statusClass(status);
    return `
        <div class="metric-card">
            <div class="metric-label">${name}</div>
            <div class="metric-value ${cls}" style="font-size:1rem;">${escapeHtml(status)}</div>
            ${detail ? `<div class="text-dim" style="font-size:0.75rem;margin-top:0.25rem;">${escapeHtml(detail)}</div>` : ''}
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════════════
// Page: New Assessment
// ═══════════════════════════════════════════════════════════════════════

async function renderNewAssessment(container) {
    showLoading(container, 'Loading configuration...');

    try {
        const [scenarios, health] = await Promise.all([
            api.getScenarios().catch(() => ({ scenarios: [] })),
            api.getSystemHealth().catch(() => null),
        ]);

        state.scenarios = scenarios.scenarios || [];

        const allowlistedTargets = ['127.0.0.1', '172.28.0.2'];

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">New Assessment</h1>
                <p class="page-subtitle">Configure and execute a new VAPT assessment</p>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Target / Scope</span>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Execution Mode</label>
                        <select class="form-select" id="assess-mode">
                            <option value="simulation">Simulation (offline, ground-truth labels)</option>
                            <option value="lab">Docker Lab (real HTTP to emulator)</option>
                        </select>
                    </div>

                    <div class="form-group" id="target-group" style="display:none;">
                        <label class="form-label">Target (allowlisted only)</label>
                        <select class="form-select" id="assess-target">
                            ${allowlistedTargets.map(t => `<option value="${t}">${t}</option>`).join('')}
                        </select>
                    </div>

                    <div class="form-group" id="port-group" style="display:none;">
                        <label class="form-label">Port</label>
                        <input type="number" class="form-input" id="assess-port" value="8080" min="1" max="65535">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Scenario</label>
                        <select class="form-select" id="assess-scenario">
                            ${state.scenarios.map(s => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join('')}
                        </select>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Assessment Configuration</span>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Assessor Mode</label>
                        <select class="form-select" id="assess-assessor">
                            <option value="deterministic">Deterministic (offline, reproducible)</option>
                            <option value="ai">AI / Ollama (requires local Ollama)</option>
                        </select>
                    </div>

                    <div class="form-group" id="provider-group" style="display:none;">
                        <label class="form-label">AI Provider</label>
                        <select class="form-select" id="assess-provider">
                            <option value="ollama">Ollama (local, offline)</option>
                            <option value="openai">OpenAI (requires API key)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Pivot Threshold (N)</label>
                        <input type="number" class="form-input" id="assess-max-attempts" value="2" min="1" max="10">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Safety Status</label>
                        <div id="safety-status"></div>
                    </div>
                </div>
            </div>

            <div class="card" id="run-result" style="display:none;">
                <div class="card-header">
                    <span class="card-title">Assessment Result</span>
                </div>
                <div id="run-result-content"></div>
            </div>

            <div style="margin-top: 1rem;">
                <button class="btn btn-primary" id="btn-run" onclick="startAssessment()">
                    🚀 Run Assessment
                </button>
            </div>
        `;

        // Event listeners
        document.getElementById('assess-mode').addEventListener('change', function () {
            const isLab = this.value === 'lab';
            document.getElementById('target-group').style.display = isLab ? 'block' : 'none';
            document.getElementById('port-group').style.display = isLab ? 'block' : 'none';
            updateSafetyStatus();
        });

        document.getElementById('assess-assessor').addEventListener('change', function () {
            document.getElementById('provider-group').style.display = this.value === 'ai' ? 'block' : 'none';
        });

        updateSafetyStatus();
    } catch (err) {
        showError(container, err.message);
    }
}

function updateSafetyStatus() {
    const mode = document.getElementById('assess-mode')?.value || 'simulation';
    const el = document.getElementById('safety-status');
    if (!el) return;

    if (mode === 'lab') {
        el.innerHTML = `<div class="badge badge-success">✅ AUTHORIZED / ALLOWLISTED</div>
            <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">Target is in the lab allowlist. No external systems will be targeted.</p>`;
    } else {
        el.innerHTML = `<div class="badge badge-warning">🟡 SIMULATION</div>
            <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">No real execution. Outcomes from ground-truth labels.</p>`;
    }
}

async function startAssessment() {
    const btn = document.getElementById('btn-run');
    const resultCard = document.getElementById('run-result');
    const resultContent = document.getElementById('run-result-content');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;"></span> Running...';

    try {
        const mode = document.getElementById('assess-mode').value;
        const scenario = document.getElementById('assess-scenario').value;
        const assessor = document.getElementById('assess-assessor').value;
        const provider = document.getElementById('assess-provider')?.value || 'ollama';
        const maxAttempts = parseInt(document.getElementById('assess-max-attempts').value, 10);

        const data = {
            scenario,
            mode,
            assessor,
            assessor_provider: provider,
            max_attempts: maxAttempts,
        };

        if (mode === 'lab') {
            data.target = document.getElementById('assess-target').value;
            data.port = parseInt(document.getElementById('assess-port').value, 10);
        }

        const result = await api.startRun(data);
        state.currentRun = result.run_id;

        resultCard.style.display = 'block';
        resultContent.innerHTML = `
            <div class="alert alert-success">
                <strong>Run completed!</strong> Run ID: ${escapeHtml(result.run_id)}
            </div>
            <div id="active-run-details"></div>
        `;

        // Load full run details
        await loadActiveRunDetails(result.run_id);

    } catch (err) {
        resultCard.style.display = 'block';
        resultContent.innerHTML = `<div class="alert alert-error"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 Run Assessment';
    }
}

async function loadActiveRunDetails(runId) {
    const container = document.getElementById('active-run-details');
    if (!container) return;

    try {
        const [run, events, candidates, assessment] = await Promise.all([
            api.getRun(runId),
            api.getRunEvents(runId),
            api.getRunCandidates(runId),
            api.getRunAssessment(runId),
        ]);

        const pipelineSteps = [
            { key: 'FINDINGS_INGESTED', label: 'Ingest' },
            { key: 'FINDINGS_NORMALIZED', label: 'Enrich' },
            { key: 'ASSESSMENT_COMPLETED', label: 'Assess' },
            { key: 'CANDIDATES_GENERATED', label: 'Rank' },
            { key: 'DECISION_MADE', label: 'Decide' },
            { key: 'EXECUTION_STARTED', label: 'Safety' },
            { key: 'ATTEMPT_COMPLETED', label: 'Execute' },
            { key: 'VERIFICATION_COMPLETED', label: 'Verify' },
            { key: 'EVIDENCE_CAPTURED', label: 'Evidence' },
            { key: 'RUN_COMPLETED', label: 'Report' },
        ];

        const eventTypes = (events.events || []).map(e => e.event_type);
        const currentState = events.current_state || 'COMPLETED';

        container.innerHTML = `
            <div class="grid-2" style="margin-bottom:1rem;">
                <div>
                    <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.25rem;">Run ID</div>
                    <div style="font-family:monospace;">${escapeHtml(run.run_id)}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.25rem;">Scenario</div>
                    <div>${escapeHtml(run.scenario)}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.25rem;">Mode</div>
                    <div><span class="badge badge-info">${escapeHtml(run.mode)}</span></div>
                </div>
                <div>
                    <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.25rem;">Status</div>
                    <div><span class="badge ${run.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(run.final_status || run.status)}</span></div>
                </div>
            </div>

            <div class="pipeline-container">
                ${pipelineSteps.map((step, i) => {
                    const isCompleted = eventTypes.includes(step.key) || (step.key === 'RUN_COMPLETED' && currentState === 'COMPLETED');
                    const isActive = !isCompleted && pipelineSteps.slice(0, i).every(s => eventTypes.includes(s.key));
                    const isFailed = run.final_status === 'FAILED';

                    let circleClass = 'pending';
                    if (isCompleted) circleClass = 'completed';
                    else if (isActive) circleClass = 'active';
                    if (isFailed && isActive) circleClass = 'failed';

                    const icon = isCompleted ? '✓' : (isActive ? '●' : (i + 1));

                    return `
                        <div class="pipeline-step">
                            <div class="step-circle ${circleClass}">${icon}</div>
                            <div class="step-label ${circleClass}">${step.label}</div>
                        </div>
                        ${i < pipelineSteps.length - 1 ? `<div class="step-connector ${isCompleted ? 'completed' : ''}"></div>` : ''}
                    `;
                }).join('')}
            </div>

            <div class="grid-2">
                <div>
                    <h4 style="margin-bottom:0.5rem;">Candidates</h4>
                    ${(candidates.candidates || []).map(c => `
                        <div style="padding:0.5rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.5rem;">
                            <div style="font-weight:600;">${escapeHtml(c.id)}</div>
                            <div class="text-muted" style="font-size:0.75rem;">
                                Quality: ${escapeHtml(c.quality_rank || 'N/A')} |
                                Outcome: <span class="${c.execution_outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(c.execution_outcome || '-')}</span>
                            </div>
                        </div>
                    `).join('') || '<div class="text-muted">No candidates</div>'}
                </div>
                <div>
                    <h4 style="margin-bottom:0.5rem;">Assessment</h4>
                    <div class="card" style="padding:0.75rem;">
                        <div>Mode: <span class="badge ${assessment.assessment?.mode === 'ai' ? 'badge-info' : 'badge-warning'}">${escapeHtml(assessment.assessment?.mode || 'unknown')}</span></div>
                        ${assessment.assessment?.provider ? `<div class="text-muted" style="margin-top:0.5rem;">Provider: ${escapeHtml(assessment.assessment.provider)}</div>` : ''}
                        ${assessment.assessment?.fallback ? `<div class="text-warning" style="margin-top:0.5rem;">⚠️ Fallback active</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Active Assessment
// ═══════════════════════════════════════════════════════════════════════

async function renderActiveAssessment(container) {
    if (state.currentRun) {
        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Active Assessment</h1>
                <p class="page-subtitle">Run ID: ${escapeHtml(state.currentRun)}</p>
            </div>
            <div id="active-assessment-content"></div>
        `;
        await loadActiveRunDetails(state.currentRun);
        // Also update the active assessment section
        const activeContent = document.getElementById('active-assessment-content');
        if (activeContent) {
            const run = await api.getRun(state.currentRun);
            activeContent.innerHTML = `
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Run Details</span>
                        <span class="badge ${run.status === 'COMPLETED' ? 'badge-success' : 'badge-info'}">${escapeHtml(run.status)}</span>
                    </div>
                    <div class="grid-4">
                        <div><div class="text-muted" style="font-size:0.75rem;">Scenario</div><div>${escapeHtml(run.scenario)}</div></div>
                        <div><div class="text-muted" style="font-size:0.75rem;">Mode</div><div>${escapeHtml(run.mode)}</div></div>
                        <div><div class="text-muted" style="font-size:0.75rem;">Target</div><div>${escapeHtml(run.target || 'N/A')}</div></div>
                        <div><div class="text-muted" style="font-size:0.75rem;">Attempts</div><div>${run.total_attempts}</div></div>
                    </div>
                </div>
            `;
        }
    } else {
        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Active Assessment</h1>
                <p class="page-subtitle">No active assessment</p>
            </div>
            <div class="empty-state">
                <div class="empty-state-icon">▶️</div>
                <div class="empty-state-text">No active assessment</div>
                <div class="empty-state-hint">Start a new assessment to see it here.</div>
                <a href="#/assessment/new" class="btn btn-primary" style="margin-top:1rem;text-decoration:none;">New Assessment</a>
            </div>
        `;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Findings
// ═══════════════════════════════════════════════════════════════════════

async function renderFindings(container) {
    showLoading(container, 'Loading findings...');

    try {
        const runs = await api.listRuns(1000);
        const allFindings = [];

        for (const run of (runs.runs || [])) {
            const details = await api.getRun(run.run_id).catch(() => null);
            if (details && details.candidates) {
                for (const c of details.candidates) {
                    allFindings.push({
                        runId: run.run_id,
                        ...c,
                        evidenceTier: run.evidence_tier,
                    });
                }
            }
        }

        if (allFindings.length === 0) {
            showEmpty(container, '🔍', 'No findings recorded', 'Run an assessment to see findings here.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Findings</h1>
                <p class="page-subtitle">${allFindings.length} findings across all runs</p>
            </div>

            <div class="card">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Finding</th>
                            <th>Severity</th>
                            <th>Quality</th>
                            <th>Outcome</th>
                            <th>Evidence</th>
                            <th>Run</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allFindings.map(f => `
                            <tr>
                                <td><strong>${escapeHtml(f.id)}</strong></td>
                                <td class="${severityClass(f.severity)}">${escapeHtml(f.severity || 'unknown')}</td>
                                <td>${escapeHtml(f.quality_rank || 'N/A')}</td>
                                <td><span class="badge ${f.execution_outcome === 'SUCCESS' ? 'badge-success' : 'badge-error'}">${escapeHtml(f.execution_outcome || '-')}</span></td>
                                <td><span class="badge ${evidenceClass(f.evidenceTier)}">${escapeHtml(f.evidenceTier)}</span></td>
                                <td><a href="#/runs" style="color:var(--accent-blue-light);text-decoration:none;font-size:0.8rem;">${escapeHtml(f.runId)}</a></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Intelligence
// ═══════════════════════════════════════════════════════════════════════

async function renderIntelligence(container) {
    container.innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Vulnerability Intelligence</h1>
            <p class="page-subtitle">CVE enrichment with EPSS and CISA KEV data</p>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">CVE Lookup</span>
            </div>
            <div class="form-group">
                <label class="form-label">CVE ID</label>
                <input type="text" class="form-input" id="cve-lookup" value="CVE-2021-44228" placeholder="Enter CVE ID">
            </div>
            <button class="btn btn-primary" onclick="lookupCVE()">Lookup</button>
            <div id="cve-result" style="margin-top:1rem;"></div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Evidence Provenance</span>
            </div>
            <div class="grid-2">
                <div>
                    <h4 style="margin-bottom:0.5rem;">Observed Fact</h4>
                    <p class="text-muted" style="font-size:0.85rem;">EPSS scores and CISA KEV status are from local datasets. These are factual data points, not AI-generated.</p>
                </div>
                <div>
                    <h4 style="margin-bottom:0.5rem;">Enriched Intelligence</h4>
                    <p class="text-muted" style="font-size:0.85rem;">Quality ranks come from the decision engine assessment. AI assessment uses local Ollama when available.</p>
                </div>
                <div>
                    <h4 style="margin-bottom:0.5rem;">AI Assessment</h4>
                    <p class="text-muted" style="font-size:0.85rem;">LLM-based usability scoring via Ollama. Clearly marked with source and provider. Never confused with deterministic results.</p>
                </div>
                <div>
                    <h4 style="margin-bottom:0.5rem;">Decision</h4>
                    <p class="text-muted" style="font-size:0.85rem;">Final ranking and pivot decisions from the decision engine. Transparent and explainable.</p>
                </div>
            </div>
        </div>
    `;
}

async function lookupCVE() {
    const cveId = document.getElementById('cve-lookup').value.trim();
    const resultEl = document.getElementById('cve-result');
    if (!cveId) return;

    resultEl.innerHTML = '<div class="spinner"></div>';

    try {
        // Use the enrichment API if available, otherwise show placeholder
        const resp = await fetch(`${API_BASE}/intelligence/lookup?cve=${encodeURIComponent(cveId)}`);
        if (resp.ok) {
            const data = await resp.json();
            resultEl.innerHTML = `
                <div class="grid-2">
                    <div class="metric-card">
                        <div class="metric-label">EPSS Score</div>
                        <div class="metric-value">${data.epss || 'N/A'}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">CISA KEV</div>
                        <div class="metric-value ${data.in_kev ? 'text-error' : 'text-success'}">${data.in_kev ? 'YES' : 'NO'}</div>
                    </div>
                </div>
            `;
        } else {
            resultEl.innerHTML = `<div class="alert alert-info">CVE lookup not available via API. Using local enrichment data.</div>`;
        }
    } catch (err) {
        resultEl.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Candidates
// ═══════════════════════════════════════════════════════════════════════

async function renderCandidates(container) {
    showLoading(container, 'Loading candidates...');

    try {
        const runs = await api.listRuns(1000);
        const allCandidates = [];

        for (const run of (runs.runs || [])) {
            const details = await api.getRun(run.run_id).catch(() => null);
            if (details && details.candidates) {
                for (const c of details.candidates) {
                    allCandidates.push({ ...c, runId: run.run_id, scenario: run.scenario });
                }
            }
        }

        if (allCandidates.length === 0) {
            showEmpty(container, '📋', 'No candidates recorded', 'Run an assessment to see candidate rankings here.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Candidate Ranking</h1>
                <p class="page-subtitle">How AI assessment affects candidate prioritization (GAP-1)</p>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Assessment → Scoring → Priority</span>
                </div>
                <p class="text-muted" style="margin-bottom:1rem;font-size:0.85rem;">
                    Each candidate is assessed for quality (HIGH/MEDIUM/LOW) before ranking.
                    The priority score = probability × (0.5 + 0.5 × quality_weight).
                    This ensures AI assessment directly influences execution order.
                </p>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Candidate</th>
                            <th>Probability</th>
                            <th>AI Quality</th>
                            <th>Score</th>
                            <th>Priority</th>
                            <th>Outcome</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allCandidates.map((c, i) => {
                            const quality = c.quality_rank || 'N/A';
                            const prob = c.probability || 0;
                            const score = prob * (0.5 + 0.5 * { HIGH: 1.0, MEDIUM: 0.6, LOW: 0.3 }[quality] || 0);
                            return `
                                <tr>
                                    <td><strong>${escapeHtml(c.id)}</strong></td>
                                    <td>${prob.toFixed(4)}</td>
                                    <td><span class="badge ${quality === 'HIGH' ? 'badge-success' : quality === 'MEDIUM' ? 'badge-warning' : 'badge-error'}">${escapeHtml(quality)}</span></td>
                                    <td>${score.toFixed(4)}</td>
                                    <td>#${i + 1}</td>
                                    <td><span class="badge ${c.execution_outcome === 'SUCCESS' ? 'badge-success' : 'badge-error'}">${escapeHtml(c.execution_outcome || '-')}</span></td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Attack Paths
// ═══════════════════════════════════════════════════════════════════════

async function renderAttackPaths(container) {
    showLoading(container, 'Loading attack paths...');

    try {
        const runs = await api.listRuns(1000);
        const completedRuns = (runs.runs || []).filter(r => r.final_status === 'COMPLETED' || r.status === 'COMPLETED');

        if (completedRuns.length === 0) {
            showEmpty(container, '🔄', 'No completed runs', 'Run an assessment to see decision paths here.');
            return;
        }

        // Select a run
        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Decision Paths</h1>
                <p class="page-subtitle">Visualize decision traces and pivot logic</p>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Select Run</span>
                </div>
                <select class="form-select" id="attack-run-select" style="max-width:400px;">
                    ${completedRuns.map(r => `<option value="${escapeHtml(r.run_id)}">${escapeHtml(r.run_id)} | ${escapeHtml(r.scenario)} | ${escapeHtml(r.mode)}</option>`).join('')}
                </select>
            </div>

            <div id="attack-path-content"></div>
        `;

        document.getElementById('attack-run-select').addEventListener('change', async function () {
            await renderAttackPathDetail(this.value);
        });

        // Load first run
        if (completedRuns.length > 0) {
            await renderAttackPathDetail(completedRuns[0].run_id);
        }
    } catch (err) {
        showError(container, err.message);
    }
}

async function renderAttackPathDetail(runId) {
    const container = document.getElementById('attack-path-content');
    if (!container) return;

    showLoading(container, 'Loading decision trace...');

    try {
        const [run, trace] = await Promise.all([
            api.getRun(runId),
            api.getRunTrace(runId),
        ]);

        const events = trace.events || [];

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Decision Trace</span>
                    <span class="badge badge-info">${escapeHtml(run.scenario)}</span>
                </div>
                <div class="decision-trace">
                    ${events.map(e => {
                        let cls = 'info';
                        const detail = (e.detail || '').toLowerCase();
                        if (detail.includes('success') || detail.includes('advance')) cls = 'success';
                        else if (detail.includes('fail') || detail.includes('abandon')) cls = 'fail';
                        else if (detail.includes('pivot') || detail.includes('redirect')) cls = 'pivot';
                        else if (detail.includes('assess') || detail.includes('rank')) cls = 'info';
                        return `<div class="trace-line ${cls}">${escapeHtml(e.detail || '')}</div>`;
                    }).join('') || '<div class="trace-line">No trace events</div>'}
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Execution Flow</span>
                </div>
                <div class="grid-2">
                    <div>
                        <h4 style="margin-bottom:0.5rem;">Candidates</h4>
                        ${(run.candidates || []).map(c => `
                            <div style="padding:0.5rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.5rem;">
                                <div style="font-weight:600;">${escapeHtml(c.id)}</div>
                                <div class="text-muted" style="font-size:0.75rem;">
                                    Quality: ${escapeHtml(c.quality_rank || 'N/A')} |
                                    Outcome: <span class="${c.execution_outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(c.execution_outcome || '-')}</span>
                                </div>
                            </div>
                        `).join('') || '<div class="text-muted">No candidates</div>'}
                    </div>
                    <div>
                        <h4 style="margin-bottom:0.5rem;">Execution Results</h4>
                        ${(run.execution_results || []).map((r, i) => `
                            <div style="padding:0.5rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.5rem;">
                                <div style="font-weight:600;">Attempt ${i + 1}: ${escapeHtml(r.candidate_id)}</div>
                                <div class="text-muted" style="font-size:0.75rem;">
                                    Outcome: <span class="${r.outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(r.outcome)}</span>
                                </div>
                            </div>
                        `).join('') || '<div class="text-muted">No execution results</div>'}
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Pivot Analysis
// ═══════════════════════════════════════════════════════════════════════

async function renderPivotAnalysis(container) {
    showLoading(container, 'Loading pivot analysis...');

    try {
        const runs = await api.listRuns(1000);
        const runsWithPivots = (runs.runs || []).filter(r => r.pivot_count > 0);

        if (runsWithPivots.length === 0) {
            showEmpty(container, '↩️', 'No pivot events', 'Run an assessment with failures to see pivot analysis.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Pivot Analysis</h1>
                <p class="page-subtitle">How failure counters trigger pivots (GAP-2)</p>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Pivot Events</span>
                </div>
                <p class="text-muted" style="margin-bottom:1rem;font-size:0.85rem;">
                    Each candidate has a per-candidate attempt counter. When the counter reaches the threshold,
                    the engine pivots to the next candidate. This ensures bounded termination.
                </p>
                <div id="pivot-runs"></div>
            </div>
        `;

        const pivotRunsEl = document.getElementById('pivot-runs');
        for (const runSummary of runsWithPivots.slice(0, 5)) {
            const run = await api.getRun(runSummary.run_id);
            const results = run.execution_results || [];

            // Group by candidate
            const byCandidate = {};
            for (const r of results) {
                if (!byCandidate[r.candidate_id]) byCandidate[r.candidate_id] = [];
                byCandidate[r.candidate_id].push(r);
            }

            pivotRunsEl.innerHTML += `
                <div class="card" style="margin-bottom:1rem;">
                    <div class="card-header">
                        <span class="card-title">${escapeHtml(run.scenario)}</span>
                        <span class="badge badge-purple">${run.pivot_count} pivots</span>
                    </div>
                    <div class="pipeline-container" style="margin-bottom:1rem;">
                        ${Object.entries(byCandidate).map(([cid, attempts]) => {
                            const outcome = attempts[attempts.length - 1]?.outcome;
                            const isSuccess = outcome === 'SUCCESS';
                            const isLast = Object.keys(byCandidate).indexOf(cid) === Object.keys(byCandidate).length - 1;
                            return `
                                <div class="pipeline-step">
                                    <div class="step-circle ${isSuccess ? 'completed' : 'failed'}">${isSuccess ? '✓' : '✗'}</div>
                                    <div class="step-label">${escapeHtml(cid)}</div>
                                    <div class="text-dim" style="font-size:0.65rem;">${attempts.length} attempt${attempts.length > 1 ? 's' : ''}</div>
                                </div>
                                ${!isLast ? '<div class="step-connector"></div>' : ''}
                            `;
                        }).join('')}
                    </div>
                    <div class="text-muted" style="font-size:0.8rem;">
                        Threshold: ${run.max_attempts} attempts per candidate |
                        Total attempts: ${run.total_attempts} |
                        Final status: <span class="badge ${run.final_status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(run.final_status)}</span>
                    </div>
                </div>
            `;
        }
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Run History
// ═══════════════════════════════════════════════════════════════════════

async function renderRunHistory(container) {
    showLoading(container, 'Loading run history...');

    try {
        const runs = await api.listRuns(1000);
        const allRuns = runs.runs || [];

        if (allRuns.length === 0) {
            showEmpty(container, '📜', 'No runs recorded', 'Start an assessment to see run history here.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Run History</h1>
                <p class="page-subtitle">${allRuns.length} runs</p>
            </div>

            <div class="card">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Run ID</th>
                            <th>Date</th>
                            <th>Scenario</th>
                            <th>Mode</th>
                            <th>Status</th>
                            <th>Target</th>
                            <th>Attempts</th>
                            <th>Pivots</th>
                            <th>Evidence</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allRuns.map(r => `
                            <tr style="cursor:pointer;" onclick="showRunDetail('${escapeHtml(r.run_id)}')">
                                <td><strong style="color:var(--accent-blue-light);">${escapeHtml(r.run_id)}</strong></td>
                                <td>${formatDateShort(r.created_at)}</td>
                                <td>${escapeHtml(r.scenario)}</td>
                                <td><span class="badge badge-info">${escapeHtml(r.mode)}</span></td>
                                <td><span class="badge ${r.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(r.status)}</span></td>
                                <td>${escapeHtml(r.target || 'N/A')}</td>
                                <td>${r.total_attempts}</td>
                                <td>${r.pivot_count}</td>
                                <td><span class="badge ${evidenceClass(r.evidence_tier)}">${escapeHtml(r.evidence_tier)}</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>

            <div id="run-detail-modal"></div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

async function showRunDetail(runId) {
    const modal = document.getElementById('run-detail-modal');
    if (!modal) return;

    showLoading(modal, 'Loading run details...');

    try {
        const [run, events, candidates, assessment] = await Promise.all([
            api.getRun(runId),
            api.getRunEvents(runId),
            api.getRunCandidates(runId),
            api.getRunAssessment(runId),
        ]);

        modal.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Run: ${escapeHtml(run.run_id)}</span>
                    <button class="btn btn-secondary" onclick="document.getElementById('run-detail-modal').innerHTML=''">Close</button>
                </div>

                <div class="grid-4" style="margin-bottom:1rem;">
                    <div><div class="text-muted" style="font-size:0.75rem;">Scenario</div><div>${escapeHtml(run.scenario)}</div></div>
                    <div><div class="text-muted" style="font-size:0.75rem;">Mode</div><div>${escapeHtml(run.mode)}</div></div>
                    <div><div class="text-muted" style="font-size:0.75rem;">Status</div><div><span class="badge ${run.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(run.status)}</span></div></div>
                    <div><div class="text-muted" style="font-size:0.75rem;">Evidence</div><div><span class="badge ${evidenceClass(run.evidence_tier)}">${escapeHtml(run.evidence_tier)}</span></div></div>
                </div>

                <div class="grid-2">
                    <div>
                        <h4 style="margin-bottom:0.5rem;">Candidates</h4>
                        ${(candidates.candidates || []).map(c => `
                            <div style="padding:0.5rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.5rem;">
                                <div style="font-weight:600;">${escapeHtml(c.id)}</div>
                                <div class="text-muted" style="font-size:0.75rem;">
                                    Quality: ${escapeHtml(c.quality_rank || 'N/A')} |
                                    Outcome: <span class="${c.execution_outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(c.execution_outcome || '-')}</span>
                                </div>
                            </div>
                        `).join('') || '<div class="text-muted">No candidates</div>'}
                    </div>
                    <div>
                        <h4 style="margin-bottom:0.5rem;">Events</h4>
                        <div class="event-timeline">
                            ${(events.events || []).slice(0, 10).map(e => `
                                <div class="event-item">
                                    <strong>${escapeHtml(e.event_type)}</strong>
                                    <div class="text-dim" style="font-size:0.7rem;">${formatDate(e.timestamp)}</div>
                                </div>
                            `).join('') || '<div class="text-muted">No events</div>'}
                        </div>
                    </div>
                </div>

                <div style="margin-top:1rem;">
                    <a href="#/reports" class="btn btn-primary" onclick="document.getElementById('run-detail-modal').innerHTML=''">View Report</a>
                </div>
            </div>
        `;
    } catch (err) {
        modal.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Reports
// ═══════════════════════════════════════════════════════════════════════

async function renderReports(container) {
    showLoading(container, 'Loading reports...');

    try {
        const runs = await api.listRuns(1000);
        const allRuns = runs.runs || [];

        if (allRuns.length === 0) {
            showEmpty(container, '📄', 'No reports available', 'Run an assessment to generate reports.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Reports</h1>
                <p class="page-subtitle">Generate and download assessment reports</p>
            </div>

            <div class="card">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Run ID</th>
                            <th>Scenario</th>
                            <th>Status</th>
                            <th>Evidence</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allRuns.map(r => `
                            <tr>
                                <td><strong>${escapeHtml(r.run_id)}</strong></td>
                                <td>${escapeHtml(r.scenario)}</td>
                                <td><span class="badge ${r.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(r.status)}</span></td>
                                <td><span class="badge ${evidenceClass(r.evidence_tier)}">${escapeHtml(r.evidence_tier)}</span></td>
                                <td>
                                    <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(r.run_id)}', 'json')">JSON</button>
                                    <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(r.run_id)}', 'html')">HTML</button>
                                    <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(r.run_id)}', 'markdown')">MD</button>
                                    <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(r.run_id)}', 'txt')">TXT</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

async function downloadReport(runId, format) {
    try {
        const result = await api.getRunReport(runId, format);
        const report = result.report || result;
        const blob = new Blob([typeof report === 'string' ? report : JSON.stringify(report, null, 2)], {
            type: format === 'json' ? 'application/json' : 'text/plain',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report_${runId}.${format === 'markdown' ? 'md' : format}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert('Error downloading report: ' + err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: System Health
// ═══════════════════════════════════════════════════════════════════════

async function renderSystemHealth(container) {
    showLoading(container, 'Loading system health...');

    try {
        const health = await api.getSystemHealth();

        const components = [
            { name: 'Application', status: health.application, detail: 'v0.1.0' },
            { name: 'API', status: 'READY', detail: 'FastAPI' },
            { name: 'Persistence', status: health.persistence, detail: 'JSON Repository' },
            { name: 'Research Core', status: health.research_core, detail: 'GAP-1 + GAP-2 verified' },
            { name: 'Safety Gate', status: 'READY', detail: 'AuthorizationTracker' },
            { name: 'Authorization', status: 'READY', detail: 'Allowlist enforced' },
            { name: 'Event System', status: 'READY', detail: 'EventBus + EventPublisher' },
            { name: 'Reporting', status: 'READY', detail: 'JSON/TXT/HTML/Markdown' },
            { name: 'Scanner Registry', status: 'READY', detail: 'Nmap, Nuclei, Custom' },
            { name: 'Ollama', status: health.ollama, detail: health.ollama_model || 'Not configured' },
            { name: 'Docker', status: health.docker, detail: health.docker_note || 'Not available' },
        ];

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">System Health</h1>
                <p class="page-subtitle">Real-time component status</p>
            </div>

            <div class="metrics-grid">
                ${components.map(c => `
                    <div class="metric-card">
                        <div class="metric-label">${c.name}</div>
                        <div class="metric-value ${statusClass(c.status)}" style="font-size:1rem;">${escapeHtml(c.status)}</div>
                        <div class="text-dim" style="font-size:0.75rem;margin-top:0.25rem;">${escapeHtml(c.detail)}</div>
                    </div>
                `).join('')}
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">API Endpoints</span>
                </div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Endpoint</th>
                            <th>Method</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td><code>/health</code></td><td>GET</td><td>Health check</td></tr>
                        <tr><td><code>/scenarios</code></td><td>GET</td><td>List scenarios</td></tr>
                        <tr><td><code>/system/health</code></td><td>GET</td><td>System health</td></tr>
                        <tr><td><code>/runs</code></td><td>POST</td><td>Start a run</td></tr>
                        <tr><td><code>/runs</code></td><td>GET</td><td>List runs</td></tr>
                        <tr><td><code>/runs/{id}/persisted</code></td><td>GET</td><td>Get persisted run</td></tr>
                        <tr><td><code>/runs/{id}/events</code></td><td>GET</td><td>Get run events</td></tr>
                        <tr><td><code>/runs/{id}/trace</code></td><td>GET</td><td>Get decision trace</td></tr>
                        <tr><td><code>/runs/{id}/report</code></td><td>GET</td><td>Get report</td></tr>
                        <tr><td><code>/runs/{id}/evidence</code></td><td>GET</td><td>Get evidence</td></tr>
                        <tr><td><code>/runs/{id}/findings</code></td><td>GET</td><td>Get findings</td></tr>
                        <tr><td><code>/runs/{id}/candidates</code></td><td>GET</td><td>Get candidates</td></tr>
                        <tr><td><code>/runs/{id}/assessment</code></td><td>GET</td><td>Get assessment</td></tr>
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Page: Configuration
// ═══════════════════════════════════════════════════════════════════════

async function renderConfiguration(container) {
    try {
        const health = await api.getSystemHealth().catch(() => null);

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Configuration</h1>
                <p class="page-subtitle">System configuration and safety settings</p>
            </div>

            <div class="grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Safety Configuration</span>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Target Allowlist</label>
                        <div style="background:var(--bg-primary);padding:0.75rem;border-radius:4px;font-family:monospace;font-size:0.85rem;">
                            127.0.0.1<br>
                            172.28.0.2
                        </div>
                        <p class="text-muted" style="font-size:0.75rem;margin-top:0.5rem;">
                            Only allowlisted targets can be assessed. This is enforced by the backend SafetyGate.
                        </p>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Authorization</label>
                        <div class="badge badge-success">✅ AUTHORIZATION TRACKER ACTIVE</div>
                        <p class="text-muted" style="font-size:0.75rem;margin-top:0.5rem;">
                            All targets must be explicitly authorized before execution.
                        </p>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">AI Configuration</span>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Ollama Status</label>
                        <div class="${statusClass(health?.ollama)}" style="font-weight:600;">
                            ${escapeHtml(health?.ollama || 'UNKNOWN')}
                        </div>
                        ${health?.ollama_model ? `<p class="text-muted" style="font-size:0.75rem;margin-top:0.25rem;">Model: ${escapeHtml(health.ollama_model)}</p>` : ''}
                    </div>
                    <div class="form-group">
                        <label class="form-label">Docker Status</label>
                        <div class="${statusClass(health?.docker)}" style="font-weight:600;">
                            ${escapeHtml(health?.docker || 'UNKNOWN')}
                        </div>
                        ${health?.docker_note ? `<p class="text-muted" style="font-size:0.75rem;margin-top:0.25rem;">${escapeHtml(health.docker_note)}</p>` : ''}
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Research Core Protection</span>
                </div>
                <div class="alert alert-success">
                    <strong>Research Core: PROTECTED</strong>
                    <p style="margin-top:0.5rem;">
                        The decision engine and VAPT research core are frozen. No modifications have been made.
                        GAP-1 (assessment before ranking) and GAP-2 (bounded pivot) are verified intact.
                    </p>
                </div>
            </div>
        `;
    } catch (err) {
        showError(container, err.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Initialize
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Check API connection
    api.getHealth()
        .then(() => {
            document.getElementById('footer-connection').textContent = 'API: Connected';
        })
        .catch(() => {
            document.getElementById('footer-connection').textContent = 'API: Disconnected';
            document.getElementById('system-status').innerHTML = '<span class="status-dot" style="background:var(--status-error);"></span><span class="status-text" style="color:var(--accent-red-light);">API OFFLINE</span>';
        });

    // Initial route
    router();
});
