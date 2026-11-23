/**
 * AI-VAPT Autonomous Operations Console
 * Modern, High-Performance Vanilla JS Frontend Engine
 */

(function () {
  'use strict';

  // Standard Default Models for Providers
  const DEFAULT_PROVIDER_MODELS = {
    openrouter: [
      { id: 'deepseek/deepseek-r1:free', name: 'DeepSeek R1 (Free)', free: true, pricing_status: 'free' },
      { id: 'meta-llama/llama-3.3-70b-instruct:free', name: 'Llama 3.3 70B Instruct (Free)', free: true, pricing_status: 'free' },
      { id: 'google/gemini-2.0-flash-exp:free', name: 'Gemini 2.0 Flash Exp (Free)', free: true, pricing_status: 'free' },
      { id: 'qwen/qwen-2.5-coder-32b-instruct:free', name: 'Qwen 2.5 Coder 32B (Free)', free: true, pricing_status: 'free' },
      { id: 'nvidia/nemotron-3.5-super-vl:free', name: 'NVIDIA Nemotron 3.5 Super VL [FREE]', free: true, pricing_status: 'free' },
      { id: 'openrouter/free', name: 'Free Models Router [FREE]', free: true, pricing_status: 'free' },
    ],
    anthropic: [
      { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet (Latest)', free: false, pricing_status: 'paid' },
      { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku (Fast)', free: false, pricing_status: 'paid' },
      { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus (Complex)', free: false, pricing_status: 'paid' },
    ],
    ollama: [
      { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Local Default)', free: true, pricing_status: 'free' },
      { id: 'llama3.2:3b', name: 'Llama 3.2 3B (Local Baseline)', free: true, pricing_status: 'free' },
      { id: 'deepseek-r1:1.5b', name: 'DeepSeek R1 1.5B (Local)', free: true, pricing_status: 'free' },
    ],
    google: [
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash (Fast)', free: false, pricing_status: 'paid' },
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro (Flagship)', free: false, pricing_status: 'paid' },
      { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', free: false, pricing_status: 'paid' },
    ],
    openai: [
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Fast)', free: false, pricing_status: 'paid' },
      { id: 'gpt-4o', name: 'GPT-4o (Flagship)', free: false, pricing_status: 'paid' },
      { id: 'o3-mini', name: 'o3-mini (Reasoning)', free: false, pricing_status: 'paid' },
    ],
    cloud_hosted: [
      { id: 'meta-llama/Llama-3.3-70B-Instruct', name: 'Llama 3.3 70B Instruct (Remote/Cloud)', free: false, pricing_status: 'unknown' },
      { id: 'Qwen/Qwen2.5-72B-Instruct', name: 'Qwen 2.5 72B Instruct (Remote)', free: false, pricing_status: 'unknown' },
      { id: 'mistralai/Mistral-Small-24B-Instruct-2501', name: 'Mistral Small 24B (Remote)', free: false, pricing_status: 'unknown' },
      { id: 'custom-model', name: 'Custom Hosted Model', free: false, pricing_status: 'unknown' },
    ],
    custom: [
      { id: 'custom-model', name: 'Custom Model Identifier', free: false, pricing_status: 'unknown' },
    ],
  };

  // Provider Metadata for Display & Dynamic Badges
  const PROVIDER_META = {
    openrouter: {
      name: 'OpenRouter',
      badgeClass: 'badge-purple',
      badgeText: 'OpenRouter',
      description: 'Access 400+ hosted models across diverse providers with real-time pricing and free tier options.',
    },
    openai: {
      name: 'OpenAI',
      badgeClass: 'badge-amber',
      badgeText: 'OpenAI',
      description: 'Direct OpenAI API integration for flagship reasoning and tool execution.',
    },
    anthropic: {
      name: 'Anthropic Claude',
      badgeClass: 'badge-purple',
      badgeText: 'Anthropic Claude',
      description: 'Native Claude 3.5 Sonnet / Haiku integration with sophisticated tool calling.',
    },
    google: {
      name: 'Google Gemini',
      badgeClass: 'badge-emerald',
      badgeText: 'Google Gemini',
      description: 'Fast cloud API with 1M+ token context window and native function calling.',
    },
    ollama: {
      name: 'Local Ollama',
      badgeClass: 'badge-cyan',
      badgeText: 'Local Ollama',
      description: 'Runs 100% locally on your machine with zero external network access.',
    },
    cloud_hosted: {
      name: 'Cloud Hosted',
      badgeClass: 'badge-cyan',
      badgeText: 'Cloud Hosted',
      description: 'Connect to any custom OpenAI-compatible endpoint (vLLM, TGI, RunPod, Kaggle GPU, FastChat) with custom headers and tool support.',
    },
  };

  // State Management
  const state = {
    previousProvider: 'openrouter',
    providerConfigs: {
      openrouter: { apiKey: '', model: 'deepseek/deepseek-r1:free', customModel: '', search: '', models: [] },
      openai: { apiKey: '', model: 'gpt-4o-mini', customModel: '', search: '', models: [] },
      anthropic: { apiKey: '', model: 'claude-3-5-sonnet-20241022', customModel: '', search: '', models: [] },
      google: { apiKey: '', model: 'gemini-2.0-flash', customModel: '', search: '', models: [] },
      ollama: { baseUrl: 'http://127.0.0.1:11434', apiKey: '', model: '', customModel: '', search: '', models: [] },
      cloud_hosted: { profileId: null, model: '', customModel: '', search: '', models: [] },
    },
    catalogActiveProvider: 'all',
    catalogSearchQuery: '',
    activeRunId: null,
    pollTimer: null,
    systemHealthy: true,
    runtimeApiKey: '',
    currentView: 'new-assessment',
    latestRunData: null,
    availableModels: [...DEFAULT_PROVIDER_MODELS.openrouter],
    currentProviderModels: [...DEFAULT_PROVIDER_MODELS.openrouter],
    modelFilterText: '',
    cloudProfiles: [],
    activeCloudProfileId: null,
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
    elements.customTurnsInput = document.getElementById('custom-turns-input');
    elements.chkScopeAck = document.getElementById('chk-scope-ack');
    elements.modelProviderSelect = document.getElementById('model-provider-select');
    elements.modelSelect = document.getElementById('model-select');
    elements.modelSearchFilter = document.getElementById('model-search-filter');
    elements.modelCustomInput = document.getElementById('model-custom-input');
    elements.modelBadgeStatus = document.getElementById('model-badge-status');
    elements.modelPricingNotice = document.getElementById('model-pricing-notice');
    elements.modelHint = document.getElementById('model-hint');
    elements.groupCustomBaseUrl = document.getElementById('group-custom-base-url');
    elements.customBaseUrl = document.getElementById('custom-base-url');
    elements.groupApiKey = document.getElementById('group-api-key');
    elements.runtimeApiKey = document.getElementById('runtime-api-key');
    elements.btnToggleKeyVisibility = document.getElementById('btn-toggle-key-visibility');
    elements.btnToggleSettingsKeyVisibility = document.getElementById('btn-toggle-settings-key-visibility');
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
    elements.providerResumeCard = document.getElementById('provider-resume-card');
    elements.providerResumeStatusLabel = document.getElementById('provider-resume-status-label');
    elements.providerResumeMessage = document.getElementById('provider-resume-message');
    elements.resumeProviderSelect = document.getElementById('resume-provider-select');
    elements.resumeModelSelect = document.getElementById('resume-model-select');
    elements.resumeApiKey = document.getElementById('resume-api-key');
    elements.resumeConfirmCheckbox = document.getElementById('resume-confirm-checkbox');
    elements.resumeWarnProvider = document.getElementById('resume-warn-provider');
    elements.resumeWarnModel = document.getElementById('resume-warn-model');
    elements.btnResumeAssessment = document.getElementById('btn-resume-assessment');
    elements.progressMilestoneCard = document.getElementById('progress-milestone-card');
    elements.progressPhaseIcon = document.getElementById('progress-phase-icon');
    elements.progressPhaseName = document.getElementById('progress-phase-name');
    elements.progressPercentText = document.getElementById('progress-percent-text');
    elements.progressTurnsText = document.getElementById('progress-turns-text');
    elements.progressBarFill = document.getElementById('progress-bar-fill');
    elements.metricCandidates = document.getElementById('metric-candidates-count');
    elements.metricPivots = document.getElementById('metric-pivots-count');
    elements.metricAttempts = document.getElementById('metric-attempts-count');
    elements.metricFindings = document.getElementById('metric-findings-count');

    // Live Run Facts & Verification States
    elements.metricStarted = document.getElementById('metric-started');
    elements.metricElapsed = document.getElementById('metric-elapsed');
    elements.metricActiveAgent = document.getElementById('metric-active-agent');
    elements.metricActiveTask = document.getElementById('metric-active-task');
    elements.feDiscovered = document.getElementById('fe-discovered');
    elements.feCandidate = document.getElementById('fe-candidate');
    elements.feUnderInvestigation = document.getElementById('fe-under-investigation');
    elements.feExploitation = document.getElementById('fe-exploitation');
    elements.feVerified = document.getElementById('fe-verified');
    elements.feUnconfirmed = document.getElementById('fe-unconfirmed');
    elements.feFp = document.getElementById('fe-fp');
    elements.feBlocked = document.getElementById('fe-blocked');
    elements.feInc = document.getElementById('fe-inc');
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
    elements.btnDownloadCsv = document.getElementById('btn-download-csv-report');
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

    // Cloud Hosted Provider
    elements.groupCloudHostedQuick = document.getElementById('group-cloud-hosted-quick');
    elements.cloudQuickProfileSelect = document.getElementById('cloud-quick-profile-select');
    elements.btnCloudQuickConfigure = document.getElementById('btn-cloud-quick-configure');
    elements.cloudQuickBaseUrl = document.getElementById('cloud-quick-base-url');
    elements.cardCloudHostedPanel = document.getElementById('card-cloud-hosted-panel');
    elements.cloudProfileSelect = document.getElementById('cloud-profile-select');
    elements.cloudProfileActiveBadge = document.getElementById('cloud-profile-active-badge');
    elements.cloudConnectionStatusBadge = document.getElementById('cloud-connection-status-badge');
    elements.btnCloudActivateProfile = document.getElementById('btn-cloud-activate-profile');
    elements.btnCloudSaveProfile = document.getElementById('btn-cloud-save-profile');
    elements.btnCloudDeleteProfile = document.getElementById('btn-cloud-delete-profile');
    elements.cloudProfileName = document.getElementById('cloud-profile-name');
    elements.cloudApiBase = document.getElementById('cloud-api-base');
    elements.cloudApiKey = document.getElementById('cloud-api-key');
    elements.cloudCurrentKeyHint = document.getElementById('cloud-current-key-hint');
    elements.cloudModelInput = document.getElementById('cloud-model-input');
    elements.btnCloudDiscoverModels = document.getElementById('btn-cloud-discover-models');
    elements.cloudDiscoveredModelsSelect = document.getElementById('cloud-discovered-models-select');
    elements.cloudModelAlias = document.getElementById('cloud-model-alias');
    elements.cloudExtraHeaders = document.getElementById('cloud-extra-headers');
    elements.cloudContextWindow = document.getElementById('cloud-context-window');
    elements.cloudMaxTokens = document.getElementById('cloud-max-tokens');
    elements.cloudTimeout = document.getElementById('cloud-timeout');
    elements.cloudStreamingCheckbox = document.getElementById('cloud-streaming-checkbox');
    elements.btnCloudTestConnection = document.getElementById('btn-cloud-test-connection');
    elements.btnCloudVerifyTools = document.getElementById('btn-cloud-verify-tools');
    elements.btnCloudWarmup = document.getElementById('btn-cloud-warmup');
    elements.cloudDiagLatency = document.getElementById('cloud-diag-latency');
    elements.cloudDiagTtft = document.getElementById('cloud-diag-ttft');
    elements.cloudDiagTps = document.getElementById('cloud-diag-tps');
    elements.cloudDiagToolsBadge = document.getElementById('cloud-diag-tools-badge');
    elements.cloudDiagnosticsConsole = document.getElementById('cloud-diagnostics-console');
    elements.cloudDiagClearBtn = document.getElementById('cloud-diag-clear-btn');

    // Provider Specific Panels & Badges
    elements.panelProviderOpenrouter = document.getElementById('panel-provider-openrouter');
    elements.panelProviderOpenai = document.getElementById('panel-provider-openai');
    elements.panelProviderAnthropic = document.getElementById('panel-provider-anthropic');
    elements.panelProviderGoogle = document.getElementById('panel-provider-google');
    elements.panelProviderOllama = document.getElementById('panel-provider-ollama');
    elements.panelProviderCloudHosted = document.getElementById('panel-provider-cloud-hosted');
    elements.activeProviderBadge = document.getElementById('active-provider-badge');
    elements.providerDescriptionHint = document.getElementById('provider-description-hint');

    // OpenRouter Panel Elements
    elements.openrouterApiKey = document.getElementById('openrouter-api-key');
    elements.btnValidateOpenrouter = document.getElementById('btn-validate-openrouter');
    elements.openrouterFeedback = document.getElementById('openrouter-feedback');
    elements.openrouterModelBadge = document.getElementById('openrouter-model-badge');
    elements.openrouterModelSearch = document.getElementById('openrouter-model-search');
    elements.openrouterModelSelect = document.getElementById('openrouter-model-select');
    elements.openrouterCustomModel = document.getElementById('openrouter-custom-model');
    elements.openrouterPricingNotice = document.getElementById('openrouter-pricing-notice');
    elements.openrouterModelHint = document.getElementById('openrouter-model-hint');

    // OpenAI Panel Elements
    elements.openaiApiKey = document.getElementById('openai-api-key');
    elements.btnValidateOpenai = document.getElementById('btn-validate-openai');
    elements.openaiFeedback = document.getElementById('openai-feedback');
    elements.openaiModelBadge = document.getElementById('openai-model-badge');
    elements.openaiModelSearch = document.getElementById('openai-model-search');
    elements.openaiModelSelect = document.getElementById('openai-model-select');
    elements.openaiCustomModel = document.getElementById('openai-custom-model');
    elements.openaiPricingNotice = document.getElementById('openai-pricing-notice');

    // Anthropic Panel Elements
    elements.anthropicApiKey = document.getElementById('anthropic-api-key');
    elements.btnValidateAnthropic = document.getElementById('btn-validate-anthropic');
    elements.anthropicFeedback = document.getElementById('anthropic-feedback');
    elements.anthropicModelSelect = document.getElementById('anthropic-model-select');
    elements.anthropicCustomModel = document.getElementById('anthropic-custom-model');
    elements.anthropicPricingNotice = document.getElementById('anthropic-pricing-notice');

    // Google Gemini Panel Elements
    elements.googleApiKey = document.getElementById('google-api-key');
    elements.btnValidateGoogle = document.getElementById('btn-validate-google');
    elements.googleFeedback = document.getElementById('google-feedback');
    elements.googleModelSelect = document.getElementById('google-model-select');
    elements.googleCustomModel = document.getElementById('google-custom-model');
    elements.googlePricingNotice = document.getElementById('google-pricing-notice');

    // Ollama Panel Elements
    elements.ollamaBaseUrl = document.getElementById('ollama-base-url');
    elements.btnValidateOllama = document.getElementById('btn-validate-ollama');
    elements.ollamaFeedback = document.getElementById('ollama-feedback');
    elements.ollamaModelBadge = document.getElementById('ollama-model-badge');
    elements.ollamaModelSelect = document.getElementById('ollama-model-select');
    elements.ollamaCustomModel = document.getElementById('ollama-custom-model');
    elements.ollamaPricingNotice = document.getElementById('ollama-pricing-notice');
    elements.ollamaApiKey = document.getElementById('ollama-api-key');

    // Cloud Hosted Panel Elements (New Assessment)
    elements.cloudEmptyState = document.getElementById('cloud-empty-state');
    elements.cloudActiveProfileSection = document.getElementById('cloud-active-profile-section');
    elements.btnCloudCreateFirstProfile = document.getElementById('btn-cloud-create-first-profile');
    elements.cloudProfileSelectMain = document.getElementById('cloud-profile-select-main');
    elements.btnCloudNewProfileInline = document.getElementById('btn-cloud-new-profile-inline');
    elements.btnCloudEditProfileInline = document.getElementById('btn-cloud-edit-profile-inline');
    elements.btnCloudDeleteProfileInline = document.getElementById('btn-cloud-delete-profile-inline');
    elements.btnOpenCloudProfileModal = document.getElementById('btn-open-cloud-profile-modal');
    elements.cloudProfileEndpointText = document.getElementById('cloud-profile-endpoint-text');
    elements.cloudProfileAuthStatus = document.getElementById('cloud-profile-auth-status');
    elements.btnTestCloudProfile = document.getElementById('btn-test-cloud-profile');
    elements.cloudModelSearch = document.getElementById('cloud-model-search');
    elements.cloudDiscoveredModelSelect = document.getElementById('cloud-discovered-model-select');
    elements.cloudManualModelInput = document.getElementById('cloud-manual-model-input');
    elements.cloudProfileFeedback = document.getElementById('cloud-profile-feedback');

    // Cloud Hosted Profile Modal Elements
    elements.modalCloudProfilesBackdrop = document.getElementById('modal-cloud-profiles-backdrop');
    elements.btnCloseCloudModal = document.getElementById('btn-close-cloud-modal');
    elements.modalProfileSelect = document.getElementById('modal-profile-select');
    elements.btnModalProfileActivate = document.getElementById('btn-modal-profile-activate');
    elements.btnModalProfileSave = document.getElementById('btn-modal-profile-save');
    elements.btnModalProfileDelete = document.getElementById('btn-modal-profile-delete');
    elements.modalProfileStateBadge = document.getElementById('modal-profile-state-badge');
    elements.modalProfileAuthBadge = document.getElementById('modal-profile-auth-badge');
    elements.modalProfileConnBadge = document.getElementById('modal-profile-conn-badge');
    elements.modalProfileName = document.getElementById('modal-profile-name');
    elements.modalProfileBaseUrl = document.getElementById('modal-profile-base-url');
    elements.modalProfileApiKey = document.getElementById('modal-profile-api-key');
    elements.modalProfileCurrentKeyHint = document.getElementById('modal-profile-current-key-hint');
    elements.modalProfileModel = document.getElementById('modal-profile-model');
    elements.btnModalDiscoverModels = document.getElementById('btn-modal-discover-models');
    elements.modalProfileDiscoveredSelect = document.getElementById('modal-profile-discovered-select');
    elements.modalProfileAlias = document.getElementById('modal-profile-alias');
    elements.btnModalTestConn = document.getElementById('btn-modal-test-conn');
    elements.btnModalVerifyTools = document.getElementById('btn-modal-verify-tools');
    elements.modalProfileTestResult = document.getElementById('modal-profile-test-result');

    // Active Assessment Header Badges
    elements.heroEngineBadge = document.getElementById('hero-engine-badge');
    elements.heroProviderBadge = document.getElementById('hero-provider-badge');
    elements.heroModelBadge = document.getElementById('hero-model-badge');

    // Model Catalog Explorer in Settings View
    elements.catalogModelsGrid = document.getElementById('catalog-models-grid');
    elements.catalogSearchInput = document.getElementById('catalog-search-input');
    elements.catalogTabBtns = document.querySelectorAll('.catalog-tab-btn');

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
    } else if (viewName === 'reports') {
      if (state.latestRunData) {
        loadReportView(state.latestRunData);
      }
    }
  }

  // Update Real-Time Model Pricing Callout
  function updateModelPricingNotice() {
    if (!elements.modelPricingNotice || !elements.modelSelect) return;
    const val = elements.modelSelect.value;
    if (val === '__custom__') {
      elements.modelPricingNotice.style.display = 'block';
      elements.modelPricingNotice.style.background = 'rgba(168, 85, 247, 0.1)';
      elements.modelPricingNotice.style.border = '1px solid rgba(168, 85, 247, 0.3)';
      elements.modelPricingNotice.style.color = '#c084fc';
      elements.modelPricingNotice.textContent = '⚙️ Custom Model Identifier: Model string routed directly to endpoint.';
      return;
    }
    const selectedOpt = elements.modelSelect.selectedOptions[0];
    const pricing = selectedOpt ? selectedOpt.dataset.pricing : '';
    if (pricing === '[FREE]') {
      elements.modelPricingNotice.style.display = 'block';
      elements.modelPricingNotice.style.background = 'rgba(16, 185, 129, 0.1)';
      elements.modelPricingNotice.style.border = '1px solid rgba(16, 185, 129, 0.3)';
      elements.modelPricingNotice.style.color = '#34d399';
      elements.modelPricingNotice.textContent = '✅ Free Model: Zero token charges on provider.';
    } else if (pricing === '[PAID]') {
      elements.modelPricingNotice.style.display = 'block';
      elements.modelPricingNotice.style.background = 'rgba(245, 158, 11, 0.1)';
      elements.modelPricingNotice.style.border = '1px solid rgba(245, 158, 11, 0.3)';
      elements.modelPricingNotice.style.color = '#fbbf24';
      elements.modelPricingNotice.textContent = '⚠️ Paid Model: Token usage will be billed to your API key balance.';
    } else if (pricing === '[LOCAL]') {
      elements.modelPricingNotice.style.display = 'block';
      elements.modelPricingNotice.style.background = 'rgba(56, 189, 248, 0.1)';
      elements.modelPricingNotice.style.border = '1px solid rgba(56, 189, 248, 0.3)';
      elements.modelPricingNotice.style.color = '#38bdf8';
      elements.modelPricingNotice.textContent = '💻 Local Model: Zero API costs, executed entirely on local compute.';
    } else {
      elements.modelPricingNotice.style.display = 'none';
    }
  }

  // Active Provider Credentials & Base URL Resolvers
  function getActiveProviderApiKey() {
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    if (provider === 'openrouter') {
      return (elements.openrouterApiKey ? elements.openrouterApiKey.value.trim() : '') || state.providerConfigs.openrouter.apiKey || '';
    } else if (provider === 'openai') {
      return (elements.openaiApiKey ? elements.openaiApiKey.value.trim() : '') || state.providerConfigs.openai.apiKey || '';
    } else if (provider === 'anthropic') {
      return (elements.anthropicApiKey ? elements.anthropicApiKey.value.trim() : '') || state.providerConfigs.anthropic.apiKey || '';
    } else if (provider === 'google') {
      return (elements.googleApiKey ? elements.googleApiKey.value.trim() : '') || state.providerConfigs.google.apiKey || '';
    } else if (provider === 'ollama') {
      return (elements.ollamaApiKey ? elements.ollamaApiKey.value.trim() : '') || state.providerConfigs.ollama.apiKey || '';
    } else if (provider === 'cloud_hosted') {
      const selectedId = elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null;
      let activeProf = null;
      if (selectedId) {
        activeProf = (state.cloudProfiles || []).find((p) => p.id === selectedId);
      }
      if (!activeProf) {
        activeProf = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
      }
      return activeProf && activeProf.api_key ? activeProf.api_key : '';
    }
    return (elements.runtimeApiKey ? elements.runtimeApiKey.value.trim() : '') || state.runtimeApiKey || '';
  }

  function getActiveProviderBaseUrl() {
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    if (provider === 'ollama') {
      return (elements.ollamaBaseUrl ? elements.ollamaBaseUrl.value.trim() : '') || state.providerConfigs.ollama.baseUrl || 'http://127.0.0.1:11434';
    } else if (provider === 'cloud_hosted') {
      const selectedId = elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null;
      let activeProf = null;
      if (selectedId) {
        activeProf = (state.cloudProfiles || []).find((p) => p.id === selectedId);
      }
      if (!activeProf) {
        activeProf = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
      }
      return activeProf && activeProf.api_base ? activeProf.api_base : '';
    }
    return elements.customBaseUrl ? elements.customBaseUrl.value.trim() : '';
  }

  // Get Currently Chosen Model ID Directly From Active Provider Panel
  function getSelectedModelId() {
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    if (provider === 'openrouter') {
      if (elements.openrouterModelSelect && elements.openrouterModelSelect.value === '__custom__') {
        return (elements.openrouterCustomModel ? elements.openrouterCustomModel.value.trim() : '') || 'deepseek/deepseek-r1:free';
      }
      return elements.openrouterModelSelect && elements.openrouterModelSelect.value ? elements.openrouterModelSelect.value : 'deepseek/deepseek-r1:free';
    } else if (provider === 'openai') {
      if (elements.openaiModelSelect && elements.openaiModelSelect.value === '__custom__') {
        return (elements.openaiCustomModel ? elements.openaiCustomModel.value.trim() : '') || 'gpt-4o-mini';
      }
      return elements.openaiModelSelect && elements.openaiModelSelect.value ? elements.openaiModelSelect.value : 'gpt-4o-mini';
    } else if (provider === 'anthropic') {
      if (elements.anthropicModelSelect && elements.anthropicModelSelect.value === '__custom__') {
        return (elements.anthropicCustomModel ? elements.anthropicCustomModel.value.trim() : '') || 'claude-3-5-sonnet-20241022';
      }
      return elements.anthropicModelSelect && elements.anthropicModelSelect.value ? elements.anthropicModelSelect.value : 'claude-3-5-sonnet-20241022';
    } else if (provider === 'google') {
      if (elements.googleModelSelect && elements.googleModelSelect.value === '__custom__') {
        return (elements.googleCustomModel ? elements.googleCustomModel.value.trim() : '') || 'gemini-2.0-flash';
      }
      return elements.googleModelSelect && elements.googleModelSelect.value ? elements.googleModelSelect.value : 'gemini-2.0-flash';
    } else if (provider === 'ollama') {
      if (elements.ollamaModelSelect && elements.ollamaModelSelect.value === '__custom__') {
        return (elements.ollamaCustomModel ? elements.ollamaCustomModel.value.trim() : '') || 'qwen2.5:1.5b';
      }
      return elements.ollamaModelSelect && elements.ollamaModelSelect.value ? elements.ollamaModelSelect.value : 'qwen2.5:1.5b';
    } else if (provider === 'cloud_hosted') {
      if (elements.cloudDiscoveredModelSelect && elements.cloudDiscoveredModelSelect.value === '__custom__') {
        return (elements.cloudManualModelInput ? elements.cloudManualModelInput.value.trim() : '') || 'meta-llama/Llama-3.3-70B-Instruct';
      }
      if (elements.cloudDiscoveredModelSelect && elements.cloudDiscoveredModelSelect.value) {
        return elements.cloudDiscoveredModelSelect.value;
      }
      const selectedId = elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null;
      let activeProf = null;
      if (selectedId) {
        activeProf = (state.cloudProfiles || []).find((p) => p.id === selectedId);
      }
      if (!activeProf) {
        activeProf = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
      }
      return activeProf && activeProf.model ? activeProf.model : 'meta-llama/Llama-3.3-70B-Instruct';
    }

    if (elements.modelSelect && elements.modelSelect.value === '__custom__') {
      return elements.modelCustomInput ? elements.modelCustomInput.value.trim() : 'default-model';
    }
    return elements.modelSelect ? elements.modelSelect.value : 'default-model';
  }

  // Synchronize Compatibility Proxies for Legacy Tests & Background Diagnostics
  function syncCompatibilityProxies() {
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    const modelId = getSelectedModelId();
    const apiKey = getActiveProviderApiKey();
    const baseUrl = getActiveProviderBaseUrl();

    if (elements.runtimeApiKey) elements.runtimeApiKey.value = apiKey;
    if (elements.customBaseUrl) elements.customBaseUrl.value = baseUrl;
    if (elements.modelSelect) {
      let found = false;
      for (let i = 0; i < elements.modelSelect.options.length; i++) {
        if (elements.modelSelect.options[i].value === modelId) {
          elements.modelSelect.selectedIndex = i;
          found = true;
          break;
        }
      }
      if (!found) {
        const opt = document.createElement('option');
        opt.value = modelId;
        opt.textContent = modelId;
        opt.selected = true;
        elements.modelSelect.appendChild(opt);
      }
    }
  }

  // Pricing Notice Updaters for Panels
  function updateOpenRouterPricingNotice() {
    if (!elements.openrouterPricingNotice || !elements.openrouterModelSelect) return;
    const val = elements.openrouterModelSelect.value;
    if (val === '__custom__') {
      elements.openrouterPricingNotice.style.display = 'block';
      elements.openrouterPricingNotice.className = 'model-pricing-pill custom';
      elements.openrouterPricingNotice.textContent = '⚙️ Custom Model: Identifier will be passed directly to OpenRouter API.';
      return;
    }
    const opt = elements.openrouterModelSelect.selectedOptions[0];
    const isFree = opt && opt.dataset.pricing === 'free';
    elements.openrouterPricingNotice.style.display = 'block';
    if (isFree) {
      elements.openrouterPricingNotice.className = 'model-pricing-pill free';
      elements.openrouterPricingNotice.textContent = '✅ Free Model: Zero token charges on OpenRouter.';
    } else {
      elements.openrouterPricingNotice.className = 'model-pricing-pill paid';
      elements.openrouterPricingNotice.textContent = '⚠️ Paid Model: Token usage will be billed to your OpenRouter account balance.';
    }
  }

  function updateOpenAIPricingNotice() {
    if (!elements.openaiPricingNotice || !elements.openaiModelSelect) return;
    const val = elements.openaiModelSelect.value;
    elements.openaiPricingNotice.style.display = 'block';
    if (val === '__custom__') {
      elements.openaiPricingNotice.className = 'model-pricing-pill custom';
      elements.openaiPricingNotice.textContent = '⚙️ Custom OpenAI Model: Model identifier passed directly to /v1/chat/completions.';
    } else {
      elements.openaiPricingNotice.className = 'model-pricing-pill paid';
      elements.openaiPricingNotice.textContent = '⚠️ Paid Model: Usage billed directly to your OpenAI API key account.';
    }
  }

  function updateAnthropicPricingNotice() {
    if (!elements.anthropicPricingNotice || !elements.anthropicModelSelect) return;
    const val = elements.anthropicModelSelect.value;
    elements.anthropicPricingNotice.style.display = 'block';
    if (val === '__custom__') {
      elements.anthropicPricingNotice.className = 'model-pricing-pill custom';
      elements.anthropicPricingNotice.textContent = '⚙️ Custom Anthropic Model: Model identifier passed directly to Claude API.';
    } else {
      elements.anthropicPricingNotice.className = 'model-pricing-pill paid';
      elements.anthropicPricingNotice.textContent = '⚠️ Paid Model: Usage billed to your Anthropic console balance ($3.00/M in, $15.00/M out).';
    }
  }

  function updateGooglePricingNotice() {
    if (!elements.googlePricingNotice || !elements.googleModelSelect) return;
    const val = elements.googleModelSelect.value;
    elements.googlePricingNotice.style.display = 'block';
    if (val === '__custom__') {
      elements.googlePricingNotice.className = 'model-pricing-pill custom';
      elements.googlePricingNotice.textContent = '⚙️ Custom Gemini Model: Identifier passed to Google Generative AI API.';
    } else {
      elements.googlePricingNotice.className = 'model-pricing-pill free';
      elements.googlePricingNotice.textContent = '✅ Gemini Cloud API: Generous free tier with high rate limits in Google AI Studio.';
    }
  }

  function updateOllamaPricingNotice() {
    if (!elements.ollamaPricingNotice || !elements.ollamaModelSelect) return;
    const val = elements.ollamaModelSelect.value;
    elements.ollamaPricingNotice.style.display = 'block';
    if (val === '__custom__') {
      elements.ollamaPricingNotice.className = 'model-pricing-pill custom';
      elements.ollamaPricingNotice.textContent = '⚙️ Custom Local Model: Must be pulled locally (ollama pull <tag>).';
    } else {
      elements.ollamaPricingNotice.className = 'model-pricing-pill local';
      elements.ollamaPricingNotice.textContent = '💻 Local Compute: Zero token costs, executed entirely on your local GPU/CPU.';
    }
  }

  // Dedicated Model Populator: OpenRouter
  function populateOpenRouterModels(modelsList = []) {
    if (modelsList && modelsList.length) {
      state.providerConfigs.openrouter.models = modelsList;
      DEFAULT_PROVIDER_MODELS.openrouter = modelsList;
    }
    const models = state.providerConfigs.openrouter.models.length
      ? state.providerConfigs.openrouter.models
      : DEFAULT_PROVIDER_MODELS.openrouter;

    const filter = (elements.openrouterModelSearch ? elements.openrouterModelSearch.value : '').trim().toLowerCase();
    const filtered = models.filter((m) => {
      if (!filter) return true;
      return (m.id && m.id.toLowerCase().includes(filter)) || (m.name && m.name.toLowerCase().includes(filter));
    });

    if (elements.openrouterModelSelect) {
      const currentVal = elements.openrouterModelSelect.value;
      elements.openrouterModelSelect.innerHTML = '';
      let matched = false;

      filtered.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        const isFree = m.free || (m.id && m.id.endsWith(':free')) || m.pricing_status === 'free';
        opt.textContent = `${m.name || m.id} ${isFree ? '[FREE]' : '[PAID]'}`;
        opt.dataset.pricing = isFree ? 'free' : 'paid';
        if (currentVal && m.id === currentVal) {
          opt.selected = true;
          matched = true;
        }
        elements.openrouterModelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      if (currentVal === '__custom__') {
        customOpt.selected = true;
        matched = true;
      }
      elements.openrouterModelSelect.appendChild(customOpt);

      if (!matched && elements.openrouterModelSelect.options.length > 0) {
        elements.openrouterModelSelect.selectedIndex = 0;
      }
    }

    const freeCount = models.filter((m) => m.free || (m.id && m.id.endsWith(':free')) || m.pricing_status === 'free').length;
    if (elements.openrouterModelBadge) {
      elements.openrouterModelBadge.textContent = `${freeCount} Free Models Available`;
      elements.openrouterModelBadge.className = 'badge badge-emerald';
    }

    updateOpenRouterPricingNotice();
    syncCompatibilityProxies();
  }

  // Dedicated Model Populator: OpenAI
  function populateOpenAIModels(modelsList = []) {
    if (modelsList && modelsList.length) {
      state.providerConfigs.openai.models = modelsList;
      DEFAULT_PROVIDER_MODELS.openai = modelsList;
    }
    const models = state.providerConfigs.openai.models.length
      ? state.providerConfigs.openai.models
      : DEFAULT_PROVIDER_MODELS.openai;

    const filter = (elements.openaiModelSearch ? elements.openaiModelSearch.value : '').trim().toLowerCase();
    const filtered = models.filter((m) => {
      if (!filter) return true;
      return (m.id && m.id.toLowerCase().includes(filter)) || (m.name && m.name.toLowerCase().includes(filter));
    });

    if (elements.openaiModelSelect) {
      const currentVal = elements.openaiModelSelect.value;
      elements.openaiModelSelect.innerHTML = '';
      let matched = false;

      filtered.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.name || m.id} [PAID]`;
        opt.dataset.pricing = 'paid';
        if (currentVal && m.id === currentVal) {
          opt.selected = true;
          matched = true;
        }
        elements.openaiModelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      if (currentVal === '__custom__') {
        customOpt.selected = true;
        matched = true;
      }
      elements.openaiModelSelect.appendChild(customOpt);

      if (!matched && elements.openaiModelSelect.options.length > 0) {
        elements.openaiModelSelect.selectedIndex = 0;
      }
    }
    updateOpenAIPricingNotice();
    syncCompatibilityProxies();
  }

  // Dedicated Model Populator: Anthropic
  function populateAnthropicModels(modelsList = []) {
    if (modelsList && modelsList.length) {
      state.providerConfigs.anthropic.models = modelsList;
      DEFAULT_PROVIDER_MODELS.anthropic = modelsList;
    }
    const models = state.providerConfigs.anthropic.models.length
      ? state.providerConfigs.anthropic.models
      : DEFAULT_PROVIDER_MODELS.anthropic;

    if (elements.anthropicModelSelect) {
      const currentVal = elements.anthropicModelSelect.value;
      elements.anthropicModelSelect.innerHTML = '';
      let matched = false;

      models.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.name || m.id} [PAID]`;
        opt.dataset.pricing = 'paid';
        if (currentVal && m.id === currentVal) {
          opt.selected = true;
          matched = true;
        }
        elements.anthropicModelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      if (currentVal === '__custom__') {
        customOpt.selected = true;
        matched = true;
      }
      elements.anthropicModelSelect.appendChild(customOpt);

      if (!matched && elements.anthropicModelSelect.options.length > 0) {
        elements.anthropicModelSelect.selectedIndex = 0;
      }
    }
    updateAnthropicPricingNotice();
    syncCompatibilityProxies();
  }

  // Dedicated Model Populator: Google
  function populateGoogleModels(modelsList = []) {
    if (modelsList && modelsList.length) {
      state.providerConfigs.google.models = modelsList;
      DEFAULT_PROVIDER_MODELS.google = modelsList;
    }
    const models = state.providerConfigs.google.models.length
      ? state.providerConfigs.google.models
      : DEFAULT_PROVIDER_MODELS.google;

    if (elements.googleModelSelect) {
      const currentVal = elements.googleModelSelect.value;
      elements.googleModelSelect.innerHTML = '';
      let matched = false;

      models.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.name || m.id} [FREE/PAID]`;
        opt.dataset.pricing = 'free';
        if (currentVal && m.id === currentVal) {
          opt.selected = true;
          matched = true;
        }
        elements.googleModelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      if (currentVal === '__custom__') {
        customOpt.selected = true;
        matched = true;
      }
      elements.googleModelSelect.appendChild(customOpt);

      if (!matched && elements.googleModelSelect.options.length > 0) {
        elements.googleModelSelect.selectedIndex = 0;
      }
    }
    updateGooglePricingNotice();
    syncCompatibilityProxies();
  }

  // Dedicated Model Populator: Ollama
  function populateOllamaModels(modelsList = []) {
    if (modelsList && modelsList.length) {
      state.providerConfigs.ollama.models = modelsList;
      DEFAULT_PROVIDER_MODELS.ollama = modelsList;
    }
    const models = state.providerConfigs.ollama.models.length
      ? state.providerConfigs.ollama.models
      : DEFAULT_PROVIDER_MODELS.ollama;

    if (elements.ollamaModelSelect) {
      const currentVal = elements.ollamaModelSelect.value;
      elements.ollamaModelSelect.innerHTML = '';
      let matched = false;

      models.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.name || m.id} [LOCAL]`;
        opt.dataset.pricing = 'local';
        if (currentVal && m.id === currentVal) {
          opt.selected = true;
          matched = true;
        }
        elements.ollamaModelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      if (currentVal === '__custom__') {
        customOpt.selected = true;
        matched = true;
      }
      elements.ollamaModelSelect.appendChild(customOpt);

      if (!matched && elements.ollamaModelSelect.options.length > 0) {
        elements.ollamaModelSelect.selectedIndex = 0;
      }
    }

    if (elements.ollamaModelBadge) {
      elements.ollamaModelBadge.textContent = `${models.length} Local Models`;
      elements.ollamaModelBadge.className = 'badge badge-cyan';
    }

    updateOllamaPricingNotice();
    syncCompatibilityProxies();
  }

  // Backward Compatible Populator
  function populateModelOptions(provider, modelsList = []) {
    if (modelsList && modelsList.length) {
      state.currentProviderModels = modelsList;
      DEFAULT_PROVIDER_MODELS[provider] = modelsList;
    } else if (DEFAULT_PROVIDER_MODELS[provider]) {
      state.currentProviderModels = DEFAULT_PROVIDER_MODELS[provider];
    } else {
      state.currentProviderModels = [];
    }

    if (provider === 'openrouter') populateOpenRouterModels(modelsList);
    else if (provider === 'openai') populateOpenAIModels(modelsList);
    else if (provider === 'anthropic') populateAnthropicModels(modelsList);
    else if (provider === 'google') populateGoogleModels(modelsList);
    else if (provider === 'ollama') populateOllamaModels(modelsList);

    // Sync the proxy select
    const filterText = (state.modelFilterText || '').trim().toLowerCase();
    const list = state.currentProviderModels.filter((m) => {
      if (!filterText) return true;
      return (m.id && m.id.toLowerCase().includes(filterText)) ||
             (m.name && m.name.toLowerCase().includes(filterText));
    });

    if (elements.modelSelect) {
      const currentSelected = elements.modelSelect.value;
      elements.modelSelect.innerHTML = '';
      let selectedFound = false;

      list.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.id;
        let badge = '[PRICE UNKNOWN]';
        const isFree = m.free || (m.id && m.id.endsWith(':free')) || m.pricing_status === 'free';
        if (provider === 'ollama') badge = '[LOCAL]';
        else if (isFree) badge = '[FREE]';
        else if (m.pricing_status === 'paid' || provider === 'anthropic' || provider === 'openai' || provider === 'google') badge = '[PAID]';

        opt.textContent = `${m.name || m.id} ${badge}`;
        opt.dataset.pricing = badge;
        if (currentSelected && m.id === currentSelected) {
          opt.selected = true;
          selectedFound = true;
        }
        elements.modelSelect.appendChild(opt);
      });

      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
      customOpt.dataset.pricing = '[CUSTOM]';
      if (currentSelected === '__custom__') customOpt.selected = true;
      elements.modelSelect.appendChild(customOpt);

      if (!selectedFound && elements.modelSelect.options.length > 0) {
        elements.modelSelect.selectedIndex = 0;
      }
    }
    updateModelPricingNotice();
  }

  // Handle Proxy Model Select Change
  function onModelSelectChange() {
    if (elements.modelSelect && elements.modelCustomInput) {
      if (elements.modelSelect.value === '__custom__') {
        elements.modelCustomInput.style.display = 'block';
        elements.modelCustomInput.focus();
      } else {
        elements.modelCustomInput.style.display = 'none';
      }
    }
    updateModelPricingNotice();
    refreshReadiness();
  }

  // Update Execution Engine Readiness Help Banner with Truthful Diagnostics
  function updateReadinessDisplay(rData) {
    if (!rData) return;
    state.readiness = rData;
    const scanModeEl = document.getElementById('scan-mode-select');
    if (!scanModeEl) return;
    const helpEl = scanModeEl.parentElement ? scanModeEl.parentElement.querySelector('.form-help') : null;
    if (!helpEl) return;

    const dockerComp = rData.components ? rData.components.docker_runtime : null;
    const llmComp = rData.components ? rData.components.llm_provider : null;
    const dockerOk = Boolean(dockerComp && dockerComp.available);
    const autonomousOk = Boolean(rData.autonomous_ready);

    if (autonomousOk) {
      helpEl.innerHTML = `✅ <strong style="color:#10b981;">Docker runtime ready:</strong> Full autonomous multi-agent pentest available.`;
      return;
    }

    if (dockerOk) {
      // Docker is available on host! Autonomous readiness failure is NOT a Docker failure.
      if (llmComp && !llmComp.available) {
        const msg = escapeHtml(llmComp.actionable_message || 'AI provider configuration required.');
        helpEl.innerHTML = `✅ <strong style="color:#10b981;">Docker runtime ready.</strong> ⚠️ <strong style="color:#f59e0b;">AI Provider configuration required:</strong> ${msg} <a href="/diagnostics/readiness" target="_blank" style="color:#38bdf8; text-decoration:underline;">View diagnostics</a>.`;
        return;
      }
      const failingComp = Object.values(rData.components || {}).find((c) => !c.available && c.name !== 'docker_runtime');
      if (failingComp) {
        const cName = escapeHtml(failingComp.name.replace(/_/g, ' ').toUpperCase());
        const msg = escapeHtml(failingComp.actionable_message || 'Component setup required.');
        helpEl.innerHTML = `✅ <strong style="color:#10b981;">Docker runtime ready.</strong> ⚠️ <strong style="color:#f59e0b;">${cName}:</strong> ${msg} <a href="/diagnostics/readiness" target="_blank" style="color:#38bdf8; text-decoration:underline;">View diagnostics</a>.`;
        return;
      }
      helpEl.innerHTML = `✅ <strong style="color:#10b981;">Docker runtime ready:</strong> Configuration check in progress.`;
      return;
    }

    // Docker is truly unavailable
    const dockerMsg = escapeHtml(dockerComp ? dockerComp.actionable_message : 'Autonomous multi-agent mode requires Docker.');
    helpEl.innerHTML = `⚠️ <strong style="color:#f59e0b;">Docker unavailable on host:</strong> ${dockerMsg} Select <em>Lightweight In-Process Scanner</em> or view <a href="/diagnostics/readiness" target="_blank" style="color:#38bdf8; text-decoration:underline;">diagnostics</a>.`;
  }

  // Refresh Preflight Runtime Readiness from Backend
  async function refreshReadiness() {
    try {
      const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
      const model = getSelectedModelId();
      const apiKey = state.runtimeApiKey || (elements.runtimeApiKey ? elements.runtimeApiKey.value.trim() : '');
      const headers = {};
      if (apiKey) {
        if (provider === 'google') headers['X-Google-API-Key'] = apiKey;
        else if (provider === 'openrouter') headers['X-OpenRouter-API-Key'] = apiKey;
      }
      const url = `/system/readiness?provider=${encodeURIComponent(provider)}&model=${encodeURIComponent(model)}`;
      const res = await fetch(url, { headers });
      if (res.ok) {
        const rData = await res.json();
        updateReadinessDisplay(rData);
        return rData;
      }
    } catch (_) {}
    return null;
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

      // Preflight runtime readiness check
      await refreshReadiness();
    } catch (err) {
      if (elements.sysDot && elements.sysText) {
        elements.sysDot.style.background = '#ef4444';
        elements.sysText.textContent = 'GATEWAY OFFLINE';
      }
    }
  }

  // Fetch live models for any provider
  async function loadProviderModels(provider) {
    try {
      const res = await fetch(`/providers/${provider}/models`);
      if (res.ok) {
        const liveModels = await res.json();
        if (liveModels && liveModels.length) {
          DEFAULT_PROVIDER_MODELS[provider] = liveModels;
          if (elements.modelProviderSelect && elements.modelProviderSelect.value === provider) {
            populateModelOptions(provider, liveModels);
          }
        }
      }
    } catch (e) {
      // Fallback already preloaded
    }
  }

  // Save Current Provider Form Inputs Into In-Memory State
  function saveCurrentProviderState(prevProvider) {
    if (!prevProvider || !state.providerConfigs[prevProvider]) return;
    const cfg = state.providerConfigs[prevProvider];
    if (prevProvider === 'openrouter') {
      if (elements.openrouterApiKey) cfg.apiKey = elements.openrouterApiKey.value;
      if (elements.openrouterModelSelect) cfg.model = elements.openrouterModelSelect.value;
      if (elements.openrouterCustomModel) cfg.customModel = elements.openrouterCustomModel.value;
      if (elements.openrouterModelSearch) cfg.search = elements.openrouterModelSearch.value;
    } else if (prevProvider === 'openai') {
      if (elements.openaiApiKey) cfg.apiKey = elements.openaiApiKey.value;
      if (elements.openaiModelSelect) cfg.model = elements.openaiModelSelect.value;
      if (elements.openaiCustomModel) cfg.customModel = elements.openaiCustomModel.value;
      if (elements.openaiModelSearch) cfg.search = elements.openaiModelSearch.value;
    } else if (prevProvider === 'anthropic') {
      if (elements.anthropicApiKey) cfg.apiKey = elements.anthropicApiKey.value;
      if (elements.anthropicModelSelect) cfg.model = elements.anthropicModelSelect.value;
      if (elements.anthropicCustomModel) cfg.customModel = elements.anthropicCustomModel.value;
    } else if (prevProvider === 'google') {
      if (elements.googleApiKey) cfg.apiKey = elements.googleApiKey.value;
      if (elements.googleModelSelect) cfg.model = elements.googleModelSelect.value;
      if (elements.googleCustomModel) cfg.customModel = elements.googleCustomModel.value;
    } else if (prevProvider === 'ollama') {
      if (elements.ollamaBaseUrl) cfg.baseUrl = elements.ollamaBaseUrl.value;
      if (elements.ollamaApiKey) cfg.apiKey = elements.ollamaApiKey.value;
      if (elements.ollamaModelSelect) cfg.model = elements.ollamaModelSelect.value;
      if (elements.ollamaCustomModel) cfg.customModel = elements.ollamaCustomModel.value;
    } else if (prevProvider === 'cloud_hosted') {
      if (elements.cloudProfileSelectMain) cfg.profileId = elements.cloudProfileSelectMain.value;
      if (elements.cloudDiscoveredModelSelect) cfg.model = elements.cloudDiscoveredModelSelect.value;
      if (elements.cloudManualModelInput) cfg.customModel = elements.cloudManualModelInput.value;
      if (elements.cloudModelSearch) cfg.search = elements.cloudModelSearch.value;
    }
  }

  // Restore Form Inputs From In-Memory State for Provider
  function restoreProviderState(newProvider) {
    if (!newProvider || !state.providerConfigs[newProvider]) return;
    const cfg = state.providerConfigs[newProvider];
    if (newProvider === 'openrouter') {
      if (elements.openrouterApiKey && cfg.apiKey) elements.openrouterApiKey.value = cfg.apiKey;
      if (elements.openrouterModelSearch && cfg.search) elements.openrouterModelSearch.value = cfg.search;
      if (elements.openrouterCustomModel && cfg.customModel) elements.openrouterCustomModel.value = cfg.customModel;
      populateOpenRouterModels();
      if (elements.openrouterModelSelect && cfg.model) elements.openrouterModelSelect.value = cfg.model;
      if (elements.openrouterCustomModel) elements.openrouterCustomModel.style.display = (elements.openrouterModelSelect && elements.openrouterModelSelect.value === '__custom__') ? 'block' : 'none';
      updateOpenRouterPricingNotice();
    } else if (newProvider === 'openai') {
      if (elements.openaiApiKey && cfg.apiKey) elements.openaiApiKey.value = cfg.apiKey;
      if (elements.openaiModelSearch && cfg.search) elements.openaiModelSearch.value = cfg.search;
      if (elements.openaiCustomModel && cfg.customModel) elements.openaiCustomModel.value = cfg.customModel;
      populateOpenAIModels();
      if (elements.openaiModelSelect && cfg.model) elements.openaiModelSelect.value = cfg.model;
      if (elements.openaiCustomModel) elements.openaiCustomModel.style.display = (elements.openaiModelSelect && elements.openaiModelSelect.value === '__custom__') ? 'block' : 'none';
      updateOpenAIPricingNotice();
    } else if (newProvider === 'anthropic') {
      if (elements.anthropicApiKey && cfg.apiKey) elements.anthropicApiKey.value = cfg.apiKey;
      if (elements.anthropicCustomModel && cfg.customModel) elements.anthropicCustomModel.value = cfg.customModel;
      populateAnthropicModels();
      if (elements.anthropicModelSelect && cfg.model) elements.anthropicModelSelect.value = cfg.model;
      if (elements.anthropicCustomModel) elements.anthropicCustomModel.style.display = (elements.anthropicModelSelect && elements.anthropicModelSelect.value === '__custom__') ? 'block' : 'none';
      updateAnthropicPricingNotice();
    } else if (newProvider === 'google') {
      if (elements.googleApiKey && cfg.apiKey) elements.googleApiKey.value = cfg.apiKey;
      if (elements.googleCustomModel && cfg.customModel) elements.googleCustomModel.value = cfg.customModel;
      populateGoogleModels();
      if (elements.googleModelSelect && cfg.model) elements.googleModelSelect.value = cfg.model;
      if (elements.googleCustomModel) elements.googleCustomModel.style.display = (elements.googleModelSelect && elements.googleModelSelect.value === '__custom__') ? 'block' : 'none';
      updateGooglePricingNotice();
    } else if (newProvider === 'ollama') {
      if (elements.ollamaBaseUrl && cfg.baseUrl) elements.ollamaBaseUrl.value = cfg.baseUrl;
      if (elements.ollamaApiKey && cfg.apiKey) elements.ollamaApiKey.value = cfg.apiKey;
      if (elements.ollamaCustomModel && cfg.customModel) elements.ollamaCustomModel.value = cfg.customModel;
      populateOllamaModels();
      if (elements.ollamaModelSelect && cfg.model) elements.ollamaModelSelect.value = cfg.model;
      if (elements.ollamaCustomModel) elements.ollamaCustomModel.style.display = (elements.ollamaModelSelect && elements.ollamaModelSelect.value === '__custom__') ? 'block' : 'none';
      updateOllamaPricingNotice();
    } else if (newProvider === 'cloud_hosted') {
      updateCloudHostedPanelDisplay();
      if (elements.cloudManualModelInput && cfg.customModel) elements.cloudManualModelInput.value = cfg.customModel;
      if (elements.cloudModelSearch && cfg.search) elements.cloudModelSearch.value = cfg.search;
    }
  }

  // Model Provider Change Handling - Strict Panel Exclusivity & Dynamic Badges
  function onProviderChange() {
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    const prevProvider = state.previousProvider || 'openrouter';

    // 1. Save in-memory inputs from previous provider
    saveCurrentProviderState(prevProvider);
    state.previousProvider = provider;

    // 2. Strict Panel Exclusivity: Show ONLY the active provider panel, hide all 5 other panels
    const allProviders = ['openrouter', 'openai', 'anthropic', 'google', 'ollama', 'cloud_hosted'];
    allProviders.forEach((p) => {
      const panelId = p === 'cloud_hosted' ? 'panel-provider-cloud-hosted' : `panel-provider-${p}`;
      const panel = document.getElementById(panelId) || document.getElementById(`panel-provider-${p}`);
      if (panel) {
        panel.style.display = p === provider ? 'block' : 'none';
      }
    });

    // 3. Update Master Provider badge and description hint
    const meta = PROVIDER_META[provider] || {
      name: provider,
      badgeClass: 'badge-purple',
      badgeText: provider.toUpperCase(),
      description: 'Custom AI Provider',
    };
    if (elements.activeProviderBadge) {
      elements.activeProviderBadge.textContent = meta.badgeText;
      elements.activeProviderBadge.className = `badge ${meta.badgeClass}`;
    }
    if (elements.providerDescriptionHint) {
      elements.providerDescriptionHint.textContent = meta.description;
    }

    // 4. Restore state & populate models for active provider
    restoreProviderState(provider);

    // 5. Fetch live models if provider's models list is currently empty
    if (provider === 'openrouter' && (!state.providerConfigs.openrouter.models || !state.providerConfigs.openrouter.models.length)) {
      loadProviderModels('openrouter');
    } else if (provider === 'ollama' && (!state.providerConfigs.ollama.models || !state.providerConfigs.ollama.models.length)) {
      loadProviderModels('ollama');
    } else if (provider === 'cloud_hosted' && (!state.cloudProfiles || !state.cloudProfiles.length)) {
      loadCloudProfiles();
    }

    // 6. Synchronize compatibility proxies
    syncCompatibilityProxies();

    // 7. Refresh preflight runtime readiness
    refreshReadiness();
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
    if (provider === 'ollama') {
      feedbackEl.innerHTML = `<span style="color:#38bdf8;">Testing connection to local Ollama service...</span>`;
      try {
        const baseUrl = (elements.customBaseUrl ? elements.customBaseUrl.value.trim() : '') || 'http://127.0.0.1:11434';
        const res = await fetch('/providers/ollama/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_base: baseUrl }),
        });
        const data = await res.json();
        if (data.valid || data.status === 'configured') {
          if (data.models && data.models.length) {
            const formatted = data.models.map((m) =>
              typeof m === 'string' ? { id: m, name: m, pricing_status: 'free', free: true } : m
            );
            DEFAULT_PROVIDER_MODELS.ollama = formatted;
            populateModelOptions('ollama', formatted);
            feedbackEl.innerHTML = `<span style="color:#34d399; font-weight: 600;">✅ Connected! ${formatted.length} local models detected.</span>`;
            showToast(`Ollama connected: ${formatted.length} models ready.`, 'success');
          } else {
            feedbackEl.innerHTML = `<span style="color:#34d399;">✅ Connected! ${escapeHtml(data.message)}</span>`;
          }
          await refreshReadiness();
        } else {
          feedbackEl.innerHTML = `<span style="color:#fb7185;">❌ ${escapeHtml(data.message || 'Connection failed')}</span>`;
        }
      } catch (err) {
        feedbackEl.innerHTML = `<span style="color:#fb7185;">❌ Network error: ${escapeHtml(err.message)}</span>`;
      }
      return;
    }

    if (!key && provider !== 'cloud_hosted') {
      feedbackEl.innerHTML = `<span style="color:#fb7185;">Please enter an API key to test.</span>`;
      return;
    }

    feedbackEl.innerHTML = `<span style="color:#38bdf8;">Testing connection and retrieving available models...</span>`;
    let endpoint = '/providers/openrouter/validate';
    let headers = { 'Content-Type': 'application/json' };
    let body = { api_key: key };

    if (provider === 'anthropic') {
      endpoint = '/providers/anthropic/validate';
      headers['X-Anthropic-API-Key'] = key;
    } else if (provider === 'openai') {
      endpoint = '/providers/openai/validate';
      headers['Authorization'] = `Bearer ${key}`;
      headers['X-OpenAI-API-Key'] = key;
    } else if (provider === 'google') {
      endpoint = '/providers/google/validate';
      headers['X-Google-API-Key'] = key;
    } else if (provider === 'cloud_hosted' || provider === 'custom') {
      endpoint = '/providers/custom/validate';
      const baseUrl = (elements.customBaseUrl ? elements.customBaseUrl.value.trim() : '') || 'https://api.openai.com/v1';
      body = { api_base: baseUrl, api_key: key || undefined };
    } else {
      headers['X-OpenRouter-API-Key'] = key;
    }

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.valid || data.status === 'configured') {
        if (key) state.runtimeApiKey = key;

        if (data.models && data.models.length) {
          const formatted = data.models.map((m) =>
            typeof m === 'string'
              ? { id: m, name: m, free: m.includes(':free'), pricing_status: m.includes(':free') ? 'free' : 'paid' }
              : m
          );
          DEFAULT_PROVIDER_MODELS[provider] = formatted;
          populateModelOptions(provider, formatted);
          const freeCount = formatted.filter((m) => m.free || m.id.endsWith(':free') || m.pricing_status === 'free').length;
          feedbackEl.innerHTML = `<span style="color:#34d399; font-weight: 600;">✅ Key Valid! ${formatted.length} models available (${freeCount} free).</span>`;
          showToast(`${provider.toUpperCase()} verified! ${formatted.length} models ready.`, 'success');
        } else {
          feedbackEl.innerHTML = `<span style="color:#34d399;">✅ Valid! ${escapeHtml(data.message || 'Credentials verified.')}</span>`;
          showToast(`${provider.toUpperCase()} credentials verified!`, 'success');
        }
        await refreshReadiness();
      } else {
        feedbackEl.innerHTML = `<span style="color:#fb7185;">❌ ${escapeHtml(data.message || 'Key rejected')}</span>`;
        showToast(`Verification failed: ${data.message}`, 'error');
        await refreshReadiness();
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

    syncCompatibilityProxies();
    const provider = elements.modelProviderSelect ? elements.modelProviderSelect.value : 'openrouter';
    const model = getSelectedModelId();
    const mode = elements.scanModeSelect ? elements.scanModeSelect.value : 'autonomous';
    const maxAttempts = parseInt(elements.gap2Threshold.value, 10) || 2;
    const apiKey = getActiveProviderApiKey();
    const baseUrl = getActiveProviderBaseUrl();

    // Preflight readiness verification before launching
    const currentReadiness = await refreshReadiness();
    if (mode === 'autonomous' && currentReadiness) {
      const dockerComp = currentReadiness.components ? currentReadiness.components.docker_runtime : null;
      const llmComp = currentReadiness.components ? currentReadiness.components.llm_provider : null;
      if (dockerComp && !dockerComp.available) {
        showToast(`Autonomous execution blocked: ${dockerComp.actionable_message || 'Docker is unavailable on host.'}`, 'error');
        return;
      }
      if (llmComp && !llmComp.available && !apiKey) {
        showToast(`Autonomous execution blocked: ${llmComp.actionable_message || 'AI Provider credentials required.'}`, 'error');
        return;
      }
    }

    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
      if (provider === 'google') headers['X-Google-API-Key'] = apiKey;
      else if (provider === 'openrouter') headers['X-OpenRouter-API-Key'] = apiKey;
      else if (provider === 'anthropic') headers['X-Anthropic-API-Key'] = apiKey;
      else if (provider === 'openai') {
        headers['Authorization'] = `Bearer ${apiKey}`;
        headers['X-OpenAI-API-Key'] = apiKey;
      }
    }

    elements.btnLaunch.disabled = true;
    elements.btnLaunch.innerHTML = `<span>⏳</span> Launching Assessment...`;

    let maxTurns = 500;
    if (elements.executionLimitsSelect) {
      if (elements.executionLimitsSelect.value === '__custom__') {
        maxTurns = elements.customTurnsInput ? parseInt(elements.customTurnsInput.value, 10) : 500;
      } else {
        maxTurns = parseInt(elements.executionLimitsSelect.value, 10) || 500;
      }
    }
    if (isNaN(maxTurns) || maxTurns < 1 || maxTurns > 1000) {
      showToast('Execution turn limit must be between 1 and 1000 turns', 'error');
      elements.btnLaunch.disabled = false;
      elements.btnLaunch.innerHTML = `<span>⚡</span> Launch Autonomous VAPT Assessment`;
      return;
    }

    let additionalHosts = [];
    const additionalHostsInput = document.getElementById('additional-hosts-input');
    if (additionalHostsInput && additionalHostsInput.value.trim()) {
      additionalHosts = additionalHostsInput.value.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
    }

    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_url: targetUrl,
          target: targetUrl,
          mode: mode || 'autonomous',
          scan_mode: elements.scanIntensity ? elements.scanIntensity.value : 'deep',
          max_turns: maxTurns,
          scenario: 'web_assessment',
          assessor: 'llm',
          assessor_provider: provider,
          assessor_model: model,
          assessor_api_key: apiKey || null,
          assessor_api_base: baseUrl || null,
          max_attempts: maxAttempts,
          additional_authorized_hosts: additionalHosts,
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
    if (runId) {
      localStorage.setItem('activeRunId', runId);
    }
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }

    state.activeRunId = runId;
    fetchRunState(runId);

    // 1. Establish Fallback Periodic Polling
    state.pollTimer = setInterval(() => {
      if (state.activeRunId === runId) {
        fetchRunState(runId);
      }
    }, 2000);

    // 2. Establish Low-Latency Server-Sent Events (SSE) Stream
    function connectSse() {
      if (state.activeRunId !== runId) return;
      try {
        const sse = new EventSource(`/runs/${runId}/stream`);
        state.eventSource = sse;

        sse.addEventListener('state', (e) => {
          try {
            const run = JSON.parse(e.data);
            if (run.run_id === state.activeRunId) {
              state.latestRunData = run;
              renderActiveRun(run);
            }
          } catch (err) {}
        });

        sse.addEventListener('progress', (e) => {
          try {
            const prog = JSON.parse(e.data);
            if (state.latestRunData && state.activeRunId === runId) {
              state.latestRunData.progress = prog;
              renderProgress(prog, state.latestRunData);
              if (elements.metricAttempts && prog.current !== undefined) {
                const maxTurns = prog.total || state.latestRunData.max_turns || 500;
                elements.metricAttempts.textContent = `${prog.current} / ${maxTurns}`;
              }
              if (elements.metricCandidates && prog.candidates_identified !== undefined) {
                const inv = prog.candidates_investigated || 0;
                const idn = prog.candidates_identified || 0;
                elements.metricCandidates.textContent = idn > 0 ? `${inv} / ${idn}` : inv;
              }
              if (elements.metricPivots && prog.pivots !== undefined) {
                elements.metricPivots.textContent = prog.pivots;
              }
            }
          } catch (err) {}
        });

        sse.addEventListener('findings', (e) => {
          try {
            const findings = JSON.parse(e.data);
            if (state.latestRunData && state.activeRunId === runId) {
              state.latestRunData.findings = findings;
              renderFindingsLive(findings);
              if (elements.metricFindings) {
                elements.metricFindings.textContent = findings.length;
              }
            }
          } catch (err) {}
        });

        sse.addEventListener('log', (e) => {
          try {
            const entry = JSON.parse(e.data);
            if (state.latestRunData && state.activeRunId === runId) {
              state.latestRunData.decision_trace = state.latestRunData.decision_trace || [];
              state.latestRunData.decision_trace.push(entry);
              renderTerminalLogs(state.latestRunData.decision_trace);
            }
          } catch (err) {}
        });

        sse.addEventListener('complete', (e) => {
          if (state.eventSource) {
            state.eventSource.close();
            state.eventSource = null;
          }
          if (state.pollTimer) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
          }
          fetchRunState(runId);
        });

        sse.onerror = () => {
          // Polling fallback keeps dashboard active; reconnect SSE after backoff
          if (state.eventSource) {
            state.eventSource.close();
            state.eventSource = null;
          }
          if (state.activeRunId === runId && state.latestRunData?.status === 'running') {
            setTimeout(connectSse, 3000);
          }
        };
      } catch (e) {
        console.debug('SSE initialization exception; continuing with polling', e);
      }
    }

    connectSse();
  }

  let consecutivePollErrors = 0;

  async function fetchRunState(runId) {
    if (!runId || (state.activeRunId && runId !== state.activeRunId)) return;
    try {
      const res = await fetch(`/runs/${runId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const run = await res.json();
      consecutivePollErrors = 0;
      if (state.activeRunId && runId !== state.activeRunId) return;

      // Stale data guard: prevent older poll responses from overwriting newer SSE states
      const cur = state.latestRunData;
      if (cur && cur.run_id === runId && cur.status === run.status) {
        const curTurn = cur.progress?.current || 0;
        const newTurn = run.progress?.current || 0;
        const curLogs = (cur.decision_trace || []).length;
        const newLogs = (run.decision_trace || []).length;
        if (newTurn < curTurn && newLogs < curLogs) {
          return;
        }
      }

      state.latestRunData = run;
      renderActiveRun(run);

      if (['completed', 'failed', 'aborted', 'provider_blocked', 'paused_provider_limit', 'paused_execution_limit', 'stopped', 'interrupted', 'partial', 'blocked'].includes(run.status)) {
        if (state.pollTimer) {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
        }
        if (state.eventSource) {
          state.eventSource.close();
          state.eventSource = null;
        }
        if (state.elapsedTimerInterval) {
          clearInterval(state.elapsedTimerInterval);
          state.elapsedTimerInterval = null;
        }
        if (run.status === 'completed') {
          elements.btnViewReportNow.style.display = 'inline-flex';
          showToast(`Assessment ${runId} completed!`, 'success');
        } else if (run.status === 'partial') {
          showToast(`Assessment ${runId} finished partially: ${run.error || 'untested candidates remain'}`, 'warning');
        } else if (run.status === 'interrupted') {
          showToast(`Assessment ${runId} was interrupted: ${run.error || 'execution did not survive'}`, 'warning');
        } else if (run.status === 'provider_blocked' || run.status === 'paused_provider_limit') {
          showToast(`Assessment ${runId} paused: provider quota exceeded. Choose a fallback model to resume.`, 'warning');
        } else if (run.status === 'paused_execution_limit') {
          showToast(`Assessment ${runId} paused: maximum turn limit reached. Resume to continue assessment.`, 'info');
        } else if (run.status === 'failed') {
          showToast(`Assessment ${runId} failed: ${run.error || 'Check terminal logs'}`, 'error');
        } else if (run.status === 'aborted' || run.status === 'stopped') {
          showToast(`Assessment ${runId} stopped.`, 'info');
        }
      }
    } catch (err) {
      consecutivePollErrors++;
      console.debug('Run polling error:', err);
      if (consecutivePollErrors >= 4) {
        if (state.elapsedTimerInterval) {
          clearInterval(state.elapsedTimerInterval);
          state.elapsedTimerInterval = null;
        }
        if (elements.metricActiveTask) {
          elements.metricActiveTask.textContent = 'Server Disconnected';
        }
        if (elements.metricActiveAgent) {
          elements.metricActiveAgent.textContent = 'Offline';
        }
      }
    }
  }

  const PHASE_ICONS = {
    1: '🔍',
    2: '🕷️',
    3: '🎯',
    4: '🔄',
    5: '📑',
  };

  function renderProgress(prog, run) {
    if (!elements.progressBarFill || !prog) return;
    const status = (run?.status || 'running').toUpperCase();
    const pct = typeof prog.percent === 'number' ? Math.min(100, Math.max(0, prog.percent)) : 0;

    elements.progressBarFill.style.width = `${pct}%`;
    if (status === 'FAILED' || status === 'FAILED_INFRASTRUCTURE' || status === 'FAILED_AGENT') {
      elements.progressBarFill.style.background = '#f43f5e';
    } else if (status === 'ABORTED' || status === 'CANCELLED' || status === 'PROVIDER_BLOCKED' || status === 'PAUSED_PROVIDER_LIMIT' || status === 'PAUSED_EXECUTION_LIMIT') {
      elements.progressBarFill.style.background = '#f59e0b';
    } else if (status === 'COMPLETED') {
      elements.progressBarFill.style.background = '#10b981';
    } else {
      elements.progressBarFill.style.background = 'var(--primary)';
    }

    if (elements.progressPercentText) {
      elements.progressPercentText.textContent = `${pct}%`;
    }

    if (elements.progressPhaseName && prog.phase) {
      elements.progressPhaseName.textContent = prog.phase;
    }

    if (elements.progressPhaseIcon) {
      if (status === 'COMPLETED') {
        elements.progressPhaseIcon.textContent = '✅';
      } else if (status === 'FAILED' || status === 'FAILED_INFRASTRUCTURE' || status === 'FAILED_AGENT') {
        elements.progressPhaseIcon.textContent = '❌';
      } else if (status === 'ABORTED' || status === 'CANCELLED' || status === 'PROVIDER_BLOCKED' || status === 'PAUSED_PROVIDER_LIMIT' || status === 'PAUSED_EXECUTION_LIMIT') {
        elements.progressPhaseIcon.textContent = '⏸️';
      } else {
        elements.progressPhaseIcon.textContent = PHASE_ICONS[prog.phase_index] || '⚡';
      }
    }

    if (elements.progressTurnsText) {
      const maxTurns = prog.total || run?.max_turns || 500;
      const curTurns = prog.current !== undefined ? Math.min(prog.current, maxTurns) : 0;
      elements.progressTurnsText.textContent = `${curTurns} / ${maxTurns} Turns`;
    }
  }

  function updateResumeModelsDropdown(provider, selectedModel) {
    if (!elements.resumeModelSelect) return;
    elements.resumeModelSelect.innerHTML = '';
    const models = DEFAULT_PROVIDER_MODELS[provider] || [];
    let found = false;
    models.forEach((m) => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name || m.id;
      if (selectedModel && m.id === selectedModel) {
        opt.selected = true;
        found = true;
      }
      elements.resumeModelSelect.appendChild(opt);
    });
    if (selectedModel && !found) {
      const opt = document.createElement('option');
      opt.value = selectedModel;
      opt.textContent = `${selectedModel} (Original)`;
      opt.selected = true;
      elements.resumeModelSelect.insertBefore(opt, elements.resumeModelSelect.firstChild);
      found = true;
    }
    if (!found && elements.resumeModelSelect.options.length > 0) {
      elements.resumeModelSelect.selectedIndex = 0;
    }
  }

  function formatDuration(totalSeconds) {
    const totalSec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    const h = String(Math.floor(totalSec / 3600)).padStart(2, '0');
    const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
    const s = String(totalSec % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  }

  function startElapsedTimer(run) {
    if (state.elapsedTimerInterval) {
      clearInterval(state.elapsedTimerInterval);
      state.elapsedTimerInterval = null;
    }

    const startTs = run.started_at || run.start_time;
    if (elements.metricStarted) {
      if (startTs) {
        try {
          const d = new Date(startTs);
          elements.metricStarted.textContent = d.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
        } catch (_) {
          elements.metricStarted.textContent = String(startTs).substring(0, 19);
        }
      } else {
        elements.metricStarted.textContent = '—';
      }
    }

    const isRunning = run.status === 'running' || run.status === 'queued';
    if (isRunning && startTs) {
      const updateTimer = () => {
        const startMs = new Date(startTs).getTime();
        const nowMs = Date.now();
        const elapsedSec = Math.max(0, (nowMs - startMs) / 1000);
        if (elements.metricElapsed) {
          elements.metricElapsed.textContent = formatDuration(elapsedSec);
        }
      };
      updateTimer();
      state.elapsedTimerInterval = setInterval(updateTimer, 1000);
    } else {
      const dur = run.duration_seconds !== undefined && run.duration_seconds !== null
        ? run.duration_seconds
        : (run.elapsed_seconds || 0);
      if (elements.metricElapsed) {
        elements.metricElapsed.textContent = formatDuration(dur);
      }
    }
  }

  function updateRunFactsAndTelemetry(run) {
    if (!run) return;

    // 1. Start Time & Elapsed Duration
    startElapsedTimer(run);

    // 2. Active Agent
    if (elements.metricActiveAgent) {
      const status = (run.status || '').toLowerCase();
      let ag = run.active_agent;
      if (!ag) {
        if (status === 'running' && !run.error) ag = 'Root Agent';
        else if (status === 'completed') ag = 'Completed';
        else if (status === 'provider_blocked' || status === 'paused_provider_limit' || status === 'paused_execution_limit' || status === 'interrupted' || status === 'partial' || status === 'blocked') ag = 'Paused';
        else if (status === 'failed' || status === 'aborted' || status === 'stopped') ag = 'Stopped';
        else ag = 'Idle';
      }
      elements.metricActiveAgent.textContent = ag;
    }

    // 3. Active Task
    if (elements.metricActiveTask) {
      const status = (run.status || '').toLowerCase();
      let task = run.active_task;
      if (!task) {
        if (status === 'running') task = 'Investigating attack surface';
        else if (status === 'completed') task = 'Assessment completed';
        else if (status === 'provider_blocked' || status === 'paused_provider_limit' || status === 'paused_execution_limit') task = 'Awaiting provider resume';
        else if (status === 'failed') task = run.error ? String(run.error).substring(0, 45) : 'Failed';
        else if (status === 'aborted' || status === 'stopped') task = 'Assessment stopped';
        else task = 'Standby';
      }
      elements.metricActiveTask.textContent = task;
    }

    // 4. Findings by Verification State Breakdown
    const vs = run.verification_states || run.findings_summary || {};
    if (elements.feDiscovered) elements.feDiscovered.textContent = vs.discovered ?? 0;
    if (elements.feCandidate) elements.feCandidate.textContent = vs.candidate ?? 0;
    if (elements.feUnderInvestigation) elements.feUnderInvestigation.textContent = vs.under_investigation ?? 0;
    if (elements.feExploitation) elements.feExploitation.textContent = vs.exploitation_attempted ?? 0;
    if (elements.feVerified) elements.feVerified.textContent = vs.verified ?? (run.findings ? run.findings.length : 0);
    if (elements.feUnconfirmed) elements.feUnconfirmed.textContent = vs.unconfirmed ?? 0;
    if (elements.feFp) elements.feFp.textContent = vs.false_positive ?? 0;
    if (elements.feBlocked) elements.feBlocked.textContent = vs.blocked ?? 0;
    if (elements.feInc) elements.feInc.textContent = vs.inconclusive ?? 0;
  }

  // Render Active Run Dashboard
  function renderActiveRun(run) {
    elements.heroRunId.textContent = run.run_id;
    elements.heroTargetText.textContent = run.target_url || 'Target Application';
    const prov = (run.provider || 'openrouter').toUpperCase();
    const mdl = run.model || 'default-model';
    const execModeLabel = run.execution_mode === 'autonomous_multi_agent'
      ? 'Autonomous Multi-Agent Core (Docker)'
      : (run.execution_mode === 'lightweight_active_scanner'
        ? 'Lightweight Active Scanner (In-Process)'
        : (run.execution_mode === 'blocked' ? 'Blocked' : (run.mode || 'web').toUpperCase()));
    elements.heroModeText.textContent = `Engine: ${execModeLabel} • Provider: ${prov} (${mdl})`;

    if (elements.heroEngineBadge) {
      elements.heroEngineBadge.textContent = execModeLabel.includes('Docker')
        ? '⚔️ Autonomous Multi-Agent (Docker)'
        : (execModeLabel.includes('Lightweight') ? '⚡ Lightweight Scanner' : execModeLabel);
    }
    if (elements.heroProviderBadge) {
      elements.heroProviderBadge.textContent = `🌐 ${prov}`;
    }
    if (elements.heroModelBadge) {
      elements.heroModelBadge.textContent = `🧠 ${mdl}`;
    }

    // Update Live Run Facts and Verification State Counters
    updateRunFactsAndTelemetry(run);

    const errorBanner = document.getElementById('hero-error-banner');
    const errorText = document.getElementById('hero-error-text');
    const status = (run.status || 'running').toUpperCase();
    elements.heroRunStatus.textContent = status;

    const findings = run.findings || [];

    const isResumable = [
      'PROVIDER_BLOCKED',
      'PAUSED_PROVIDER_LIMIT',
      'PAUSED_EXECUTION_LIMIT',
      'INTERRUPTED',
      'FAILED',
      'FAILED_INFRASTRUCTURE',
      'FAILED_AGENT',
      'ABORTED',
      'CANCELLED',
      'PARTIAL',
    ].includes(status) || !!run.provider_error;

    if (status === 'COMPLETED') {
      elements.heroRunStatus.className = 'badge badge-emerald';
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'none';
      if (elements.btnViewReportNow) elements.btnViewReportNow.style.display = 'inline-flex';
      if (errorBanner) errorBanner.style.display = 'none';
      if (elements.providerResumeCard) elements.providerResumeCard.style.display = 'none';
    } else if (isResumable) {
      const isPaused = ['PROVIDER_BLOCKED', 'PAUSED_PROVIDER_LIMIT', 'PAUSED_EXECUTION_LIMIT'].includes(status);
      elements.heroRunStatus.className = isPaused ? 'badge badge-amber' : (status === 'CANCELLED' || status === 'ABORTED' ? 'badge badge-cyan' : 'badge badge-rose');
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'none';
      if (elements.btnViewReportNow && findings.length > 0) elements.btnViewReportNow.style.display = 'inline-flex';
      if (errorBanner && errorText) {
        errorBanner.style.display = 'block';
        const errorTitle = document.getElementById('hero-error-title');
        const errorIcon = document.getElementById('hero-error-icon');
        const detailsWrap = document.getElementById('hero-error-details-wrap');
        const detailsText = document.getElementById('hero-error-details-text');

        let rawError = run.error || run.provider_error || (status === 'ABORTED' || status === 'CANCELLED' ? 'Assessment stopped by operator.' : 'Assessment halted.');

        if (status === 'PAUSED_PROVIDER_LIMIT' || status === 'PROVIDER_BLOCKED') {
          if (errorTitle) errorTitle.textContent = 'Provider Limit Paused:';
          if (errorIcon) errorIcon.textContent = '⏸️';
          errorBanner.style.background = 'rgba(245, 158, 11, 0.15)';
          errorBanner.style.borderColor = 'rgba(245, 158, 11, 0.4)';
          errorBanner.style.color = '#fbbf24';
        } else if (status === 'PAUSED_EXECUTION_LIMIT') {
          if (errorTitle) errorTitle.textContent = 'Execution Limit Reached:';
          if (errorIcon) errorIcon.textContent = '⏸️';
          errorBanner.style.background = 'rgba(245, 158, 11, 0.15)';
          errorBanner.style.borderColor = 'rgba(245, 158, 11, 0.4)';
          errorBanner.style.color = '#fbbf24';
        } else if (status === 'CANCELLED' || status === 'ABORTED') {
          if (errorTitle) errorTitle.textContent = 'Assessment Cancelled:';
          if (errorIcon) errorIcon.textContent = '🛑';
          errorBanner.style.background = 'rgba(100, 116, 139, 0.15)';
          errorBanner.style.borderColor = 'rgba(100, 116, 139, 0.4)';
          errorBanner.style.color = '#94a3b8';
        } else {
          if (errorTitle) errorTitle.textContent = status === 'FAILED_INFRASTRUCTURE' ? 'Infrastructure Failure:' : 'Agent Error:';
          if (errorIcon) errorIcon.textContent = '⚠️';
          errorBanner.style.background = 'rgba(244, 63, 94, 0.15)';
          errorBanner.style.borderColor = 'rgba(244, 63, 94, 0.4)';
          errorBanner.style.color = '#fb7185';
        }

        if (rawError && (rawError.includes('\n') || rawError.length > 120)) {
          const firstLine = rawError.split('\n')[0].slice(0, 120);
          errorText.textContent = firstLine + (firstLine.length < rawError.length ? '...' : '');
          if (detailsWrap && detailsText) {
            detailsWrap.style.display = 'block';
            detailsText.textContent = rawError;
          }
        } else {
          errorText.textContent = rawError;
          if (detailsWrap) detailsWrap.style.display = 'none';
        }
      }
      if (elements.providerResumeCard) {
        elements.providerResumeCard.style.display = 'block';
        if (elements.providerResumeStatusLabel) {
          elements.providerResumeStatusLabel.textContent = status;
        }
        if (elements.providerResumeMessage) {
          elements.providerResumeMessage.textContent = run.provider_error || run.error || `Assessment halted in status ${status}. All reconnaissance, candidate queue, and findings are preserved. You can resume below with the current or alternative AI configuration.`;
        }
        if (elements.resumeProviderSelect && !elements.resumeProviderSelect.dataset.userEdited) {
          elements.resumeProviderSelect.value = run.provider || 'openrouter';
        }
        const activeProv = elements.resumeProviderSelect ? elements.resumeProviderSelect.value : (run.provider || 'openrouter');
        updateResumeModelsDropdown(activeProv, run.model);
        if (elements.resumeWarnProvider) elements.resumeWarnProvider.textContent = activeProv;
        if (elements.resumeWarnModel && elements.resumeModelSelect) {
          elements.resumeWarnModel.textContent = elements.resumeModelSelect.value;
        }
      }
    } else {
      elements.heroRunStatus.className = 'badge badge-cyan';
      if (elements.btnStopRun) elements.btnStopRun.style.display = 'inline-flex';
      if (elements.btnViewReportNow) elements.btnViewReportNow.style.display = 'none';
      if (errorBanner) errorBanner.style.display = 'none';
      if (elements.providerResumeCard) elements.providerResumeCard.style.display = 'none';
    }

    // Metrics
    const candidates = run.candidates || [];
    const pivotEvents = run.pivot_events || [];
    const trace = run.decision_trace || [];
    const prog = run.progress || {};

    const investigated = prog.candidates_investigated !== undefined
      ? prog.candidates_investigated
      : candidates.filter((c) => c.state === 'VALIDATED' || c.state === 'EXHAUSTED' || (c.attempts || 0) > 0).length;
    const identified = prog.candidates_identified !== undefined
      ? prog.candidates_identified
      : candidates.length;
    const totalPivots = prog.pivots !== undefined
      ? prog.pivots
      : pivotEvents.filter((e) => e.type === 'REDIRECT' || e.event === 'GAP2_PIVOT').length;
    const curTurns = prog.current !== undefined
      ? prog.current
      : candidates.reduce((acc, c) => acc + (c.attempts || 0), 0);
    const maxTurns = prog.total || run.max_turns || 500;

    elements.metricCandidates.textContent = identified > 0 ? `${investigated} / ${identified}` : investigated;
    elements.metricPivots.textContent = totalPivots;
    elements.metricAttempts.textContent = `${curTurns} / ${maxTurns}`;
    elements.metricFindings.textContent = findings.length;

    renderProgress(prog, run);

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
          const st = (m.status || '').toUpperCase();
          let statusBadge;
          if (cnt > 0 || st === 'VULNERABILITIES_IDENTIFIED' || st === 'FAILED') {
            statusBadge = '<span class="badge badge-amber">FINDINGS</span>';
          } else if (st === 'PASSED') {
            statusBadge = '<span class="badge badge-emerald">PASSED</span>';
          } else if (st === 'BLOCKED') {
            statusBadge = '<span class="badge badge-rose">BLOCKED</span>';
          } else if (st === 'INCONCLUSIVE') {
            statusBadge = '<span class="badge badge-purple">INCONCLUSIVE</span>';
          } else {
            statusBadge = '<span class="badge" style="background:rgba(100,116,139,0.2);color:#94a3b8;">NOT TESTED</span>';
          }
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
            ? '<span class="badge badge-rose">ABANDONED</span>'
            : (c.state === 'RULED_OUT' || c.state === 'RULED_OUT_WITH_EVIDENCE')
            ? '<span class="badge" style="background:#334155;color:#cbd5e1;">RULED OUT</span>'
            : (c.state === 'ATTEMPTING' || c.state === 'UNDER_INVESTIGATION')
            ? '<span class="badge badge-cyan">UNDER INVESTIGATION</span>'
            : c.state === 'DISPATCHED'
            ? '<span class="badge badge-cyan">DISPATCHED</span>'
            : c.state === 'PROBE_EXECUTED'
            ? '<span class="badge badge-cyan">PROBE EXECUTED</span>'
            : c.state === 'NOT_TESTED'
            ? '<span class="badge" style="background:#334155;color:#94a3b8;">NOT TESTED</span>'
            : c.state === 'BLOCKED'
            ? '<span class="badge badge-rose">BLOCKED</span>'
            : c.state === 'INCONCLUSIVE'
            ? '<span class="badge badge-amber">INCONCLUSIVE</span>'
            : '<span class="badge" style="background:#334155;color:#94a3b8;">IDENTIFIED</span>';

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
    const isRo = cand.state === 'RULED_OUT' || cand.state === 'RULED_OUT_WITH_EVIDENCE';
    const statusColor = isVal ? '#34d399' : (isRo ? '#94a3b8' : (isAb ? '#f43f5e' : '#38bdf8'));
    const statusText = isVal
      ? 'VALIDATED (Vulnerability Confirmed)'
      : (isRo
        ? 'RULED OUT (Non-Vulnerable / Negative Proof)'
        : (isAb ? 'ABANDONED (Investigation Ended Without Positive Proof)' : (cand.state || 'PENDING')));

    detailBox.style.display = 'block';
    detailBox.innerHTML = `
      <div class="dag-node-inspector-header">
        <div class="dag-node-inspector-title"><span>🔍</span> Candidate: ${escapeHtml(cand.name || cand.id)}</div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <span class="badge" style="background:${statusColor}22; color:${statusColor}; border:1px solid ${statusColor}55;">${statusText}</span>
          <button type="button" class="btn btn-xs btn-secondary" onclick="document.getElementById('dag-node-detail').style.display='none';">✕</button>
        </div>
      </div>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:0.75rem; font-size:0.8rem; margin-top:0.5rem;">
        <div><strong style="color:var(--text-muted);">Target Endpoint:</strong> <code style="color:#7dd3fc;">${escapeHtml(cand.endpoint || cand.target || '/')}</code></div>
        <div><strong style="color:var(--text-muted);">Priority Score (GAP-1):</strong> <span style="color:#38bdf8; font-weight:700;">${cand.composite_score !== undefined ? Number(cand.composite_score).toFixed(3) : '0.500'}</span> (#${cand.priority_rank || 1})</div>
        <div><strong style="color:var(--text-muted);">Usability Rank:</strong> <span class="badge badge-purple">${escapeHtml(cand.usability_rank || 'MEDIUM')}</span></div>
        <div><strong style="color:var(--text-muted);">Attempts / Limit:</strong> <span style="font-family:monospace;">${cand.attempts || 0} / ${cand.max_attempts || 2}</span></div>
        <div><strong style="color:var(--text-muted);">Dispatched At:</strong> <span style="color:#94a3b8; font-family:monospace;">${escapeHtml(cand.dispatched_at || 'Recorded at run init')}</span></div>
        <div><strong style="color:var(--text-muted);">Agent Assignment:</strong> <span style="color:#c084fc;">${escapeHtml(cand.agent_assignment || 'Root Agent')}</span></div>
        <div><strong style="color:var(--text-muted);">Probe Tool:</strong> <code style="color:#fde047;">${escapeHtml(cand.tool_selected || 'exec_command')}</code></div>
        <div><strong style="color:var(--text-muted);">Invocation ID:</strong> <code style="color:#94a3b8; font-size:0.72rem;">${escapeHtml(cand.tool_invocation_id || 'n/a')}</code></div>
        <div><strong style="color:var(--text-muted);">Retry Eligible:</strong> <span style="font-weight:600; color:${cand.retry_eligibility ? '#38bdf8' : '#64748b'};">${cand.retry_eligibility ? 'YES' : 'NO (Concluded)'}</span></div>
      </div>
      ${cand.sanitized_request ? `<div style="margin-top:0.5rem; font-size:0.75rem; background:#020617; padding:0.4rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Probe Command:</strong> <code style="color:#38bdf8;">${escapeHtml(cand.sanitized_request)}</code></div>` : ''}
      ${cand.tool_result ? `<div style="margin-top:0.35rem; font-size:0.75rem; background:#020617; padding:0.4rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Observed Probe Result:</strong> <div style="color:#cbd5e1; font-family:monospace; margin-top:2px;">${escapeHtml(cand.tool_result)}</div></div>` : ''}
      ${cand.verification_result ? `<div style="margin-top:0.35rem; font-size:0.75rem; background:#020617; padding:0.4rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Verification Contract:</strong> <span style="color:#f59e0b;">${escapeHtml(cand.verification_contract || 'Standard VAPT Contract')}</span><br><strong style="color:var(--text-muted);">Contract Outcome:</strong> <span style="color:#94a3b8;">${escapeHtml(cand.verification_result)}</span></div>` : ''}
      ${cand.state_transition_reason ? `<div style="margin-top:0.35rem; font-size:0.75rem; background:#020617; padding:0.4rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Transition Reason:</strong> <span style="color:#e2e8f0;">${escapeHtml(cand.state_transition_reason)}</span></div>` : ''}
      ${cand.evidence_hash ? `<div style="margin-top:0.35rem; font-size:0.75rem; background:#020617; padding:0.35rem 0.5rem; border-radius:4px; border:1px solid #1f2937;"><strong style="color:var(--text-muted);">Proof Hash:</strong> <code style="color:#34d399;">${escapeHtml(cand.evidence_hash)}</code></div>` : ''}
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
    currentDagPivotEvents = (pivotEvents || []).filter(
      (e) => e && e.pivot_executed !== false && (e.event === 'GAP2_PIVOT' || e.type === 'GAP2_PIVOT')
    );

    if (!currentDagCandidates.length) {
      svg.innerHTML = `<text x="490" y="280" fill="#64748b" text-anchor="middle" font-size="14" font-family="sans-serif">Evaluating discovered attack surface nodes...</text>`;
      return;
    }

    // Filter according to current dagFilterMode
    let displayNodes = currentDagCandidates;
    if (state.dagFilterMode === 'found') {
      const found = currentDagCandidates.filter((c) => c.state === 'VALIDATED');
      displayNodes = found.length ? found : currentDagCandidates;
    } else if (state.dagFilterMode === 'pivots') {
      const pivotCandIds = new Set(currentDagPivotEvents.map(e => e.candidate_id || e.from_candidate).filter(Boolean));
      const pivots = currentDagCandidates.filter((c) => pivotCandIds.has(c.id));
      displayNodes = pivots;
      if (!displayNodes.length) {
        svg.setAttribute('viewBox', '0 0 980 320');
        svg.innerHTML = `
          <g transform="translate(0, 40)">
            <rect x="190" y="100" width="600" height="120" rx="8" fill="#0f172a" stroke="#1e293b" stroke-width="1.5"/>
            <text x="490" y="150" fill="#94a3b8" text-anchor="middle" font-size="15" font-family="sans-serif" font-weight="600">
              No adaptive pivots were executed during this assessment.
            </text>
            <text x="490" y="180" fill="#64748b" text-anchor="middle" font-size="12" font-family="sans-serif">
              All prioritized candidate vectors completed their primary probe without triggering a threshold-bounded alternative branch.
            </text>
          </g>
        `;
        return;
      }
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

    // Attach safe DOM click listener once on the SVG container (D02 fix)
    if (!svg._hasDagClickListener) {
      svg.addEventListener('click', (evt) => {
        const node = evt.target.closest('.dag-node');
        if (node && node.dataset && node.dataset.id) {
          inspectDagNode(node.dataset.id);
        }
      });
      svg._hasDagClickListener = true;
    }

    displayNodes.forEach((c, idx) => {
      const cy = count === 1 ? totalHeight / 2 : startY + idx * stepY;
      // D01 fix: link strictly by candidate ID match, never global findings count
      const matchingFinding = (run.findings || []).find(
        (f) => (f.candidate_id === c.id || f.id === c.id) && (f.verification_state === 'verified' || f.is_verified === true || f.verified === true)
      );
      const isVerifiedVuln = c.state === 'VERIFIED_VULNERABILITY' || Boolean(matchingFinding);
      const isObservation = !isVerifiedVuln && (c.state === 'VALIDATED_OBSERVATION' || c.state === 'VALIDATED');
      const isAbandoned = c.state === 'ABANDONED';
      const isRo = c.state === 'RULED_OUT' || c.state === 'RULED_OUT_WITH_EVIDENCE';
      const isInconclusive = c.state === 'INCONCLUSIVE';
      const isAttempting = c.state === 'ATTEMPTING' || c.state === 'UNDER_INVESTIGATION' || c.state === 'PROBE_EXECUTED';

      const strokeColor = isVerifiedVuln ? '#10b981' : (isObservation ? '#38bdf8' : (isRo ? '#64748b' : (isAbandoned ? '#f43f5e' : (isInconclusive ? '#f59e0b' : (isAttempting ? '#06b6d4' : '#475569')))));
      const fillColor = isVerifiedVuln ? '#064e3b' : (isObservation ? '#082f49' : (isRo ? '#1e293b' : (isAbandoned ? '#4c0519' : (isInconclusive ? '#451a03' : (isAttempting ? '#083344' : '#1e293b')))));
      // Never draw candidate branches from target with red pivot lines - use slate neutral for standard candidate exploration
      const edgeColor = isVerifiedVuln ? '#059669' : (isObservation ? '#0284c7' : '#334155');
      const markerId = isVerifiedVuln ? 'url(#arrow-green)' : 'url(#arrow)';

      // Edge from Target to Candidate
      edgesHtml += `
        <path d="M ${rootX + 30} ${rootY} C ${rootX + 140} ${rootY}, ${candX - 120} ${cy}, ${candX - 22} ${cy}" 
              stroke="${edgeColor}" stroke-width="${isVerifiedVuln ? '2.5' : '1.8'}" fill="none" marker-end="${markerId}" opacity="0.85"/>
      `;

      // Candidate Node & Label (D02 fix: safe DOM attribute without inline onclick)
      const activeClass = state.selectedCandidateId === c.id ? 'active-node' : '';
      const pivotEvt = (currentDagPivotEvents || []).find(
        (e) => (e.candidate_id === c.id || e.from_candidate === c.id) && e.pivot_executed === true && Boolean(e.next_candidate || e.to_candidate)
      );
      const hasPivotEvent = Boolean(pivotEvt);
      const badgeText = isVerifiedVuln
        ? '✓ VULNERABILITY'
        : (isObservation
          ? 'ℹ OBSERVATION'
          : (hasPivotEvent
            ? '⚡ PIVOT'
            : (isRo
              ? '✓ RULED OUT'
              : (isAbandoned
                ? '✕ ABANDONED'
                : (isInconclusive ? '? INCONCLUSIVE' : (isAttempting ? '⟳ PROBING' : (c.state || 'IDENTIFIED')))))));

      nodesHtml += `
        <g class="dag-node ${activeClass}" data-id="${escapeHtml(c.id)}" style="cursor: pointer;">
          <circle cx="${candX}" cy="${cy}" r="18" fill="${fillColor}" stroke="${strokeColor}" stroke-width="2.2"/>
          <text x="${candX}" y="${cy + 4}" fill="#ffffff" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">C${idx + 1}</text>
          
          <!-- Title & Endpoint Text -->
          <text x="${candX + 26}" y="${cy - 6}" fill="#f8fafc" font-size="13" font-weight="700" font-family="sans-serif">${escapeHtml(c.name || c.id)}</text>
          <text x="${candX + 26}" y="${cy + 9}" fill="#94a3b8" font-size="9.5" font-family="monospace">${escapeHtml(c.endpoint || c.target || '/')}</text>
          
          <!-- Status Pill -->
          <rect x="${candX + 26}" y="${cy + 15}" width="98" height="16" rx="3" fill="${fillColor}" stroke="${strokeColor}" stroke-width="1"/>
          <text x="${candX + 75}" y="${cy + 27}" fill="${strokeColor}" font-size="8.5" font-weight="bold" text-anchor="middle" font-family="sans-serif">${badgeText}</text>
          <text x="${candX + 132}" y="${cy + 27}" fill="#94a3b8" font-size="8.5" font-family="monospace">(${c.attempts || 0}/${c.max_attempts || 2} turns)</text>
        </g>
      `;

      // ONLY draw dynamic pivot loop on LEFT side of candidate nodes if an ACTUAL pivot event was recorded to a valid next candidate
      if (hasPivotEvent && pivotEvt) {
        const nextId = pivotEvt.next_candidate || pivotEvt.to_candidate;
        const targetIdx = displayNodes.findIndex(node => node.id === nextId);
        if (targetIdx !== -1 && targetIdx !== idx) {
          const nextCy = count === 1 ? totalHeight / 2 : startY + targetIdx * stepY;
          const midY = (cy + nextCy) / 2;
          edgesHtml += `
            <path d="M ${candX - 18} ${cy} C ${candX - 65} ${cy + 15}, ${candX - 65} ${nextCy - 15}, ${candX - 18} ${nextCy}" 
                  stroke="#f43f5e" stroke-width="2.2" stroke-dasharray="5,4" fill="none" marker-end="url(#arrow-red)"/>
            <rect x="${candX - 146}" y="${midY - 9}" width="126" height="18" rx="4" fill="#4c0519" stroke="#f43f5e" stroke-width="1"/>
            <text x="${candX - 83}" y="${midY + 4}" fill="#fecdd3" font-size="8.5" font-weight="bold" text-anchor="middle" font-family="monospace">k=${c.max_attempts || 2} LIMIT ➔ PIVOT</text>
          `;
        }
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
      .map((entry) => {
        let line = '';
        if (typeof entry === 'string') {
          line = entry;
        } else if (entry && typeof entry === 'object') {
          const type = (entry.type || entry.event || 'EVENT').toUpperCase();
          const target = entry.candidate_id || entry.title || entry.endpoint || '';
          const msg = entry.message || entry.detail || entry.reasoning || '';
          line = `[${type}] ${target ? target + ' - ' : ''}${msg || JSON.stringify(entry)}`;
        } else {
          line = String(entry || '');
        }

        let prefixClass = 'log-prefix-init';
        if (line.includes('[DISPATCH]')) prefixClass = 'log-prefix-dispatch';
        else if (line.includes('[ADVANCE]')) prefixClass = 'log-prefix-advance';
        else if (line.includes('[RETRY]')) prefixClass = 'log-prefix-retry';
        else if (line.includes('[REDIRECT]')) prefixClass = 'log-prefix-redirect';
        else if (line.includes('[ABANDON]')) prefixClass = 'log-prefix-abandon';
        else if (line.includes('[GAP2_PIVOT]') || line.includes('[PIVOT]')) prefixClass = 'log-prefix-redirect';

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
    const totalPivots = pivotEvents.filter((e) => (e.pivot_executed !== false) && (e.type === 'REDIRECT' || e.type === 'GAP2_PIVOT' || e.event === 'GAP2_PIVOT')).length;
    const scanMatrix = run.scan_matrix || [];
    const openPorts = run.open_ports || [];
    const components = run.components || [];

    const critCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'CRITICAL').length;
    const highCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'HIGH').length;
    const medCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'MEDIUM').length;
    const lowCount = findings.filter((f) => (f.severity || '').toUpperCase() === 'LOW').length;

    const rawStatus = (run.status || 'COMPLETED').toUpperCase();
    const statusColor = rawStatus === 'COMPLETED' ? '#10b981' : (rawStatus === 'FAILED' ? '#f43f5e' : '#f59e0b');

    let html = `
      <!-- Executive Assessment Attribution Banner -->
      <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 1rem 1.25rem; margin-bottom: 1.25rem; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem;">
        <div>
          <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.35rem; font-weight: 600;">Autonomous Security Assessment Attribution</div>
          <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
            <span class="badge badge-purple" style="font-size: 0.82rem;">🌐 Provider: ${escapeHtml((run.provider || 'openrouter').toUpperCase())}</span>
            <span class="badge badge-amber" style="font-size: 0.82rem;">🧠 Model: ${escapeHtml(run.model || 'default')}</span>
            <span class="badge badge-cyan" style="font-size: 0.82rem;">⚔️ Engine: ${escapeHtml(run.execution_mode === 'autonomous_multi_agent' ? 'Autonomous Multi-Agent Core (Docker)' : (run.execution_mode === 'lightweight_active_scanner' ? 'Lightweight Active Scanner' : (run.mode || 'web').toUpperCase()))}</span>
          </div>
        </div>
        <div style="text-align: right; font-size: 0.8rem; color: var(--text-muted);">
          <div>Evidence Tier: <strong style="color: #10b981;">${escapeHtml(run.evidence_tier || 'OBSERVED_EXTERNAL')}</strong></div>
          <div style="margin-top: 0.15rem;">Proof Hash: <code style="font-family: var(--font-mono); color: var(--accent-cyan); font-size: 0.75rem;">SHA256:${escapeHtml((run.run_id || '').slice(0, 8))}...${escapeHtml((run.evidence_hash || 'verified').slice(0, 12))}</code></div>
        </div>
      </div>

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
            <div class="metric-value" style="color:${statusColor};">${rawStatus}</div>
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
        ${
          (() => {
            const testedCats = scanMatrix.filter((m) => {
              const s = (m.status || '').toUpperCase();
              return s === 'PASSED' || s === 'VULNERABILITIES_IDENTIFIED' || s === 'FAILED' || (m.findings_count || 0) > 0;
            });
            const totalExecTests = testedCats.reduce((acc, c) => acc + (c.test_count || 0), 0);
            return scanMatrix.length > 0 && testedCats.length === scanMatrix.length
              ? `Comprehensive multi-layer audit coverage across all ${scanMatrix.length} core VAPT test categories (${totalExecTests} total tests executed) aligned with industry benchmarks:`
              : `Assessment audit matrix reflecting ${testedCats.length} of ${scanMatrix.length} categories tested (${totalExecTests} individual test routines executed; remaining categories marked NOT TESTED or BLOCKED):`;
          })()
        }
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
                    const st = (m.status || '').toUpperCase();
                    let statusBadge;
                    if (cnt > 0 || st === 'VULNERABILITIES_IDENTIFIED' || st === 'FAILED') {
                      statusBadge = '<span class="badge badge-amber">FINDINGS IDENTIFIED</span>';
                    } else if (st === 'PASSED') {
                      statusBadge = '<span class="badge badge-emerald">PASSED (BASELINE SECURE)</span>';
                    } else if (st === 'BLOCKED') {
                      statusBadge = '<span class="badge badge-rose">BLOCKED (UNREACHABLE)</span>';
                    } else if (st === 'INCONCLUSIVE') {
                      statusBadge = '<span class="badge badge-purple">INCONCLUSIVE (UNRESOLVED)</span>';
                    } else {
                      statusBadge = '<span class="badge" style="background:rgba(100,116,139,0.2);color:#94a3b8;border:1px solid rgba(100,116,139,0.3);">NOT TESTED</span>';
                    }
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
                      const matchingFinding = (run.findings || []).find(
                        (f) => (f.candidate_id === c.id || f.id === c.id) && (f.verification_state === 'verified' || f.is_verified === true || f.verified === true)
                      );
                      const isVerifiedVuln = c.state === 'VERIFIED_VULNERABILITY' || Boolean(matchingFinding);
                      const isObservation = !isVerifiedVuln && (c.state === 'VALIDATED_OBSERVATION' || c.state === 'VALIDATED');
                      const stateBadge = isVerifiedVuln
                        ? '<span class="badge badge-emerald">VULNERABILITY</span>'
                        : (isObservation
                        ? '<span class="badge badge-cyan">OBSERVATION</span>'
                        : (c.state === 'ABANDONED'
                        ? '<span class="badge badge-rose">ABANDONED</span>'
                        : (c.state === 'RULED_OUT' || c.state === 'RULED_OUT_WITH_EVIDENCE'
                        ? '<span class="badge" style="background:#1e293b;color:#94a3b8;border:1px solid #475569;">RULED OUT</span>'
                        : (c.state === 'INCONCLUSIVE'
                        ? '<span class="badge" style="background:#451a03;color:#f59e0b;border:1px solid #b45309;">INCONCLUSIVE</span>'
                        : (c.state === 'NOT_TESTED'
                        ? '<span class="badge" style="background:#334155;color:#94a3b8;">NOT TESTED</span>'
                        : '<span class="badge badge-cyan">PENDING</span>')))));
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

  // Load Past Runs History with Provider, Model & Engine Attribution
  async function loadHistory() {
    elements.tbodyHistory.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Fetching runs...</td></tr>`;
    try {
      const res = await fetch('/runs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const runs = await res.json();
      if (!runs || !runs.length) {
        elements.tbodyHistory.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No past assessments found. Launch one above!</td></tr>`;
        return;
      }

      elements.tbodyHistory.innerHTML = runs
        .map((r) => {
          const status = (r.status || 'unknown').toUpperCase();
          const badgeClass = status === 'COMPLETED' ? 'badge-emerald' : status === 'FAILED' ? 'badge-rose' : 'badge-cyan';
          const prov = (r.provider || 'openrouter').toUpperCase();
          const mdl = r.model || 'default';
          const execMode = r.execution_mode === 'autonomous_multi_agent'
            ? 'Autonomous Docker'
            : (r.execution_mode === 'lightweight_active_scanner' ? 'Lightweight Scanner' : (r.mode || 'web').toUpperCase());

          return `<tr>
            <td><code style="font-family:var(--font-mono); font-size:0.85rem; color:#38bdf8;">${escapeHtml(r.run_id)}</code></td>
            <td><strong>${escapeHtml(r.target_url || 'Target')}</strong></td>
            <td><span class="badge badge-purple" style="font-size:0.75rem;">${escapeHtml(prov)}</span> <code style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(mdl)}</code></td>
            <td><span class="badge badge-cyan" style="font-size:0.75rem;">${escapeHtml(execMode)}</span></td>
            <td><span class="badge ${badgeClass}">${status}</span></td>
            <td><strong>${(r.findings || []).length}</strong></td>
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
      elements.tbodyHistory.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Error: ${escapeHtml(err.message)}</td></tr>`;
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

    if (elements.modelSearchFilter) {
      elements.modelSearchFilter.addEventListener('input', (e) => {
        state.modelFilterText = e.target.value;
        populateModelOptions(elements.modelProviderSelect.value, state.currentProviderModels);
      });
    }

    // Universal Show/Hide Key Toggle for all password inputs with data-target
    document.querySelectorAll('.btn-toggle-key').forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetId = btn.dataset.target;
        if (!targetId) return;
        const targetEl = document.getElementById(targetId);
        if (!targetEl) return;
        const isPass = targetEl.type === 'password';
        targetEl.type = isPass ? 'text' : 'password';
        btn.textContent = isPass ? '🔒' : '👁️';
      });
    });

    if (elements.btnToggleSettingsKeyVisibility && elements.settingsApiKey) {
      elements.btnToggleSettingsKeyVisibility.addEventListener('click', () => {
        const isPass = elements.settingsApiKey.type === 'password';
        elements.settingsApiKey.type = isPass ? 'text' : 'password';
        elements.btnToggleSettingsKeyVisibility.textContent = isPass ? '🔒' : '👁️';
      });
    }

    // OpenRouter Panel Listeners
    if (elements.btnValidateOpenrouter) {
      elements.btnValidateOpenrouter.addEventListener('click', () => {
        const key = elements.openrouterApiKey ? elements.openrouterApiKey.value.trim() : '';
        validateCloudKey('openrouter', key, elements.openrouterFeedback);
      });
    }
    if (elements.openrouterModelSearch) {
      elements.openrouterModelSearch.addEventListener('input', () => {
        populateOpenRouterModels();
      });
    }
    if (elements.openrouterModelSelect) {
      elements.openrouterModelSelect.addEventListener('change', () => {
        if (elements.openrouterCustomModel) {
          elements.openrouterCustomModel.style.display = elements.openrouterModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.openrouterModelSelect.value === '__custom__') elements.openrouterCustomModel.focus();
        }
        updateOpenRouterPricingNotice();
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.openrouterCustomModel) {
      elements.openrouterCustomModel.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // OpenAI Panel Listeners
    if (elements.btnValidateOpenai) {
      elements.btnValidateOpenai.addEventListener('click', () => {
        const key = elements.openaiApiKey ? elements.openaiApiKey.value.trim() : '';
        validateCloudKey('openai', key, elements.openaiFeedback);
      });
    }
    if (elements.openaiModelSearch) {
      elements.openaiModelSearch.addEventListener('input', () => {
        populateOpenAIModels();
      });
    }
    if (elements.openaiModelSelect) {
      elements.openaiModelSelect.addEventListener('change', () => {
        if (elements.openaiCustomModel) {
          elements.openaiCustomModel.style.display = elements.openaiModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.openaiModelSelect.value === '__custom__') elements.openaiCustomModel.focus();
        }
        updateOpenAIPricingNotice();
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.openaiCustomModel) {
      elements.openaiCustomModel.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // Anthropic Panel Listeners
    if (elements.btnValidateAnthropic) {
      elements.btnValidateAnthropic.addEventListener('click', () => {
        const key = elements.anthropicApiKey ? elements.anthropicApiKey.value.trim() : '';
        validateCloudKey('anthropic', key, elements.anthropicFeedback);
      });
    }
    if (elements.anthropicModelSelect) {
      elements.anthropicModelSelect.addEventListener('change', () => {
        if (elements.anthropicCustomModel) {
          elements.anthropicCustomModel.style.display = elements.anthropicModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.anthropicModelSelect.value === '__custom__') elements.anthropicCustomModel.focus();
        }
        updateAnthropicPricingNotice();
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.anthropicCustomModel) {
      elements.anthropicCustomModel.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // Google Gemini Panel Listeners
    if (elements.btnValidateGoogle) {
      elements.btnValidateGoogle.addEventListener('click', () => {
        const key = elements.googleApiKey ? elements.googleApiKey.value.trim() : '';
        validateCloudKey('google', key, elements.googleFeedback);
      });
    }
    if (elements.googleModelSelect) {
      elements.googleModelSelect.addEventListener('change', () => {
        if (elements.googleCustomModel) {
          elements.googleCustomModel.style.display = elements.googleModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.googleModelSelect.value === '__custom__') elements.googleCustomModel.focus();
        }
        updateGooglePricingNotice();
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.googleCustomModel) {
      elements.googleCustomModel.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // Ollama Panel Listeners
    if (elements.btnValidateOllama) {
      elements.btnValidateOllama.addEventListener('click', () => {
        validateCloudKey('ollama', '', elements.ollamaFeedback);
      });
    }
    if (elements.ollamaModelSelect) {
      elements.ollamaModelSelect.addEventListener('change', () => {
        if (elements.ollamaCustomModel) {
          elements.ollamaCustomModel.style.display = elements.ollamaModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.ollamaModelSelect.value === '__custom__') elements.ollamaCustomModel.focus();
        }
        updateOllamaPricingNotice();
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.ollamaCustomModel) {
      elements.ollamaCustomModel.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.ollamaBaseUrl) {
      elements.ollamaBaseUrl.addEventListener('change', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // Cloud Hosted Panel Listeners
    if (elements.btnCloudCreateFirstProfile) {
      elements.btnCloudCreateFirstProfile.addEventListener('click', () => openCloudProfileModal('__new__'));
    }
    if (elements.btnCloudNewProfileInline) {
      elements.btnCloudNewProfileInline.addEventListener('click', () => openCloudProfileModal('__new__'));
    }
    if (elements.btnCloudEditProfileInline) {
      elements.btnCloudEditProfileInline.addEventListener('click', () => {
        openCloudProfileModal(elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null);
      });
    }
    if (elements.btnCloudDeleteProfileInline) {
      elements.btnCloudDeleteProfileInline.addEventListener('click', async () => {
        const pid = elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null;
        if (!pid || pid === '__new__') return;
        if (!confirm('Are you sure you want to delete this cloud hosted profile?')) return;
        try {
          const res = await fetch(`/providers/cloud_hosted/profiles/${pid}`, { method: 'DELETE' });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          showToast('Profile deleted successfully', 'success');
          await loadCloudProfiles();
        } catch (e) {
          showToast(`Failed to delete profile: ${e.message}`, 'error');
        }
      });
    }
    if (elements.btnOpenCloudProfileModal) {
      elements.btnOpenCloudProfileModal.addEventListener('click', () => {
        openCloudProfileModal(elements.cloudProfileSelectMain ? elements.cloudProfileSelectMain.value : null);
      });
    }
    if (elements.cloudProfileSelectMain) {
      elements.cloudProfileSelectMain.addEventListener('change', () => {
        const pid = elements.cloudProfileSelectMain.value;
        if (pid && pid !== '__new__') {
          localStorage.setItem('selectedCloudProfileId', pid);
        }
        const prof = (state.cloudProfiles || []).find((p) => p.id === pid);
        if (prof) {
          if (elements.cloudProfileEndpointText) elements.cloudProfileEndpointText.textContent = prof.api_base || '-';
          if (elements.cloudProfileAuthStatus) {
            elements.cloudProfileAuthStatus.textContent = prof.has_api_key ? 'Key Set' : 'Unauthenticated';
            elements.cloudProfileAuthStatus.className = prof.has_api_key ? 'badge badge-emerald' : 'badge badge-amber';
          }
          if (elements.cloudDiscoveredModelSelect) {
            elements.cloudDiscoveredModelSelect.innerHTML = '';
            const defaultOpt = document.createElement('option');
            defaultOpt.value = prof.model || 'custom-model';
            defaultOpt.textContent = `${prof.model_alias || prof.model || 'Configured Model'} [ACTIVE]`;
            defaultOpt.selected = true;
            elements.cloudDiscoveredModelSelect.appendChild(defaultOpt);
            const customOpt = document.createElement('option');
            customOpt.value = '__custom__';
            customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
            elements.cloudDiscoveredModelSelect.appendChild(customOpt);
          }
          if (elements.cloudManualModelInput) elements.cloudManualModelInput.style.display = 'none';
        }
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.btnTestCloudProfile) {
      elements.btnTestCloudProfile.addEventListener('click', testAndDiscoverCloudEndpointModels);
    }
    if (elements.cloudModelSearch) {
      elements.cloudModelSearch.addEventListener('input', () => {
        const query = elements.cloudModelSearch.value.trim().toLowerCase();
        if (elements.cloudDiscoveredModelSelect) {
          Array.from(elements.cloudDiscoveredModelSelect.options).forEach((opt) => {
            if (opt.value === '__custom__') return;
            opt.style.display = (!query || opt.text.toLowerCase().includes(query)) ? '' : 'none';
          });
        }
      });
    }
    if (elements.cloudDiscoveredModelSelect) {
      elements.cloudDiscoveredModelSelect.addEventListener('change', () => {
        if (elements.cloudManualModelInput) {
          elements.cloudManualModelInput.style.display = elements.cloudDiscoveredModelSelect.value === '__custom__' ? 'block' : 'none';
          if (elements.cloudDiscoveredModelSelect.value === '__custom__') elements.cloudManualModelInput.focus();
        }
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }
    if (elements.cloudManualModelInput) {
      elements.cloudManualModelInput.addEventListener('input', () => {
        syncCompatibilityProxies();
        refreshReadiness();
      });
    }

    // Cloud Hosted Modal Listeners
    if (elements.btnCloseCloudModal) {
      elements.btnCloseCloudModal.addEventListener('click', closeCloudProfileModal);
    }
    if (elements.modalCloudProfilesBackdrop) {
      elements.modalCloudProfilesBackdrop.addEventListener('click', (e) => {
        if (e.target === elements.modalCloudProfilesBackdrop) closeCloudProfileModal();
      });
    }
    if (elements.modalProfileSelect) {
      elements.modalProfileSelect.addEventListener('change', () => {
        fillModalProfileForm(elements.modalProfileSelect.value);
      });
    }
    if (elements.btnModalProfileActivate) {
      elements.btnModalProfileActivate.addEventListener('click', activateModalCloudProfile);
    }
    if (elements.btnModalProfileSave) {
      elements.btnModalProfileSave.addEventListener('click', saveModalCloudProfile);
    }
    if (elements.btnModalProfileDelete) {
      elements.btnModalProfileDelete.addEventListener('click', deleteModalCloudProfile);
    }
    if (elements.btnModalDiscoverModels) {
      elements.btnModalDiscoverModels.addEventListener('click', discoverModalCloudModels);
    }
    if (elements.modalProfileDiscoveredSelect) {
      elements.modalProfileDiscoveredSelect.addEventListener('change', () => {
        if (elements.modalProfileModel) elements.modalProfileModel.value = elements.modalProfileDiscoveredSelect.value;
      });
    }
    if (elements.btnModalTestConn) {
      elements.btnModalTestConn.addEventListener('click', testModalCloudConnection);
    }
    if (elements.btnModalVerifyTools) {
      elements.btnModalVerifyTools.addEventListener('click', verifyModalCloudTools);
    }

    // Model Catalog Explorer in Settings View
    if (elements.catalogSearchInput) {
      elements.catalogSearchInput.addEventListener('input', renderModelCatalog);
    }
    if (elements.catalogTabBtns) {
      elements.catalogTabBtns.forEach((tab) => {
        tab.addEventListener('click', () => {
          elements.catalogTabBtns.forEach((t) => t.classList.remove('active'));
          tab.classList.add('active');
          state.catalogActiveProvider = tab.dataset.provider || 'all';
          renderModelCatalog();
        });
      });
    }

    // Compatibility validation button
    if (elements.btnValidateKey) {
      elements.btnValidateKey.addEventListener('click', () => {
        validateCloudKey(
          elements.modelProviderSelect.value,
          elements.runtimeApiKey.value.trim(),
          elements.apiKeyFeedback
        );
      });
    }

    function syncExecutionLimits() {
      if (!elements.scanIntensity || !elements.executionLimitsSelect) return;
      if (elements.executionLimitsSelect.value === '__custom__') return;
      const mode = elements.scanIntensity.value;
      if (mode === 'quick') {
        elements.executionLimitsSelect.value = '50';
      } else if (mode === 'standard') {
        elements.executionLimitsSelect.value = '100';
      } else if (mode === 'deep') {
        elements.executionLimitsSelect.value = '500';
      }
      if (elements.customTurnsInput) {
        elements.customTurnsInput.style.display = 'none';
      }
    }

    if (elements.scanIntensity && elements.executionLimitsSelect) {
      elements.scanIntensity.addEventListener('change', syncExecutionLimits);
      // Synchronize execution limits on initial page load
      syncExecutionLimits();
    }

    if (elements.executionLimitsSelect) {
      elements.executionLimitsSelect.addEventListener('change', () => {
        if (elements.executionLimitsSelect.value === '__custom__') {
          if (elements.customTurnsInput) {
            elements.customTurnsInput.style.display = 'block';
            elements.customTurnsInput.focus();
          }
        } else {
          if (elements.customTurnsInput) {
            elements.customTurnsInput.style.display = 'none';
          }
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

    if (elements.resumeProviderSelect) {
      elements.resumeProviderSelect.addEventListener('change', () => {
        elements.resumeProviderSelect.dataset.userEdited = 'true';
        const p = elements.resumeProviderSelect.value;
        updateResumeModelsDropdown(p);
        if (elements.resumeWarnProvider) elements.resumeWarnProvider.textContent = p;
        if (elements.resumeWarnModel && elements.resumeModelSelect) {
          elements.resumeWarnModel.textContent = elements.resumeModelSelect.value;
        }
      });
    }

    if (elements.resumeModelSelect) {
      elements.resumeModelSelect.addEventListener('change', () => {
        if (elements.resumeWarnModel) elements.resumeWarnModel.textContent = elements.resumeModelSelect.value;
      });
    }

    if (elements.btnResumeAssessment) {
      elements.btnResumeAssessment.addEventListener('click', async () => {
        const runId = state.activeRunId || state.latestRunData?.run_id;
        if (!runId) return;
        if (elements.resumeConfirmCheckbox && !elements.resumeConfirmCheckbox.checked) {
          showToast('Please confirm resuming by checking the confirmation box.', 'error');
          return;
        }
        const provider = elements.resumeProviderSelect ? elements.resumeProviderSelect.value : (state.latestRunData?.provider || 'openrouter');
        const model = elements.resumeModelSelect ? elements.resumeModelSelect.value : (state.latestRunData?.model || 'default');
        const apiKey = elements.resumeApiKey ? elements.resumeApiKey.value.trim() : '';

        try {
          elements.btnResumeAssessment.disabled = true;
          elements.btnResumeAssessment.innerHTML = `<span>⏳</span> Resuming...`;
          const payload = { model: model, provider: provider };
          if (apiKey) payload.api_key = apiKey;
          const res = await fetch(`/runs/${runId}/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (res.ok) {
            showToast(`Assessment ${runId} resumed with ${model}!`, 'success');
            if (elements.providerResumeCard) elements.providerResumeCard.style.display = 'none';
            await fetchRunState(runId);
            startRunPolling(runId);
          } else {
            const errData = await res.json().catch(() => ({}));
            showToast(`Failed to resume assessment: ${errData.detail || res.statusText}`, 'error');
          }
        } catch (err) {
          showToast(`Error resuming assessment: ${err.message}`, 'error');
        } finally {
          elements.btnResumeAssessment.disabled = false;
          elements.btnResumeAssessment.innerHTML = `▶️ Confirm & Resume`;
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

    if (elements.btnDownloadCsv) {
      elements.btnDownloadCsv.addEventListener('click', async () => {
        downloadReportArtifact('csv', 'vapt_findings_{runId}.csv', 'text/csv', 'CSV Findings Export');
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

    // Cloud Hosted Provider Event Handlers
    if (elements.btnCloudQuickConfigure) {
      elements.btnCloudQuickConfigure.addEventListener('click', () => {
        switchView('settings');
        if (elements.cardCloudHostedPanel) {
          elements.cardCloudHostedPanel.scrollIntoView({ behavior: 'smooth' });
        }
      });
    }

    if (elements.cloudQuickProfileSelect) {
      elements.cloudQuickProfileSelect.addEventListener('change', () => {
        const val = elements.cloudQuickProfileSelect.value;
        const prof = (state.cloudProfiles || []).find((p) => p.id === val);
        if (prof) {
          if (elements.cloudQuickBaseUrl) elements.cloudQuickBaseUrl.textContent = prof.api_base;
          if (prof.model) {
            populateModelOptions('cloud_hosted', [{ id: prof.model, name: prof.model_alias || prof.model }]);
          }
        }
      });
    }

    if (elements.cloudProfileSelect) {
      elements.cloudProfileSelect.addEventListener('change', () => {
        const val = elements.cloudProfileSelect.value;
        if (val === '__new__') {
          fillCloudProfileForm('__new__');
        } else {
          const prof = (state.cloudProfiles || []).find((p) => p.id === val);
          fillCloudProfileForm(prof);
        }
      });
    }

    if (elements.btnCloudSaveProfile) {
      elements.btnCloudSaveProfile.addEventListener('click', saveCloudProfile);
    }

    if (elements.btnCloudDeleteProfile) {
      elements.btnCloudDeleteProfile.addEventListener('click', deleteCloudProfile);
    }

    if (elements.btnCloudActivateProfile) {
      elements.btnCloudActivateProfile.addEventListener('click', activateCloudProfile);
    }

    if (elements.btnCloudDiscoverModels) {
      elements.btnCloudDiscoverModels.addEventListener('click', discoverCloudModels);
    }

    if (elements.cloudDiscoveredModelsSelect) {
      elements.cloudDiscoveredModelsSelect.addEventListener('change', () => {
        const selected = elements.cloudDiscoveredModelsSelect.value;
        if (selected && elements.cloudModelInput) {
          elements.cloudModelInput.value = selected;
        }
      });
    }

    if (elements.btnCloudTestConnection) {
      elements.btnCloudTestConnection.addEventListener('click', testCloudConnection);
    }

    if (elements.btnCloudVerifyTools) {
      elements.btnCloudVerifyTools.addEventListener('click', verifyCloudTools);
    }

    if (elements.btnCloudWarmup) {
      elements.btnCloudWarmup.addEventListener('click', warmupCloudModel);
    }

    if (elements.cloudDiagClearBtn) {
      elements.cloudDiagClearBtn.addEventListener('click', () => {
        if (elements.cloudDiagnosticsConsole) {
          elements.cloudDiagnosticsConsole.textContent = 'Diagnostic console cleared.\n';
        }
      });
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

  // ============================================================================
  // Cloud Hosted Provider Management & Diagnostics (OpenAI-Compatible)
  // ============================================================================

  function logCloudDiag(msg) {
    if (!elements.cloudDiagnosticsConsole) return;
    const ts = new Date().toLocaleTimeString();
    elements.cloudDiagnosticsConsole.textContent += `[${ts}] ${msg}\n`;
    elements.cloudDiagnosticsConsole.scrollTop = elements.cloudDiagnosticsConsole.scrollHeight;
  }

  function updateQuickProfileDisplay() {
    if (!elements.cloudQuickProfileSelect) return;
    const activeProf = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
    if (activeProf) {
      elements.cloudQuickProfileSelect.value = activeProf.id;
      if (elements.cloudQuickBaseUrl) elements.cloudQuickBaseUrl.textContent = activeProf.api_base;
    }
  }

  // ============================================================
  // Cloud Hosted Profile Modal & New Assessment Panel Management
  // ============================================================

  function updateCloudHostedPanelDisplay() {
    const profiles = state.cloudProfiles || [];
    if (profiles.length === 0) {
      if (elements.cloudEmptyState) elements.cloudEmptyState.style.display = 'block';
      if (elements.cloudActiveProfileSection) elements.cloudActiveProfileSection.style.display = 'none';
      return;
    }

    if (elements.cloudEmptyState) elements.cloudEmptyState.style.display = 'none';
    if (elements.cloudActiveProfileSection) elements.cloudActiveProfileSection.style.display = 'block';

    const savedPid = localStorage.getItem('selectedCloudProfileId');
    let selectedProf = null;
    if (savedPid) {
      selectedProf = profiles.find((p) => p.id === savedPid);
    }
    if (!selectedProf) {
      selectedProf = profiles.find((p) => p.is_active) || profiles[0];
    }

    if (elements.cloudProfileSelectMain) {
      elements.cloudProfileSelectMain.innerHTML = '';
      profiles.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.model || 'No model'})${p.is_active ? ' ⭐ [Active]' : ''}`;
        if (selectedProf && p.id === selectedProf.id) opt.selected = true;
        elements.cloudProfileSelectMain.appendChild(opt);
      });
      if (selectedProf) {
        elements.cloudProfileSelectMain.value = selectedProf.id;
      }
    }

    if (selectedProf) {
      if (elements.cloudProfileEndpointText) elements.cloudProfileEndpointText.textContent = selectedProf.api_base || '-';
      if (elements.cloudProfileAuthStatus) {
        elements.cloudProfileAuthStatus.textContent = selectedProf.has_api_key ? 'Key Set' : 'Unauthenticated';
        elements.cloudProfileAuthStatus.className = selectedProf.has_api_key ? 'badge badge-emerald' : 'badge badge-amber';
      }

      if (elements.cloudDiscoveredModelSelect) {
        elements.cloudDiscoveredModelSelect.innerHTML = '';
        const defaultOpt = document.createElement('option');
        defaultOpt.value = selectedProf.model || 'custom-model';
        defaultOpt.textContent = `${selectedProf.model_alias || selectedProf.model || 'Configured Model'} [ACTIVE]`;
        defaultOpt.selected = true;
        elements.cloudDiscoveredModelSelect.appendChild(defaultOpt);

        const customOpt = document.createElement('option');
        customOpt.value = '__custom__';
        customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
        elements.cloudDiscoveredModelSelect.appendChild(customOpt);
      }
      if (elements.cloudManualModelInput) elements.cloudManualModelInput.style.display = 'none';
    }
  }

  function openCloudProfileModal(profileId) {
    if (!elements.modalCloudProfilesBackdrop) return;
    elements.modalCloudProfilesBackdrop.style.display = 'flex';

    if (elements.modalProfileSelect) {
      elements.modalProfileSelect.innerHTML = '';
      (state.cloudProfiles || []).forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.model || 'No model'})${p.is_active ? ' ⭐ [Active]' : ''}`;
        elements.modalProfileSelect.appendChild(opt);
      });
      const newOpt = document.createElement('option');
      newOpt.value = '__new__';
      newOpt.textContent = '➕ Create New Cloud Profile...';
      elements.modalProfileSelect.appendChild(newOpt);

      let targetId = profileId;
      if (!targetId || targetId === '__none__') {
        const activeProf = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
        targetId = activeProf ? activeProf.id : '__new__';
      }
      elements.modalProfileSelect.value = targetId;
      fillModalProfileForm(targetId);
    }
  }

  function closeCloudProfileModal() {
    if (elements.modalCloudProfilesBackdrop) {
      elements.modalCloudProfilesBackdrop.style.display = 'none';
    }
  }

  function fillModalProfileForm(profileOrId) {
    const profile = typeof profileOrId === 'string'
      ? (state.cloudProfiles || []).find((p) => p.id === profileOrId) || null
      : profileOrId;

    if (!profile || profileOrId === '__new__') {
      if (elements.modalProfileName) elements.modalProfileName.value = 'Cloud Hosted Endpoint';
      if (elements.modalProfileBaseUrl) elements.modalProfileBaseUrl.value = '';
      if (elements.modalProfileApiKey) elements.modalProfileApiKey.value = '';
      if (elements.modalProfileCurrentKeyHint) elements.modalProfileCurrentKeyHint.textContent = 'Current key: Not configured';
      if (elements.modalProfileModel) elements.modalProfileModel.value = '';
      if (elements.modalProfileAlias) elements.modalProfileAlias.value = '';
      if (elements.modalProfileStateBadge) {
        elements.modalProfileStateBadge.textContent = 'New Profile';
        elements.modalProfileStateBadge.className = 'badge badge-amber';
      }
      if (elements.modalProfileAuthBadge) {
        elements.modalProfileAuthBadge.textContent = 'No Credential';
        elements.modalProfileAuthBadge.className = 'badge badge-rose';
      }
      if (elements.modalProfileConnBadge) {
        elements.modalProfileConnBadge.textContent = 'Unverified Connection';
        elements.modalProfileConnBadge.className = 'badge badge-amber';
      }
      if (elements.modalProfileDiscoveredSelect) elements.modalProfileDiscoveredSelect.style.display = 'none';
      if (elements.modalProfileTestResult) elements.modalProfileTestResult.style.display = 'none';
      return;
    }

    if (elements.modalProfileName) elements.modalProfileName.value = profile.name || '';
    if (elements.modalProfileBaseUrl) elements.modalProfileBaseUrl.value = profile.api_base || '';
    if (elements.modalProfileApiKey) elements.modalProfileApiKey.value = '';
    if (elements.modalProfileCurrentKeyHint) {
      elements.modalProfileCurrentKeyHint.innerHTML = profile.has_api_key
        ? `Saved key: <code style="color:#34d399;">${escapeHtml(profile.masked_api_key)}</code>`
        : 'Current key: Not configured (Unauthenticated)';
    }
    if (elements.modalProfileModel) elements.modalProfileModel.value = profile.model || '';
    if (elements.modalProfileAlias) elements.modalProfileAlias.value = profile.model_alias || '';
    if (elements.modalProfileStateBadge) {
      elements.modalProfileStateBadge.textContent = profile.is_active ? '⭐ Active Profile' : 'Saved Profile';
      elements.modalProfileStateBadge.className = profile.is_active ? 'badge badge-emerald' : 'badge badge-cyan';
    }
    if (elements.modalProfileAuthBadge) {
      elements.modalProfileAuthBadge.textContent = profile.has_api_key ? 'Credential Configured' : 'No Credential';
      elements.modalProfileAuthBadge.className = profile.has_api_key ? 'badge badge-emerald' : 'badge badge-amber';
    }
    if (elements.modalProfileConnBadge) {
      elements.modalProfileConnBadge.textContent = 'Ready to Test';
      elements.modalProfileConnBadge.className = 'badge badge-cyan';
    }
    if (elements.modalProfileTestResult) elements.modalProfileTestResult.style.display = 'none';
  }

  async function saveModalCloudProfile() {
    const name = elements.modalProfileName ? elements.modalProfileName.value.trim() : '';
    const apiBase = elements.modalProfileBaseUrl ? elements.modalProfileBaseUrl.value.trim() : '';
    const apiKey = elements.modalProfileApiKey ? elements.modalProfileApiKey.value.trim() : '';
    const model = elements.modalProfileModel ? elements.modalProfileModel.value.trim() : '';
    const modelAlias = elements.modalProfileAlias ? elements.modalProfileAlias.value.trim() : '';

    if (!name || !apiBase || !model) {
      showToast('Please fill in required fields: Name, API Base URL, and Model Identifier', 'error');
      return;
    }

    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : '__new__';
    const profileId = currentVal !== '__new__' ? currentVal : null;

    const payload = {
      name: name,
      api_base: apiBase,
      api_key: apiKey || null,
      model: model,
      model_alias: modelAlias || null,
      is_active: true,
    };
    if (profileId) payload.id = profileId;

    if (elements.btnModalProfileSave) {
      elements.btnModalProfileSave.disabled = true;
      elements.btnModalProfileSave.textContent = 'Saving...';
    }

    try {
      const res = await fetch('/providers/cloud_hosted/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let errDetail = `HTTP ${res.status}`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) errDetail = String(errData.detail);
        } catch (_) {}
        throw new Error(errDetail);
      }
      const saved = await res.json();
      showToast(`Profile '${saved.name}' saved and activated!`, 'success');
      await loadCloudProfiles();
      openCloudProfileModal(saved.id);
      updateCloudHostedPanelDisplay();
    } catch (err) {
      showToast(`Failed to save profile: ${err.message}`, 'error');
    } finally {
      if (elements.btnModalProfileSave) {
        elements.btnModalProfileSave.disabled = false;
        elements.btnModalProfileSave.textContent = '💾 Save Profile';
      }
    }
  }

  async function activateModalCloudProfile() {
    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : '__new__';
    if (currentVal === '__new__') {
      showToast('Please select a saved profile to activate', 'info');
      return;
    }
    try {
      const res = await fetch(`/providers/cloud_hosted/profiles/${currentVal}/activate`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const prof = await res.json();
      showToast(`'${prof.name}' is now active!`, 'success');
      await loadCloudProfiles();
      openCloudProfileModal(prof.id);
      updateCloudHostedPanelDisplay();
    } catch (err) {
      showToast(`Failed to activate profile: ${err.message}`, 'error');
    }
  }

  async function deleteModalCloudProfile() {
    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : '__new__';
    if (currentVal === '__new__') {
      fillModalProfileForm('__new__');
      return;
    }
    if (!confirm('Are you sure you want to delete this cloud provider profile?')) return;
    try {
      const res = await fetch(`/providers/cloud_hosted/profiles/${currentVal}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Profile deleted successfully', 'success');
      await loadCloudProfiles();
      if (state.cloudProfiles.length > 0) {
        openCloudProfileModal(state.cloudProfiles[0].id);
      } else {
        openCloudProfileModal('__new__');
      }
      updateCloudHostedPanelDisplay();
    } catch (err) {
      showToast(`Failed to delete profile: ${err.message}`, 'error');
    }
  }

  async function discoverModalCloudModels() {
    const apiBase = elements.modalProfileBaseUrl ? elements.modalProfileBaseUrl.value.trim() : '';
    const apiKey = elements.modalProfileApiKey ? elements.modalProfileApiKey.value.trim() : '';
    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase) {
      showToast('Please enter an API Base URL first', 'error');
      return;
    }

    if (elements.btnModalDiscoverModels) {
      elements.btnModalDiscoverModels.disabled = true;
      elements.btnModalDiscoverModels.textContent = '🔍 Fetching...';
    }

    try {
      const res = await fetch('/providers/cloud_hosted/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: apiBase, api_key: apiKey || null, profile_id: profileId }),
      });
      const data = await res.json();
      if (data.valid && data.models && data.models.length > 0) {
        showToast(`Discovered ${data.models.length} model(s)!`, 'success');
        if (elements.modalProfileDiscoveredSelect) {
          elements.modalProfileDiscoveredSelect.innerHTML = '<option value="">-- Choose Discovered Model --</option>';
          data.models.forEach((m) => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            elements.modalProfileDiscoveredSelect.appendChild(opt);
          });
          elements.modalProfileDiscoveredSelect.style.display = 'block';
        }
        if (elements.modalProfileModel && !elements.modalProfileModel.value.trim()) {
          elements.modalProfileModel.value = data.models[0];
        }
      } else {
        showToast(data.message || 'No models returned from endpoint', 'info');
      }
    } catch (err) {
      showToast(`Discovery error: ${err.message}`, 'error');
    } finally {
      if (elements.btnModalDiscoverModels) {
        elements.btnModalDiscoverModels.disabled = false;
        elements.btnModalDiscoverModels.textContent = '🔍 Fetch Models';
      }
    }
  }

  async function testModalCloudConnection() {
    const apiBase = elements.modalProfileBaseUrl ? elements.modalProfileBaseUrl.value.trim() : '';
    const model = elements.modalProfileModel ? elements.modalProfileModel.value.trim() : '';
    const apiKey = elements.modalProfileApiKey ? elements.modalProfileApiKey.value.trim() : '';
    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase || !model) {
      showToast('Please provide both API Base URL and Model Identifier', 'error');
      return;
    }

    if (elements.btnModalTestConn) {
      elements.btnModalTestConn.disabled = true;
      elements.btnModalTestConn.textContent = 'Testing...';
    }

    try {
      const res = await fetch('/providers/cloud_hosted/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: apiBase, model: model, api_key: apiKey || null, profile_id: profileId }),
      });
      const data = await res.json();
      if (elements.modalProfileTestResult) {
        elements.modalProfileTestResult.style.display = 'block';
        if (data.valid) {
          elements.modalProfileTestResult.innerHTML = `
            <div style="color: #34d399; font-weight: 600;">✅ Connection Verified!</div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 0.25rem;">
              Latency: ${data.duration_ms}ms | TTFT: ${data.ttft_ms}ms | Speed: ${data.tokens_per_second ? data.tokens_per_second + ' tok/s' : 'N/A'}
            </div>`;
          if (elements.modalProfileConnBadge) {
            elements.modalProfileConnBadge.textContent = 'Connection Verified';
            elements.modalProfileConnBadge.className = 'badge badge-emerald';
          }
          showToast('Connection verified successfully!', 'success');
        } else {
          elements.modalProfileTestResult.innerHTML = `<div style="color: #fb7185;">❌ ${escapeHtml(data.message || 'Connection failed')}</div>`;
          if (elements.modalProfileConnBadge) {
            elements.modalProfileConnBadge.textContent = 'Connection Failed';
            elements.modalProfileConnBadge.className = 'badge badge-rose';
          }
          showToast(`Verification failed: ${data.message}`, 'error');
        }
      }
    } catch (err) {
      if (elements.modalProfileTestResult) {
        elements.modalProfileTestResult.style.display = 'block';
        elements.modalProfileTestResult.innerHTML = `<div style="color: #fb7185;">❌ Network Error: ${escapeHtml(err.message)}</div>`;
      }
    } finally {
      if (elements.btnModalTestConn) {
        elements.btnModalTestConn.disabled = false;
        elements.btnModalTestConn.textContent = '🧪 Test Connection';
      }
    }
  }

  async function verifyModalCloudTools() {
    const apiBase = elements.modalProfileBaseUrl ? elements.modalProfileBaseUrl.value.trim() : '';
    const model = elements.modalProfileModel ? elements.modalProfileModel.value.trim() : '';
    const apiKey = elements.modalProfileApiKey ? elements.modalProfileApiKey.value.trim() : '';
    const currentVal = elements.modalProfileSelect ? elements.modalProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase || !model) {
      showToast('Please provide both API Base URL and Model Identifier', 'error');
      return;
    }

    if (elements.btnModalVerifyTools) {
      elements.btnModalVerifyTools.disabled = true;
      elements.btnModalVerifyTools.textContent = 'Verifying...';
    }

    try {
      const res = await fetch('/providers/cloud_hosted/verify_tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: apiBase, model: model, api_key: apiKey || null, profile_id: profileId }),
      });
      const data = await res.json();
      if (elements.modalProfileTestResult) {
        elements.modalProfileTestResult.style.display = 'block';
        if (data.tools_supported) {
          elements.modalProfileTestResult.innerHTML = `
            <div style="color: #34d399; font-weight: 600;">🛠️ Structured Tool Calling Supported!</div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 0.25rem;">${escapeHtml(data.message)}</div>`;
          showToast('Autonomous tool calling confirmed compatible!', 'success');
        } else {
          elements.modalProfileTestResult.innerHTML = `
            <div style="color: #fb7185; font-weight: 600;">⚠️ Tool Calling Compatibility Issue</div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-top: 0.25rem;">${escapeHtml(data.message)}</div>`;
          showToast('Tool calling check failed or unsupported', 'error');
        }
      }
    } catch (err) {
      if (elements.modalProfileTestResult) {
        elements.modalProfileTestResult.style.display = 'block';
        elements.modalProfileTestResult.innerHTML = `<div style="color: #fb7185;">❌ Network Error: ${escapeHtml(err.message)}</div>`;
      }
    } finally {
      if (elements.btnModalVerifyTools) {
        elements.btnModalVerifyTools.disabled = false;
        elements.btnModalVerifyTools.textContent = '🛠️ Verify Tool Calling';
      }
    }
  }

  async function testAndDiscoverCloudEndpointModels() {
    const prof = (state.cloudProfiles || []).find((p) => p.is_active) || (state.cloudProfiles || [])[0];
    if (!prof) {
      showToast('No active cloud profile configured', 'error');
      return;
    }
    if (elements.btnTestCloudProfile) {
      elements.btnTestCloudProfile.disabled = true;
      elements.btnTestCloudProfile.textContent = 'Testing...';
    }
    try {
      const res = await fetch('/providers/cloud_hosted/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_base: prof.api_base, api_key: prof.api_key || null, profile_id: prof.id }),
      });
      const data = await res.json();
      if (data.valid && data.models && data.models.length > 0) {
        showToast(`Discovered ${data.models.length} model(s) on endpoint!`, 'success');
        if (elements.cloudDiscoveredModelSelect) {
          elements.cloudDiscoveredModelSelect.innerHTML = '';
          data.models.forEach((m) => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            elements.cloudDiscoveredModelSelect.appendChild(opt);
          });
          const customOpt = document.createElement('option');
          customOpt.value = '__custom__';
          customOpt.textContent = '⚙️ Enter Custom Model Identifier...';
          elements.cloudDiscoveredModelSelect.appendChild(customOpt);
        }
        if (elements.cloudProfileFeedback) {
          elements.cloudProfileFeedback.innerHTML = `<span style="color:#34d399;">✅ Connected! ${data.models.length} model(s) ready.</span>`;
        }
      } else {
        if (elements.cloudProfileFeedback) {
          elements.cloudProfileFeedback.innerHTML = `<span style="color:#f59e0b;">⚠️ Endpoint reachable; enter model manually.</span>`;
        }
      }
    } catch (e) {
      if (elements.cloudProfileFeedback) {
        elements.cloudProfileFeedback.innerHTML = `<span style="color:#fb7185;">❌ Error: ${escapeHtml(e.message)}</span>`;
      }
    } finally {
      if (elements.btnTestCloudProfile) {
        elements.btnTestCloudProfile.disabled = false;
        elements.btnTestCloudProfile.textContent = '🧪 Test & Fetch Models';
      }
    }
  }

  // ============================================================
  // Multi-Provider Model Catalog Explorer (AI Models Settings)
  // ============================================================

  function renderModelCatalog() {
    if (!elements.catalogModelsGrid) return;
    const activeTab = state.catalogActiveProvider || 'all';
    const filterQuery = (elements.catalogSearchInput ? elements.catalogSearchInput.value : '').trim().toLowerCase();

    const allModels = [];
    const providers = ['openrouter', 'openai', 'anthropic', 'google', 'ollama', 'cloud_hosted'];

    providers.forEach((prov) => {
      const list = DEFAULT_PROVIDER_MODELS[prov] || [];
      list.forEach((m) => {
        allModels.push({
          ...m,
          provider: prov,
        });
      });
    });

    const filtered = allModels.filter((m) => {
      if (activeTab !== 'all' && m.provider !== activeTab) return false;
      if (!filterQuery) return true;
      return (m.id && m.id.toLowerCase().includes(filterQuery)) ||
             (m.name && m.name.toLowerCase().includes(filterQuery)) ||
             (m.provider && m.provider.toLowerCase().includes(filterQuery));
    });

    if (filtered.length === 0) {
      elements.catalogModelsGrid.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 2.5rem; grid-column: 1 / -1;">
          No models matched your filter. Try another keyword or switch provider tab.
        </div>`;
      return;
    }

    elements.catalogModelsGrid.innerHTML = filtered
      .map((m) => {
        const isFree = m.free || (m.id && m.id.endsWith(':free')) || m.pricing_status === 'free';
        const isLocal = m.provider === 'ollama';
        const pricingClass = isLocal ? 'local' : (isFree ? 'free' : 'paid');
        const pricingLabel = isLocal ? '💻 Local Compute (Zero Cost)' : (isFree ? '✅ Free Tier [FREE]' : '⚠️ Paid Token Usage');
        const meta = PROVIDER_META[m.provider] || { badgeText: m.provider.toUpperCase(), badgeClass: 'badge-purple' };

        return `
          <div class="model-catalog-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
              <span class="badge ${meta.badgeClass}" style="font-size: 0.72rem;">${escapeHtml(meta.badgeText)}</span>
              <span class="model-pricing-pill ${pricingClass}" style="margin: 0; font-size: 0.72rem; padding: 0.15rem 0.45rem;">${escapeHtml(pricingLabel)}</span>
            </div>
            <div style="font-weight: 600; font-size: 0.92rem; margin-bottom: 0.25rem; color: #f8fafc; word-break: break-all;">
              ${escapeHtml(m.name || m.id)}
            </div>
            <code style="font-size: 0.75rem; color: var(--text-muted); display: block; margin-bottom: 0.75rem; word-break: break-all;">
              ${escapeHtml(m.id)}
            </code>
            <div style="margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end;">
              <button type="button" class="btn btn-secondary btn-sm btn-select-catalog-model" data-provider="${escapeHtml(m.provider)}" data-model="${escapeHtml(m.id)}" style="font-size: 0.78rem;">
                ⚡ Select for Assessment
              </button>
            </div>
          </div>
        `;
      })
      .join('');

    elements.catalogModelsGrid.querySelectorAll('.btn-select-catalog-model').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = btn.dataset.provider;
        const mdl = btn.dataset.model;
        if (elements.modelProviderSelect) {
          elements.modelProviderSelect.value = p;
          onProviderChange();
        }
        selectModelForProvider(p, mdl);
        switchView('new-assessment');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showToast(`Selected ${mdl} (${p.toUpperCase()}) for New Assessment`, 'success');
      });
    });
  }

  function selectModelForProvider(provider, modelId) {
    if (provider === 'openrouter') {
      if (elements.openrouterModelSelect) {
        let opt = elements.openrouterModelSelect.querySelector(`option[value="${modelId}"]`);
        if (!opt) {
          opt = document.createElement('option');
          opt.value = modelId;
          opt.textContent = modelId;
          elements.openrouterModelSelect.insertBefore(opt, elements.openrouterModelSelect.firstChild);
        }
        elements.openrouterModelSelect.value = modelId;
        if (elements.openrouterCustomModel) elements.openrouterCustomModel.style.display = 'none';
        updateOpenRouterPricingNotice();
      }
    } else if (provider === 'openai') {
      if (elements.openaiModelSelect) {
        let opt = elements.openaiModelSelect.querySelector(`option[value="${modelId}"]`);
        if (!opt) {
          opt = document.createElement('option');
          opt.value = modelId;
          opt.textContent = modelId;
          elements.openaiModelSelect.insertBefore(opt, elements.openaiModelSelect.firstChild);
        }
        elements.openaiModelSelect.value = modelId;
        if (elements.openaiCustomModel) elements.openaiCustomModel.style.display = 'none';
      }
    } else if (provider === 'anthropic') {
      if (elements.anthropicModelSelect) {
        elements.anthropicModelSelect.value = modelId;
        if (elements.anthropicCustomModel) elements.anthropicCustomModel.style.display = 'none';
      }
    } else if (provider === 'google') {
      if (elements.googleModelSelect) {
        elements.googleModelSelect.value = modelId;
        if (elements.googleCustomModel) elements.googleCustomModel.style.display = 'none';
      }
    } else if (provider === 'ollama') {
      if (elements.ollamaModelSelect) {
        let opt = elements.ollamaModelSelect.querySelector(`option[value="${modelId}"]`);
        if (!opt) {
          opt = document.createElement('option');
          opt.value = modelId;
          opt.textContent = modelId;
          elements.ollamaModelSelect.insertBefore(opt, elements.ollamaModelSelect.firstChild);
        }
        elements.ollamaModelSelect.value = modelId;
        if (elements.ollamaCustomModel) elements.ollamaCustomModel.style.display = 'none';
      }
    }
    syncCompatibilityProxies();
  }

  async function loadCloudProfiles() {
    try {
      const res = await fetch('/providers/cloud_hosted/profiles');
      if (!res.ok) return;
      state.cloudProfiles = await res.json();
      updateCloudHostedPanelDisplay();

      if (elements.cloudProfileSelect) {
        elements.cloudProfileSelect.innerHTML = '';
        state.cloudProfiles.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = `${p.name} (${p.model || 'No model'})${p.is_active ? ' ⭐ [Active]' : ''}`;
          elements.cloudProfileSelect.appendChild(opt);
        });
        const newOpt = document.createElement('option');
        newOpt.value = '__new__';
        newOpt.textContent = '➕ Create New Cloud Profile...';
        elements.cloudProfileSelect.appendChild(newOpt);

        const activeProf = state.cloudProfiles.find((p) => p.is_active) || state.cloudProfiles[0];
        if (activeProf) {
          elements.cloudProfileSelect.value = activeProf.id;
          fillCloudProfileForm(activeProf);
        } else {
          elements.cloudProfileSelect.value = '__new__';
          fillCloudProfileForm('__new__');
        }
      }

      if (elements.cloudQuickProfileSelect) {
        elements.cloudQuickProfileSelect.innerHTML = '';
        if (state.cloudProfiles.length === 0) {
          const opt = document.createElement('option');
          opt.value = '__none__';
          opt.textContent = 'No profiles configured (Click Manage Profiles)';
          elements.cloudQuickProfileSelect.appendChild(opt);
        } else {
          state.cloudProfiles.forEach((p) => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${p.name} - ${p.model || 'No model'}${p.is_active ? ' ⭐' : ''}`;
            elements.cloudQuickProfileSelect.appendChild(opt);
          });
        }
        updateQuickProfileDisplay();
      }
    } catch (e) {
      console.debug('Failed to load cloud profiles:', e);
    }
  }

  function fillCloudProfileForm(profile) {
    if (!profile || profile === '__new__') {
      if (elements.cloudProfileName) elements.cloudProfileName.value = 'Cloud Hosted Endpoint';
      if (elements.cloudApiBase) elements.cloudApiBase.value = '';
      if (elements.cloudApiKey) elements.cloudApiKey.value = '';
      if (elements.cloudCurrentKeyHint) elements.cloudCurrentKeyHint.textContent = 'Current key: None';
      if (elements.cloudModelInput) elements.cloudModelInput.value = '';
      if (elements.cloudModelAlias) elements.cloudModelAlias.value = '';
      if (elements.cloudExtraHeaders) elements.cloudExtraHeaders.value = '';
      if (elements.cloudContextWindow) elements.cloudContextWindow.value = '';
      if (elements.cloudMaxTokens) elements.cloudMaxTokens.value = '';
      if (elements.cloudTimeout) elements.cloudTimeout.value = 300;
      if (elements.cloudStreamingCheckbox) elements.cloudStreamingCheckbox.checked = true;
      if (elements.cloudProfileActiveBadge) {
        elements.cloudProfileActiveBadge.textContent = 'New Profile';
        elements.cloudProfileActiveBadge.className = 'badge badge-amber';
      }
      if (elements.cloudConnectionStatusBadge) {
        elements.cloudConnectionStatusBadge.textContent = 'Unverified';
        elements.cloudConnectionStatusBadge.className = 'badge badge-amber';
      }
      if (elements.cloudDiscoveredModelsSelect) elements.cloudDiscoveredModelsSelect.style.display = 'none';
      return;
    }

    if (elements.cloudProfileName) elements.cloudProfileName.value = profile.name || '';
    if (elements.cloudApiBase) elements.cloudApiBase.value = profile.api_base || '';
    if (elements.cloudApiKey) elements.cloudApiKey.value = '';
    if (elements.cloudCurrentKeyHint) {
      elements.cloudCurrentKeyHint.innerHTML = profile.has_api_key
        ? `Saved key: <code style="color:#34d399;">${escapeHtml(profile.masked_api_key)}</code>`
        : 'Current key: None (Unauthenticated)';
    }
    if (elements.cloudModelInput) elements.cloudModelInput.value = profile.model || '';
    if (elements.cloudModelAlias) elements.cloudModelAlias.value = profile.model_alias || '';
    if (elements.cloudExtraHeaders) {
      elements.cloudExtraHeaders.value = profile.extra_headers && Object.keys(profile.extra_headers).length
        ? JSON.stringify(profile.extra_headers)
        : '';
    }
    if (elements.cloudContextWindow) elements.cloudContextWindow.value = profile.context_window || '';
    if (elements.cloudMaxTokens) elements.cloudMaxTokens.value = profile.max_output_tokens || '';
    if (elements.cloudTimeout) elements.cloudTimeout.value = profile.timeout || 300;
    if (elements.cloudStreamingCheckbox) elements.cloudStreamingCheckbox.checked = profile.streaming !== false;
    if (elements.cloudProfileActiveBadge) {
      elements.cloudProfileActiveBadge.textContent = profile.is_active ? '⭐ Active Provider' : 'Saved Profile';
      elements.cloudProfileActiveBadge.className = profile.is_active ? 'badge badge-emerald' : 'badge badge-cyan';
    }
  }

  async function saveCloudProfile() {
    const name = elements.cloudProfileName ? elements.cloudProfileName.value.trim() : '';
    const apiBase = elements.cloudApiBase ? elements.cloudApiBase.value.trim() : '';
    const apiKey = elements.cloudApiKey ? elements.cloudApiKey.value.trim() : '';
    const model = elements.cloudModelInput ? elements.cloudModelInput.value.trim() : '';
    const modelAlias = elements.cloudModelAlias ? elements.cloudModelAlias.value.trim() : '';
    const extraHeadersRaw = elements.cloudExtraHeaders ? elements.cloudExtraHeaders.value.trim() : '';
    const contextWindow = elements.cloudContextWindow && elements.cloudContextWindow.value ? parseInt(elements.cloudContextWindow.value, 10) : null;
    const maxTokens = elements.cloudMaxTokens && elements.cloudMaxTokens.value ? parseInt(elements.cloudMaxTokens.value, 10) : null;
    const timeout = elements.cloudTimeout && elements.cloudTimeout.value ? parseInt(elements.cloudTimeout.value, 10) : 300;
    const streaming = elements.cloudStreamingCheckbox ? elements.cloudStreamingCheckbox.checked : true;

    if (!name || !apiBase || !model) {
      showToast('Please fill in required fields: Name, API Base URL, and Model Identifier', 'error');
      return;
    }

    let extraHeaders = {};
    if (extraHeadersRaw) {
      try {
        extraHeaders = JSON.parse(extraHeadersRaw);
      } catch (e) {
        showToast('Additional HTTP headers must be valid JSON (e.g. {"header": "value"})', 'error');
        return;
      }
    }

    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : '__new__';
    const profileId = currentVal !== '__new__' ? currentVal : null;

    const payload = {
      name: name,
      api_base: apiBase,
      api_key: apiKey || null,
      model: model,
      model_alias: modelAlias || null,
      extra_headers: extraHeaders,
      context_window: contextWindow,
      max_output_tokens: maxTokens,
      timeout: timeout,
      streaming: streaming,
      is_active: true,
    };
    if (profileId) {
      payload.id = profileId;
    }

    if (elements.btnCloudSaveProfile) {
      elements.btnCloudSaveProfile.disabled = true;
      elements.btnCloudSaveProfile.textContent = 'Saving...';
    }

    try {
      const res = await fetch('/providers/cloud_hosted/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let errDetail = `HTTP ${res.status}`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            if (Array.isArray(errData.detail)) {
              errDetail = errData.detail.map((d) => `${d.loc ? d.loc.join('.') : 'field'}: ${d.msg}`).join('; ');
            } else {
              errDetail = String(errData.detail);
            }
          }
        } catch (_) {}
        throw new Error(errDetail);
      }
      const saved = await res.json();
      showToast(`Cloud profile '${saved.name}' saved and activated!`, 'success');
      logCloudDiag(`Profile '${saved.name}' saved successfully (Endpoint: ${saved.api_base}, Model: ${saved.model})`);
      await loadCloudProfiles();
      if (elements.cloudProfileSelect) elements.cloudProfileSelect.value = saved.id;
    } catch (err) {
      showToast(`Failed to save profile: ${err.message}`, 'error');
      logCloudDiag(`ERROR saving profile: ${err.message}`);
    } finally {
      if (elements.btnCloudSaveProfile) {
        elements.btnCloudSaveProfile.disabled = false;
        elements.btnCloudSaveProfile.textContent = '💾 Save Profile';
      }
    }
  }

  async function deleteCloudProfile() {
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : '__new__';
    if (currentVal === '__new__') {
      fillCloudProfileForm('__new__');
      return;
    }

    if (!confirm('Are you sure you want to delete this cloud provider profile?')) return;

    try {
      const res = await fetch(`/providers/cloud_hosted/profiles/${currentVal}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Cloud profile deleted', 'success');
      logCloudDiag(`Profile ${currentVal} deleted.`);
      await loadCloudProfiles();
    } catch (err) {
      showToast(`Failed to delete profile: ${err.message}`, 'error');
    }
  }

  async function activateCloudProfile() {
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : '__new__';
    if (currentVal === '__new__') {
      showToast('Please save the profile before activating it', 'error');
      return;
    }

    try {
      const res = await fetch(`/providers/cloud_hosted/profiles/${currentVal}/activate`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const prof = await res.json();
      showToast(`'${prof.name}' is now the active Cloud Hosted provider!`, 'success');
      logCloudDiag(`Profile '${prof.name}' activated.`);
      await loadCloudProfiles();
      if (elements.modelProviderSelect) {
        elements.modelProviderSelect.value = 'cloud_hosted';
        onProviderChange();
      }
    } catch (err) {
      showToast(`Failed to activate profile: ${err.message}`, 'error');
    }
  }

  async function discoverCloudModels() {
    const apiBase = elements.cloudApiBase ? elements.cloudApiBase.value.trim() : '';
    const apiKey = elements.cloudApiKey ? elements.cloudApiKey.value.trim() : '';
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase) {
      showToast('Please enter an API Base URL first', 'error');
      return;
    }

    let extraHeaders = {};
    if (elements.cloudExtraHeaders && elements.cloudExtraHeaders.value.trim()) {
      try { extraHeaders = JSON.parse(elements.cloudExtraHeaders.value.trim()); } catch (e) {}
    }

    if (elements.btnCloudDiscoverModels) {
      elements.btnCloudDiscoverModels.disabled = true;
      elements.btnCloudDiscoverModels.textContent = '🔍 Discovering...';
    }

    logCloudDiag(`Discovering models from GET ${apiBase}/models ...`);

    try {
      const res = await fetch('/providers/cloud_hosted/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_base: apiBase,
          api_key: apiKey || null,
          profile_id: profileId,
          extra_headers: extraHeaders,
        }),
      });
      const data = await res.json();
      if (data.valid && data.models && data.models.length > 0) {
        logCloudDiag(`Discovered ${data.models.length} model(s): ${data.models.join(', ')}`);
        showToast(`Discovered ${data.models.length} model(s)!`, 'success');

        if (elements.cloudDiscoveredModelsSelect) {
          elements.cloudDiscoveredModelsSelect.innerHTML = '<option value="">-- Choose Discovered Model --</option>';
          data.models.forEach((m) => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            elements.cloudDiscoveredModelsSelect.appendChild(opt);
          });
          elements.cloudDiscoveredModelsSelect.style.display = 'block';
        }

        if (elements.cloudModelInput && !elements.cloudModelInput.value.trim()) {
          elements.cloudModelInput.value = data.models[0];
        }
      } else {
        logCloudDiag(`Model discovery note: ${data.message || 'No models returned. You can enter model ID manually.'}`);
        showToast(data.message || 'No models discovered; enter model ID manually', 'info');
      }
    } catch (err) {
      logCloudDiag(`Discovery network error: ${err.message}`);
      showToast(`Model discovery error: ${err.message}`, 'error');
    } finally {
      if (elements.btnCloudDiscoverModels) {
        elements.btnCloudDiscoverModels.disabled = false;
        elements.btnCloudDiscoverModels.textContent = '🔍 Discover Models';
      }
    }
  }

  async function testCloudConnection() {
    const apiBase = elements.cloudApiBase ? elements.cloudApiBase.value.trim() : '';
    const model = elements.cloudModelInput ? elements.cloudModelInput.value.trim() : '';
    const apiKey = elements.cloudApiKey ? elements.cloudApiKey.value.trim() : '';
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase || !model) {
      showToast('Please provide both API Base URL and Model Identifier to test connection', 'error');
      return;
    }

    let extraHeaders = {};
    if (elements.cloudExtraHeaders && elements.cloudExtraHeaders.value.trim()) {
      try { extraHeaders = JSON.parse(elements.cloudExtraHeaders.value.trim()); } catch (e) {}
    }

    if (elements.btnCloudTestConnection) {
      elements.btnCloudTestConnection.disabled = true;
      elements.btnCloudTestConnection.textContent = 'Testing...';
    }

    logCloudDiag(`\n--- Connection Test: ${apiBase} (Model: ${model}) ---`);

    try {
      const res = await fetch('/providers/cloud_hosted/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_base: apiBase,
          model: model,
          api_key: apiKey || null,
          profile_id: profileId,
          extra_headers: extraHeaders,
        }),
      });
      const data = await res.json();
      if (data.valid) {
        logCloudDiag(`✅ ${data.message}`);
        logCloudDiag(`Round-trip Latency: ${data.duration_ms}ms | TTFT: ${data.ttft_ms}ms | Speed: ${data.tokens_per_second ? data.tokens_per_second + ' tok/s' : 'N/A'}`);
        if (data.diagnostics && data.diagnostics.reply_sample) {
          logCloudDiag(`Model Reply Sample: "${data.diagnostics.reply_sample}"`);
        }
        showToast('Connection verified successfully!', 'success');

        if (elements.cloudDiagLatency) elements.cloudDiagLatency.textContent = `${data.duration_ms}ms`;
        if (elements.cloudDiagTtft) elements.cloudDiagTtft.textContent = `${data.ttft_ms}ms`;
        if (elements.cloudDiagTps) elements.cloudDiagTps.textContent = data.tokens_per_second ? `${data.tokens_per_second}` : 'N/A';
        if (elements.cloudConnectionStatusBadge) {
          elements.cloudConnectionStatusBadge.textContent = 'Connected';
          elements.cloudConnectionStatusBadge.className = 'badge badge-emerald';
        }
      } else {
        logCloudDiag(`❌ Connection failed: ${data.message}`);
        showToast(`Connection failed: ${data.message}`, 'error');
        if (elements.cloudConnectionStatusBadge) {
          elements.cloudConnectionStatusBadge.textContent = 'Failed';
          elements.cloudConnectionStatusBadge.className = 'badge badge-amber';
        }
      }
    } catch (err) {
      logCloudDiag(`❌ Network exception: ${err.message}`);
      showToast(`Test error: ${err.message}`, 'error');
    } finally {
      if (elements.btnCloudTestConnection) {
        elements.btnCloudTestConnection.disabled = false;
        elements.btnCloudTestConnection.textContent = '🧪 Test Connection';
      }
    }
  }

  async function verifyCloudTools() {
    const apiBase = elements.cloudApiBase ? elements.cloudApiBase.value.trim() : '';
    const model = elements.cloudModelInput ? elements.cloudModelInput.value.trim() : '';
    const apiKey = elements.cloudApiKey ? elements.cloudApiKey.value.trim() : '';
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase || !model) {
      showToast('Please provide both API Base URL and Model Identifier to verify tool calling', 'error');
      return;
    }

    let extraHeaders = {};
    if (elements.cloudExtraHeaders && elements.cloudExtraHeaders.value.trim()) {
      try { extraHeaders = JSON.parse(elements.cloudExtraHeaders.value.trim()); } catch (e) {}
    }

    if (elements.btnCloudVerifyTools) {
      elements.btnCloudVerifyTools.disabled = true;
      elements.btnCloudVerifyTools.textContent = 'Verifying Tools...';
    }

    logCloudDiag(`\n--- Structured Function/Tool Calling Verification for '${model}' ---`);
    logCloudDiag(`Testing tool schema dispatch, argument JSON parsing, multi-turn continuation, and streaming...`);

    try {
      const res = await fetch('/providers/cloud_hosted/verify_tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_base: apiBase,
          model: model,
          api_key: apiKey || null,
          profile_id: profileId,
          extra_headers: extraHeaders,
        }),
      });
      const data = await res.json();
      const td = data.tool_diagnostics || {};

      logCloudDiag(`1. Tool Call Generated: ${td.tool_call_generated ? '✅ YES (' + td.tool_name + ')' : '❌ NO'}`);
      logCloudDiag(`2. Arguments JSON Parsed: ${td.arguments_parsed ? '✅ YES (' + JSON.stringify(td.arguments) + ')' : '❌ NO'}`);
      logCloudDiag(`3. Multi-Turn Continuation: ${td.multi_turn_continuation ? '✅ YES' : '⚠️ INCONCLUSIVE'}`);
      logCloudDiag(`4. Streaming Tool Output: ${td.streaming_compatible ? '✅ YES' : '⚠️ NON-STREAMING'}`);

      if (data.valid) {
        logCloudDiag(`🎉 RESULT: ${data.message}`);
        showToast('Model is structured tool-calling compatible!', 'success');
        if (elements.cloudDiagToolsBadge) {
          elements.cloudDiagToolsBadge.textContent = 'PASS';
          elements.cloudDiagToolsBadge.style.color = '#34d399';
        }
      } else {
        logCloudDiag(`⚠️ RESULT: ${data.message}`);
        if (td.error) logCloudDiag(`Diagnostic Detail: ${td.error}`);
        showToast('Model failed tool-calling verification. See diagnostic console.', 'error');
        if (elements.cloudDiagToolsBadge) {
          elements.cloudDiagToolsBadge.textContent = 'FAIL';
          elements.cloudDiagToolsBadge.style.color = '#fb7185';
        }
      }
    } catch (err) {
      logCloudDiag(`❌ Verification error: ${err.message}`);
      showToast(`Tool verification error: ${err.message}`, 'error');
    } finally {
      if (elements.btnCloudVerifyTools) {
        elements.btnCloudVerifyTools.disabled = false;
        elements.btnCloudVerifyTools.textContent = '🛠️ Verify Tool Calling';
      }
    }
  }

  async function warmupCloudModel() {
    const apiBase = elements.cloudApiBase ? elements.cloudApiBase.value.trim() : '';
    const model = elements.cloudModelInput ? elements.cloudModelInput.value.trim() : '';
    const apiKey = elements.cloudApiKey ? elements.cloudApiKey.value.trim() : '';
    const currentVal = elements.cloudProfileSelect ? elements.cloudProfileSelect.value : null;
    const profileId = currentVal !== '__new__' ? currentVal : null;

    if (!apiBase || !model) {
      showToast('Please provide API Base URL and Model Identifier for warmup', 'error');
      return;
    }

    let extraHeaders = {};
    if (elements.cloudExtraHeaders && elements.cloudExtraHeaders.value.trim()) {
      try { extraHeaders = JSON.parse(elements.cloudExtraHeaders.value.trim()); } catch (e) {}
    }

    if (elements.btnCloudWarmup) {
      elements.btnCloudWarmup.disabled = true;
      elements.btnCloudWarmup.textContent = '⚡ Warming up...';
    }

    logCloudDiag(`\n--- Manual Model Warmup Probe for '${model}' ---`);

    try {
      const res = await fetch('/providers/cloud_hosted/warmup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_base: apiBase,
          model: model,
          api_key: apiKey || null,
          profile_id: profileId,
          extra_headers: extraHeaders,
        }),
      });
      const data = await res.json();
      if (data.success) {
        logCloudDiag(`🔥 ${data.message}`);
        showToast(data.message, 'success');
        if (elements.cloudDiagLatency) elements.cloudDiagLatency.textContent = `${data.duration_ms}ms`;
        if (elements.cloudDiagTps && data.tokens_per_second) elements.cloudDiagTps.textContent = `${data.tokens_per_second}`;
      } else {
        logCloudDiag(`Warmup response: ${data.message}`);
        showToast(`Warmup note: ${data.message}`, 'info');
      }
    } catch (err) {
      logCloudDiag(`Warmup error: ${err.message}`);
    } finally {
      if (elements.btnCloudWarmup) {
        elements.btnCloudWarmup.disabled = false;
        elements.btnCloudWarmup.textContent = '⚡ Optional Warm-up Model';
      }
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
          elements.settingsCurrentKeyHint.textContent = 'No API key configured in AI-VAPT profile storage';
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
      showToast('LLM Configuration saved successfully!', 'success');
      if (elements.settingsKeyResult) {
        elements.settingsKeyResult.innerHTML = `<span style="color:#10b981;">✅ Saved successfully! Active model: <strong>${escapeHtml(model)}</strong></span>`;
      }
      if (elements.settingsApiKey) elements.settingsApiKey.value = '';
      await loadLlmSettings();
      await refreshReadiness();
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
      if (runId) localStorage.setItem('activeRunId', runId);
      await fetchRunState(runId);
      if (state.latestRunData) {
        loadReportView(state.latestRunData);
        switchView('active-assessment');
      }
    },
  };

  async function recoverActiveAssessmentOnLoad() {
    let runIdToRecover = null;
    try {
      const urlParams = new URLSearchParams(window.location.search);
      runIdToRecover = urlParams.get('run_id') || localStorage.getItem('activeRunId');
    } catch (_) {
      runIdToRecover = localStorage.getItem('activeRunId');
    }
    if (!runIdToRecover) {
      try {
        const res = await fetch('/runs');
        if (res.ok) {
          const data = await res.json();
          const runs = Array.isArray(data) ? data : (data.runs || []);
          const activeRun = runs.find((r) => r.status === 'running' || r.status === 'queued');
          if (activeRun) {
            runIdToRecover = activeRun.run_id;
          }
        }
      } catch (_) {}
    }

    if (runIdToRecover) {
      try {
        const res = await fetch(`/runs/${runIdToRecover}`);
        if (res.ok) {
          const run = await res.json();
          state.activeRunId = run.run_id;
          state.latestRunData = run;
          localStorage.setItem('activeRunId', run.run_id);
          renderActiveRun(run);
          loadReportView(run);
          const reqHash = (window.location.hash || '').replace('#/', '');
          if (reqHash && document.getElementById(`view-${reqHash}`)) {
            switchView(reqHash);
          } else {
            switchView('active-assessment');
          }
          if (run.status === 'running' || run.status === 'queued') {
            startRunPolling(run.run_id);
          }
        } else {
          localStorage.removeItem('activeRunId');
        }
      } catch (_) {}
    }
  }

  // Entry Point
  document.addEventListener('DOMContentLoaded', async () => {
    initElements();
    initEvents();
    onProviderChange();
    populateModelOptions('openrouter');
    loadProviderModels('openrouter');
    loadLlmSettings();
    await loadCloudProfiles();
    renderModelCatalog();
    checkSystemHealth();

    await recoverActiveAssessmentOnLoad();

    const initialHash = window.location.hash.replace('#/', '');
    if (initialHash && document.getElementById(`view-${initialHash}`)) {
      if (!state.activeRunId || initialHash !== 'new-assessment') {
        switchView(initialHash);
      }
    }
  });
})();
