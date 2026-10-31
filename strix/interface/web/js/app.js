/**
 * AI-VAPT Autonomous Operations Console
 * Modern, High-Performance Vanilla JS Frontend Engine
 */

(function () {
  'use strict';

  // Standard Default Models for Providers
  const DEFAULT_PROVIDER_MODELS = {
    openrouter: [
      { id: 'openrouter/free', name: 'Free Models Router [FREE]', free: true },
      { id: 'meta-llama/llama-3.3-70b-instruct:free', name: 'Llama 3.3 70B Instruct [FREE]', free: true },
      { id: 'deepseek/deepseek-r1:free', name: 'DeepSeek R1 Reasoning [FREE]', free: true },
      { id: 'meta-llama/llama-3.2-3b-instruct:free', name: 'Llama 3.2 3B Instruct [FREE]', free: true },
      { id: 'google/gemini-2.0-flash-exp:free', name: 'Gemini 2.0 Flash Exp [FREE]', free: true },
      { id: 'google/gemma-4-31b-it:free', name: 'Google Gemma 4 31B [FREE]', free: true },
      { id: 'google/gemma-4-26b-a4b-it:free', name: 'Google Gemma 4 26B [FREE]', free: true },
      { id: 'cohere/north-mini-code:free', name: 'Cohere North Mini Code [FREE]', free: true },
      { id: 'nvidia/nemotron-3.5-lightning:free', name: 'NVIDIA Nemotron 3.5 Lightning [FREE]', free: true },
      { id: 'qwen/qwen-2.5-coder-32b-instruct:free', name: 'Qwen 2.5 Coder 32B [FREE]', free: true },
      { id: 'mistralai/mistral-7b-instruct:free', name: 'Mistral 7B Instruct [FREE]', free: true },
    ],
    ollama: [
      { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Local Default)' },
      { id: 'llama3.2:3b', name: 'Llama 3.2 3B (Local Baseline)' },
      { id: 'deepseek-r1:1.5b', name: 'DeepSeek R1 1.5B (Local)' },
    ],
    google: [
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash (Fast)' },
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro (Flagship)' },
      { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash' },
    ],
    openai: [
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Fast)' },
      { id: 'gpt-4o', name: 'GPT-4o (Flagship)' },
      { id: 'o3-mini', name: 'o3-mini (Reasoning)' },
    ],
  };

  // State Management
  const state = {
    activeRunId: null,
    pollTimer: null,
    systemHealthy: true,
    runtimeApiKey: '',
    currentView: 'new-assessment',
    latestRunData: null,
    availableModels: [...DEFAULT_PROVIDER_MODELS.openrouter],
    dagZoom: 1.0,
    dagPanX: 0,
    dagPanY: 0,
    dagFilterMode: 'found',
    selectedCandidateId: null,
  };

  let isDagPanning = false;
  let dagStartX = 0;
  let dagStartY = 0;
  let currentDagCandidates = [];
  let currentDagPivotEvents = [];

  // DOM Elements Cache
  const elements = {};

  function initElements() {
    elements.navLinks = document.querySelectorAll('.nav-link');
    elements.views = document.querySelectorAll('.view-section');
    elements.sysDot = document.getElementById('sys-status-dot');
    elements.sysText = document.getElementById('sys-status-text');

    // New Assessment
    elements.targetUrlInput = document.getElementById('target-url-input');
    elements.btnPreflight = document.getElementById('btn-preflight-target');
    elements.scopeFeedback = document.getElementById('target-scope-feedback');
    elements.scanModeSelect = document.getElementById('scan-mode-select');
    elements.scanIntensity = document.getElementById('scan-intensity-select');
    elements.executionLimitsSelect = document.getElementById('execution-limits-select');
    elements.chkScopeAck = document.getElementById('chk-scope-ack');
    elements.modelProviderSelect = document.getElementById('model-provider-select');
    elements.modelSelect = document.getElementById('model-select');
    elements.modelCustomInput = document.getElementById('model-custom-input');
    elements.modelBadgeStatus = document.getElementById('model-badge-status');
    elements.modelHint = document.getElementById('model-hint');
    elements.groupApiKey = document.getElementById('group-api-key');
    elements.runtimeApiKey = document.getElementById('runtime-api-key');
    elements.btnValidateKey = document.getElementById('btn-validate-model-key');
    elements.apiKeyFeedback = document.getElementById('api-key-feedback');
    elements.gap2Threshold = document.getElementById('gap2-threshold-select');
    elements.btnLaunch = document.getElementById('btn-launch-assessment');

    // Active Assessment
    elements.heroRunStatus = document.getElementById('hero-run-status');
    elements.heroRunId = document.getElementById('hero-run-id');
    elements.heroTargetText = document.getElementById('hero-target-text');
    elements.heroModeText = document.getElementById('hero-mode-text');
    elements.btnStopRun = document.getElementById('btn-stop-run');
    elements.btnViewReportNow = document.getElementById('btn-view-report-now');
    elements.btnRefreshRun = document.getElementById('btn-refresh-run');
    elements.metricCandidates = document.getElementById('metric-candidates-count');
    elements.metricPivots = document.getElementById('metric-pivots-count');
    elements.metricAttempts = document.getElementById('metric-attempts-count');
    elements.metricFindings = document.getElementById('metric-findings-count');
    elements.tbodyCandidates = document.getElementById('tbody-candidates');
    elements.findingsLive = document.getElementById('findings-live-container');
    elements.tbodyMatrixLive = document.getElementById('tbody-matrix-live');
    elements.tbodyPortsLive = document.getElementById('tbody-ports-live');
    elements.tbodyComponentsLive = document.getElementById('tbody-components-live');
    elements.badgePortsCount = document.getElementById('badge-ports-count');
    elements.badgeComponentsCount = document.getElementById('badge-components-count');
    elements.badgeSpiderLive = document.getElementById('badge-spider-live');
    elements.dagSvg = document.getElementById('dag-svg');
    elements.dagContainer = document.getElementById('dag-container');
    elements.dagNodeDetail = document.getElementById('dag-node-detail');
    elements.btnDagZoomIn = document.getElementById('btn-dag-zoom-in');
    elements.btnDagZoomOut = document.getElementById('btn-dag-zoom-out');
    elements.btnDagReset = document.getElementById('btn-dag-reset');
    elements.btnDagFilterFound = document.getElementById('btn-dag-filter-found');
    elements.btnDagFilterPivots = document.getElementById('btn-dag-filter-pivots');
    elements.btnDagFilterAll = document.getElementById('btn-dag-filter-all');
    elements.btnDagExpand = document.getElementById('btn-dag-expand');
    elements.terminalBody = document.getElementById('terminal-body');
    elements.terminalCount = document.getElementById('terminal-line-count');

    // Reports
    elements.reportRunRef = document.getElementById('report-run-ref');
    elements.reportContentArea = document.getElementById('report-content-area');
    elements.btnDownloadHtml = document.getElementById('btn-download-html-report');
    elements.btnDownloadPdf = document.getElementById('btn-download-pdf-report');
    elements.btnDownloadJson = document.getElementById('btn-download-json-report');
    elements.btnDownloadSarif = document.getElementById('btn-download-sarif-report');
    elements.btnDownloadMd = document.getElementById('btn-download-md-report');

    // History
    elements.tbodyHistory = document.getElementById('tbody-history');
    elements.btnRefreshHistory = document.getElementById('btn-refresh-history');

    // Settings
    elements.cardOllamaBadge = document.getElementById('card-ollama-badge');
    elements.ollamaModelsList = document.getElementById('ollama-models-list');
    elements.btnProbeOllama = document.getElementById('btn-probe-ollama');
    elements.settingsProviderSelect = document.getElementById('settings-provider-select');
    elements.settingsModelInput = document.getElementById('settings-model-input');
    elements.settingsApiKey = document.getElementById('settings-api-key');
    elements.settingsCurrentKeyHint = document.getElementById('settings-current-key-hint');
    elements.btnTestCloudKey = document.getElementById('btn-test-cloud-key');
    elements.btnSaveLlmConfig = document.getElementById('btn-save-llm-config');
    elements.settingsStatusBadge = document.getElementById('settings-status-badge');
    elements.settingsKeyResult = document.getElementById('settings-key-result');

    // Toasts
    elements.toastContainer = document.getElementById('toast-container');
  }

  // Toast Notification Helper
  function showToast(message, type = 'info') {
    if (!elements.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    toast.innerHTML = `<span>${icon}</span><span style="font-size:0.9rem;">${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // View Navigation
  function switchView(viewName) {
    state.currentView = viewName;
    elements.views.forEach((v) => {
      v.classList.remove('active');
      if (v.id === `view-${viewName}`) v.classList.add('active');
    });

    elements.navLinks.forEach((link) => {
      link.classList.remove('active');
      if (link.dataset.view === viewName) link.classList.add('active');
    });

    window.location.hash = `#/${viewName}`;

    if (viewName === 'history') {
      loadHistory();
    } else if (viewName === 'settings') {
      probeOllamaService();
    }
  }

  // Populate Dynamic Models in Dropdown
  function populateModelOptions(provider, modelsList = []) {
    const list = modelsList && modelsList.length ? modelsList : DEFAULT_PROVIDER_MODELS[provider] || [];
    elements.modelSelect.innerHTML = '';

    list.forEach((m) => {
      const opt = document.createElement('option');
      opt.value = m.id;
      const isFree = m.free || m.id.endsWith(':free');
      opt.textContent = isFree ? `${m.id} [FREE]` : (m.name || m.id);
      elements.modelSelect.appendChild(opt);
    });

    // Custom option
    const customOpt = document.createElement('option');
    customOpt.value = '__custom__';
    customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
    elements.modelSelect.appendChild(customOpt);

    // Update status badge
    if (provider === 'openrouter') {
      const freeCount = list.filter((m) => m.free || m.id.endsWith(':free')).length;
      elements.modelBadgeStatus.textContent = `${freeCount} Free Models Available`;
      elements.modelBadgeStatus.className = 'badge badge-emerald';
      elements.modelHint.textContent = 'All free models are loaded from OpenRouter with zero token charges.';
    } else if (provider === 'ollama') {
      elements.modelBadgeStatus.textContent = 'Local Offline';
      elements.modelBadgeStatus.className = 'badge badge-cyan';
      elements.modelHint.textContent = 'Runs entirely locally on your machine with zero external network access.';
    } else if (provider === 'google') {
      elements.modelBadgeStatus.textContent = 'Google Cloud';
      elements.modelBadgeStatus.className = 'badge badge-purple';
      elements.modelHint.textContent = 'High-speed completions via Google Gemini API.';
    } else {
      elements.modelBadgeStatus.textContent = 'OpenAI API';
      elements.modelBadgeStatus.className = 'badge badge-amber';
    }

    elements.modelCustomInput.style.display = 'none';
  }

  // Handle Model Select Change
  function onModelSelectChange() {
    if (elements.modelSelect.value === '__custom__') {
      elements.modelCustomInput.style.display = 'block';
      elements.modelCustomInput.focus();
    } else {
      elements.modelCustomInput.style.display = 'none';
    }
  }

  // Get Currently Chosen Model ID
  function getSelectedModelId() {
    if (elements.modelSelect.value === '__custom__') {
      return elements.modelCustomInput.value.trim() || 'meta-llama/llama-3.2-3b-instruct:free';
    }
    return elements.modelSelect.value;
  }

  // System Health Probe
  async function checkSystemHealth() {
    try {
      const res = await fetch('/system/health');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.systemHealthy = data.status === 'READY';
      if (elements.sysDot && elements.sysText) {
        elements.sysDot.style.background = state.systemHealthy ? '#10b981' : '#f59e0b';
        elements.sysText.textContent = state.systemHealthy ? 'SYSTEM OPERATIONAL' : 'SYSTEM DEGRADED';
      }

      // If Ollama is active, sync its models
      const ollama = data.components?.ollama;
      if (ollama && elements.cardOllamaBadge) {
        if (ollama.available) {
          elements.cardOllamaBadge.textContent = 'AVAILABLE';
          elements.cardOllamaBadge.className = 'badge badge-emerald';
        } else {
          elements.cardOllamaBadge.textContent = 'UNAVAILABLE';
          elements.cardOllamaBadge.className = 'badge badge-rose';
        }
        if (ollama.models && elements.ollamaModelsList) {
          elements.ollamaModelsList.innerHTML = ollama.models.length
            ? ollama.models.map((m) => `<div>• ${escapeHtml(m)}</div>`).join('')
            : 'No models found in Ollama tags.';
        }
      }
    } catch (err) {
      if (elements.sysDot && elements.sysText) {
        elements.sysDot.style.background = '#ef4444';
        elements.sysText.textContent = 'GATEWAY OFFLINE';
      }
    }
  }

  // Fetch live free models from OpenRouter catalog
  async function loadOpenRouterFreeModels() {
    try {
      const res = await fetch('/providers/openrouter/models');
      if (res.ok) {
        const liveModels = await res.json();
        if (liveModels && liveModels.length) {
          DEFAULT_PROVIDER_MODELS.openrouter = liveModels;
          if (elements.modelProviderSelect && elements.modelProviderSelect.value === 'openrouter') {
            const currentSelected = elements.modelSelect ? elements.modelSelect.value : null;
            populateModelOptions('openrouter', liveModels);
            if (currentSelected && elements.modelSelect.querySelector(`option[value="${currentSelected}"]`)) {
              elements.modelSelect.value = currentSelected;
            }
          }
        }
      }
    } catch (e) {
      // Fallback already preloaded
    }
  }

  // Model Provider Change Handling
  function onProviderChange() {
    const provider = elements.modelProviderSelect.value;
    if (provider === 'ollama') {
      elements.groupApiKey.style.display = 'none';
      populateModelOptions('ollama');
    } else {
      elements.groupApiKey.style.display = 'block';
      populateModelOptions(provider);
      if (provider === 'openrouter') {
        elements.runtimeApiKey.placeholder = 'Paste OpenRouter API key (Never saved to disk)';
        loadOpenRouterFreeModels();
      } else if (provider === 'google') {
        elements.runtimeApiKey.placeholder = 'Paste Google Gemini API key';
      } else {
        elements.runtimeApiKey.placeholder = 'Paste OpenAI API key';
      }
    }
  }

  // Preflight Scope Validation
  async function preflightTarget() {
    const url = elements.targetUrlInput.value.trim();
    if (!url) {
      showToast('Please enter a target URL first', 'error');
      return;
    }

    elements.scopeFeedback.style.display = 'block';
    elements.scopeFeedback.innerHTML = `<span class="badge badge-cyan">Validating DNS & Scope...</span>`;

    try {
      const res = await fetch('/targets/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_url: url }),
      });
      const data = await res.json();
      if (data.authorized) {
        elements.scopeFeedback.innerHTML = `
          <div style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); padding: 0.65rem 1rem; border-radius: var(--radius-md); font-size: 0.85rem; color: #34d399;">
            <strong>Target Scope Authorized:</strong> ${escapeHtml(data.detail)} (Resolved: ${escapeHtml((data.resolved_ips || []).join(', ') || 'Public Target')})
          </div>`;
        showToast('Target authorization verified!', 'success');
      } else {
        elements.scopeFeedback.innerHTML = `
          <div style="background: rgba(244,63,94,0.1); border: 1px solid rgba(244,63,94,0.3); padding: 0.65rem 1rem; border-radius: var(--radius-md); font-size: 0.85rem; color: #fb7185;">
            <strong>Scope Alert:</strong> ${escapeHtml(data.detail)}
          </div>`;
        showToast('Target rejected by fail-closed gatekeeper', 'error');
      }
    } catch (err) {
      elements.scopeFeedback.innerHTML = `<span class="badge badge-rose">Validation Error: ${escapeHtml(err.message)}</span>`;
    }
  }

  // Test Cloud API Key & Fetch Available Models
  async function validateCloudKey(provider, key, feedbackEl) {
    if (!key) {
      feedbackEl.innerHTML = `<span style="color:#fb7185;">Please enter an API key to test.</span>`;
      return;
    }

    feedbackEl.innerHTML = `<span style="color:#38bdf8;">Testing connection and retrieving available models...</span>`;
    const endpoint = provider === 'google' ? '/providers/google/validate' : '/providers/openrouter/validate';
    const headerName = provider === 'google' ? 'X-Google-API-Key' : 'X-OpenRouter-API-Key';

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          [headerName]: key,
        },
        body: JSON.stringify({ api_key: key }),
      });
      const data = await res.json();
      if (data.valid || data.status === 'configured') {
        state.runtimeApiKey = key;

        // If OpenRouter returns models, dynamically populate the dropdown
        if (data.models && data.models.length) {
          const formatted = data.models.map((m) =>
            typeof m === 'string' ? { id: m, name: m, free: m.includes(':free') } : m
          );
          populateModelOptions(provider, formatted);
          const freeCount = formatted.filter((m) => m.free || m.id.endsWith(':free') || m.id === 'openrouter/free').length;
          feedbackEl.innerHTML = `<span style="color:#34d399; font-weight: 600;">✅ Key Valid! ${freeCount} free models available in dropdown above.</span>`;
          showToast(`OpenRouter verified! ${freeCount} free models ready.`, 'success');
        } else {
          feedbackEl.innerHTML = `<span style="color:#34d399;">✅ Valid! ${escapeHtml(data.message)}</span>`;
          showToast(`${provider.toUpperCase()} credentials verified!`, 'success');
        }
      } else {
        feedbackEl.innerHTML = `<span style="color:#fb7185;">❌ ${escapeHtml(data.message || 'Key rejected')}</span>`;
        showToast(`Verification failed: ${data.message}`, 'error');
      }
    } catch (err) {
      feedbackEl.innerHTML = `<span style="color:#fb7185;">❌ Network error: ${escapeHtml(err.message)}</span>`;
    }
  }

  // Probe Ollama from Settings
  async function probeOllamaService() {
    elements.cardOllamaBadge.textContent = 'PROBING...';
    elements.cardOllamaBadge.className = 'badge badge-cyan';
    try {
      await checkSystemHealth();
      showToast('Ollama service probed', 'info');
    } catch (err) {
      showToast('Failed to probe Ollama', 'error');
    }
  }

  // Launch Assessment Run
  async function launchAssessment() {
    const targetUrl = elements.targetUrlInput.value.trim();
    if (!targetUrl) {
      showToast('Target URL is required', 'error');
      return;
    }

    if (!elements.chkScopeAck.checked) {
      showToast('Please confirm target scope authorization', 'error');
      return;
    }

    const provider = elements.modelProviderSelect.value;
    const model = getSelectedModelId();
    const mode = elements.scanModeSelect ? elements.scanModeSelect.value : 'autonomous';
    const maxAttempts = parseInt(elements.gap2Threshold.value, 10) || 2;
    const apiKey = elements.runtimeApiKey.value.trim();

    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
      if (provider === 'google') headers['X-Google-API-Key'] = apiKey;
      else if (provider === 'openrouter') headers['X-OpenRouter-API-Key'] = apiKey;
    }

    elements.btnLaunch.disabled = true;
    elements.btnLaunch.innerHTML = `<span>⏳</span> Launching Assessment...`;

    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_url: targetUrl,
          target: targetUrl,
          mode: mode || 'autonomous',
          scan_mode: elements.scanIntensity ? elements.scanIntensity.value : 'deep',
          max_turns: elements.executionLimitsSelect ? parseInt(elements.executionLimitsSelect.value, 10) : 100,
          scenario: 'web_assessment',
          assessor: 'llm',
          assessor_provider: provider,
          assessor_model: model,
          assessor_api_key: apiKey || null,
          max_attempts: maxAttempts,
          target_scope_acknowledged: true,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.activeRunId = data.run_id;

      showToast(`Assessment ${data.run_id} launched!`, 'success');
      switchView('active-assessment');
      startRunPolling(data.run_id);
    } catch (err) {
      showToast(`Failed to launch assessment: ${err.message}`, 'error');
    } finally {
      elements.btnLaunch.disabled = false;
      elements.btnLaunch.innerHTML = `<span>⚡</span> Launch Autonomous VAPT Assessment`;
    }
  }

  // Active Assessment Polling and Server-Sent Events (SSE) Streaming
  function startRunPolling(runId) {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }

    fetchRunState(runId);

    // Attempt Server-Sent Events (SSE) for low-latency live streaming
    try {
      const sse = new EventSource(`/runs/${runId}/stream`);
      state.eventSource = sse;

      sse.addEventListener('state', (e) => {
        try {
          const run = JSON.parse(e.data);
          state.latestRunData = run;
          renderActiveRun(run);
        } catch (err) {}
      });

      sse.addEventListener('log', (e) => {
        try {
          const entry = JSON.parse(e.data);
          if (state.latestRunData) {
            state.latestRunData.decision_trace = state.latestRunData.decision_trace || [];
            state.latestRunData.decision_trace.push(entry);
            renderTerminalLogs(state.latestRunData.decision_trace);
          }
        } catch (err) {}
      });

      sse.addEventListener('complete', (e) => {
        sse.close();
        state.eventSource = null;
        fetchRunState(runId);
      });

      sse.onerror = () => {
        // Fall back to polling if SSE disconnected
        if (!state.pollTimer) {
          state.pollTimer = setInterval(() => {
            fetchRunState(runId);
          }, 1500);
        }
      };
    } catch (e) {
      state.pollTimer = setInterval(() => {
        fetchRunState(runId);
      }, 1500);
    }
  }

  async function fetchRunState(runId) {
    if (!runId) return;
    try {
      const res = await fetch(`/runs/${runId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const run = await res.json();
      state.latestRunData = run;
      renderActiveRun(run);

      if (run.status === 'completed' || run.status === 'failed') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        if (run.status === 'completed') {
          elements.btnViewReportNow.style.display = 'inline-flex';
          showToast(`Assessment ${runId} completed!`, 'success');
        }
      }
    } catch (err) {
      console.error('Run polling error:', err);
    }
  }

  // Render Active Run Dashboard
  function renderActiveRun(run) {
    elements.heroRunId.textContent = run.run_id;
    elements.heroTargetText.textContent = run.target_url || 'Target Application';
    elements.heroModeText.textContent = `Mode: ${(run.mode || 'web').toUpperCase()}`;

    const status = (run.status || 'running').toUpperCase();
    elements.heroRunStatus.textContent = status;
    if (status === 'COMPLETED') {
      elements.heroRunStatus.className = 'badge badge-emerald';
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'none';
      if (elements.btnViewReportNow) elements.btnViewReportNow.style.display = 'inline-flex';
    } else if (status === 'FAILED' || status === 'ABORTED') {
      elements.heroRunStatus.className = 'badge badge-rose';
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'none';
    } else {
      elements.heroRunStatus.className = 'badge badge-cyan';
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'inline-flex';
      if (elements.btnViewReportNow) elements.btnViewReportNow.style.display = 'none';
    }

    // Metrics
    const candidates = run.candidates || [];
    const pivotEvents = run.pivot_events || [];
    const findings = run.findings || [];
    const trace = run.decision_trace || [];

    const totalAttempts = candidates.reduce((acc, c) => acc + (c.attempts || 0), 0);
    const totalPivots = pivotEvents.filter((e) => e.type === 'REDIRECT').length;

    elements.metricCandidates.textContent = candidates.length;
    elements.metricPivots.textContent = totalPivots;
    elements.metricAttempts.textContent = totalAttempts;
    elements.metricFindings.textContent = findings.length;

    renderCandidateTable(candidates);
    renderDecisionDag(candidates, pivotEvents);
    renderTerminalLogs(trace);
    renderFindingsLive(findings);
    renderReconSummaryLive(run);
  }

  // Render Live Multi-Category Reconnaissance Summary Cards
  function renderReconSummaryLive(run) {
    if (!run) return;
    const scanMatrix = run.scan_matrix || [];
    const openPorts = run.open_ports || [];
    const components = run.components || [];
    const spider = run.spider_stats;

    // 0. Spider Status
    if (elements.badgeSpiderLive) {
      if (spider && spider.discovered_paths && spider.discovered_paths.length) {
        elements.badgeSpiderLive.style.display = 'inline-block';
        elements.badgeSpiderLive.textContent = `🕷️ Spider: ${spider.discovered_paths.length} route(s), ${spider.forms_count || 0} form(s)`;
      } else {
        elements.badgeSpiderLive.style.display = 'none';
      }
    }

    // 1. Matrix
    if (elements.tbodyMatrixLive) {
      if (scanMatrix.length) {
        elements.tbodyMatrixLive.innerHTML = scanMatrix.map((m) => {
          const cnt = m.findings_count || 0;
          const statusBadge = cnt > 0
            ? '<span class="badge badge-amber">FINDINGS</span>'
            : '<span class="badge badge-emerald">PASSED</span>';
          return `<tr>
            <td><strong>${escapeHtml(m.title)}</strong></td>
            <td>${m.test_count} tests</td>
            <td style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(m.capability || 'Passive/Active')}</td>
            <td><strong style="color:${cnt > 0 ? '#f59e0b' : '#10b981'};">${cnt}</strong> ${statusBadge}</td>
          </tr>`;
        }).join('');
      }
    }

    // 2. Open Ports
    if (elements.badgePortsCount) {
      elements.badgePortsCount.textContent = `${openPorts.length} Open Port(s)`;
    }
    if (elements.tbodyPortsLive) {
      if (openPorts.length) {
        elements.tbodyPortsLive.innerHTML = openPorts.map((p) => {
          const sev = (p.severity || 'low').toUpperCase();
          const badgeClass = sev === 'HIGH' ? 'badge-rose' : (sev === 'MEDIUM' ? 'badge-amber' : 'badge-cyan');
          return `<tr>
            <td><strong style="font-family:var(--font-mono); color:#38bdf8;">${p.port}/${(p.protocol || 'tcp').toUpperCase()}</strong></td>
            <td>${escapeHtml(p.service || 'TCP')}</td>
            <td><span class="badge badge-emerald">OPEN</span></td>
            <td><span class="badge ${badgeClass}">${sev}</span></td>
          </tr>`;
        }).join('');
      }
    }

    // 3. Components (SCA)
    if (elements.badgeComponentsCount) {
      elements.badgeComponentsCount.textContent = `${components.length} Library(ies)`;
    }
    if (elements.tbodyComponentsLive) {
      if (components.length) {
        elements.tbodyComponentsLive.innerHTML = components.map((comp) => {
          const cves = comp.cves || [];
          const cveBadges = cves.length
            ? cves.slice(0, 2).map((cve) => `<span style="font-family:var(--font-mono); font-size:0.7rem; background:rgba(99,102,241,0.15); color:#a5b4fc; padding:0.15rem 0.35rem; border-radius:3px;">${escapeHtml(cve)}</span>`).join(' ') + (cves.length > 2 ? ` <small>+${cves.length - 2}</small>` : '')
            : '<span style="font-size:0.75rem; color:var(--text-muted);">None</span>';
          const statBadge = comp.vulnerable
            ? '<span class="badge badge-amber">OUTDATED</span>'
            : '<span class="badge badge-emerald">SECURE</span>';
          return `<tr>
            <td><strong>${escapeHtml(comp.library.toUpperCase())}</strong></td>
            <td><code style="color:#38bdf8;">v${escapeHtml(comp.version)}</code></td>
            <td>${statBadge}</td>
            <td>${cveBadges}</td>
          </tr>`;
        }).join('');
      }
    }
  }

  // Render Candidates Table (GAP-1)
  function renderCandidateTable(candidates) {
    if (!candidates || !candidates.length) {
      elements.tbodyCandidates.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Assessing surface candidates...</td></tr>`;
      return;
    }

    elements.tbodyCandidates.innerHTML = candidates
      .map((c, idx) => {
        const rank = c.usability_rank || 'MEDIUM';
        const rankBadge =
          rank === 'HIGH'
            ? '<span class="badge badge-emerald">HIGH</span>'
            : rank === 'MEDIUM'
            ? '<span class="badge badge-amber">MEDIUM</span>'
            : '<span class="badge badge-rose">LOW</span>';

        const stateBadge =
          c.state === 'VALIDATED'
            ? '<span class="badge badge-emerald">VALIDATED</span>'
            : c.state === 'ABANDONED'
            ? '<span class="badge badge-rose">ABANDONED (PIVOT)</span>'
            : c.state === 'ATTEMPTING'
            ? '<span class="badge badge-cyan">ATTEMPTING</span>'
            : '<span class="badge" style="background:#334155;color:#94a3b8;">PENDING</span>';

        const priorityScore = (c.composite_score !== undefined && c.composite_score !== null)
          ? Number(c.composite_score).toFixed(3)
          : (c.probability !== undefined ? Number(c.probability).toFixed(3) : '0.500');

        const rankNum = c.priority_rank || (idx + 1);
        const rankPillClass = rankNum === 1 ? 'badge-amber' : (rankNum <= 3 ? 'badge-cyan' : 'badge-secondary');

        return `<tr>
          <td style="text-align: center;"><span class="badge ${rankPillClass}" style="font-weight:700;">#${rankNum}</span></td>
          <td>
            <strong>${escapeHtml(c.name || c.id)}</strong>
            <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(c.owasp_category || '')} ${escapeHtml(c.cwe_id || '')}</div>
          </td>
          <td><span class="badge badge-amber">${escapeHtml((c.severity || 'medium').toUpperCase())}</span></td>
          <td>${rankBadge}</td>
          <td><strong style="color:#38bdf8; font-family:var(--font-mono); font-size:0.95rem;">${priorityScore}</strong></td>
          <td>${stateBadge}</td>
        </tr>`;
      })
      .join('');
  }

  // Interactive DAG State & Inspection Controls
  function applyDagTransform() {
    const vp = document.getElementById('dag-viewport');
    if (vp) {
      vp.setAttribute('transform', `translate(${state.dagPanX}, ${state.dagPanY}) scale(${state.dagZoom})`);
    }
  }

  function setDagFilter(mode) {
    state.dagFilterMode = mode;
    ['found', 'pivots', 'all'].forEach((m) => {
      const btn = document.getElementById(`btn-dag-filter-${m}`);
      if (btn) {
        if (m === mode) {
          btn.classList.add('btn-active');
          btn.classList.remove('btn-secondary');
        } else {
          btn.classList.remove('btn-active');
          btn.classList.add('btn-secondary');
        }
      }
    });
    renderDecisionDag(currentDagCandidates, currentDagPivotEvents);
  }

  function inspectDagNode(cid) {
    state.selectedCandidateId = cid;
    const cand = (currentDagCandidates || []).find((c) => c.id === cid);
    const detailBox = elements.dagNodeDetail || document.getElementById('dag-node-detail');
    if (!detailBox || !cand) return;

    // Highlight active node in SVG
    document.querySelectorAll('.dag-node').forEach((n) => {
      if (n.getAttribute('data-id') === cid) {
        n.classList.add('active-node');
      } else {
        n.classList.remove('active-node');
      }
    });

    const isVal = cand.state === 'VALIDATED';
    const isAb = cand.state === 'ABANDONED';
    const statusColor = isVal ? '#34d399' : (isAb ? '#f43f5e' : '#38bdf8');
    const statusText = isVal ? 'CONFIRMED VULNERABILITY (PoC Validated)' : (isAb ? 'PIVOT REDIRECT (k=2 Attempt Limit Hit)' : cand.state);

    detailBox.style.display = 'block';
    detailBox.innerHTML = `
      <div class="dag-node-inspector-header">
        <div class="dag-node-inspector-title"><span>🔍</span> Candidate: ${escapeHtml(cand.name || cand.id)}</div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <span class="badge" style="background:${statusColor}22; color:${statusColor}; border:1px solid ${statusColor}55;">${statusText}</span>
          <button type="button" class="btn btn-xs btn-secondary" onclick="document.getElementById('dag-node-detail').style.display='none';">✕</button>
        </div>
      </div>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:0.75rem; font-size:0.8rem; margin-top:0.5rem;">
        <div><strong style="color:var(--text-muted);">Target Endpoint:</strong> <code style="color:#7dd3fc;">${escapeHtml(cand.endpoint || cand.target || '/')}</code></div>
        <div><strong style="color:var(--text-muted);">Priority Score (GAP-1):</strong> <span style="color:#38bdf8; font-weight:700;">${cand.composite_score !== undefined ? Number(cand.composite_score).toFixed(3) : '0.500'}</span> (#${cand.priority_rank || 1})</div>
        <div><strong style="color:var(--text-muted);">Usability Rank:</strong> <span class="badge badge-purple">${escapeHtml(cand.usability_rank || 'MEDIUM')}</span></div>
        <div><strong style="color:var(--text-muted);">Attempts / Limit:</strong> <span style="font-family:monospace;">${cand.attempts || 0} / ${cand.max_attempts || 2}</span></div>
      </div>
      ${cand.evidence_hash ? `<div style="margin-top:0.5rem; font-size:0.75rem; background:#020617; padding:0.35rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Proof Hash:</strong> <code style="color:#34d399;">${escapeHtml(cand.evidence_hash)}</code></div>` : ''}
    `;
  }

  // Expose to window for inline svg onclick handlers
  window.inspectDagNode = inspectDagNode;
  window.setDagFilter = setDagFilter;

  // Render Live Interactive SVG Decision DAG
  function renderDecisionDag(candidates, pivotEvents) {
    const svg = elements.dagSvg;
    if (!svg) return;

    currentDagCandidates = candidates || [];
    currentDagPivotEvents = pivotEvents || [];

    if (!currentDagCandidates.length) {
      svg.innerHTML = `<text x="490" y="280" fill="#64748b" text-anchor="middle" font-size="14" font-family="sans-serif">Evaluating discovered attack surface nodes...</text>`;
      return;
    }

    // Filter according to current dagFilterMode
    let displayNodes = currentDagCandidates;
    if (state.dagFilterMode === 'found') {
      const found = currentDagCandidates.filter((c) => c.state === 'VALIDATED' || c.state === 'ABANDONED');
      displayNodes = found.length ? found : currentDagCandidates;
    } else if (state.dagFilterMode === 'pivots') {
      const pivots = currentDagCandidates.filter((c) => c.state === 'ABANDONED' || (c.attempts && c.attempts > 1));
      displayNodes = pivots.length ? pivots : currentDagCandidates;
    }

    const count = displayNodes.length;
    const rowHeight = 64;
    const totalHeight = Math.max(620, count * rowHeight + 90);
    svg.setAttribute('viewBox', `0 0 980 ${totalHeight}`);

    const rootX = 70;
    const rootY = totalHeight / 2;
    const candX = 330;
    const startY = 55;
    const stepY = count > 1 ? (totalHeight - 110) / (count - 1) : 0;

    let nodesHtml = '';
    let edgesHtml = '';

    displayNodes.forEach((c, idx) => {
      const cy = count === 1 ? totalHeight / 2 : startY + idx * stepY;
      const isValidated = c.state === 'VALIDATED';
      const isAbandoned = c.state === 'ABANDONED';
      const isAttempting = c.state === 'ATTEMPTING';

      const strokeColor = isValidated ? '#10b981' : (isAbandoned ? '#f43f5e' : (isAttempting ? '#06b6d4' : '#475569'));
      const fillColor = isValidated ? '#064e3b' : (isAbandoned ? '#4c0519' : (isAttempting ? '#083344' : '#1e293b'));
      const edgeColor = isValidated ? '#059669' : (isAbandoned ? '#f43f5e' : '#334155');
      const markerId = isAbandoned ? 'url(#arrow-red)' : (isValidated ? 'url(#arrow-green)' : 'url(#arrow)');

      // Edge from Target to Candidate
      edgesHtml += `
        <path d="M ${rootX + 30} ${rootY} C ${rootX + 140} ${rootY}, ${candX - 120} ${cy}, ${candX - 22} ${cy}" 
              stroke="${edgeColor}" stroke-width="${isValidated ? '2.5' : '1.8'}" fill="none" marker-end="${markerId}" opacity="0.85"/>
      `;

      // Candidate Node & Label
      const activeClass = state.selectedCandidateId === c.id ? 'active-node' : '';
      const badgeText = isValidated ? '✓ VALIDATED' : (isAbandoned ? '✕ PIVOT HIT' : (isAttempting ? '⟳ PROBING' : (c.state || 'PENDING')));

      nodesHtml += `
        <g class="dag-node ${activeClass}" data-id="${c.id}" onclick="inspectDagNode('${c.id}')">
          <circle cx="${candX}" cy="${cy}" r="18" fill="${fillColor}" stroke="${strokeColor}" stroke-width="2.2"/>
          <text x="${candX}" y="${cy + 4}" fill="#ffffff" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">C${idx + 1}</text>
          
          <!-- Title & Endpoint Text -->
          <text x="${candX + 26}" y="${cy - 6}" fill="#f8fafc" font-size="13" font-weight="700" font-family="sans-serif">${escapeHtml(c.name || c.id)}</text>
          <text x="${candX + 26}" y="${cy + 9}" fill="#94a3b8" font-size="9.5" font-family="monospace">${escapeHtml(c.endpoint || c.target || '/')}</text>
          
          <!-- Status Pill -->
          <rect x="${candX + 26}" y="${cy + 15}" width="88" height="16" rx="3" fill="${fillColor}" stroke="${strokeColor}" stroke-width="1"/>
          <text x="${candX + 70}" y="${cy + 27}" fill="${strokeColor}" font-size="8.5" font-weight="bold" text-anchor="middle" font-family="sans-serif">${badgeText}</text>
          <text x="${candX + 124}" y="${cy + 27}" fill="#94a3b8" font-size="8.5" font-family="monospace">(${c.attempts || 0}/${c.max_attempts || 2} turns)</text>
        </g>
      `;

      // If abandoned, draw dynamic pivot loop on LEFT side of candidate nodes (never overlaps labels on right)
      if (isAbandoned && idx + 1 < count) {
        const nextCy = count === 1 ? totalHeight / 2 : startY + (idx + 1) * stepY;
        const midY = (cy + nextCy) / 2;
        edgesHtml += `
          <path d="M ${candX - 18} ${cy} C ${candX - 65} ${cy + 15}, ${candX - 65} ${nextCy - 15}, ${candX - 18} ${nextCy}" 
                stroke="#f43f5e" stroke-width="2.2" stroke-dasharray="5,4" fill="none" marker-end="url(#arrow-red)"/>
          <rect x="${candX - 146}" y="${midY - 9}" width="126" height="18" rx="4" fill="#4c0519" stroke="#f43f5e" stroke-width="1"/>
          <text x="${candX - 83}" y="${midY + 4}" fill="#fecdd3" font-size="8.5" font-weight="bold" text-anchor="middle" font-family="monospace">k=${c.max_attempts || 2} LIMIT ➔ PIVOT</text>
        `;
      }
    });

    const html = `
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
        </marker>
        <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981"/>
        </marker>
        <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#f43f5e"/>
        </marker>
      </defs>
      
      <g id="dag-viewport" transform="translate(${state.dagPanX}, ${state.dagPanY}) scale(${state.dagZoom})">
        <!-- Root Target Node -->
        <g style="cursor: pointer;">
          <circle cx="${rootX}" cy="${rootY}" r="30" fill="#0369a1" stroke="#38bdf8" stroke-width="2.5"/>
          <text x="${rootX}" y="${rootY - 4}" fill="#ffffff" font-size="11" font-weight="bold" text-anchor="middle" font-family="sans-serif">TARGET</text>
          <text x="${rootX}" y="${rootY + 11}" fill="#bae6fd" font-size="8" text-anchor="middle" font-family="monospace">START</text>
        </g>
        
        <!-- Edges -->
        ${edgesHtml}
        
        <!-- Nodes -->
        ${nodesHtml}
      </g>
    `;

    svg.innerHTML = html;
  }

  // Render Terminal Logs
  function renderTerminalLogs(trace) {
    if (!trace || !trace.length) return;
    elements.terminalCount.textContent = `${trace.length} events`;

    elements.terminalBody.innerHTML = trace
      .map((line) => {
        let prefixClass = 'log-prefix-init';
        if (line.includes('[DISPATCH]')) prefixClass = 'log-prefix-dispatch';
        else if (line.includes('[ADVANCE]')) prefixClass = 'log-prefix-advance';
        else if (line.includes('[RETRY]')) prefixClass = 'log-prefix-retry';
        else if (line.includes('[REDIRECT]')) prefixClass = 'log-prefix-redirect';
        else if (line.includes('[ABANDON]')) prefixClass = 'log-prefix-abandon';

        return `<div class="terminal-line"><span class="log-prefix ${prefixClass}">${escapeHtml(line)}</span></div>`;
      })
      .join('');

    elements.terminalBody.scrollTop = elements.terminalBody.scrollHeight;
  }

  // Render Confirmed Findings Live
  function renderFindingsLive(findings) {
    if (!findings || !findings.length) {
      elements.findingsLive.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No confirmed findings filed yet.</div>`;
      return;
    }

    elements.findingsLive.innerHTML = findings
      .map((f, idx) => {
        const sev = (f.severity || 'medium').toUpperCase();
        const sevColor = sev === 'CRITICAL' || sev === 'HIGH' ? '#f43f5e' : '#f59e0b';
        return `
        <div style="background: var(--bg-secondary); border-left: 4px solid ${sevColor}; padding: 0.85rem 1rem; border-radius: var(--radius-sm); margin-bottom: 0.75rem; border: 1px solid var(--border-color); border-left-width: 4px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            <strong style="color: #f8fafc; font-size: 0.95rem;">${idx + 1}. ${escapeHtml(f.title || f.id)}</strong>
            <span class="badge" style="background:${sevColor}22; color:${sevColor}; border:1px solid ${sevColor}44;">${sev} (CVSS ${f.cvss_score || 5.0})</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.35rem;">
            ${escapeHtml(f.owasp_category || 'A01:2021')} • ${escapeHtml(f.cwe_id || 'CWE-200')}
          </div>
          <div style="font-family: var(--font-mono); font-size: 0.75rem; background: #020617; padding: 0.35rem 0.5rem; border-radius: 4px; color: #38bdf8; word-break: break-all;">
            SHA-256 Proof: ${escapeHtml(f.evidence_hash || 'Verified')}
          </div>
        </div>`;
      })
      .join('');
  }

  // Render Full Comprehensive Audit Report View
  function loadReportView(run) {
    if (!run) {
      elements.reportContentArea.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 3rem;">No assessment report available.</div>`;
      return;
    }

    elements.reportRunRef.textContent = `Run Reference: ${run.run_id}`;

    const findings = run.findings || [];
    const candidates = run.candidates || [];
    const trace = run.decision_trace || [];
    const pivotEvents = run.pivot_events || [];
    const totalPivots = pivotEvents.filter((e) => e.type === 'REDIRECT').length;
    const scanMatrix = run.scan_matrix || [];
    const openPorts = run.open_ports || [];
    const components = run.components || [];

    const critCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'CRITICAL').length;
    const highCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'HIGH').length;
    const medCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'MEDIUM').length;
    const lowCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'LOW').length;

    let html = `
      <!-- Engagement Verification & Integrity Notice -->
      <div style="background:rgba(16, 185, 129, 0.08); border:1px solid rgba(16, 185, 129, 0.3); border-radius:var(--radius-md); padding:0.75rem 1rem; margin-bottom:1.5rem; display:flex; align-items:center; gap:0.75rem;">
        <span style="font-size:1.25rem;">🔒</span>
        <div>
          <strong style="color:#34d399; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em;">Engagement Verification & Integrity Notice:</strong>
          <div style="color:#cbd5e1; font-size:0.8rem; margin-top:0.15rem;">${escapeHtml(run.safety_notice || 'LIVE ACTIVE VAPT — Verified against authorized target endpoint with non-destructive cryptographic evidence.')} ${run.target_ip ? `(Target IP: ${escapeHtml(run.target_ip)})` : ''} • Evidence Tier: <strong style="color:#10b981;">${escapeHtml(run.evidence_tier || 'OBSERVED_EXTERNAL')}</strong></div>
        </div>
      </div>

      <!-- Top Metrics Overview -->
      <div class="grid-4" style="margin-bottom: 1.5rem;">
        <div class="metric-card">
          <div class="metric-icon">🎯</div>
          <div class="metric-data">
            <div class="metric-value" style="font-size:1.05rem; word-break:break-all;">${escapeHtml(run.target_url || 'Target Scope')}</div>
            <div class="metric-label">Target Scope ${run.target_ip ? `(${escapeHtml(run.target_ip)})` : ''}</div>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon">🛡️</div>
          <div class="metric-data">
            <div class="metric-value" style="color:#10b981;">${(run.status || 'COMPLETED').toUpperCase()}</div>
            <div class="metric-label">Assessment Status (${escapeHtml(run.evidence_tier || 'OBSERVED_EXTERNAL')})</div>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon">🔄</div>
          <div class="metric-data">
            <div class="metric-value" style="color:#f59e0b;">${totalPivots}</div>
            <div class="metric-label">GAP-2 Dynamic Pivots (k=2)</div>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon">🚨</div>
          <div class="metric-data">
            <div class="metric-value" style="color:#f43f5e;">${findings.length}</div>
            <div class="metric-label">Confirmed Vulnerabilities</div>
          </div>
        </div>
      </div>

      <!-- Severity Breakdown Bar -->
      <div style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:var(--radius-md); padding:1rem 1.25rem; margin-bottom:2rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.75rem;">
          <strong style="color:var(--text-bright); font-size:0.9rem;">Vulnerability Severity Distribution:</strong>
          <div style="display:flex; gap:0.75rem; font-size:0.85rem;">
            <span style="color:#ef4444; font-weight:700;">Critical: ${critCount}</span>
            <span style="color:#f97316; font-weight:700;">High: ${highCount}</span>
            <span style="color:#f59e0b; font-weight:700;">Medium: ${medCount}</span>
            <span style="color:#38bdf8; font-weight:700;">Low: ${lowCount}</span>
          </div>
        </div>
        <div style="display:flex; height:8px; border-radius:4px; overflow:hidden; background:rgba(255,255,255,0.05);">
          <div style="background:#ef4444; width:${(critCount / Math.max(findings.length, 1)) * 100}%;"></div>
          <div style="background:#f97316; width:${(highCount / Math.max(findings.length, 1)) * 100}%;"></div>
          <div style="background:#f59e0b; width:${(medCount / Math.max(findings.length, 1)) * 100}%;"></div>
          <div style="background:#38bdf8; width:${(lowCount / Math.max(findings.length, 1)) * 100}%;"></div>
        </div>
      </div>

      <!-- SECTION 1: Confirmed Findings Table with CVE & CWE -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">1. Confirmed Vulnerability Findings & Cryptographic PoC Evidence</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem; line-height: 1.5;">
        All confirmed vulnerabilities with associated CVSS scores, CVE references, CWE tags, and SHA-256 evidence hashes.<br>
        <span style="color:#cbd5e1; font-size:0.8rem;"><em>Note on Vulnerability Taxonomy:</em> Architectural and web configuration weaknesses (e.g. missing HTTP hardening headers, insecure cookie flags, missing CSRF tokens, permissive CSP) are categorized under authoritative <strong>Common Weakness Enumerations (CWE)</strong> and <strong>OWASP Top 10</strong> standards. <strong>CVE Identifiers</strong> are strictly reserved for verified Common Vulnerabilities and Exposures in third-party COTS software components.</span>
      </p>
      <div class="data-table-container" style="margin-bottom: 2rem;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Vulnerability Title & Location</th>
              <th>Severity</th>
              <th>CVSS</th>
              <th>CVE Reference</th>
              <th>CWE Identifier</th>
              <th>OWASP Classification</th>
              <th>SHA-256 Proof Hash</th>
            </tr>
          </thead>
          <tbody>
            ${
              findings.length
                ? findings
                    .map((f) => {
                      const sev = (f.severity || 'medium').toUpperCase();
                      const badgeClass = sev === 'CRITICAL' ? 'badge-rose' : (sev === 'HIGH' ? 'badge-amber' : (sev === 'MEDIUM' ? 'badge-purple' : 'badge-cyan'));
                      const hasRealCve = Boolean(f.cve_id && String(f.cve_id).toUpperCase().startsWith('CVE-') && !String(f.cve_id).toUpperCase().includes('XXXX') && !String(f.cve_id).toUpperCase().includes('N/A'));
                      const cveBadge = hasRealCve
                        ? `<span style="font-family:var(--font-mono); font-size:0.8rem; background:rgba(99,102,241,0.15); color:#a5b4fc; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(99,102,241,0.3);">${escapeHtml(f.cve_id)}</span>`
                        : `<span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(148,163,184,0.12); color:#94a3b8; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(148,163,184,0.25);">N/A (CWE-based)</span>`;
                      return `
                        <tr>
                          <td>
                            <strong>${escapeHtml(f.title || f.id)}</strong>
                            <div style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted);">${escapeHtml(f.location || '/')}</div>
                          </td>
                          <td><span class="badge ${badgeClass}">${sev}</span></td>
                          <td><strong style="color:var(--text-bright);">${f.cvss_score || 5.0}</strong></td>
                          <td>${cveBadge}</td>
                          <td><span style="font-family:var(--font-mono); font-size:0.8rem; background:rgba(16,185,129,0.15); color:#6ee7b7; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(16,185,129,0.3);">${escapeHtml(f.cwe_id || 'CWE-200')}</span></td>
                          <td style="font-size:0.85rem;">${escapeHtml(f.owasp_category || 'A01:2021')}</td>
                          <td><code style="font-family:var(--font-mono); font-size:0.75rem; color:#38bdf8;">${escapeHtml((f.evidence_hash || 'N/A').slice(0, 14))}...</code></td>
                        </tr>`;
                    })
                    .join('')
                : '<tr><td colspan="7" style="text-align:center;">No vulnerabilities confirmed.</td></tr>'
            }
          </tbody>
        </table>
      </div>

      <!-- SECTION 2: Scan Capabilities & Vulnerability Category Matrix -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">2. Scan Capabilities & Vulnerability Category Matrix</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Comprehensive multi-layer audit coverage across 6 core VAPT test categories (72 total tests) aligned with industry benchmarks:
      </p>
      <div class="data-table-container" style="margin-bottom: 2rem;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Vulnerability Category</th>
              <th>Total Rules</th>
              <th>Execution Capability</th>
              <th>Findings Identified</th>
              <th>Audit Status</th>
            </tr>
          </thead>
          <tbody>
            ${
              scanMatrix.length
                ? scanMatrix.map((m) => {
                    const cnt = m.findings_count || 0;
                    const statusBadge = cnt > 0
                      ? '<span class="badge badge-amber">FINDINGS IDENTIFIED</span>'
                      : '<span class="badge badge-emerald">PASSED (BASELINE SECURE)</span>';
                    return `
                      <tr>
                        <td><strong>${escapeHtml(m.title)}</strong></td>
                        <td>${m.test_count} tests</td>
                        <td style="font-size:0.8rem; color:var(--text-muted);">${escapeHtml(m.capability || 'Passive & Active')}</td>
                        <td><strong style="color:${cnt > 0 ? '#f59e0b' : '#10b981'};">${cnt} finding(s)</strong></td>
                        <td>${statusBadge}</td>
                      </tr>`;
                  }).join('')
                : '<tr><td colspan="5" style="text-align:center;">Category matrix updating...</td></tr>'
            }
          </tbody>
        </table>
      </div>

      <!-- SECTION 3: Target Network Surface & Open Port Reconnaissance -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">3. Target Network Surface & Open Port Reconnaissance</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Native non-destructive TCP socket reconnaissance across standard, database, administrative, and telephony daemons:
      </p>
      <div class="data-table-container" style="margin-bottom: 2rem;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Listening Port & Protocol</th>
              <th>Service Name</th>
              <th>Socket State</th>
              <th>Exposure Severity</th>
              <th>Security Implication & Exposure Risk</th>
            </tr>
          </thead>
          <tbody>
            ${
              openPorts.length
                ? openPorts.map((p) => {
                    const sev = (p.severity || 'low').toUpperCase();
                    const badgeClass = sev === 'HIGH' ? 'badge-rose' : (sev === 'MEDIUM' ? 'badge-amber' : 'badge-cyan');
                    return `
                      <tr>
                        <td><strong style="font-family:var(--font-mono); color:#38bdf8;">Port ${p.port}/${(p.protocol || 'tcp').toUpperCase()}</strong></td>
                        <td>${escapeHtml(p.service || 'TCP')}</td>
                        <td><span class="badge badge-emerald">${escapeHtml(p.state || 'OPEN')}</span></td>
                        <td><span class="badge ${badgeClass}">${sev}</span></td>
                        <td style="font-size:0.85rem; color:#cbd5e1;">${escapeHtml(p.risk || 'Exposed listening port.')}</td>
                      </tr>`;
                  }).join('')
                : '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Standard web ports inspected. No anomalous non-standard ports exposed.</td></tr>'
            }
          </tbody>
        </table>
      </div>

      <!-- SECTION 4: Software Component Analysis (SCA) & Library Inventory -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">4. Software Component Analysis (SCA) & Library Inventory</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Client-side JavaScript libraries detected in page source cross-referenced with National Vulnerability Database (NVD) CVEs:
      </p>
      <div class="data-table-container" style="margin-bottom: 2rem;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Library Component</th>
              <th>Detected Version</th>
              <th>Source Asset Location</th>
              <th>Security Status</th>
              <th>Known Public CVE References</th>
              <th>Recommended Action</th>
            </tr>
          </thead>
          <tbody>
            ${
              components.length
                ? components.map((comp) => {
                    const cves = comp.cves || [];
                    const cveBadges = cves.length
                      ? cves.map((cve) => `<span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(99,102,241,0.15); color:#a5b4fc; padding:0.2rem 0.4rem; border-radius:4px; border:1px solid rgba(99,102,241,0.3); margin-right:0.25rem;">${escapeHtml(cve)}</span>`).join(' ')
                      : '<span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(148,163,184,0.12); color:#94a3b8; padding:0.2rem 0.4rem; border-radius:4px;">N/A (No Known CVEs)</span>';
                    const statBadge = comp.vulnerable
                      ? '<span class="badge badge-amber">OUTDATED / VULNERABLE</span>'
                      : '<span class="badge badge-emerald">SECURE VERSION</span>';
                    return `
                      <tr>
                        <td><strong>${escapeHtml(comp.library.toUpperCase())}</strong></td>
                        <td><code style="color:#38bdf8;">v${escapeHtml(comp.version)}</code></td>
                        <td><small style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted);">${escapeHtml(comp.source_file || '/')}</small></td>
                        <td>${statBadge}</td>
                        <td>${cveBadges}</td>
                        <td style="font-size:0.85rem; color:#cbd5e1;">${escapeHtml(comp.remediation || 'Maintain patched version.')}</td>
                      </tr>`;
                  }).join('')
                : '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No outdated third-party JavaScript libraries detected.</td></tr>'
            }
          </tbody>
        </table>
      </div>

      <!-- SECTION 5: Tailored Remediation Roadmap -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">5. Tailored Remediation Roadmap & Server Hardening Patches</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Customized mitigation instructions, web server configuration snippets, and code patches tailored to each finding:
      </p>
      <div style="margin-bottom: 2rem;">
        ${
          findings.length
            ? findings
                .map((f, idx) => {
                  const borderCol = f.severity === 'CRITICAL' ? '#ef4444' : (f.severity === 'HIGH' ? '#f97316' : '#06b6d4');
                  const hasRealCve = Boolean(f.cve_id && String(f.cve_id).toUpperCase().startsWith('CVE-') && !String(f.cve_id).toUpperCase().includes('XXXX') && !String(f.cve_id).toUpperCase().includes('N/A'));
                  const mitCveBadge = hasRealCve
                    ? `<span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(99,102,241,0.15); color:#a5b4fc; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(99,102,241,0.3);">${escapeHtml(f.cve_id)}</span>`
                    : `<span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(148,163,184,0.12); color:#94a3b8; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(148,163,184,0.25);">CWE-based Weakness</span>`;
                  return `
                    <div style="background:var(--bg-secondary); border-left:4px solid ${borderCol}; padding:1.25rem; border-radius:var(--radius-md); margin-bottom:1rem; border:1px solid var(--border-color); border-left-width:4px;">
                      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.5rem;">
                        <h3 style="color:#f8fafc; font-size:1.05rem; margin:0;">${idx + 1}. Mitigations for: ${escapeHtml(f.title)}</h3>
                        <div style="display:flex; gap:0.5rem;">
                          ${mitCveBadge}
                          <span style="font-family:var(--font-mono); font-size:0.75rem; background:rgba(16,185,129,0.15); color:#6ee7b7; padding:0.2rem 0.5rem; border-radius:4px; border:1px solid rgba(16,185,129,0.3);">${escapeHtml(f.cwe_id || 'CWE-200')}</span>
                        </div>
                      </div>
                      <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.4rem;">
                        <strong>OWASP Classification:</strong> ${escapeHtml(f.owasp_category || 'A01:2021')}
                      </p>
                      <p style="font-size:0.85rem; color:#cbd5e1; margin-bottom:0.5rem;">
                        <strong>Vulnerability Impact:</strong> ${escapeHtml(f.impact || 'Remote attack surface exposure')}
                      </p>
                      <div style="font-size:0.8rem; font-weight:700; color:#38bdf8; margin-top:0.5rem; margin-bottom:0.25rem;">Server Hardening Configuration & Code Patch:</div>
                      <pre style="background:#020617; padding:0.75rem; border-radius:4px; font-family:var(--font-mono); font-size:0.8rem; color:#e2e8f0; overflow-x:auto; border:1px solid rgba(255,255,255,0.06);">${escapeHtml(f.remediation_technical || 'Apply input validation and least privilege controls.')}</pre>
                      <div style="font-size:0.8rem; font-weight:700; color:#34d399; margin-top:0.5rem; margin-bottom:0.25rem;">Retest Verification Procedure:</div>
                      <code style="background:#020617; padding:0.35rem 0.65rem; border-radius:4px; font-family:var(--font-mono); font-size:0.8rem; color:#bae6fd; display:block; border:1px solid rgba(255,255,255,0.06);">${escapeHtml((f.retest_procedure || '').replace('<target>', (run.target_url || 'target').replace('https://','').replace('http://','').replace(/\/$/,'')))}</code>
                    </div>`;
                })
                .join('')
            : '<p style="color:var(--text-muted);">No remediation required.</p>'
        }
      </div>

      <!-- SECTION 6: GAP-1 Candidate Triage Prioritization Queue -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">6. GAP-1 Exploit Quality Prioritization & Candidate Queue</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        Candidate selection queue ranked by multi-parameter composite scoring: <em>Score = (w_cvss &times; S_cvss) + (w_exp &times; E_exp) + (w_ai &times; Q_ai)</em>
      </p>
      <div class="data-table-container" style="margin-bottom: 2rem;">
        <table class="data-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Candidate & Attack Vector</th>
              <th>Severity & CVSS</th>
              <th>Usability Rank</th>
              <th>Composite Score</th>
              <th>State</th>
              <th>AI Triage Reasoning</th>
            </tr>
          </thead>
          <tbody>
            ${
              candidates.length
                ? candidates
                    .map((c) => {
                      const stateBadge = c.state === 'VALIDATED'
                        ? '<span class="badge badge-emerald">VALIDATED</span>'
                        : (c.state === 'ABANDONED'
                        ? '<span class="badge badge-rose">ABANDONED (PIVOT)</span>'
                        : '<span class="badge badge-cyan">PENDING</span>');
                      const scoreFormatted = (c.composite_score !== undefined && c.composite_score !== null)
                        ? Number(c.composite_score).toFixed(3)
                        : (c.probability !== undefined ? Number(c.probability).toFixed(3) : '0.500');
                      const rankVal = (c.usability_rank || 'MEDIUM').toUpperCase();
                      const usabBadge = rankVal === 'HIGH'
                        ? '<span class="badge badge-emerald">HIGH</span>'
                        : (rankVal === 'MEDIUM'
                        ? '<span class="badge badge-amber">MEDIUM</span>'
                        : '<span class="badge badge-purple">LOW</span>');
                      return `
                        <tr>
                          <td><strong>#${c.priority_rank || '-'}</strong></td>
                          <td>
                            <strong>${escapeHtml(c.name || c.id)}</strong>
                            <div style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted);">${escapeHtml(c.endpoint || c.target || '/')}</div>
                          </td>
                          <td>${(c.severity || 'medium').toUpperCase()} (${c.cvss_score || 5.0})</td>
                          <td>${usabBadge}</td>
                          <td><strong style="color:#38bdf8; font-family:var(--font-mono);">${scoreFormatted}</strong></td>
                          <td>${stateBadge}</td>
                          <td style="font-size:0.8rem; color:#cbd5e1;">${escapeHtml(c.reasoning || '')}</td>
                        </tr>`;
                    })
                    .join('')
                : '<tr><td colspan="7" style="text-align:center;">No candidate queue data available.</td></tr>'
            }
          </tbody>
        </table>
      </div>

      <!-- SECTION 7: GAP-2 Dynamic Decision Trail & Audit Log -->
      <h2 style="font-size: 1.25rem; color: #38bdf8; margin-bottom: 0.5rem;">7. GAP-2 Bounded Dynamic Decision Trail & Audit Log</h2>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
        State machine execution log bounding agent attempts (k=2) and dynamically redirecting upon dead ends:
      </p>
      <div class="terminal-window" style="margin-bottom: 2rem;">
        <div class="terminal-body report-terminal-body">
          ${trace.map((l) => `<div class="terminal-line">${escapeHtml(l)}</div>`).join('')}
        </div>
      </div>
    `;

    elements.reportContentArea.innerHTML = html;
  }

  // Load Past Runs History
  async function loadHistory() {
    elements.tbodyHistory.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Fetching runs...</td></tr>`;
    try {
      const res = await fetch('/runs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const runs = await res.json();
      if (!runs || !runs.length) {
        elements.tbodyHistory.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No past assessments found. Launch one above!</td></tr>`;
        return;
      }

      elements.tbodyHistory.innerHTML = runs
        .map((r) => {
          const status = (r.status || 'unknown').toUpperCase();
          const badgeClass = status === 'COMPLETED' ? 'badge-emerald' : status === 'FAILED' ? 'badge-rose' : 'badge-cyan';
          return `<tr>
            <td><code style="font-family:var(--font-mono); font-size:0.85rem; color:#38bdf8;">${escapeHtml(r.run_id)}</code></td>
            <td><strong>${escapeHtml(r.target_url || 'Target')}</strong></td>
            <td>${escapeHtml((r.mode || 'web').toUpperCase())}</td>
            <td><span class="badge ${badgeClass}">${status}</span></td>
            <td>${(r.findings || []).length}</td>
            <td style="font-size:0.8rem; color:var(--text-muted);">${escapeHtml(r.created_at ? r.created_at.replace('T', ' ').slice(0, 19) : '—')}</td>
            <td>
              <button class="btn btn-secondary" style="padding:0.35rem 0.65rem; font-size:0.8rem;" onclick="window.vaptApp.openRun('${escapeHtml(r.run_id)}')">
                View Run
              </button>
            </td>
          </tr>`;
        })
        .join('');
    } catch (err) {
      elements.tbodyHistory.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  // Event Listeners Initialization
  function initEvents() {
    elements.navLinks.forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        switchView(link.dataset.view);
      });
    });

    window.addEventListener('hashchange', () => {
      const hash = window.location.hash.replace('#/', '');
      if (hash && document.getElementById(`view-${hash}`)) {
        switchView(hash);
      }
    });

    elements.modelProviderSelect.addEventListener('change', onProviderChange);
    elements.modelSelect.addEventListener('change', onModelSelectChange);
    elements.btnPreflight.addEventListener('click', preflightTarget);

    elements.btnValidateKey.addEventListener('click', () => {
      validateCloudKey(
        elements.modelProviderSelect.value,
        elements.runtimeApiKey.value.trim(),
        elements.apiKeyFeedback
      );
    });

    if (elements.scanIntensity && elements.executionLimitsSelect) {
      elements.scanIntensity.addEventListener('change', () => {
        const mode = elements.scanIntensity.value;
        if (mode === 'quick') {
          elements.executionLimitsSelect.value = '25';
        } else if (mode === 'standard') {
          elements.executionLimitsSelect.value = '100';
        } else if (mode === 'deep') {
          elements.executionLimitsSelect.value = '500';
        }
      });
    }

    elements.btnLaunch.addEventListener('click', launchAssessment);

    if (elements.btnStopRun) {
      elements.btnStopRun.addEventListener('click', async () => {
        const runId = state.activeRunId || state.latestRunData?.run_id;
        if (!runId) return;
        if (!confirm('Are you sure you want to stop this assessment?')) return;
        try {
          elements.btnStopRun.disabled = true;
          elements.btnStopRun.innerHTML = `<span>⏳</span> Stopping...`;
          const res = await fetch(`/runs/${runId}/stop`, { method: 'POST' });
          if (res.ok) {
            showToast('Assessment stop signal sent!', 'info');
            await fetchRunState(runId);
          }
        } catch (err) {
          showToast(`Failed to stop run: ${err.message}`, 'error');
        } finally {
          elements.btnStopRun.disabled = false;
          elements.btnStopRun.innerHTML = `<span>🛑</span> Stop Scan`;
        }
      });
    }

    elements.btnRefreshRun.addEventListener('click', () => {
      if (state.activeRunId) fetchRunState(state.activeRunId);
    });

    elements.btnViewReportNow.addEventListener('click', () => {
      if (state.latestRunData) {
        loadReportView(state.latestRunData);
        switchView('reports');
      }
    });

    elements.btnDownloadHtml.addEventListener('click', async () => {
      downloadReportArtifact('html', 'vapt_report_{runId}.html', 'text/html', 'HTML Report');
    });

    if (elements.btnDownloadPdf) {
      elements.btnDownloadPdf.addEventListener('click', async () => {
        downloadReportArtifact('pdf', 'vapt_report_{runId}.pdf', 'application/pdf', 'PDF Report');
      });
    }

    elements.btnDownloadJson.addEventListener('click', async () => {
      downloadReportArtifact('json', 'vapt_audit_{runId}.json', 'application/json', 'JSON Audit Package');
    });

    if (elements.btnDownloadSarif) {
      elements.btnDownloadSarif.addEventListener('click', async () => {
        downloadReportArtifact('sarif', 'vapt_findings_{runId}.sarif', 'application/json', 'SARIF Report');
      });
    }

    if (elements.btnDownloadMd) {
      elements.btnDownloadMd.addEventListener('click', async () => {
        downloadReportArtifact('markdown', 'vapt_report_{runId}.md', 'text/markdown', 'Markdown Report');
      });
    }

    // DAG Interactive Controls (Zoom, Pan, Filter)
    if (elements.btnDagZoomIn) {
      elements.btnDagZoomIn.addEventListener('click', () => {
        state.dagZoom = Math.min(2.5, state.dagZoom * 1.25);
        applyDagTransform();
      });
    }
    if (elements.btnDagZoomOut) {
      elements.btnDagZoomOut.addEventListener('click', () => {
        state.dagZoom = Math.max(0.4, state.dagZoom / 1.25);
        applyDagTransform();
      });
    }
    if (elements.btnDagReset) {
      elements.btnDagReset.addEventListener('click', () => {
        state.dagZoom = 1.0;
        state.dagPanX = 0;
        state.dagPanY = 0;
        applyDagTransform();
      });
    }
    if (elements.btnDagFilterFound) {
      elements.btnDagFilterFound.addEventListener('click', () => setDagFilter('found'));
    }
    if (elements.btnDagFilterPivots) {
      elements.btnDagFilterPivots.addEventListener('click', () => setDagFilter('pivots'));
    }
    if (elements.btnDagFilterAll) {
      elements.btnDagFilterAll.addEventListener('click', () => setDagFilter('all'));
    }
    if (elements.btnDagExpand) {
      elements.btnDagExpand.addEventListener('click', () => {
        const isExpanded = elements.dagContainer.classList.toggle('expanded');
        elements.btnDagExpand.textContent = isExpanded ? '🗗 Compact' : '⛶ Expand';
        elements.btnDagExpand.classList.toggle('btn-active', isExpanded);
      });
    }

    if (elements.dagContainer) {
      elements.dagContainer.addEventListener('wheel', (e) => {
        e.preventDefault();
        const rect = elements.dagContainer.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const factor = e.deltaY < 0 ? 1.12 : 0.89;
        const oldZoom = state.dagZoom;
        const newZoom = Math.max(0.35, Math.min(3.5, oldZoom * factor));
        state.dagPanX = mouseX - (mouseX - state.dagPanX) * (newZoom / oldZoom);
        state.dagPanY = mouseY - (mouseY - state.dagPanY) * (newZoom / oldZoom);
        state.dagZoom = newZoom;
        applyDagTransform();
      }, { passive: false });

      elements.dagContainer.addEventListener('mousedown', (e) => {
        if (e.target.closest('button') || e.target.closest('.dag-node-inspector')) return;
        isDagPanning = true;
        dagStartX = e.clientX - state.dagPanX;
        dagStartY = e.clientY - state.dagPanY;
        elements.dagContainer.classList.add('panning');
      });

      window.addEventListener('mousemove', (e) => {
        if (!isDagPanning) return;
        state.dagPanX = e.clientX - dagStartX;
        state.dagPanY = e.clientY - dagStartY;
        applyDagTransform();
      });

      window.addEventListener('mouseup', () => {
        if (isDagPanning) {
          isDagPanning = false;
          if (elements.dagContainer) elements.dagContainer.classList.remove('panning');
        }
      });
    }

    elements.btnProbeOllama.addEventListener('click', probeOllamaService);
    elements.btnTestCloudKey.addEventListener('click', () => {
      validateCloudKey(
        elements.settingsProviderSelect.value,
        elements.settingsApiKey.value.trim(),
        elements.settingsKeyResult
      );
    });

    if (elements.btnSaveLlmConfig) {
      elements.btnSaveLlmConfig.addEventListener('click', saveLlmSettings);
    }

    elements.btnRefreshHistory.addEventListener('click', loadHistory);
  }

  // Download Report Artifact Helper
  async function downloadReportArtifact(format, filename, defaultMime, label) {
    const runId = state.activeRunId || state.latestRunData?.run_id;
    if (!runId) {
      showToast('No assessment run available to download', 'error');
      return;
    }
    try {
      showToast(`Preparing ${label} download...`, 'info');
      const res = await fetch(`/runs/${runId}/report?format=${format}&download=1`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = filename.replace('{runId}', runId);
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      showToast(`${label} downloaded successfully!`, 'success');
    } catch (err) {
      window.location.href = `/runs/${runId}/report?format=${format}&download=1`;
    }
  }

  // Load Persisted LLM Settings
  async function loadLlmSettings() {
    try {
      const res = await fetch('/settings/llm');
      if (!res.ok) return;
      const cfg = await res.json();
      if (elements.settingsProviderSelect && cfg.provider) {
        elements.settingsProviderSelect.value = cfg.provider;
      }
      if (elements.settingsModelInput && cfg.model) {
        elements.settingsModelInput.value = cfg.model;
      }
      if (elements.settingsCurrentKeyHint) {
        if (cfg.has_api_key) {
          elements.settingsCurrentKeyHint.innerHTML = `Saved key active: <code style="color:#34d399;">${escapeHtml(cfg.masked_api_key)}</code> (provider: ${escapeHtml(cfg.provider)})`;
          if (elements.settingsStatusBadge) {
            elements.settingsStatusBadge.textContent = 'Configured';
            elements.settingsStatusBadge.className = 'badge badge-emerald';
          }
        } else {
          elements.settingsCurrentKeyHint.textContent = 'No API key configured in ~/.strix/cli-config.json';
          if (elements.settingsStatusBadge) {
            elements.settingsStatusBadge.textContent = 'Not Configured';
            elements.settingsStatusBadge.className = 'badge badge-amber';
          }
        }
      }

      // Synchronize active LLM settings to the New Assessment launch panel
      if (elements.modelProviderSelect && cfg.provider) {
        elements.modelProviderSelect.value = cfg.provider;
        onProviderChange();
      }
      if (elements.runtimeApiKey && cfg.has_api_key) {
        elements.runtimeApiKey.placeholder = `Saved key (${cfg.masked_api_key}) - leave blank to use`;
        if (elements.apiKeyFeedback) {
          elements.apiKeyFeedback.innerHTML = `<span style="color:#34d399;">Saved credentials ready (<code>${escapeHtml(cfg.masked_api_key)}</code>)</span>`;
        }
      }
      if (elements.modelSelect && cfg.model) {
        const matchingOpt = elements.modelSelect.querySelector(`option[value="${cfg.model}"]`);
        if (matchingOpt) {
          elements.modelSelect.value = cfg.model;
          if (elements.modelCustomInput) elements.modelCustomInput.style.display = 'none';
        } else {
          elements.modelSelect.value = '__custom__';
          if (elements.modelCustomInput) {
            elements.modelCustomInput.value = cfg.model;
            elements.modelCustomInput.style.display = 'block';
          }
        }
      }
    } catch (e) {
      console.debug('Failed to load LLM settings:', e);
    }
  }

  // Save LLM Settings
  async function saveLlmSettings() {
    const provider = elements.settingsProviderSelect ? elements.settingsProviderSelect.value : 'openrouter';
    const model = elements.settingsModelInput ? elements.settingsModelInput.value.trim() : '';
    const apiKey = elements.settingsApiKey ? elements.settingsApiKey.value.trim() : '';

    if (elements.btnSaveLlmConfig) {
      elements.btnSaveLlmConfig.disabled = true;
      elements.btnSaveLlmConfig.innerHTML = `<span>⏳</span> Saving...`;
    }

    try {
      const res = await fetch('/settings/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: provider,
          model: model,
          api_key: apiKey || null,
          reasoning_effort: 'low',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      showToast('LLM Configuration saved to ~/.strix/cli-config.json!', 'success');
      if (elements.settingsKeyResult) {
        elements.settingsKeyResult.innerHTML = `<span style="color:#10b981;">✅ Saved successfully! Active model: <strong>${escapeHtml(model)}</strong></span>`;
      }
      if (elements.settingsApiKey) elements.settingsApiKey.value = '';
      await loadLlmSettings();
    } catch (err) {
      showToast(`Failed to save config: ${err.message}`, 'error');
      if (elements.settingsKeyResult) {
        elements.settingsKeyResult.innerHTML = `<span style="color:#f43f5e;">❌ Error: ${escapeHtml(err.message)}</span>`;
      }
    } finally {
      if (elements.btnSaveLlmConfig) {
        elements.btnSaveLlmConfig.disabled = false;
        elements.btnSaveLlmConfig.innerHTML = `<span>💾</span> Save Configuration`;
      }
    }
  }

  // Global App Interface
  window.vaptApp = {
    openRun: async function (runId) {
      state.activeRunId = runId;
      await fetchRunState(runId);
      if (state.latestRunData) {
        loadReportView(state.latestRunData);
        switchView('active-assessment');
      }
    },
  };

  // Entry Point
  document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initEvents();
    populateModelOptions('openrouter');
    loadOpenRouterFreeModels();
    loadLlmSettings();
    checkSystemHealth();

    const initialHash = window.location.hash.replace('#/', '');
    if (initialHash && document.getElementById(`view-${initialHash}`)) {
      switchView(initialHash);
    }
  });
})();
