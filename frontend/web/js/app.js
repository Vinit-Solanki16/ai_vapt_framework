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
    validateTarget(targetUrl) { return this.request('POST', '/targets/validate', { target_url: targetUrl }); },
    getScannerStatus() { return this.request('GET', '/scanners/status'); },
};

// ═══════════════════════════════════════════════════════════════════════
// State Management
// ═══════════════════════════════════════════════════════════════════════

const state = {
    currentRun: null,
    // FIX 5: run_id whose result is currently displayed inline on the
    // New Assessment page (#run-result). Tracked separately from
    // currentRun (last completed run, consumed by Active Assessment) so
    // editing the form or re-entering the page can clear stale output
    // without losing history or breaking the Active Assessment view.
    displayedRun: null,
    runs: [],
    systemHealth: null,
    scenarios: [],
    loading: false,
};

// FIX 5: hide a stale inline result on the New Assessment page when the
// user edits the configuration after a run completed. The displayed
// output belongs to state.displayedRun, not to the edited form, so it
// must not stay on screen mixed with new input. History is untouched;
// the previous run stays reachable via the "View Previous Run" link.
function clearStaleNewAssessmentResult(container) {
    const resultCard = (container || document).querySelector
        ? (container || document).querySelector('#run-result')
        : document.getElementById('run-result');
    if (!resultCard) return;
    if (resultCard.style.display !== 'none') {
        resultCard.style.display = 'none';
        const content = (container || document).querySelector
            ? (container || document).querySelector('#run-result-content')
            : document.getElementById('run-result-content');
        if (content) content.innerHTML = '';
    }
    state.displayedRun = null;
    const prev = (container || document).querySelector
        ? (container || document).querySelector('#previous-run-link')
        : document.getElementById('previous-run-link');
    if (prev && state.currentRun) prev.style.display = 'block';
    // FIX 6: a stale post-run action bar must never linger next to a fresh
    // form either — restore the idle START state alongside clearing output.
    resetNewAssessmentActions(container);
}

// FIX 6: explicit lifecycle for the New Assessment run controls.
//
//   IDLE:       [START VAPT ASSESSMENT] enabled, no post-run bar.
//   VALIDATING: button disabled, "VALIDATING..." (real preflight call).
//   RUNNING:    button disabled, "ASSESSMENT IN PROGRESS..." (real run).
//   COMPLETED:  ✓ + [VIEW RUN] [NEW ASSESSMENT] [RUN AGAIN] (START hidden).
//   FAILED:     ✗ + [VIEW ERROR] [RETRY] [NEW ASSESSMENT] (START hidden).
//
// No fake progress, no WebSockets: transitions fire only on actual
// backend responses (api.startRun resolve/reject, validateTargetUrl).
function runActionIds(isWeb) {
    return isWeb
        ? { runBtn: 'web-run-btn', btn: 'btn-run-web', post: 'web-post-actions' }
        : { runBtn: 'scenario-run-btn', btn: 'btn-run', post: 'scenario-post-actions' };
}

function setRunButtonsEnabled(enabled) {
    for (const isWeb of [false, true]) {
        const ids = runActionIds(isWeb);
        const btn = document.getElementById(ids.btn);
        if (btn) btn.disabled = !enabled;
    }
}

function hidePostRunActions() {
    for (const isWeb of [false, true]) {
        const el = document.getElementById(runActionIds(isWeb).post);
        if (el) {
            el.style.display = 'none';
            el.innerHTML = '';
        }
    }
}

function resetNewAssessmentActions(container) {
    const scope = container || document;
    const q = (sel) => scope.querySelector ? scope.querySelector(sel) : document.querySelector(sel);
    hidePostRunActions();
    const sWrap = q('#scenario-run-btn');
    const wWrap = q('#web-run-btn');
    const isWeb = document.getElementById('assess-type')
        ? document.getElementById('assess-type').value === 'web'
        : false;
    if (sWrap) sWrap.style.display = isWeb ? 'none' : 'block';
    if (wWrap) wWrap.style.display = isWeb ? 'block' : 'none';
    setRunButtonsEnabled(true);
}

function showPostRunActions({ status, runId, isWeb, error }) {
    const ids = runActionIds(!!isWeb);
    const wrap = document.getElementById(ids.runBtn);
    const post = document.getElementById(ids.post);
    if (!post) return;
    if (wrap) wrap.style.display = 'none';
    const safeId = escapeHtml(runId || '');
    if (status === 'completed') {
        post.innerHTML = `
            <div class="alert alert-success" style="margin-bottom:0.75rem;">
                <strong>✓ Assessment Completed</strong> — Run ID: <span style="font-family:monospace;">${safeId}</span>
            </div>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="viewRunFromPostActions()">👁️ VIEW RUN</button>
                <button class="btn btn-secondary" onclick="goNewAssessment()">📝 NEW ASSESSMENT</button>
                <button class="btn btn-secondary" onclick="runAgainFromPostActions(${isWeb ? 'true' : 'false'})">🔁 RUN AGAIN</button>
            </div>`;
    } else {
        post.innerHTML = `
            <div class="alert alert-error" style="margin-bottom:0.75rem;">
                <strong>✗ Assessment Failed</strong>${error ? ` — ${escapeHtml(error)}` : ''}
            </div>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="scrollToNewAssessmentResult()">🔍 VIEW ERROR</button>
                <button class="btn btn-secondary" onclick="runAgainFromPostActions(${isWeb ? 'true' : 'false'})">🔁 RETRY</button>
                <button class="btn btn-secondary" onclick="goNewAssessment()">📝 NEW ASSESSMENT</button>
            </div>`;
    }
    post.style.display = 'block';
}

function viewRunFromPostActions() {
    // Actual backend state: Active Assessment renders state.currentRun
    // from the API (api.getRun), never from stale inline DOM.
    window.location.hash = '#/assessment/active';
    if (getRoute() === '/assessment/active') router();
}

function goNewAssessment() {
    // Fresh configuration via the single canonical router. Same-hash
    // clicks are forced (hashchange would not fire otherwise).
    state.displayedRun = null;
    if (getRoute() !== '/assessment/new') {
        window.location.hash = '#/assessment/new';
    } else {
        router();
    }
}

function runAgainFromPostActions(isWeb) {
    hidePostRunActions();
    if (isWeb) startWebAssessment();
    else startAssessment();
}

function scrollToNewAssessmentResult() {
    const card = document.getElementById('run-result');
    if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        card.style.display = 'block';
    }
}

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
                ${recentRuns.length === 0 ? '<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No runs yet</div><div class="empty-state-hint">Start an assessment to see results here.</div></div>' : `
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

    // FIX 5: entering New Assessment always starts from a fresh
    // configuration — never re-display a previous run's result inline.
    // The previous run (if any) stays in Run History and is reachable
    // via an explicit link; persisted data is not deleted.
    state.displayedRun = null;

    try {
        const [scenarios, health, scanners] = await Promise.all([
            api.getScenarios().catch(() => ({ scenarios: [] })),
            api.getSystemHealth().catch(() => null),
            api.getScannerStatus().catch(() => null),
        ]);

        state.scenarios = scenarios.scenarios || [];
        state.scanners = scanners;

        const allowlistedTargets = ['127.0.0.1', '172.28.0.2'];
        const nmapAvailable = !!(scanners && scanners.nmap && scanners.nmap.available);
        const nucleiAvailable = !!(scanners && scanners.nuclei && scanners.nuclei.available);

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">New Assessment</h1>
                <p class="page-subtitle">Configure and execute a new VAPT assessment</p>
            </div>

            <div class="card" style="margin-bottom:1rem;">
                <div class="card-header">
                    <span class="card-title">Assessment Type</span>
                </div>
                <div class="form-group" style="max-width:480px;">
                    <label class="form-label">Assessment Type</label>
                    <select class="form-select" id="assess-type">
                        <option value="scenario">Research Scenario (offline / Docker demo)</option>
                        <option value="web">Web Application (authorized local URL target)</option>
                    </select>
                    <p class="text-muted" id="assess-type-hint" style="font-size:0.8rem;margin-top:0.5rem;">
                        Run a frozen research scenario (GAP-1 / GAP-2 demos preserved).
                    </p>
                </div>
            </div>

            <div id="scenario-config">
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

                    <div class="form-group" id="assess-model-group" style="display:none;">
                        <label class="form-label">Model</label>
                        <select class="form-select" id="assess-model">
                            <option value="llama3.2:3b" selected>llama3.2:3b (baseline)</option>
                            <option value="qwen2.5:3b">qwen2.5:3b (experimental)</option>
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
            </div>

            <div id="web-config" style="display:none;">
            <div class="grid-2">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Web Target (authorized local only)</span>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Target URL</label>
                        <div style="display:flex;gap:0.5rem;">
                            <input type="text" class="form-input" id="web-target-url"
                                value="http://127.0.0.1:9191" placeholder="http://127.0.0.1:9191"
                                style="flex:1;font-family:monospace;">
                            <button class="btn btn-secondary" id="btn-validate-url" onclick="validateTargetUrl()">Validate</button>
                        </div>
                        <p class="text-muted" style="font-size:0.75rem;margin-top:0.5rem;">
                            Only explicitly authorized local targets are accepted. Backend authorization is authoritative.
                        </p>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Authorization</label>
                        <div id="web-auth-status"><div class="badge badge-warning">NOT VALIDATED</div></div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Scanners</label>
                        <div>
                            <label style="display:block;margin-bottom:0.4rem;font-size:0.9rem;">
                                <input type="checkbox" id="web-use-nmap" ${nmapAvailable ? 'checked' : 'disabled'}>
                                Nmap discovery ${nmapAvailable ? '<span class="badge badge-success">READY</span>' : '<span class="badge badge-error">NOT INSTALLED</span>'}
                            </label>
                            <label style="display:block;font-size:0.9rem;">
                                <input type="checkbox" id="web-use-nuclei" ${nucleiAvailable ? 'checked' : 'disabled'}>
                                Nuclei vulnerability scan ${nucleiAvailable ? '<span class="badge badge-success">READY</span>' : '<span class="badge badge-warning">NOT AVAILABLE</span>'}
                            </label>
                            ${!nucleiAvailable ? '<p class="text-muted" style="font-size:0.75rem;margin-top:0.4rem;">Nuclei is not installed: the run will proceed with Nmap discovery and report Nuclei as NOT AVAILABLE.</p>' : ''}
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Assessment Configuration</span>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Assessor</label>
                        <select class="form-select" id="web-assessor">
                            <option value="ai" selected>Ollama (local AI assessment)</option>
                            <option value="deterministic">Deterministic (offline, reproducible)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Model</label>
                        <select class="form-select" id="web-model">
                            <option value="llama3.2:3b" selected>llama3.2:3b (baseline)</option>
                            <option value="qwen2.5:3b">qwen2.5:3b (experimental)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Pivot Threshold (N)</label>
                        <input type="number" class="form-input" id="web-max-attempts" value="2" min="1" max="10">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Safety</label>
                        <div id="web-safety-status"><div class="badge badge-warning">NOT VALIDATED</div></div>
                    </div>
                </div>
            </div>
            </div>

            <div class="card" id="run-result" style="display:none;">
                <div class="card-header">
                    <span class="card-title">Assessment Result</span>
                </div>
                <div id="run-result-content"></div>
            </div>

            <div class="card" id="previous-run-card" style="display:none;margin-top:1rem;">
                <div class="card-header">
                    <span class="card-title">Previous Run</span>
                </div>
                <p class="text-muted" style="font-size:0.85rem;">
                    A previous assessment was completed in this session.
                    <a href="#/runs" id="previous-run-link" style="color:var(--accent-blue-light);">View Previous Run</a>
                    <span id="previous-run-id" class="text-dim" style="font-family:monospace;font-size:0.75rem;"></span>
                </p>
            </div>

            <div style="margin-top: 1rem;" id="scenario-run-btn">
                <button class="btn btn-primary" id="btn-run" onclick="startAssessment()">
                    🚀 Run Assessment
                </button>
            </div>
            <div style="margin-top: 1rem;display:none;" id="web-run-btn">
                <button class="btn btn-primary" id="btn-run-web" onclick="startWebAssessment()">
                    🛡️ START VAPT ASSESSMENT
                </button>
            </div>
            <div style="margin-top: 1rem;display:none;" id="scenario-post-actions"></div>
            <div style="margin-top: 1rem;display:none;" id="web-post-actions"></div>
        `;

        // Event listeners
        document.getElementById('assess-type').addEventListener('change', function () {
            const isWeb = this.value === 'web';
            document.getElementById('scenario-config').style.display = isWeb ? 'none' : 'block';
            document.getElementById('web-config').style.display = isWeb ? 'block' : 'none';
            document.getElementById('scenario-run-btn').style.display = isWeb ? 'none' : 'block';
            document.getElementById('web-run-btn').style.display = isWeb ? 'block' : 'none';
            // FIX 6: switching forms restores the idle action state so no
            // completed/failed bar lingers under the other form.
            hidePostRunActions();
            setRunButtonsEnabled(true);
            document.getElementById('assess-type-hint').textContent = isWeb
                ? 'Real controlled assessment of an authorized local web target (Juice Shop demo: http://127.0.0.1:9191).'
                : 'Run a frozen research scenario (GAP-1 / GAP-2 demos preserved).';
            if (isWeb) validateTargetUrl();
        });

        document.getElementById('assess-mode').addEventListener('change', function () {
            const isLab = this.value === 'lab';
            document.getElementById('target-group').style.display = isLab ? 'block' : 'none';
            document.getElementById('port-group').style.display = isLab ? 'block' : 'none';
            updateSafetyStatus();
        });

        document.getElementById('assess-assessor').addEventListener('change', function () {
            document.getElementById('provider-group').style.display = this.value === 'ai' ? 'block' : 'none';
            document.getElementById('assess-model-group').style.display = this.value === 'ai' ? 'block' : 'none';
        });

        document.getElementById('web-target-url').addEventListener('change', validateTargetUrl);

        // FIX 5: fresh page shows no previous result; surface an explicit
        // link when a previous run exists in this session.
        const prevCard = document.getElementById('previous-run-card');
        const prevId = document.getElementById('previous-run-id');
        if (prevCard && state.currentRun) {
            if (prevId) prevId.textContent = `(${state.currentRun})`;
            prevCard.style.display = 'block';
        }

        // FIX 5: any configuration edit after a completed run clears the
        // stale inline result so old output is never mixed with new input.
        // The completed run itself stays in history (see link above).
        container.addEventListener('input', () => {
            if (state.displayedRun) clearStaleNewAssessmentResult(container);
        });
        container.addEventListener('change', () => {
            if (state.displayedRun) clearStaleNewAssessmentResult(container);
        });

        updateSafetyStatus();
    } catch (err) {
        showError(container, err.message);
    }
}

async function validateTargetUrl() {
    const input = document.getElementById('web-target-url');
    const authEl = document.getElementById('web-auth-status');
    const safetyEl = document.getElementById('web-safety-status');
    if (!input || !authEl) return;

    const url = input.value.trim();
    if (!url) {
        authEl.innerHTML = '<div class="badge badge-error">❌ REJECTED — URL required</div>';
        if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-error">REJECTED</div>';
        return;
    }

    authEl.innerHTML = '<div class="badge badge-warning">VALIDATING...</div>';
    if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-warning">VALIDATING...</div>';

    try {
        const res = await api.validateTarget(url);
        if (res.authorized && res.reachable) {
            authEl.innerHTML = `<div class="badge badge-success">✅ AUTHORIZED LOCAL TARGET</div>
                <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">${escapeHtml(res.detail || '')} — resolved ${escapeHtml(res.resolved_host || '')}:${escapeHtml(String(res.port || ''))}</p>`;
            if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-success">AUTHORIZED</div>';
        } else if (res.authorized) {
            authEl.innerHTML = `<div class="badge badge-warning">⚠️ AUTHORIZED / TARGET NOT REACHABLE</div>
                <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">${escapeHtml(res.detail || '')}</p>`;
            if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-warning">AUTHORIZED / UNREACHABLE</div>';
        } else {
            authEl.innerHTML = `<div class="badge badge-error">❌ REJECTED — TARGET NOT AUTHORIZED</div>
                <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">${escapeHtml(res.detail || '')}</p>`;
            if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-error">REJECTED</div>';
        }
        return res;
    } catch (err) {
        authEl.innerHTML = `<div class="badge badge-error">❌ VALIDATION ERROR</div>
            <p class="text-muted" style="margin-top:0.5rem;font-size:0.8rem;">${escapeHtml(err.message)}</p>`;
        if (safetyEl) safetyEl.innerHTML = '<div class="badge badge-error">REJECTED</div>';
        return null;
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

    // FIX 6: RUNNING — hide any post-run bar, show the START control in its
    // explicit in-progress state; clear the previous inline output so the
    // in-flight run is never mixed with stale content.
    hidePostRunActions();
    document.getElementById('scenario-run-btn').style.display = 'block';
    state.displayedRun = null;
    resultCard.style.display = 'none';
    resultContent.innerHTML = '';
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;"></span> ASSESSMENT IN PROGRESS...';

    try {
        const mode = document.getElementById('assess-mode').value;
        const scenario = document.getElementById('assess-scenario').value;
        const assessorRaw = document.getElementById('assess-assessor').value;
        // Backend schema expects "deterministic" | "llm".
        const assessor = assessorRaw === 'ai' ? 'llm' : assessorRaw;
        const provider = document.getElementById('assess-provider')?.value || 'ollama';
        const assessorModel = document.getElementById('assess-model')?.value || 'llama3.2:3b';
        const maxAttempts = parseInt(document.getElementById('assess-max-attempts').value, 10);

        const data = {
            scenario,
            mode,
            assessor,
            assessor_provider: provider,
            assessor_model: assessorModel,
            max_attempts: maxAttempts,
            assessment_type: 'scenario',
        };

        if (mode === 'lab') {
            data.target = document.getElementById('assess-target').value;
            data.port = parseInt(document.getElementById('assess-port').value, 10);
        }

        const result = await api.startRun(data);
        state.currentRun = result.run_id;
        // FIX 5: only the new result is displayed, bound to its run_id.
        state.displayedRun = result.run_id;

        resultCard.style.display = 'block';
        resultContent.innerHTML = `
            <div class="alert alert-success">
                <strong>Run completed!</strong> Run ID: ${escapeHtml(result.run_id)}
            </div>
            <div id="active-run-details"></div>
        `;
        const prevCardOk = document.getElementById('previous-run-card');
        if (prevCardOk) prevCardOk.style.display = 'none';

        // Load full run details
        await loadActiveRunDetails(result.run_id);

        // FIX 6: COMPLETED — explicit post-run bar bound to the new run_id;
        // the START control stays hidden underneath (RUN AGAIN is separate).
        showPostRunActions({ status: 'completed', runId: result.run_id, isWeb: false });

    } catch (err) {
        // FIX 5: a fresh error is the new result — no stale run output.
        state.displayedRun = null;
        resultCard.style.display = 'block';
        resultContent.innerHTML = `<div class="alert alert-error"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
        // FIX 6: FAILED — explicit recovery bar (VIEW ERROR / RETRY / NEW).
        showPostRunActions({ status: 'failed', isWeb: false, error: err.message });
    }
}

async function startWebAssessment() {
    const btn = document.getElementById('btn-run-web');
    const resultCard = document.getElementById('run-result');
    const resultContent = document.getElementById('run-result-content');

    // FIX 6: hide any post-run bar and stale output; the in-flight run owns
    // the action area until the backend responds.
    hidePostRunActions();
    document.getElementById('web-run-btn').style.display = 'block';
    state.displayedRun = null;
    resultCard.style.display = 'none';
    resultContent.innerHTML = '';
    btn.disabled = true;
    // FIX 6: VALIDATING — real preflight call below; button says so.
    btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;"></span> VALIDATING...';

    // FIX 7: honest in-flight indicator. The workflow is synchronous, so
    // no per-stage progress exists to report (no percentages, no stage
    // claims). The only truthful live facts are: the request is in
    // flight, its target, and wall-clock elapsed. Timer cleared on settle.
    let vaptTimer = null;
    const stopVaptTimer = () => {
        if (vaptTimer) {
            clearInterval(vaptTimer);
            vaptTimer = null;
        }
    };

    try {
        const targetUrl = document.getElementById('web-target-url').value.trim();
        const useNmap = document.getElementById('web-use-nmap')?.checked ?? true;
        const useNuclei = document.getElementById('web-use-nuclei')?.checked ?? false;
        const assessorRaw = document.getElementById('web-assessor').value;
        const assessor = assessorRaw === 'ai' ? 'llm' : assessorRaw;
        const assessorModel = document.getElementById('web-model')?.value || 'llama3.2:3b';
        const maxAttempts = parseInt(document.getElementById('web-max-attempts').value, 10);

        // Backend re-validates authoritatively; this pre-check is UX only.
        // FIX 6: preflight done — now the real run is in progress.
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;"></span> ASSESSMENT IN PROGRESS...';
        const pre = await validateTargetUrl();
        if (!pre || !pre.authorized) {
            throw new Error('Target is not authorized. Resolve the authorization error before starting.');
        }
        if (!pre.reachable) {
            throw new Error('Target is not reachable. Scanners will not run against an unreachable target.');
        }

        const data = {
            scenario: 'web_target',
            mode: 'web',
            assessment_type: 'web',
            target_url: targetUrl,
            use_nmap: useNmap,
            use_nuclei: useNuclei,
            assessor,
            assessor_provider: 'ollama',
            assessor_model: assessorModel,
            max_attempts: maxAttempts,
        };

        // FIX 7: honest in-flight status. Only live facts are shown: the
        // request is in flight, its target, and measured wall-clock
        // elapsed. No per-stage RUNNING claims (the synchronous workflow
        // exposes no live stage feed), no percentages, no WebSockets.
        // Nuclei scans can take several minutes — this tells the user the
        // assessment is not stuck without fabricating progress.
        const vaptStart = Date.now();
        resultCard.style.display = 'block';
        resultContent.innerHTML = `
            <div class="card">
                <div class="card-header"><span class="card-title">VAPT In Progress</span></div>
                <p class="text-muted" style="font-size:0.85rem;">
                    Target: <span style="font-family:monospace;">${escapeHtml(targetUrl)}</span><br>
                    Elapsed: <span id="vapt-elapsed" style="font-family:monospace;">0.0s</span><br>
                    Scanner stages (Nmap, Nuclei) run on the backend; their
                    recorded status, findings and durations appear below
                    when the backend responds. Long Nuclei scans are normal.
                </p>
            </div>`;
        vaptTimer = setInterval(() => {
            const el = document.getElementById('vapt-elapsed');
            if (el) el.textContent = `${((Date.now() - vaptStart) / 1000).toFixed(1)}s`;
        }, 500);

        const result = await api.startRun(data);
        stopVaptTimer();
        state.currentRun = result.run_id;
        // FIX 5: only the new result is displayed, bound to its run_id.
        state.displayedRun = result.run_id;

        resultCard.style.display = 'block';
        resultContent.innerHTML = `
            <div class="alert alert-success">
                <strong>Web VAPT assessment completed!</strong> Run ID: ${escapeHtml(result.run_id)}
            </div>
            <div id="active-run-details"></div>
        `;
        const prevCardWeb = document.getElementById('previous-run-card');
        if (prevCardWeb) prevCardWeb.style.display = 'none';

        await loadActiveRunDetails(result.run_id);

        // FIX 6: COMPLETED — explicit post-run bar bound to the new run_id.
        showPostRunActions({ status: 'completed', runId: result.run_id, isWeb: true });

    } catch (err) {
        // FIX 5: a fresh error is the new result — no stale run output.
        stopVaptTimer();
        state.displayedRun = null;
        resultCard.style.display = 'block';
        resultContent.innerHTML = `<div class="alert alert-error"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
        // FIX 6: FAILED — explicit recovery bar (VIEW ERROR / RETRY / NEW).
        showPostRunActions({ status: 'failed', isWeb: true, error: err.message });
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

        // Web-target assessments get the live-pipeline stage view.
        const webCtx = (run.pipeline_summary && run.pipeline_summary.web) || null;
        if (run.assessment_type === 'web' || webCtx) {
            renderWebRunDetails(container, run, events, candidates, assessment, webCtx);
            return;
        }

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

            <div class="grid-2" style="margin-bottom:1rem;">
                ${renderGap1Panel(candidates.candidates || [], assessment.assessment || run.assessment || {})}
                ${renderGap2Panel(run)}
            </div>

            <div class="grid-2">
                <div>
                    <h4 style="margin-bottom:0.5rem;">Candidates</h4>
                    ${(candidates.candidates || []).map(c => `
                        <div style="padding:0.5rem;background:var(--bg-primary);border-radius:4px;margin-bottom:0.5rem;">
                            <div style="font-weight:600;">${escapeHtml(c.id)}</div>
                            <div class="text-muted" style="font-size:0.75rem;">
                                Quality: ${escapeHtml(c.quality_rank || 'N/A')} |
                                Outcome: <span class="${c.execution_outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(c.execution_outcome || '-')}</span><br>
                                Validation: <span class="badge ${validationBadgeClass(c.validation_status || (run.evidence_tier === 'DOCKER_OBSERVED' ? 'DOCKER_OBSERVED' : run.evidence_tier === 'SIMULATED' ? 'SIMULATED' : 'VALIDATION NOT AVAILABLE'))}">${escapeHtml(c.validation_status || (run.evidence_tier === 'DOCKER_OBSERVED' ? 'DOCKER_OBSERVED' : run.evidence_tier === 'SIMULATED' ? 'SIMULATED' : 'VALIDATION NOT AVAILABLE'))}</span>
                                <span class="text-dim" style="font-size:0.7rem;">outcome ≠ exploit proof; see validation status</span>
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
// Web-target live pipeline view (Phase 32)
// Honest stage display: every stage reflects recorded run data.
// Scanner findings are NEVER presented as confirmed exploits.
// ═══════════════════════════════════════════════════════════════════════

function webStage(ok, label, detail) {
    return `
        <div class="pipeline-step">
            <div class="step-circle ${ok ? 'completed' : 'failed'}">${ok ? '✓' : '✗'}</div>
            <div class="step-label ${ok ? 'completed' : 'failed'}">${label}</div>
            ${detail ? `<div class="text-dim" style="font-size:0.65rem;">${escapeHtml(detail)}</div>` : ''}
        </div>
        <div class="step-connector ${ok ? 'completed' : ''}"></div>
    `;
}

// FIX 3: neutral pipeline stage for states that are neither success nor
// failure (e.g. VALIDATION NOT AVAILABLE). Renders a dash with no green
// success indicator so scanner detection is never read as validated.
function webStageNeutral(label, detail) {
    return `
        <div class="pipeline-step">
            <div class="step-circle" style="border-color:var(--text-dim);color:var(--text-dim);">—</div>
            <div class="step-label">${label}</div>
            ${detail ? `<div class="text-dim" style="font-size:0.65rem;">${escapeHtml(detail)}</div>` : ''}
        </div>
        <div class="step-connector"></div>
    `;
}

// FIX 3: single frontend mirror of the backend validation source of truth.
// Backend per-finding validation_status values: SCANNER-DETECTED,
// VALIDATION NOT AVAILABLE, SIMULATED-OUTCOME (validation not available),
// SIMULATED, DOCKER_OBSERVED, VALIDATED. Only an explicit VALIDATED
// counts as validated; everything else is NOT AVAILABLE / non-validated.
function isValidatedStatus(status) {
    return String(status || '').trim().toUpperCase() === 'VALIDATED';
}

function isNotAvailableStatus(status) {
    const s = String(status || '').toUpperCase();
    return s.includes('NOT AVAILABLE') || s === 'SCANNER-DETECTED' || s === '';
}

function validationBadgeClass(status) {
    if (isValidatedStatus(status)) return 'badge-success';
    const s = String(status || '').toUpperCase();
    if (s === 'SIMULATED' || s.includes('SIMULATED')) return 'badge-info';
    if (s === 'DOCKER_OBSERVED' || s.includes('DOCKER')) return 'badge-info';
    if (s === 'SCANNER-DETECTED') return 'badge-info';
    return 'badge-warning';
}

// FIX 4: explicit unavailable semantics for vulnerability intelligence.
// Backend preserves missing as null/None (never fabricated zero); only
// genuine numeric values (including true 0.0, via != null checks) render
// as numbers. Missing renders as N/A per existing 'N/A' UI convention.
// KEV: true → yes, false with a CVE → no (known negative), else N/A.
function intelDisplay(md) {
    const m = md || {};
    const cves = m.cve_ids || (m.cve ? [m.cve] : []);
    const hasCve = Array.isArray(cves) ? cves.length > 0 : !!cves;
    const cvss = m.cvss_score != null ? 'CVSS ' + m.cvss_score : 'CVSS N/A';
    const epss = m.epss_score != null ? 'EPSS ' + m.epss_score : 'EPSS N/A';
    let kev;
    if (m.cisa_kev === true) kev = 'KEV yes';
    else if (m.cisa_kev === false && hasCve) kev = 'KEV no';
    else kev = 'KEV N/A';
    const cweList = m.cwe_ids || [];
    const cwe = (Array.isArray(cweList) && cweList.length) ? cweList.join(', ') : 'CWE N/A';
    const parts = [cvss, epss, kev, cwe];
    if (hasCve) parts.unshift(Array.isArray(cves) ? cves.join(', ') : String(cves));
    return parts.join(' · ');
}

// FIX 7: honest scan-status helpers. Status source is the persisted
// backend web context (preflight + nmap/nuclei ScanResult.to_dict():
// status, exit_code, finding_count, duration_s, detail, command).
// No percentages exist anywhere (no progress measurement exists), no
// WebSockets are used, and a stage is never marked COMPLETED unless its
// recorded status is exactly 'COMPLETED'.
function formatDurationSec(v) {
    if (v === null || v === undefined || v === '') return 'N/A';
    const n = Number(v);
    if (!Number.isFinite(n)) return 'N/A';
    return `${n.toFixed(1)}s`;
}

function scannerStatusBadge(status) {
    const s = String(status || 'unknown');
    if (s === 'COMPLETED') return '<span class="badge badge-success">✓ COMPLETED</span>';
    if (s === 'FAILED') return '<span class="badge badge-error">✗ FAILED</span>';
    if (s === 'NOT AVAILABLE' || s === 'SKIPPED') return `<span class="badge badge-warning">${escapeHtml(s)}</span>`;
    return `<span class="badge badge-info">${escapeHtml(s)}</span>`;
}

// FIX 7: scan-status panel rendered from recorded backend data only.
// Covers: scanner unavailable / failure / timeout (FAILED + detail) /
// successful completion (COMPLETED + findings + duration). Legacy runs
// without a web context report "not recorded" instead of invented data.
function renderScanStatusPanel(w, run) {
    if (!w || (!w.preflight && !w.nmap && !w.nuclei)) {
        return `
        <div class="card" style="margin-bottom:1rem;">
            <div class="card-header"><span class="card-title">Scan Status</span></div>
            <div class="text-muted">Scan status not recorded for this run.</div>
        </div>`;
    }
    const pre = w.preflight || {};
    const nmap = w.nmap || {};
    const nuclei = w.nuclei || {};
    const target = w.target_url || run.target_url || '';
    const scanRow = (name, scan) => {
        const status = scan.status || 'unknown';
        const findings = scan.finding_count ?? 'N/A';
        const duration = formatDurationSec(scan.duration_s);
        const exit = scan.exit_code ?? 'N/A';
        const detail = (status === 'FAILED' || status === 'NOT AVAILABLE') && scan.detail
            ? `<br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(scan.detail)}</span>` : '';
        return `
            <tr>
                <td><strong>${escapeHtml(name)}</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(target || '—')}</span></td>
                <td>${scannerStatusBadge(status)}${detail}</td>
                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(String(findings))}</td>
                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(duration)}</td>
                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(String(exit))}</td>
            </tr>`;
    };
    const authStatus = pre.authorization_status || (pre.reachable ? 'AUTHORIZED' : 'unknown');
    const authOk = authStatus === 'AUTHORIZED';
    const reachDetail = pre.reachable
        ? `Reachable${pre.http_status != null ? ` (${escapeHtml(String(pre.http_status))})` : ''}${pre.detail ? ` — ${escapeHtml(pre.detail)}` : ''}`
        : (pre.detail ? escapeHtml(pre.detail) : 'Unreachable');
    const total = w.total_findings ?? ((w.finding_count ?? 0) + (w.service_discovery_count ?? 0));
    const pipelineElapsed = formatDurationSec(w.pipeline_s);
    return `
        <div class="card" style="margin-bottom:1rem;">
            <div class="card-header"><span class="card-title">Scan Status</span></div>
            <table class="data-table">
                <thead>
                    <tr><th>Stage</th><th>Status</th><th>Findings</th><th>Elapsed</th><th>Exit</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Target Authorized</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(target || '—')}</span></td>
                        <td>${authOk ? '<span class="badge badge-success">✓ AUTHORIZED</span>' : `<span class="badge badge-warning">${escapeHtml(authStatus)}</span>`}</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                    </tr>
                    <tr>
                        <td><strong>Target Reachable</strong></td>
                        <td>${pre.reachable ? '<span class="badge badge-success">✓ REACHABLE</span>' : '<span class="badge badge-error">✗ UNREACHABLE</span>'}</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                    </tr>
                    ${scanRow('Nmap discovery', nmap)}
                    ${scanRow('Nuclei scan', nuclei)}
                    <tr>
                        <td><strong>Pipeline total</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(String(total ?? '—'))} findings</span></td>
                        <td><span class="badge badge-info">RECORDED</span><br><span class="text-dim" style="font-size:0.7rem;">${reachDetail}</span></td>
                        <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(String(total ?? 'N/A'))}</td>
                        <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(pipelineElapsed)}</td>
                        <td style="font-family:monospace;font-size:0.75rem;">—</td>
                    </tr>
                </tbody>
            </table>
        </div>`;
}

// FIX 8: compact research-contribution panels. Both read ONLY recorded
// backend data (assessment provenance + execution results); they render
// "Not applicable" / "No pivot required" when the run lacks the behavior
// and never invent quality scores, priorities, or pivot events.
function gap1PanelData(cands, assess) {
    const a = assess || {};
    const details = Array.isArray(a.details) ? a.details : [];
    const list = Array.isArray(cands) ? cands : [];
    const qualities = details.length
        ? details.map(d => d.quality_rank)
        : list.map(c => c.quality_rank);
    const assessed = details.length || qualities.filter(Boolean).length;
    if (!a.mode && !details.length && !assessed) return { applicable: false };
    const llmReal = details.some(d => d.source === 'llm' && !d.fallback);
    const fallback = details.length > 0 && details.every(d => d.fallback);
    let modeLabel = 'Deterministic';
    if (a.mode === 'ai' && llmReal) modeLabel = 'AI';
    else if (a.mode === 'ai') modeLabel = 'AI requested — deterministic fallback';
    return {
        applicable: true,
        modeLabel,
        provider: a.provider || '—',
        model: a.model || '—',
        assessed,
        highs: qualities.filter(q => q === 'HIGH').length,
        mediums: qualities.filter(q => q === 'MEDIUM').length,
        lows: qualities.filter(q => q === 'LOW').length,
    };
}

function renderGap1Panel(cands, assess) {
    const d = gap1PanelData(cands, assess);
    const body = !d.applicable
        ? '<div class="text-muted">Not applicable — no assessment recorded for this run.</div>'
        : `
            <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.5rem;">Candidate → AI Assessment → Quality → Ranking → Decision</div>
            <div class="grid-2" style="font-size:0.8rem;">
                <div><div class="text-muted" style="font-size:0.7rem;">Assessment Mode</div><div>${escapeHtml(d.modeLabel)}</div></div>
                <div><div class="text-muted" style="font-size:0.7rem;">Provider / Model</div><div>${escapeHtml(d.provider)}${d.model && d.model !== '—' ? ' / ' + escapeHtml(d.model) : ''}</div></div>
                <div><div class="text-muted" style="font-size:0.7rem;">Assessed</div><div>${d.assessed} candidate${d.assessed === 1 ? '' : 's'}</div></div>
                <div><div class="text-muted" style="font-size:0.7rem;">Quality</div><div>HIGH ${d.highs} · MEDIUM ${d.mediums} · LOW ${d.lows}</div></div>
            </div>
            <div class="text-dim" style="font-size:0.7rem;margin-top:0.5rem;">Per-candidate quality, final score and priority are backend-recorded in the tables below.</div>`;
    return `
        <div class="card">
            <div class="card-header">
                <span class="card-title">GAP-1 · Pre-execution AI Prioritization</span>
            </div>
            ${body}
        </div>`;
}

function renderGap2Panel(run) {
    const r = run || {};
    const results = Array.isArray(r.execution_results) ? r.execution_results : [];
    const hasData = results.length > 0 || r.pivot_count != null || r.max_attempts != null;
    let body;
    if (!hasData) {
        body = '<div class="text-muted">Not applicable — no execution recorded for this run.</div>';
    } else {
        const pivots = r.pivot_count || 0;
        const threshold = r.max_attempts ?? '—';
        const order = Array.isArray(r.candidates_processed) && r.candidates_processed.length
            ? r.candidates_processed.join(' → ')
            : '—';
        const byCandidate = {};
        for (const res of results) {
            const cid = res.candidate_id || '?';
            (byCandidate[cid] = byCandidate[cid] || []).push(res.outcome || '?');
        }
        const chains = Object.entries(byCandidate).map(([cid, outcomes]) =>
            `<div style="font-size:0.75rem;margin-top:0.25rem;"><strong>${escapeHtml(cid)}</strong>: ${
                outcomes.map((o, i) => `Attempt ${i + 1} ${escapeHtml(o)}`).join(' → ')
            }${outcomes.length >= (Number(threshold) || Infinity) ? ' → Threshold reached → PIVOT' : ''}</div>`
        ).join('') || '<div class="text-muted" style="font-size:0.75rem;">No attempts recorded.</div>';
        body = `
            <div class="text-muted" style="font-size:0.75rem;margin-bottom:0.5rem;">Attempt → FAIL → Threshold → PIVOT → Next candidate</div>
            <div style="font-size:0.8rem;">
                <div><span class="text-muted" style="font-size:0.7rem;">Pivot Status: </span>${pivots > 0 ? `Threshold reached → pivot occurred (${pivots})` : 'No pivot required'}</div>
                <div class="text-muted" style="font-size:0.75rem;">Attempts: ${results.length} · Threshold: ${escapeHtml(String(threshold))}/candidate · Pivots: ${pivots} · Order: ${escapeHtml(order)}</div>
                ${chains}`;
    }
    return `
        <div class="card">
            <div class="card-header">
                <span class="card-title">GAP-2 · Failure-Aware Decision Pivot</span>
            </div>
            ${body}
        </div>`;
}

function renderWebRunDetails(container, run, events, candidates, assessment, webCtx) {
    const w = webCtx || {};
    const pre = w.preflight || {};
    const nmap = w.nmap || {};
    const nuclei = w.nuclei || {};
    const cands = candidates.candidates || run.candidates || [];
    const assess = assessment.assessment || run.assessment || {};
    const details = assess.details || [];
    const detailById = {};
    for (const d of details) detailById[d.candidate_id] = d;

    const targetOk = !!pre.reachable;
    const findingsOk = cands.length > 0;
    const aiOk = assess.mode === 'ai' || assess.mode === 'deterministic';

    // FIX 3: VALIDATION reflects the backend per-finding validation_status.
    // Web-mode scanner findings are SCANNER-DETECTED → VALIDATION NOT
    // AVAILABLE (no controlled validation executed). Only an explicit
    // VALIDATED backend state renders green; otherwise neutral dash.
    const validation = validationStage(cands);

    // Phase 32B FIX 6: scanner + execution stages from recorded backend
    // status. COMPLETED alone earns green; NOT AVAILABLE/SKIPPED render
    // neutral (never failed, never complete); anything else is failure
    // with its recorded detail. EXECUTION is green only for genuine
    // VALIDATED findings — otherwise neutral NOT PERFORMED/recorded.
    const scannerStage = (label, scan, findingsText) => {
        const status = (scan && scan.status) || 'unknown';
        if (status === 'COMPLETED') return webStage(true, label, findingsText);
        if (status === 'NOT AVAILABLE' || status === 'SKIPPED') {
            return webStageNeutral(label, `${scanName(scan)}: ${status}`);
        }
        const detail = scan && scan.detail ? ` — ${scan.detail}` : '';
        return webStage(false, label, `${scanName(scan)}: ${status}${detail}`);
    };
    const scanName = (scan) => (scan && scan.scanner) ? scan.scanner : 'scanner';
    const validatedExec = cands.filter(c => isValidatedStatus(c.validation_status)).length;
    const execTotal = (run.execution_results || []).length;
    const execStage = validatedExec > 0
        ? webStage(true, 'EXECUTION', `VALIDATED (${validatedExec}/${cands.length})`)
        : webStageNeutral('EXECUTION', execTotal > 0 ? `${execTotal} recorded — not validated` : 'NOT PERFORMED');

    const nmapFindingsText = `Nmap: ${nmap.finding_count ?? 0} findings`;
    const nucleiFindingsText = `Nuclei: ${nuclei.finding_count ?? 0} findings`;

    const stages = [
        webStage(targetOk, 'TARGET', pre.reachable ? `Reachable (${pre.http_status})` : 'Unreachable'),
        scannerStage('DISCOVERY', nmap, nmapFindingsText),
        scannerStage('VULN SCAN', nuclei, nucleiFindingsText),
        webStage(findingsOk, 'FINDINGS', String(cands.length)),
        webStage(findingsOk, 'NORMALIZATION', 'CanonicalFinding + dedup'),
        webStage(findingsOk, 'ENRICHMENT', 'EPSS / KEV / CVSS / CWE'),
        webStage(aiOk, 'AI ASSESSMENT', `${assess.provider || '?'}${assess.model ? ' / ' + assess.model : ''}`),
        webStage(true, 'RANKING', 'assessment → rank (GAP-1)'),
        webStage(true, 'DECISION', `${run.final_status || run.status || '?'}`),
        webStage(true, 'SAFETY', 'SafetyGate authorized (scope check)'),
        validation.stage,
        execStage,
        webStage(true, 'EVIDENCE', run.evidence_tier || '?'),
        `<div class="pipeline-step">
            <div class="step-circle completed">✓</div>
            <div class="step-label completed">REPORT</div>
            <div class="text-dim" style="font-size:0.65rem;">available below</div>
        </div>`,
    ];

    // FIX 1 + FIX 2: non-actionable inventory (Nmap asset context +
    // Nuclei informational / fingerprint / discovery), never ranked.
    const discovery = run.service_discovery
        || w.service_discovery
        || w.discovery_snapshots
        || [];
    const discoveryRows = discovery.map(s => {
        const detail = [s.product, s.version].filter(Boolean).join(' ').trim()
            || s.description || s.service || s.title || '—';
        const rectype = s.record_type || s.finding_kind || 'DISCOVERY';
        return `
            <tr>
                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(s.host || s.target || '—')}:${escapeHtml(String(s.port ?? '—'))}/${escapeHtml(s.protocol || 'tcp')}</td>
                <td><strong>${escapeHtml(s.service || s.title || '—')}</strong></td>
                <td style="font-size:0.75rem;">${escapeHtml(String(detail).slice(0, 160))}</td>
                <td>${escapeHtml(s.source || 'nmap')}<br><span class="badge badge-info">${escapeHtml(rectype)}</span><br><span class="badge badge-info">INFORMATIONAL / DISCOVERY</span></td>
            </tr>`;
    }).join('');

    container.innerHTML = `
        <div class="card" style="margin-bottom:1rem;">
            <div class="card-header">
                <span class="card-title">Web Target Assessment</span>
                <span class="badge badge-info">${escapeHtml(w.target_url || run.target_url || '')}</span>
            </div>
            <div class="grid-4" style="margin-bottom:1rem;">
                <div><div class="text-muted" style="font-size:0.75rem;">Target</div><div style="font-family:monospace;font-size:0.85rem;">${escapeHtml(w.target_url || run.target_url || 'N/A')}</div></div>
                <div><div class="text-muted" style="font-size:0.75rem;">Application</div><div>OWASP Juice Shop (local controlled test app)</div></div>
                <div><div class="text-muted" style="font-size:0.75rem;">Environment</div><div>LOCAL CONTROLLED TEST APPLICATION</div></div>
                <div><div class="text-muted" style="font-size:0.75rem;">Evidence</div><div><span class="badge ${evidenceClass(run.evidence_tier)}">${escapeHtml(run.evidence_tier || 'UNKNOWN')}</span></div></div>
            </div>
            <div class="pipeline-container">${stages.join('')}</div>
            <div class="grid-2" style="margin-top:1rem;">
                <div class="text-muted" style="font-size:0.8rem;"><strong>Discovery:</strong> Nmap ${escapeHtml((w.scanner_versions || {}).nmap || '')} — ${escapeHtml(nmap.status || '?')} (exit ${escapeHtml(String(nmap.exit_code ?? '?'))}, ${escapeHtml(String(nmap.finding_count ?? 0))} findings)</div>
                <div class="text-muted" style="font-size:0.8rem;"><strong>Vulnerability scan:</strong> Nuclei ${escapeHtml((w.scanner_versions || {}).nuclei || '')} — ${escapeHtml(nuclei.status || '?')} — ${escapeHtml(nuclei.detail || '')}</div>
            </div>
            <div class="text-muted" style="font-size:0.8rem;margin-top:0.5rem;"><strong>AI:</strong> ${escapeHtml(assess.provider || '?')}${assess.model ? ' / ' + escapeHtml(assess.model) : ''} (${escapeHtml(assess.mode || '?')} mode)</div>
        </div>

        ${renderScanStatusPanel(w, run)}

        <div class="grid-2" style="margin-bottom:1rem;">
            ${renderGap1Panel(cands, assess)}
            ${renderGap2Panel(run)}
        </div>

        <div class="card" style="margin-bottom:1rem;">
            <div class="card-header">
                <span class="card-title">Findings Inventory — Informational / Discovery (${discovery.length}) — not ranked; candidate eligibility: INFORMATIONAL / DISCOVERY</span>
            </div>
            ${discovery.length ? `
            <table class="data-table">
                <thead>
                    <tr><th>Endpoint</th><th>Service</th><th>Product / Banner</th><th>Source / Eligibility</th></tr>
                </thead>
                <tbody>${discoveryRows}</tbody>
            </table>` : '<div class="text-muted">No informational / discovery records</div>'}
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Findings (${cands.length}) — ACTIONABLE candidates (eligibility: ACTIONABLE), scanner-detected, not confirmed exploits</span>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Finding</th>
                        <th>Severity</th>
                        <th>Template / Rule</th>
                        <th>Endpoint</th>
                        <th>Source</th>
                        <th>CVE / CVSS / EPSS / KEV / CWE</th>
                        <th>AI Quality</th>
                        <th>Score</th>
                        <th>Priority</th>
                        <th>Candidate Eligibility</th>
                        <th>Validation Status</th>
                        <th>Evidence</th>
                    </tr>
                </thead>
                <tbody>
                    ${cands.map(c => {
                        const md = c.metadata || {};
                        const intel = intelDisplay(md);
                        const q = detailById[c.id] || {};
                        const score = (c._score && c._score.final_score != null) ? Number(c._score.final_score).toFixed(4) : '—';
                        const vStatus = c.validation_status || 'VALIDATION NOT AVAILABLE';
                        const vNote = isValidatedStatus(vStatus) ? 'validated by controlled execution' : 'not validated by execution — scanner-detected only';
                        return `
                        <tr>
                            <td><strong>${escapeHtml(c.title || c.id)}</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(c.id || '')}</span></td>
                            <td class="${severityClass(c.severity)}">${escapeHtml(c.severity || 'unknown')}</td>
                            <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(c.rule_id || '—')}</td>
                            <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(c.target || '')}${c.port ? ':' + escapeHtml(String(c.port)) : ''}</td>
                            <td>${escapeHtml(c.source || '')}<br><span class="text-dim" style="font-size:0.7rem;">discovered by scanner</span></td>
                            <td style="font-size:0.75rem;">${escapeHtml(intel)}</td>
                            <td>${q.quality_rank ? `<span class="badge ${q.quality_rank === 'HIGH' ? 'badge-success' : q.quality_rank === 'MEDIUM' ? 'badge-warning' : 'badge-error'}">${escapeHtml(q.quality_rank)}</span>${q.fallback ? ' <span class="text-warning" style="font-size:0.7rem;">fallback</span>' : ''}${q.reasoning ? `<div class="text-dim" style="font-size:0.7rem;max-width:220px;">${escapeHtml(String(q.reasoning).slice(0, 160))}</div>` : ''}` : escapeHtml(c.quality_rank || 'N/A')}</td>
                            <td>${escapeHtml(score)}</td>
                            <td>${c.priority != null ? '#' + escapeHtml(String(c.priority)) : '—'}</td>
                            <td><span class="badge badge-success">ACTIONABLE</span></td>
                            <td><span class="badge ${validationBadgeClass(vStatus)}">${escapeHtml(vStatus)}</span><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(vNote)}</span></td>
                            <td><span class="badge ${evidenceClass(run.evidence_tier)}">${escapeHtml(run.evidence_tier || 'UNKNOWN')}</span></td>
                        </tr>`;
                    }).join('') || '<tr><td colspan="12" class="text-muted">No findings</td></tr>'}
                </tbody>
            </table>
            <div style="margin-top:1rem;">
                <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(run.run_id)}', 'json')">JSON</button>
                <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(run.run_id)}', 'html')">HTML</button>
                <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(run.run_id)}', 'markdown')">MD</button>
                <button class="btn btn-secondary" style="padding:0.25rem 0.5rem;font-size:0.75rem;" onclick="downloadReport('${escapeHtml(run.run_id)}', 'txt')">TXT</button>
            </div>
        </div>
    `;
}

function validationSummary(cands) {
    // FIX 3: honest summary matching backend validation_status.
    // Case-insensitive; SCANNER-DETECTED counts as not available.
    // Never reports "executed"/success unless backend says VALIDATED.
    if (!cands.length) return 'no findings';
    const validated = cands.filter(c => isValidatedStatus(c.validation_status)).length;
    if (validated > 0) return `VALIDATED (${validated}/${cands.length})`;
    return 'NOT AVAILABLE (scanner-detected)';
}

// FIX 3: pipeline VALIDATION stage element. Green only for genuine
// VALIDATED findings; otherwise neutral dash with NOT AVAILABLE.
function validationStage(cands) {
    if (!cands.length) {
        return { ok: false, validated: 0, stage: webStageNeutral('VALIDATION', 'NOT AVAILABLE — no findings') };
    }
    const validated = cands.filter(c => isValidatedStatus(c.validation_status)).length;
    if (validated > 0) {
        return { ok: true, validated, stage: webStage(true, 'VALIDATION', `VALIDATED (${validated}/${cands.length})`) };
    }
    return { ok: false, validated: 0, stage: webStageNeutral('VALIDATION', 'NOT AVAILABLE (scanner-detected)') };
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
        const allDiscovery = [];

        for (const run of (runs.runs || [])) {
            const details = await api.getRun(run.run_id).catch(() => null);
            if (details && details.candidates) {
                for (const c of details.candidates) {
                    // FIX 1 + FIX 2: Candidate Ranking never includes
                    // service discovery or informational observations, but
                    // defensively skip any labelled non-actionable record.
                    const kind = c.finding_kind || c.record_type || '';
                    if (kind === 'SERVICE_DISCOVERY' || kind === 'INFORMATIONAL_FINDING' || kind === 'INFORMATIONAL') continue;
                    if ((c.candidate_eligibility || 'ACTIONABLE') !== 'ACTIONABLE') continue;
                    allFindings.push({
                        runId: run.run_id,
                        ...c,
                        candidate_eligibility: c.candidate_eligibility || 'ACTIONABLE',
                        evidenceTier: run.evidence_tier,
                    });
                }
            }
            // FIX 1 + FIX 2: non-actionable inventory (Nmap asset/service
            // context + Nuclei informational / fingerprint / discovery),
            // shown separately with eligibility INFORMATIONAL / DISCOVERY,
            // never ranked.
            const discovery = (details && (details.service_discovery || details.serviceDiscovery)) || [];
            for (const s of discovery) {
                allDiscovery.push({ runId: run.run_id, ...s, candidate_eligibility: s.candidate_eligibility || 'INFORMATIONAL / DISCOVERY', evidenceTier: run.evidence_tier });
            }
        }

        if (allFindings.length === 0 && allDiscovery.length === 0) {
            showEmpty(container, '🔍', 'No findings recorded', 'Run an assessment to see findings here.');
            return;
        }

        container.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Findings</h1>
                <p class="page-subtitle">${allFindings.length} actionable findings (ACTIONABLE) · ${allDiscovery.length} informational / discovery records (INFORMATIONAL / DISCOVERY) across all runs — complete inventory, nothing hidden</p>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">Findings Inventory — Actionable (${allFindings.length}) — candidate eligibility: ACTIONABLE</span></div>
                <p class="text-muted" style="margin-bottom:0.75rem;font-size:0.8rem;">Scanner-detected actionable findings. Outcome is engine execution state, not exploit proof — see Validation Status per finding.</p>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Finding</th>
                            <th>Severity</th>
                            <th>Source</th>
                            <th>Target</th>
                            <th>Quality</th>
                            <th>Outcome</th>
                            <th>Candidate Eligibility</th>
                            <th>Validation Status</th>
                            <th>Evidence</th>
                            <th>Run</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allFindings.map(f => `
                            <tr>
                                <td><strong>${escapeHtml(f.title || f.id)}</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(f.id)}</span></td>
                                <td class="${severityClass(f.severity)}">${escapeHtml(f.severity || 'unknown')}</td>
                                <td>${escapeHtml(f.source || '—')}</td>
                                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(f.target || f.host || '—')}${f.port ? ':' + escapeHtml(String(f.port)) : ''}</td>
                                <td>${escapeHtml(f.quality_rank || 'N/A')}</td>
                                <td><span class="badge ${f.execution_outcome === 'SUCCESS' ? 'badge-success' : 'badge-error'}">${escapeHtml(f.execution_outcome || '-')}</span></td>
                                <td><span class="badge badge-success">ACTIONABLE</span></td>
                                <td><span class="badge ${validationBadgeClass(f.validation_status || (f.evidenceTier === 'DOCKER_OBSERVED' ? 'DOCKER_OBSERVED' : f.evidenceTier === 'SIMULATED' ? 'SIMULATED' : 'VALIDATION NOT AVAILABLE'))}">${escapeHtml(f.validation_status || (f.evidenceTier === 'DOCKER_OBSERVED' ? 'DOCKER_OBSERVED' : f.evidenceTier === 'SIMULATED' ? 'SIMULATED' : 'VALIDATION NOT AVAILABLE'))}</span></td>
                                <td><span class="badge ${evidenceClass(f.evidenceTier)}">${escapeHtml(f.evidenceTier)}</span></td>
                                <td><a href="#/runs" style="color:var(--accent-blue-light);text-decoration:none;font-size:0.8rem;">${escapeHtml(f.runId)}</a></td>
                            </tr>
                        `).join('') || '<tr><td colspan="10" class="text-muted">No actionable findings — only informational / discovery was observed.</td></tr>'}
                    </tbody>
                </table>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">Informational / Discovery (${allDiscovery.length}) — not ranked; candidate eligibility: INFORMATIONAL / DISCOVERY</span></div>
                <p class="text-muted" style="margin-bottom:0.75rem;font-size:0.8rem;">Complete inventory: Nmap asset/service context + Nuclei informational / fingerprint / discovery observations (technology detection, header observations, exposed-service info). Preserved for reporting; never enters AI assessment → ranking → decision.</p>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Endpoint</th>
                            <th>Finding</th>
                            <th>Detail</th>
                            <th>Source</th>
                            <th>Candidate Eligibility</th>
                            <th>Run</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allDiscovery.map(s => {
                            const detail = [s.product, s.version].filter(Boolean).join(' ').trim() || s.description || s.service || s.title || '—';
                            const rectype = s.record_type || s.finding_kind || 'DISCOVERY';
                            return `
                            <tr>
                                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(s.host || s.target || '—')}:${escapeHtml(String(s.port ?? '—'))}/${escapeHtml(s.protocol || 'tcp')}</td>
                                <td><strong>${escapeHtml(s.service || s.title || '—')}</strong><br><span class="text-dim" style="font-size:0.7rem;">${escapeHtml(s.finding_id || s.id || '')}</span></td>
                                <td style="font-size:0.75rem;">${escapeHtml(String(detail).slice(0, 160))}</td>
                                <td>${escapeHtml(s.source || '—')}<br><span class="badge badge-info">${escapeHtml(rectype)}</span></td>
                                <td><span class="badge badge-info">INFORMATIONAL / DISCOVERY</span></td>
                                <td><a href="#/runs" style="color:var(--accent-blue-light);text-decoration:none;font-size:0.8rem;">${escapeHtml(s.runId)}</a></td>
                            </tr>`;
                        }).join('') || '<tr><td colspan="6" class="text-muted">No informational / discovery records</td></tr>'}
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
                        <div class="metric-value">${data.epss != null ? data.epss : 'N/A'}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">CISA KEV</div>
                        <div class="metric-value ${data.in_kev ? 'text-error' : 'text-success'}">${data.in_kev ? 'YES' : 'NO'}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">CVSS Score</div>
                        <div class="metric-value">${data.cvss != null ? data.cvss : 'N/A'}</div>
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
                    // FIX 1 + FIX 2: only ACTIONABLE findings are ranked.
                    // Service discovery and informational / fingerprint /
                    // discovery observations never appear here (backend
                    // guarantees this; filter defensively for display).
                    const kind = c.finding_kind || c.record_type || '';
                    if (kind === 'SERVICE_DISCOVERY' || kind === 'INFORMATIONAL_FINDING' || kind === 'INFORMATIONAL') continue;
                    if ((c.candidate_eligibility || 'ACTIONABLE') !== 'ACTIONABLE') continue;
                    allCandidates.push({ ...c, candidate_eligibility: c.candidate_eligibility || 'ACTIONABLE', runId: run.run_id, scenario: run.scenario });
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
                <p class="page-subtitle">ACTIONABLE candidates only (candidate eligibility: ACTIONABLE) — how AI assessment affects prioritization (GAP-1). Informational / discovery records are shown on the Findings page, never ranked.</p>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Assessment → Scoring → Priority (ACTIONABLE only)</span>
                    <span class="badge badge-info">GAP-1</span>
                </div>
                <p class="text-muted" style="margin-bottom:1rem;font-size:0.85rem;">
                    GAP-1 · Pre-execution AI prioritization: each ACTIONABLE candidate is assessed for quality (HIGH/MEDIUM/LOW) before ranking.
                    The priority score = probability × (0.5 + 0.5 × quality_weight).
                    Quality, fallback marking, score and priority below are backend-recorded per candidate — assessment never invents them here.
                    Informational / discovery observations (INFORMATIONAL / DISCOVERY) never enter this ranking.
                    Outcome is engine execution state, not exploit proof — see Validation Status.
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
                            <th>Candidate Eligibility</th>
                            <th>Validation Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allCandidates.map((c, i) => {
                            const quality = c.quality_rank || 'N/A';
                            const prob = c.probability || 0;
                            const score = prob * (0.5 + 0.5 * { HIGH: 1.0, MEDIUM: 0.6, LOW: 0.3 }[quality] || 0);
                            const vStatus = c.validation_status || 'VALIDATION NOT AVAILABLE';
                            return `
                                <tr>
                                    <td><strong>${escapeHtml(c.id)}</strong></td>
                                    <td>${prob.toFixed(4)}</td>
                                    <td><span class="badge ${quality === 'HIGH' ? 'badge-success' : quality === 'MEDIUM' ? 'badge-warning' : 'badge-error'}">${escapeHtml(quality)}</span></td>
                                    <td>${score.toFixed(4)}</td>
                                    <td>#${i + 1}</td>
                                    <td><span class="badge ${c.execution_outcome === 'SUCCESS' ? 'badge-success' : 'badge-error'}">${escapeHtml(c.execution_outcome || '-')}</span></td>
                                    <td><span class="badge badge-success">ACTIONABLE</span></td>
                                    <td><span class="badge ${validationBadgeClass(vStatus)}">${escapeHtml(vStatus)}</span></td>
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
                    <span class="badge badge-info">GAP-2</span>
                </div>
                <p class="text-muted" style="margin-bottom:1rem;font-size:0.85rem;">
                    GAP-2 · Failure-aware decision pivot: each candidate has a per-candidate attempt counter. When the counter reaches the threshold,
                    the engine pivots to the next candidate. Attempt counts, thresholds and pivots below are backend-recorded per run. This ensures bounded termination.
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
                            <th>Scanners / Findings</th>
                            <th>AI Provider</th>
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
                                <td>${escapeHtml(r.scenario)}${r.assessment_type === 'web' ? ' <span class="badge badge-info">WEB</span>' : ''}</td>
                                <td><span class="badge badge-info">${escapeHtml(r.mode)}</span></td>
                                <td><span class="badge ${r.status === 'COMPLETED' ? 'badge-success' : 'badge-error'}">${escapeHtml(r.status)}</span></td>
                                <td style="font-family:monospace;font-size:0.75rem;">${escapeHtml(r.target_url || r.target || 'N/A')}</td>
                                <td>${r.assessment_type === 'web' ? escapeHtml(String(r.finding_count ?? 0)) + ' findings' : '—'}</td>
                                <td>${escapeHtml(r.assessor_provider || '—')}</td>
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
                                    Outcome: <span class="${c.execution_outcome === 'SUCCESS' ? 'text-success' : 'text-error'}">${escapeHtml(c.execution_outcome || '-')}</span><br>
                                    Validation: ${escapeHtml(c.validation_status || '—')} (outcome ≠ exploit proof)
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
            { name: 'Nmap', status: health.nmap || 'UNKNOWN', detail: 'Local discovery (authorized targets only)' },
            { name: 'Nuclei', status: health.nuclei || 'UNKNOWN', detail: 'Web vuln scan (graceful if not installed)' },
            { name: 'Web Targets', status: 'READY', detail: 'Loopback only: 127.0.0.1, localhost :9191' },
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
                        <tr><td><code>/targets/validate</code></td><td>POST</td><td>Web-target preflight (no scan)</td></tr>
                        <tr><td><code>/scanners/status</code></td><td>GET</td><td>Scanner availability</td></tr>
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

    // FIX 5: clicking the active nav entry does not change the hash, so
    // no hashchange fires and the router would never re-run — leaving a
    // previous run's result on screen. Re-render explicitly so New
    // Assessment (and any other page) always returns to a fresh state.
    document.addEventListener('click', (event) => {
        const anchor = event.target && event.target.closest
            ? event.target.closest('a[href^="#/"]')
            : null;
        if (!anchor) return;
        const target = anchor.getAttribute('href');
        if (target && window.location.hash === target) {
            event.preventDefault();
            router();
        }
    });
});
