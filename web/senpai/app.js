(function() {
    'use strict';

    // ════════════════════════════════════════════════════════════
    // CONFIGURATION OBJECT (centralized magic numbers)
    // ════════════════════════════════════════════════════════════
    const CONFIG = Object.freeze({
        brain: {
            initialNodes: 1,
            initialConnections: 0,
            maxNodes: 3000,
            maxConnections: 8000,
            clusters: 6,
            ellipsoid: { a: 6.0, b: 4.1, c: 4.9 },
            growthUser: 1,
            growthAI: 0,
            connectionRadius: 1.5,
        },
        animation: {
            autoRotateSpeed: 0.08,
            scanInterval: 5,
        },
        ui: {
            tmTicks: 40,
            slidingWindow: 20,
            budgetAlerts: { warn: 0.8, critical: 0.95 },
            maxHistoryLength: 200, // auto-prune after this many messages
        },
        api: {
            timeout: 4000,
            maxRetries: 3,
        },
    });

    // ════════════════════════════════════════════════════════════
    // PROVIDER DEFAULTS (frozen)
    // ════════════════════════════════════════════════════════════
    const PROVIDER_DEFAULTS = Object.freeze({
        '9router': {
            baseUrl: 'http://localhost:20128/v1',
            needsKey: true,
            label: '9Router (local endpoint)',
            hint: "Your local 9Router instance — OpenAI-compatible /v1 API. Paste your API key below (it's encrypted before being stored locally). Only reachable from the machine actually running 9Router.",
            chatStyle: 'openai',
            supportsStream: true,
        },
        ollama: {
            baseUrl: 'http://localhost:11434',
            needsKey: false,
            label: 'Ollama (local LLM)',
            hint: "Ollama runs models entirely on your machine — no API key, no data leaves your network.",
            chatStyle: 'ollama-native',
            supportsStream: true,
        },
        lmstudio: {
            baseUrl: 'http://localhost:1234/v1',
            needsKey: false,
            label: 'LM Studio (local, OpenAI-compatible)',
            hint: "LM Studio exposes an OpenAI-compatible /v1 API on your machine. No key needed by default.",
            chatStyle: 'openai',
            supportsStream: true,
        },
        openrouter: {
            baseUrl: 'https://openrouter.ai/api/v1',
            needsKey: true,
            label: 'OpenRouter (cloud, any model)',
            hint: "OpenRouter proxies hundreds of models through one API key. Paste any model ID from openrouter.ai/models.",
            chatStyle: 'openai',
            supportsStream: true,
        },
        gemini: {
            baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
            needsKey: true,
            label: 'Google Gemini',
            hint: "Direct Gemini API access. Get a key at aistudio.google.com.",
            chatStyle: 'gemini',
            supportsStream: false,
        },
        custom: {
            baseUrl: '',
            needsKey: true,
            label: 'Custom OpenAI-compatible endpoint',
            hint: "Point at any server implementing the OpenAI /v1/chat/completions contract.",
            chatStyle: 'openai',
            supportsStream: true,
        },
    });

    const FALLBACK_MODEL_LISTS = {
        '9router': [
            'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free',
            'openrouter/nvidia/nemotron-3-super-120b-a12b:free',
            'openrouter/openai/gpt-oss-120b:free',
            'openrouter/google/gemma-4-31b-it:free',
            'openrouter/deepseek/deepseek-v4-flash',
            'openrouter/deepseek/deepseek-v4-pro',
            'cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast',
            'cf/@cf/meta/llama-3.1-70b-instruct-fp8-fast',
            'cf/@cf/moonshotai/kimi-k2.6',
            'cf/@cf/qwen/qwen2.5-coder-32b-instruct',
        ],
        ollama: ['llama3.3', 'llama3.2', 'llama3.1', 'qwen2.5', 'qwen2.5-coder', 'mistral', 'mixtral', 'phi3', 'gemma2',
            'deepseek-coder-v2', 'codellama'
        ],
        lmstudio: ['local-model'],
        openrouter: [
            'anthropic/claude-3.7-sonnet', 'anthropic/claude-3.5-sonnet', 'anthropic/claude-3.5-haiku',
            'openai/gpt-4o', 'openai/gpt-4o-mini', 'openai/o3-mini',
            'google/gemini-2.0-flash-exp', 'google/gemini-2.0-pro-exp',
            'meta-llama/llama-3.3-70b-instruct', 'mistralai/mixtral-8x22b-instruct',
            'deepseek/deepseek-chat', 'deepseek/deepseek-r1', 'qwen/qwen-2.5-72b-instruct',
        ],
        gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
        custom: ['default'],
    };

    // ════════════════════════════════════════════════════════════
    // DOM REFS
    // ════════════════════════════════════════════════════════════
    const brainSection = document.getElementById('brainSection');
    const hudOverlay = document.getElementById('hudOverlay');
    const chatPanel = document.getElementById('chatPanel');
    const messagesContainer = document.getElementById('messagesContainer');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const scrollBottomBtn = document.getElementById('scrollBottomBtn');
    const settingsOverlay = document.getElementById('settingsOverlay');
    const configBtn = document.getElementById('configBtn');
    const closeSettings = document.getElementById('closeSettings');
    const saveSettingsBtn = document.getElementById('saveSettings');
    const cancelSettingsBtn = document.getElementById('cancelSettings');
    const clearChatBtn = document.getElementById('clearChatBtn');

    const providerSelect = document.getElementById('providerSelect');
    const providerHint = document.getElementById('providerHint');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const toggleApiKey = document.getElementById('toggleApiKey');
    const baseUrlInput = document.getElementById('baseUrlInput');
    const baseUrlLabel = document.getElementById('baseUrlLabel');
    const baseUrlHint = document.getElementById('baseUrlHint');
    const apiKeyGroup = document.getElementById('apiKeyGroup');
    const baseUrlGroup = document.getElementById('baseUrlGroup');

    const modelSelect = document.getElementById('modelSelect');
    const refreshModelsBtn = document.getElementById('refreshModelsBtn');
    const modelFetchStatus = document.getElementById('modelFetchStatus');
    const customModelInput = document.getElementById('customModelInput');
    const addCustomModelBtn = document.getElementById('addCustomModelBtn');
    const priceInInput = document.getElementById('priceInInput');
    const priceOutInput = document.getElementById('priceOutInput');

    const tokenBudgetInput = document.getElementById('tokenBudgetInput');
    const contextWindowInput = document.getElementById('contextWindowInput');
    const estimateTokensCheckbox = document.getElementById('estimateTokensCheckbox');
    const slidingWindowInput = document.getElementById('slidingWindowInput');
    const resetTokenMeterBtn = document.getElementById('resetTokenMeterBtn');

    const systemPromptInput = document.getElementById('systemPromptInput');
    const tempSlider = document.getElementById('tempSlider');
    const tempDisplay = document.getElementById('tempDisplay');
    const maxTokensInput = document.getElementById('maxTokensInput');
    const topPInput = document.getElementById('topPInput');
    const freqPenaltyInput = document.getElementById('freqPenaltyInput');
    const presPenaltyInput = document.getElementById('presPenaltyInput');
    const voiceLangSelect = document.getElementById('voiceLangSelect');
    const voiceToggleBtn = document.getElementById('voiceToggleBtn');

    const micBtn = document.getElementById('micBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    const imagePreviewContainer = document.getElementById('imagePreviewContainer');
    const fileToast = document.getElementById('fileToast');
    const micStatusLabel = document.getElementById('micStatusLabel');

    const linkDot = document.getElementById('linkDot');
    const linkLabel = document.getElementById('linkLabel');
    const stateLabel = document.getElementById('stateLabel');
    const nodeCountDisplay = document.getElementById('nodeCountDisplay');
    const connCountDisplay = document.getElementById('connCountDisplay');
    const latencyDisplay = document.getElementById('latencyDisplay');
    const strengthDisplay = document.getElementById('strengthDisplay');
    const providerDisplay = document.getElementById('providerDisplay');
    const modelDisplay = document.getElementById('modelDisplay');

    const tmUsedTokens = document.getElementById('tmUsedTokens');
    const tmRemainingTokens = document.getElementById('tmRemainingTokens');
    const tmCost = document.getElementById('tmCost');
    const tmLastReq = document.getElementById('tmLastReq');
    const tmGauge = document.getElementById('tmGauge');

    const searchToggleBtn = document.getElementById('searchToggleBtn');
    const searchBar = document.getElementById('searchBar');
    const searchInput = document.getElementById('searchInput');
    const searchRegexToggle = document.getElementById('searchRegexToggle');
    const searchCount = document.getElementById('searchCount');
    const searchClose = document.getElementById('searchClose');
    const searchResultsPanel = document.getElementById('searchResultsPanel');
    const searchResultsList = document.getElementById('searchResultsList');
    const closeSearchResults = document.getElementById('closeSearchResults');

    const convListBtn = document.getElementById('convListBtn');
    const convList = document.getElementById('convList');
    const convListItems = document.getElementById('convListItems');
    const exportConvBtn = document.getElementById('exportConvBtn');
    const clearAllConvsBtn = document.getElementById('clearAllConvsBtn');
    const exportMdBtn = document.getElementById('exportMdBtn');

    const themeBtns = document.querySelectorAll('.theme-btn');

    const promptLibrarySelect = document.getElementById('promptLibrarySelect');
    const promptNameInput = document.getElementById('promptNameInput');
    const savePromptBtn = document.getElementById('savePromptBtn');
    const loadPromptBtn = document.getElementById('loadPromptBtn');
    const deletePromptBtn = document.getElementById('deletePromptBtn');

    // New DOM refs
    const headerModelSwitcher = document.getElementById('headerModelSwitcher');
    const zenToggleBtn = document.getElementById('zenToggleBtn');
    const tabBar = document.getElementById('tabBar');
    const tabAddBtn = document.getElementById('tabAddBtn');
    const pinnedArea = document.getElementById('pinnedArea');
    const pinnedMessagesList = document.getElementById('pinnedMessagesList');
    const commandPalette = document.getElementById('commandPalette');
    const cpInput = document.getElementById('cpInput');
    const cpResults = document.getElementById('cpResults');

    const stopSequencesInput = document.getElementById('stopSequencesInput');
    const seedInput = document.getElementById('seedInput');
    const responseFormatSelect = document.getElementById('responseFormatSelect');
    const useWebSocketCheckbox = document.getElementById('useWebSocketCheckbox');
    const factoryResetBtn = document.getElementById('factoryResetBtn');
    const exportProfileBtn = document.getElementById('exportProfileBtn');
    const importProfileBtn = document.getElementById('importProfileBtn');
    const importProfileInput = document.getElementById('importProfileInput');

    // ════════════════════════════════════════════════════════════
    // STATE OBJECT (unified)
    // ════════════════════════════════════════════════════════════
    const appState = {
        settings: {
            provider: '9router',
            apiKey: '',
            baseUrl: PROVIDER_DEFAULTS['9router'].baseUrl,
            model: 'openrouter/nvidia/nemotron-3-super-120b-a12b:free',
            systemPrompt: 'You are SenPai, an advanced AI debugging assistant with a living neural network interface. Respond concisely and precisely. Use markdown and code blocks when helpful. Be analytical and professional.',
            temperature: 0.8,
            maxTokens: 4096,
            topP: null,
            freqPenalty: null,
            presPenalty: null,
            voiceLang: 'en-US',
            ttsEnabled: false,
            priceIn: 0,
            priceOut: 0,
            tokenBudget: 128000,
            contextWindow: 128000,
            estimateTokens: true,
            slidingWindow: 20,
            theme: 'github-dark',
            promptLibrary: [], // array of {name, text}
            // Advanced
            stopSequences: [],
            seed: null,
            responseFormat: '',
            useWebSocket: false,
        },
        usage: {
            promptTokens: 0,
            completionTokens: 0,
            totalTokens: 0,
            cost: 0,
            lastReqTokens: 0,
            lastReqMs: 0,
        },
        chat: {
            history: [], // array of {role, text, images?, pinned?, feedback?, id?}
            allConversations: [], // saved conversations
            streaming: false,
            abortController: null,
            streamBuffer: '',
            currentStreamingWrapper: null,
            currentStreamingMsgDiv: null,
            pinnedMessages: [], // array of message indices or ids
        },
        ui: {
            searchActive: false,
            searchRegex: false,
            pendingImages: [],
            zenMode: false,
        },
        agent: {
            enabled: false,           // Agent Vibe master toggle (off by default)
            cotCollapsed: false,
            tools: {
                webSearch: false,
                codeRunner: false,
                fileExplorer: false,
            },
            mission: {
                active: false,
                goal: '',
                tasks: [],            // [{text, status: pending|active|done|error}]
                currentIndex: -1,
            },
            consciousness: 'idle',    // idle | thinking | speaking | agent-processing
        },
        brain: {
            mode: 'idle', // idle, thinking, speaking
            pulsePhase: 0,
            clusterIndex: 0,
            clusterTimer: 0,
            nodeCount: CONFIG.brain.initialNodes,
            connCount: CONFIG.brain.initialConnections,
        },
        three: {
            scene: null,
            camera: null,
            renderer: null,
            group: null,
            nodeMeshes: [],
            glowSprites: [],
            connectionGroups: [],
            nodeData: [],
            conns: [],
            clusterMap: [],
            orbitTheta: 0,
            orbitPhi: Math.PI / 2,
            orbitRadius: 19,
            isDragging: false,
            autoRotate: true,
            cinematicActive: false,
            autoRotateSpeed: CONFIG.animation.autoRotateSpeed,
            starParticles: null,
            starParticlesFar: null,
            glowTexture: null,
        },
        tabs: {
            activeTabId: null,
            tabs: [], // array of {id, name, history}
            nextId: 1,
        },
        feedback: {
            // Store feedback per message id: { thumbsUp, thumbsDown }
        },
        memory: {
            enabled: false,
            topics: {}, // { keyword: weight }
            mood: 'neutral', // positive | neutral | negative — heuristic only, never diagnostic
        },
        extras: {
            focusMode: false,
            councilProvider: '',
            councilApiKey: '',
            councilBaseUrl: '',
            tickerEnabled: false,
        },
        accessibility: {
            fontScale: 100,
            reducedMotion: false,
            highContrast: false,
            dyslexiaFont: false,
        },
        security: {
            localLockEnabled: false,
            localLockHash: '', // SHA-256 of passphrase, local-only gate — see Security settings tab hint
        },
        analytics: {
            messageTokens: [], // [{role, tokens, ts}]
            sessionStart: Date.now(),
        },
    };

    // ════════════════════════════════════════════════════════════
    // SANITIZATION — every AI/markdown string that reaches innerHTML
    // must pass through here first. marked.parse() alone happily
    // emits raw <script>/onerror=... markup if it appears in a
    // message (AI output, imported profile, pasted text), so we run
    // DOMPurify on top of it. Falls back to marked's own output only
    // if DOMPurify failed to load (never falls back to raw text).
    // ════════════════════════════════════════════════════════════
    function renderMarkdown(text) {
        const raw = marked.parse(text == null ? '' : String(text));
        if (typeof DOMPurify !== 'undefined') {
            return DOMPurify.sanitize(raw, { ADD_ATTR: ['target'] });
        }
        console.warn('DOMPurify unavailable — rendering markdown unsanitized.');
        return raw;
    }

    // ════════════════════════════════════════════════════════════
    // ENCRYPTION with Web Crypto API (SubtleCrypto)
    // ════════════════════════════════════════════════════════════
    // SECURITY FIX: the previous implementation generated an AES key
    // and exported its raw bytes into the *same* blob as the
    // ciphertext ("iv + key + encrypted"), then stored that whole
    // blob in localStorage. That means the "encryption" carried the
    // key right next to the lock — anyone reading localStorage (a
    // browser extension, a synced-storage backup, another script)
    // could decrypt the API key trivially. It protected against
    // nothing.
    //
    // Fix: generate the AES-GCM key ONCE as non-extractable
    // (extractable: false) and keep it only inside IndexedDB, which
    // can store live CryptoKey handles without ever exposing their
    // raw bytes to JavaScript. localStorage now only ever holds
    // iv + ciphertext. This doesn't stop an attacker who can run
    // arbitrary JS in the page (nothing client-side can fully
    // prevent that), but it does stop the much more common case of
    // someone reading/exfiltrating localStorage/backup data at rest
    // without executing the page's own script.
    const SENPAI_IDB_NAME = 'senpai_secure_store';
    const SENPAI_IDB_KEY_ID = 'apiKeyEncKey';
    let _senpaiCryptoKeyPromise = null;

    function openSenpaiIDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(SENPAI_IDB_NAME, 1);
            req.onupgradeneeded = () => {
                req.result.createObjectStore('keys');
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    async function getOrCreateCryptoKey() {
        if (_senpaiCryptoKeyPromise) return _senpaiCryptoKeyPromise;
        _senpaiCryptoKeyPromise = (async () => {
            const db = await openSenpaiIDB();
            const existing = await new Promise((resolve, reject) => {
                const tx = db.transaction('keys', 'readonly');
                const req = tx.objectStore('keys').get(SENPAI_IDB_KEY_ID);
                req.onsuccess = () => resolve(req.result || null);
                req.onerror = () => reject(req.error);
            });
            if (existing) return existing;
            // extractable:false — the raw bytes can never be read back
            // out by any code, ours or an attacker's; the key only
            // ever exists as an opaque handle usable for encrypt/decrypt.
            const key = await crypto.subtle.generateKey(
                { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
            );
            await new Promise((resolve, reject) => {
                const tx = db.transaction('keys', 'readwrite');
                tx.objectStore('keys').put(key, SENPAI_IDB_KEY_ID);
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error);
            });
            return key;
        })();
        return _senpaiCryptoKeyPromise;
    }

    async function encryptText(text) {
        if (!text) return '';
        try {
            const key = await getOrCreateCryptoKey();
            const data = new TextEncoder().encode(text);
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data);
            const combined = new Uint8Array(iv.length + encrypted.byteLength);
            combined.set(iv, 0);
            combined.set(new Uint8Array(encrypted), iv.length);
            return btoa(String.fromCharCode(...combined));
        } catch (err) {
            console.error('encryptText failed, refusing to store key in plaintext fallback:', err);
            return '';
        }
    }

    async function decryptText(enc) {
        if (!enc) return '';
        try {
            const key = await getOrCreateCryptoKey();
            const combined = Uint8Array.from(atob(enc), c => c.charCodeAt(0));
            const iv = combined.slice(0, 12);
            const ciphertext = combined.slice(12);
            const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
            return new TextDecoder().decode(decrypted);
        } catch (err) {
            console.error('decryptText failed (key may be from an old/incompatible format):', err);
            return '';
        }
    }

    // ════════════════════════════════════════════════════════════
    // LOAD / SAVE
    // ════════════════════════════════════════════════════════════
    async function loadSettings() {
        try {
            const s = JSON.parse(localStorage.getItem('senpai_neural_v1'));
            if (s) {
                if (s.apiKeyEncrypted) {
                    s.apiKey = await decryptText(s.apiKeyEncrypted);
                    delete s.apiKeyEncrypted;
                }
                Object.assign(appState.settings, s);
            }
        } catch (_) {}
        try {
            const u = JSON.parse(localStorage.getItem('senpai_neural_v1_usage'));
            if (u) Object.assign(appState.usage, u);
        } catch (_) {}
        try {
            const c = JSON.parse(localStorage.getItem('senpai_neural_v1_convs'));
            if (c && Array.isArray(c)) appState.chat.allConversations = c;
        } catch (_) {}
        try {
            const p = JSON.parse(localStorage.getItem('senpai_neural_v1_prompts'));
            if (p && Array.isArray(p)) appState.settings.promptLibrary = p;
        } catch (_) {}
        try {
            const t = JSON.parse(localStorage.getItem('senpai_neural_v1_tabs'));
            if (t && Array.isArray(t.tabs)) appState.tabs = t;
        } catch (_) {}
        try {
            const fb = JSON.parse(localStorage.getItem('senpai_neural_v1_feedback'));
            if (fb) appState.feedback = fb;
        } catch (_) {}
        try {
            const pinned = JSON.parse(localStorage.getItem('senpai_neural_v1_pinned'));
            if (pinned && Array.isArray(pinned)) appState.chat.pinnedMessages = pinned;
        } catch (_) {}
        applySettingsToUI();
        renderTokenGauge();
        updateTokenMeterText();
        loadTheme();
        renderConvList();
        renderPromptLibrary();
        renderTabs();
        renderPinnedMessages();
        updateHeaderModelSwitcher();
    }

    async function saveSettingsToStorage() {
        try {
            const s = { ...appState.settings };
            if (s.apiKey) {
                s.apiKeyEncrypted = await encryptText(s.apiKey);
                delete s.apiKey;
            } else {
                delete s.apiKeyEncrypted;
            }
            localStorage.setItem('senpai_neural_v1', JSON.stringify(s));
        } catch (_) {}
    }

    function saveUsageToStorage() {
        try { localStorage.setItem('senpai_neural_v1_usage', JSON.stringify(appState.usage)); } catch (_) {}
    }

    function saveConversations() {
        try { localStorage.setItem('senpai_neural_v1_convs', JSON.stringify(appState.chat.allConversations)); } catch (_) {}
    }

    function savePromptLibrary() {
        try { localStorage.setItem('senpai_neural_v1_prompts', JSON.stringify(appState.settings.promptLibrary)); } catch (_) {}
    }

    function saveTabs() {
        try { localStorage.setItem('senpai_neural_v1_tabs', JSON.stringify({ tabs: appState.tabs.tabs, activeTabId: appState.tabs.activeTabId, nextId: appState.tabs.nextId })); } catch (_) {}
    }

    function saveFeedback() {
        try { localStorage.setItem('senpai_neural_v1_feedback', JSON.stringify(appState.feedback)); } catch (_) {}
    }

    function savePinned() {
        try { localStorage.setItem('senpai_neural_v1_pinned', JSON.stringify(appState.chat.pinnedMessages)); } catch (_) {}
    }

    function saveMemory() {
        try { localStorage.setItem('senpai_neural_v1_memory', JSON.stringify(appState.memory)); } catch (_) {}
    }
    function loadMemory() {
        try {
            const raw = localStorage.getItem('senpai_neural_v1_memory');
            if (raw) Object.assign(appState.memory, JSON.parse(raw));
        } catch (_) {}
    }
    function saveExtras() {
        try { localStorage.setItem('senpai_neural_v1_extras', JSON.stringify(appState.extras)); } catch (_) {}
    }
    function loadExtras() {
        try {
            const raw = localStorage.getItem('senpai_neural_v1_extras');
            if (raw) Object.assign(appState.extras, JSON.parse(raw));
        } catch (_) {}
    }
    function saveAccessibility() {
        try { localStorage.setItem('senpai_neural_v1_a11y', JSON.stringify(appState.accessibility)); } catch (_) {}
    }
    function loadAccessibility() {
        try {
            const raw = localStorage.getItem('senpai_neural_v1_a11y');
            if (raw) Object.assign(appState.accessibility, JSON.parse(raw));
        } catch (_) {}
    }
    function saveSecurity() {
        try { localStorage.setItem('senpai_neural_v1_security', JSON.stringify(appState.security)); } catch (_) {}
    }
    function loadSecurity() {
        try {
            const raw = localStorage.getItem('senpai_neural_v1_security');
            if (raw) Object.assign(appState.security, JSON.parse(raw));
        } catch (_) {}
    }

    // ════════════════════════════════════════════════════════════
    // THEME
    // ════════════════════════════════════════════════════════════
    function applyTheme(themeName) {
        if (themeName === 'system') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            themeName = prefersDark ? 'github-dark' : 'github-light';
        }
        document.documentElement.setAttribute('data-theme', themeName);
        appState.settings.theme = themeName;
        themeBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === (themeName === 'github-dark' || themeName === 'github-light' ? 'system' : themeName) || btn.dataset.theme === themeName);
        });
        saveSettingsToStorage();
        updateConnectionStatus();
    }

    function loadTheme() {
        const saved = appState.settings.theme || 'github-dark';
        applyTheme(saved);
    }

    themeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            applyTheme(btn.dataset.theme);
        });
    });

    // Listen to system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (appState.settings.theme === 'system') {
            applyTheme('system');
        }
    });

    // ════════════════════════════════════════════════════════════
    // PROVIDER UI
    // ════════════════════════════════════════════════════════════
    function updateProviderUI() {
        const prov = providerSelect.value;
        const cfg = PROVIDER_DEFAULTS[prov];
        providerHint.textContent = cfg.hint;
        apiKeyGroup.style.display = cfg.needsKey ? 'block' : 'none';
        baseUrlGroup.style.display = (prov === 'ollama' || prov === 'lmstudio' || prov === 'custom') ? 'block' : 'none';
        const keyLabel = apiKeyGroup.querySelector('label');
        if (keyLabel) keyLabel.textContent = cfg.label.split(' ')[0] + ' API Key';
        baseUrlLabel.textContent = prov === 'custom' ? 'Endpoint Base URL' : 'Local Server URL';
        baseUrlHint.textContent = prov === 'ollama' ?
            'Default Ollama URL: http://localhost:11434' :
            prov === 'lmstudio' ?
            'Default LM Studio URL: http://localhost:1234/v1' :
            'Must implement POST {baseUrl}/chat/completions';
        if (!baseUrlInput.value || baseUrlInput.dataset.autofilled === '1') {
            baseUrlInput.value = cfg.baseUrl;
            baseUrlInput.dataset.autofilled = '1';
        }
        providerDisplay.textContent = cfg.label.split(' ')[0];
    }

    function updateConnectionStatus() {
        const prov = appState.settings.provider;
        const cfg = PROVIDER_DEFAULTS[prov];
        if (!cfg.needsKey) {
            linkDot.classList.remove('warning');
            linkLabel.textContent = prov.toUpperCase() + ': LOCAL';
            stateLabel.textContent = 'READY';
            return;
        }
        if (appState.settings.apiKey && appState.settings.apiKey.trim().length > 8) {
            linkDot.classList.remove('warning');
            linkLabel.textContent = 'NEURAL LINK: ACTIVE';
            stateLabel.textContent = 'READY';
        } else {
            linkDot.classList.add('warning');
            linkLabel.textContent = 'NO SIGNAL';
            stateLabel.textContent = 'API KEY REQUIRED';
        }
    }

    function updateVoiceToggleUI() {
        const icon = voiceToggleBtn.querySelector('use');
        if (appState.settings.ttsEnabled) {
            voiceToggleBtn.classList.add('active-btn');
            voiceToggleBtn.title = 'Text-to-speech: on';
            if (icon) icon.setAttribute('href', '#icon-volume');
        } else {
            voiceToggleBtn.classList.remove('active-btn');
            voiceToggleBtn.title = 'Text-to-speech: off';
            if (icon) icon.setAttribute('href', '#icon-volume-off');
        }
    }

    function populateModelSelect(models, selectElement) {
        const sel = selectElement || modelSelect;
        sel.innerHTML = '';
        const list = (models && models.length) ? models : ['(no models found)'];
        list.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            if (m === appState.settings.model) opt.selected = true;
            sel.appendChild(opt);
        });
        if (!list.includes(appState.settings.model) && appState.settings.model) {
            const opt = document.createElement('option');
            opt.value = appState.settings.model;
            opt.textContent = appState.settings.model + ' (current)';
            opt.selected = true;
            sel.insertBefore(opt, sel.firstChild);
        }
    }

    function updateHeaderModelSwitcher() {
        const currentModels = Array.from(modelSelect.options).map(o => o.value);
        populateModelSelect(currentModels.length ? currentModels : FALLBACK_MODEL_LISTS[appState.settings.provider] || [], headerModelSwitcher);
        headerModelSwitcher.value = appState.settings.model;
    }

    function applySettingsToUI() {
        providerSelect.value = appState.settings.provider;
        apiKeyInput.value = appState.settings.apiKey || '';
        baseUrlInput.value = appState.settings.baseUrl || PROVIDER_DEFAULTS[appState.settings.provider].baseUrl;
        systemPromptInput.value = appState.settings.systemPrompt || '';
        tempSlider.value = appState.settings.temperature ?? 0.8;
        tempDisplay.textContent = (appState.settings.temperature ?? 0.8).toFixed(2);
        maxTokensInput.value = appState.settings.maxTokens ?? 4096;
        topPInput.value = appState.settings.topP !== null && appState.settings.topP !== undefined ? appState.settings.topP : '';
        freqPenaltyInput.value = appState.settings.freqPenalty !== null && appState.settings.freqPenalty !== undefined ? appState.settings.freqPenalty : '';
        presPenaltyInput.value = appState.settings.presPenalty !== null && appState.settings.presPenalty !== undefined ? appState.settings.presPenalty : '';
        voiceLangSelect.value = appState.settings.voiceLang || 'en-US';
        priceInInput.value = appState.settings.priceIn ?? 0;
        priceOutInput.value = appState.settings.priceOut ?? 0;
        tokenBudgetInput.value = appState.settings.tokenBudget ?? 128000;
        contextWindowInput.value = appState.settings.contextWindow ?? 128000;
        estimateTokensCheckbox.checked = appState.settings.estimateTokens !== false;
        slidingWindowInput.value = appState.settings.slidingWindow ?? 20;
        updateVoiceToggleUI();
        updateConnectionStatus();
        updateProviderUI();
        populateModelSelect(FALLBACK_MODEL_LISTS[appState.settings.provider] || []);
        providerDisplay.textContent = PROVIDER_DEFAULTS[appState.settings.provider]?.label.split(' ')[0] || appState.settings.provider;
        modelDisplay.textContent = appState.settings.model || '—';
        renderPromptLibrary();

        // Advanced
        stopSequencesInput.value = (appState.settings.stopSequences || []).join(', ');
        seedInput.value = appState.settings.seed !== null ? appState.settings.seed : '';
        responseFormatSelect.value = appState.settings.responseFormat || '';
        useWebSocketCheckbox.checked = appState.settings.useWebSocket || false;
    }

    // ════════════════════════════════════════════════════════════
    // TOKEN METER
    // ════════════════════════════════════════════════════════════
    function renderTokenGauge() {
        tmGauge.innerHTML = '';
        for (let i = 0; i < CONFIG.ui.tmTicks; i++) {
            const t = document.createElement('div');
            t.className = 'tm-tick';
            tmGauge.appendChild(t);
        }
        paintTokenGauge();
    }

    function paintTokenGauge(justFilledIndex) {
        const budget = Math.max(1, appState.settings.tokenBudget || 128000);
        const ratio = Math.min(1, appState.usage.totalTokens / budget);
        const filledCount = Math.round(ratio * CONFIG.ui.tmTicks);
        const ticks = tmGauge.children;
        for (let i = 0; i < ticks.length; i++) {
            const tick = ticks[i];
            tick.classList.remove('filled', 'warn', 'crit', 'pulse');
            if (i < filledCount) {
                tick.classList.add('filled');
                if (ratio > CONFIG.ui.budgetAlerts.critical) tick.classList.add('crit');
                else if (ratio > CONFIG.ui.budgetAlerts.warn) tick.classList.add('warn');
            }
        }
        if (typeof justFilledIndex === 'number' && ticks[justFilledIndex]) {
            ticks[justFilledIndex].classList.add('pulse');
        }
        // Alerts
        if (ratio > CONFIG.ui.budgetAlerts.warn && ratio <= CONFIG.ui.budgetAlerts.critical) {
            showFileToast('⚠️ Token usage exceeded 80% of budget.', false);
            setTimeout(hideFileToast, 3000);
        } else if (ratio > CONFIG.ui.budgetAlerts.critical) {
            showFileToast('🔴 CRITICAL: Token usage exceeded 95% of budget!', true);
            setTimeout(hideFileToast, 4000);
        }
    }

    function updateTokenMeterText() {
        const budget = Math.max(0, appState.settings.tokenBudget || 0);
        const remaining = Math.max(0, budget - appState.usage.totalTokens);
        tmUsedTokens.textContent = appState.usage.totalTokens.toLocaleString();
        tmRemainingTokens.textContent = remaining.toLocaleString();
        tmCost.textContent = '$' + appState.usage.cost.toFixed(4);
        tmLastReq.textContent = `${appState.usage.lastReqTokens.toLocaleString()} tok / ${appState.usage.lastReqMs} ms`;
        paintTokenGauge(Math.round(Math.min(1, appState.usage.totalTokens / Math.max(1, budget)) * CONFIG.ui.tmTicks) - 1);
    }

    function recordUsage(promptTok, completionTok, latencyMs) {
        const pt = Math.max(0, Math.round(promptTok || 0));
        const ct = Math.max(0, Math.round(completionTok || 0));
        appState.usage.promptTokens += pt;
        appState.usage.completionTokens += ct;
        appState.usage.totalTokens += (pt + ct);
        const reqCost = (pt / 1e6) * (appState.settings.priceIn || 0) + (ct / 1e6) * (appState.settings.priceOut || 0);
        appState.usage.cost += reqCost;
        appState.usage.lastReqTokens = pt + ct;
        appState.usage.lastReqMs = Math.round(latencyMs || 0);
        saveUsageToStorage();
        updateTokenMeterText();
        recordAnalyticsPoint(pt, ct);
        return { promptTokens: pt, completionTokens: ct, cost: reqCost };
    }

    // ── Session Analytics (new feature) ──
    function recordAnalyticsPoint(promptTok, completionTok) {
        appState.analytics.messageTokens.push({ promptTok, completionTok, ts: Date.now() });
        if (appState.analytics.messageTokens.length > 200) appState.analytics.messageTokens.shift();
        if (document.getElementById('analyticsOverlay')?.classList.contains('open')) renderAnalytics();
    }
    function renderAnalytics() {
        const statsEl = document.getElementById('analyticsStats');
        const canvas = document.getElementById('analyticsCanvas');
        if (!statsEl || !canvas) return;
        const points = appState.analytics.messageTokens;
        const msgCount = points.length;
        const totalTok = points.reduce((s, p) => s + p.promptTok + p.completionTok, 0);
        const avgLatency = appState.usage.lastReqMs || 0;
        const minutesActive = Math.max(1, Math.round((Date.now() - appState.analytics.sessionStart) / 60000));
        statsEl.innerHTML = [
            ['Messages', msgCount],
            ['Total tokens', totalTok.toLocaleString()],
            ['Est. cost', '$' + (appState.usage.cost || 0).toFixed(4)],
            ['Last latency', avgLatency + ' ms'],
            ['Session length', minutesActive + ' min'],
        ].map(([label, value]) => `<div class="analytics-stat"><div class="as-value">${value}</div><div class="as-label">${label}</div></div>`).join('');

        const ctx = canvas.getContext('2d');
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        if (!points.length) {
            ctx.fillStyle = 'rgba(255,255,255,0.35)';
            ctx.font = '12px monospace';
            ctx.fillText('No requests yet this session.', 14, h / 2);
            return;
        }
        const recent = points.slice(-40);
        const maxVal = Math.max(1, ...recent.map(p => p.promptTok + p.completionTok));
        const barW = w / recent.length;
        recent.forEach((p, i) => {
            const total = p.promptTok + p.completionTok;
            const barH = (total / maxVal) * (h - 20);
            const x = i * barW + 2;
            const promptH = (p.promptTok / maxVal) * (h - 20);
            const completionH = barH - promptH;
            ctx.fillStyle = 'rgba(88,166,255,0.85)';
            ctx.fillRect(x, h - promptH - 4, barW - 4, promptH);
            ctx.fillStyle = 'rgba(255,179,71,0.85)';
            ctx.fillRect(x, h - barH - 4, barW - 4, completionH);
        });
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.font = '10px monospace';
        ctx.fillText('■ prompt', 8, 14);
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillText('■ completion', 70, 14);
    }
    function openAnalytics() {
        document.getElementById('analyticsOverlay').classList.add('open');
        renderAnalytics();
    }
    function closeAnalytics() {
        document.getElementById('analyticsOverlay').classList.remove('open');
    }

    // ── Local Memory & Mood (ported concept from Xpai, rebuilt as a disclosed heuristic) ──
    const STOPWORDS = new Set('the a an and or but if is are was were be been being to of in on at for with by from as this that these those i you he she it we they my your his her its our their me him her them not no do does did doing have has had can could will would should shall may might must about into over under again further then once here there when where why how all any both each few more most other some such only own same so than too very'.split(' '));
    function extractKeywords(text) {
        return (text.toLowerCase().match(/[a-z\u0600-\u06FF]{3,}/g) || [])
            .filter(w => !STOPWORDS.has(w));
    }
    const MOOD_POSITIVE = new Set(['thanks','great','awesome','love','good','nice','happy','excellent','perfect','amazing','glad']);
    const MOOD_NEGATIVE = new Set(['angry','sad','hate','bad','terrible','annoyed','frustrated','broken','worried','stressed','tired']);
    function updateMood(text) {
        const words = extractKeywords(text);
        let score = 0;
        words.forEach(w => { if (MOOD_POSITIVE.has(w)) score++; if (MOOD_NEGATIVE.has(w)) score--; });
        appState.memory.mood = score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral';
        document.querySelectorAll('.mood-badge').forEach(el => {
            el.textContent = appState.memory.mood;
            el.className = 'mood-badge mood-' + appState.memory.mood;
        });
    }
    function rememberFrom(text) {
        extractKeywords(text).forEach(w => {
            appState.memory.topics[w] = (appState.memory.topics[w] || 0) + 1;
        });
        // Keep the memory list from growing unbounded — trim to the top 60 by weight
        const entries = Object.entries(appState.memory.topics).sort((a, b) => b[1] - a[1]);
        if (entries.length > 60) appState.memory.topics = Object.fromEntries(entries.slice(0, 60));
        updateMood(text);
        saveMemory();
        renderMemoryList();
    }
    function renderMemoryList() {
        const entries = Object.entries(appState.memory.topics).sort((a, b) => b[1] - a[1]).slice(0, 40);
        const html = entries.length
            ? entries.map(([word, weight]) => `<div class="memory-chip"><span>${escapeHtmlLocal(word)}</span><span class="mc-weight">×${weight}</span><button class="mc-forget" data-word="${escapeHtmlLocal(word)}" title="Forget this">✕</button></div>`).join('')
            : '<div class="memory-empty">Nothing remembered yet — enable memory in Settings → Memory, then chat normally.</div>';
        ['memoryList', 'memoryPopoverList'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = html;
        });
        const countEl = document.getElementById('memoryCount');
        if (countEl) countEl.textContent = entries.length ? `(${entries.length})` : '';
        document.querySelectorAll('.mc-forget').forEach(btn => {
            btn.addEventListener('click', () => {
                delete appState.memory.topics[btn.dataset.word];
                saveMemory();
                renderMemoryList();
            });
        });
        document.querySelectorAll('.mood-badge').forEach(el => {
            el.textContent = appState.memory.mood;
            el.className = 'mood-badge mood-' + appState.memory.mood;
        });
    }
    function forgetAllMemory() {
        appState.memory.topics = {};
        appState.memory.mood = 'neutral';
        saveMemory();
        renderMemoryList();
        showFileToast('Memory cleared');
        setTimeout(hideFileToast, 1500);
    }

    // ── Focus Mode (ported from Xpai) ──
    function toggleFocusMode() {
        appState.extras.focusMode = !appState.extras.focusMode;
        document.body.classList.toggle('focus-mode', appState.extras.focusMode);
        document.getElementById('focusModeBtn')?.classList.toggle('active', appState.extras.focusMode);
        saveExtras();
    }

    // ── Council Mode (new feature — asks the main provider + a second configured
    //    provider the same prompt and shows both, reusing the existing streaming
    //    call functions so there is exactly one code path for "talk to a provider") ──
    function openCouncil() {
        document.getElementById('councilOverlay').classList.add('open');
        document.getElementById('councilColHeadA').textContent = `Main: ${appState.settings.provider} / ${appState.settings.model || 'default'}`;
        document.getElementById('councilColHeadB').textContent = appState.extras.councilProvider
            ? `Compare: ${appState.extras.councilProvider}`
            : 'Comparison provider not set';
        const lastUser = [...appState.chat.history].reverse().find(m => m.role === 'user');
        if (lastUser) document.getElementById('councilPromptInput').value = lastUser.text;
    }
    function closeCouncil() {
        document.getElementById('councilOverlay').classList.remove('open');
    }
    async function runCouncil() {
        const prompt = document.getElementById('councilPromptInput').value.trim();
        if (!prompt) return;
        const bodyA = document.getElementById('councilColBodyA');
        const bodyB = document.getElementById('councilColBodyB');
        bodyA.textContent = 'Thinking…';
        // Column A: reuse the app's normal, already-configured provider
        (async () => {
            try {
                if (appState.settings.provider === 'gemini') {
                    const r = await callGemini(prompt, []);
                    bodyA.textContent = r?.text || '(no response)';
                } else if (appState.settings.provider === 'ollama') {
                    await callOllamaStream(prompt, [], (chunk, full) => { bodyA.textContent = full; }, () => {}, (err) => { bodyA.textContent = 'Error: ' + err.message; });
                } else {
                    await callOpenAICompatibleStream(prompt, [], {}, (chunk, full) => { bodyA.textContent = full; }, () => {}, (err) => { bodyA.textContent = 'Error: ' + err.message; });
                }
            } catch (err) { bodyA.textContent = 'Error: ' + err.message; }
        })();
        // Column B: the comparison provider, if configured
        if (!appState.extras.councilProvider) {
            bodyB.textContent = 'Set a comparison provider in Settings → Extras first.';
            return;
        }
        bodyB.textContent = 'Thinking…';
        const altKey = appState.extras.councilApiKey || appState.settings.apiKey;
        const altBase = appState.extras.councilBaseUrl || appState.settings.baseUrl;
        try {
            if (appState.extras.councilProvider === 'gemini') {
                const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${encodeURIComponent(altKey)}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: prompt }] }] }),
                });
                const data = await res.json();
                bodyB.textContent = data?.candidates?.[0]?.content?.parts?.[0]?.text || ('Error: ' + (data?.error?.message || 'no response'));
            } else if (appState.extras.councilProvider === 'ollama') {
                const base = altBase || 'http://localhost:11434';
                const res = await fetch(`${base}/api/chat`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: appState.settings.ollamaModel || 'llama3', messages: [{ role: 'user', content: prompt }], stream: false }),
                });
                const data = await res.json();
                bodyB.textContent = data?.message?.content || 'Error: no response';
            } else {
                const res = await fetch(`${altBase || 'https://api.openai.com/v1'}/chat/completions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${altKey}` },
                    body: JSON.stringify({ model: appState.settings.model || 'gpt-4o-mini', messages: [{ role: 'user', content: prompt }] }),
                });
                const data = await res.json();
                bodyB.textContent = data?.choices?.[0]?.message?.content || ('Error: ' + (data?.error?.message || 'no response'));
            }
        } catch (err) {
            bodyB.textContent = 'Error: ' + err.message;
        }
    }

    // ── Accessibility (new feature) ──
    function applyAccessibility() {
        const a = appState.accessibility;
        document.documentElement.style.fontSize = a.fontScale + '%';
        document.body.style.zoom = (a.fontScale !== 100) ? (a.fontScale / 100) : ''; // Chromium/Safari convenience; Firefox falls back to the rem-based scale above
        document.body.classList.toggle('a11y-reduced-motion', !!a.reducedMotion);
        document.body.classList.toggle('a11y-high-contrast', !!a.highContrast);
        document.body.classList.toggle('a11y-dyslexia-font', !!a.dyslexiaFont);
    }

    // ── Local device lock (new feature — honest naming: this is NOT server auth) ──
    async function sha256Hex(text) {
        const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    function updateSecurityUI() {
        const setup = document.getElementById('securitySetupBlock');
        const remove = document.getElementById('securityRemoveBlock');
        if (!setup || !remove) return;
        const on = !!appState.security.localLockEnabled;
        setup.style.display = on ? 'none' : '';
        remove.style.display = on ? '' : 'none';
    }

    // ── Live price ticker (ported from Xpai — client-only demo, off by default) ──
    let tickerTimer = null;
    async function refreshTicker() {
        const el = document.getElementById('tickerContent');
        if (!el) return;
        try {
            const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true');
            const data = await res.json();
            const fmt = (c) => `${c.usd.toLocaleString(undefined, { maximumFractionDigits: 0 })} (${c.usd_24h_change >= 0 ? '▲' : '▼'}${Math.abs(c.usd_24h_change).toFixed(1)}%)`;
            el.textContent = `BTC $${fmt(data.bitcoin)}   ·   ETH $${fmt(data.ethereum)}`;
        } catch (_) {
            el.textContent = 'Price feed unavailable right now.';
        }
    }
    function setTickerEnabled(on) {
        appState.extras.tickerEnabled = on;
        document.getElementById('priceTicker')?.classList.toggle('visible', on);
        if (on) {
            refreshTicker();
            if (tickerTimer) clearInterval(tickerTimer);
            tickerTimer = setInterval(refreshTicker, 60000);
        } else if (tickerTimer) {
            clearInterval(tickerTimer);
            tickerTimer = null;
        }
        saveExtras();
    }

    // ── PWA — manifest + service worker + install hint (ported from Hermes) ──
    function setupPWAExtra() {
        try {
            const manifest = {
                name: 'SenPai Neural OS — Ultimate Edition',
                short_name: 'SenPai',
                description: 'Merged neural-OS chat interface: multi-provider LLM chat, agent tools, local memory, and more.',
                start_url: '.',
                display: 'standalone',
                background_color: '#05070d',
                theme_color: '#58a6ff',
                icons: [],
                orientation: 'portrait',
            };
            const blob = new Blob([JSON.stringify(manifest)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            let link = document.querySelector('link[rel="manifest"]');
            if (!link) { link = document.createElement('link'); link.rel = 'manifest'; document.head.appendChild(link); }
            link.href = url;

            if ('serviceWorker' in navigator) {
                const swCode = `self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
                    self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
                    self.addEventListener('fetch', e => { e.respondWith(fetch(e.request).catch(() => new Response('Offline', {status:503}))); });`;
                const swBlob = new Blob([swCode], { type: 'application/javascript' });
                const swUrl = URL.createObjectURL(swBlob);
                navigator.serviceWorker.register(swUrl, { scope: '.' }).catch(() => {});
            }
        } catch (_) { /* PWA setup is a progressive enhancement — never block the app on it */ }
    }

    function resetTokenMeter() {
        appState.usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0, cost: 0, lastReqTokens: 0, lastReqMs: 0 };
        saveUsageToStorage();
        updateTokenMeterText();
        showFileToast('Token counters reset');
        setTimeout(hideFileToast, 1500);
    }

    // ════════════════════════════════════════════════════════════
    // NEURAL DNA — 10 Neuron Archetypes (shape + color encode "type")
    // ════════════════════════════════════════════════════════════
    const DNA_TYPES = [
        { name: 'Sensory',    color: 0x00d4ff, geo: s => new THREE.SphereGeometry(s, 10, 10) },
        { name: 'Cognitive',  color: 0xffb347, geo: s => new THREE.IcosahedronGeometry(s, 0) },
        { name: 'Memory',     color: 0xa78bfa, geo: s => new THREE.OctahedronGeometry(s, 0) },
        { name: 'Logic',      color: 0x3fb950, geo: s => new THREE.TetrahedronGeometry(s, 0) },
        { name: 'Emotion',    color: 0xf87171, geo: s => new THREE.TorusGeometry(s * 0.7, s * 0.32, 8, 14) },
        { name: 'Insight',    color: 0xfbbf24, geo: s => new THREE.DodecahedronGeometry(s, 0) },
        { name: 'Language',   color: 0x38bdf8, geo: s => new THREE.ConeGeometry(s * 0.85, s * 1.6, 8) },
        { name: 'Creativity', color: 0xe879f9, geo: s => new THREE.TorusKnotGeometry(s * 0.55, s * 0.18, 40, 6) },
        { name: 'Action',     color: 0xa3e635, geo: s => new THREE.CylinderGeometry(s * 0.75, s * 0.75, s * 1.4, 8) },
        { name: 'Energy',     color: 0xfb923c, geo: s => new THREE.BoxGeometry(s * 1.3, s * 1.3, s * 1.3) },
    ];
    function dnaTypeForIndex(i) { return DNA_TYPES[((i % DNA_TYPES.length) + DNA_TYPES.length) % DNA_TYPES.length]; }
    function renderDnaLegend() {
        const list = document.getElementById('dnaLegendList');
        if (!list) return;
        list.innerHTML = DNA_TYPES.map(t => {
            const hex = '#' + t.color.toString(16).padStart(6, '0');
            return `<div class="dna-legend-item">
                <span class="dna-legend-swatch" style="background:${hex};--sw-glow:${hex}"></span>
                <span class="dna-legend-name">${t.name}</span>
            </div>`;
        }).join('');
    }

    // ════════════════════════════════════════════════════════════
    // SENPAI SOCIAL CTA — 3D logo orb (own tiny Three.js scene)
    // Independent renderer/scene bound to #ctaLogoCanvas so it costs
    // almost nothing and can't be affected by the main brain's state.
    // The logo cycles through the same 10 DNA colors as the brain —
    // ties the "follow us" moment back into the app's own visual
    // language instead of a generic footer icon.
    // ════════════════════════════════════════════════════════════
    function initSenpaiLogoOrb() {
        const canvas = document.getElementById('ctaLogoCanvas');
        if (!canvas || typeof THREE === 'undefined') return;

        const size = canvas.clientWidth || 58;
        const logoScene = new THREE.Scene();
        const logoCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 20);
        logoCamera.position.set(0, 0, 4.2);

        const logoRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
        logoRenderer.setSize(size, size, false);
        logoRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        logoScene.add(new THREE.AmbientLight(0xffffff, 0.5));
        const logoLight = new THREE.PointLight(0x00d4ff, 2, 12);
        logoLight.position.set(2, 2, 3);
        logoScene.add(logoLight);

        // Outer wireframe shell + inner glowing core — reads as a small "brain seed"
        const shellGeo = new THREE.IcosahedronGeometry(1.15, 1);
        const shellMat = new THREE.MeshBasicMaterial({ color: 0x00d4ff, wireframe: true, transparent: true, opacity: 0.55 });
        const shell = new THREE.Mesh(shellGeo, shellMat);
        logoScene.add(shell);

        const coreGeo = new THREE.IcosahedronGeometry(0.55, 1);
        const coreMat = new THREE.MeshStandardMaterial({ color: 0x00d4ff, emissive: 0x00d4ff, emissiveIntensity: 1.4, roughness: 0.2, metalness: 0.4 });
        const core = new THREE.Mesh(coreGeo, coreMat);
        logoScene.add(core);

        let dnaIdx = 0;
        let lastSwap = performance.now();

        function tick(now) {
            requestAnimationFrame(tick);
            shell.rotation.y += 0.008;
            shell.rotation.x += 0.003;
            core.rotation.y -= 0.012;
            core.rotation.x += 0.006;

            // Cycle DNA color every few seconds, matching the brain's palette
            if (now - lastSwap > 3200) {
                lastSwap = now;
                dnaIdx = (dnaIdx + 1) % DNA_TYPES.length;
                const c = DNA_TYPES[dnaIdx].color;
                shellMat.color.setHex(c);
                coreMat.color.setHex(c);
                coreMat.emissive.setHex(c);
                logoLight.color.setHex(c);
            }
            logoRenderer.render(logoScene, logoCamera);
        }
        requestAnimationFrame(tick);
    }

    function initSenpaiCta() {
        const orbBtn = document.getElementById('ctaOrbBtn');
        const panel = document.getElementById('ctaPanel');
        const dock = document.getElementById('senpaiCta');
        if (!orbBtn || !panel || !dock) return;

        orbBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            panel.classList.toggle('open');
        });
        document.addEventListener('click', (e) => {
            if (!dock.contains(e.target)) panel.classList.remove('open');
        });
        panel.querySelectorAll('.cta-link').forEach(link => {
            link.addEventListener('click', () => panel.classList.remove('open'));
        });
    }

    // ════════════════════════════════════════════════════════════
    // THREE.JS — COSMIC BRAIN (Fully Enhanced)
    // ════════════════════════════════════════════════════════════

    // ── Cosmic Variables ──
    let scene, camera, renderer;
    let cosmicGroup;
    let blackHoleCore, accretionDisk;
    let atomCloud;
    let neuronNodes = [];
    let dataRings = [];
    let cosmicLines = [];
    let starField;
    let pulseLines = []; // for line pulse animation

    const MAX_ATOMS = 3000;
    const SPIRAL_TURNS = 3; // how many turns in the spiral
    const LINE_PULSE_DURATION = 800; // ms

    // ── 1. Initialize the Cosmic Space ──
    function initThreeJS() {
        const container = brainSection;
        const w = container.clientWidth || window.innerWidth * 0.56;
        const h = container.clientHeight || window.innerHeight;

        // Scene Setup with Space Fog
        scene = new THREE.Scene();
        scene.background = new THREE.Color(0x050510);
        scene.fog = new THREE.FogExp2(0x050510, 0.003);

        camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 80);
        camera.position.set(0, 1.5, 14);
        camera.lookAt(0, 0, 0);

        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        renderer.setSize(w, h);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setClearColor(0x050510, 1);
        container.insertBefore(renderer.domElement, container.firstChild);

        cosmicGroup = new THREE.Group();
        scene.add(cosmicGroup);

        // 1.1 Create the Black Hole (Core)
        createBlackHole();

        // 1.2 Create Atom Cloud (Initial particles)
        createAtomCloud(MAX_ATOMS);

        // 1.3 Create Star Field Background
        createStarField();

        // 1.4 Add Lights
        const ambient = new THREE.AmbientLight(0x112244, 0.4);
        scene.add(ambient);
        const light = new THREE.PointLight(0x00d4ff, 1.5, 30);
        light.position.set(5, 5, 5);
        scene.add(light);

        // Initial Neuron (Seed) — brain starts at 1 neuron and grows as the user speaks
        for (let i = 0; i < CONFIG.brain.initialNodes; i++) {
            const pos = randomSpherePoint(1.5, 4.0);
            createNeuron(pos.x, pos.y, pos.z, 'seed', 'INIT', i);
        }

        appState.three.scene = scene;
        appState.three.camera = camera;
        appState.three.renderer = renderer;
        setupOrbitControls();
        animateCosmic();
    }

    // ── 2. The Black Hole ──
    function createBlackHole() {
        const geo = new THREE.SphereGeometry(0.6, 32, 32);
        const mat = new THREE.MeshBasicMaterial({ color: 0x000000 });
        blackHoleCore = new THREE.Mesh(geo, mat);
        cosmicGroup.add(blackHoleCore);

        // Accretion Disk
        const diskGeo = new THREE.RingGeometry(0.9, 1.8, 64);
        const diskMat = new THREE.MeshBasicMaterial({
            color: 0x00d4ff,
            transparent: true,
            opacity: 0.15,
            side: THREE.DoubleSide,
            blending: THREE.AdditiveBlending
        });
        accretionDisk = new THREE.Mesh(diskGeo, diskMat);
        accretionDisk.rotation.x = Math.PI / 3.5;
        accretionDisk.rotation.z = 0.2;
        cosmicGroup.add(accretionDisk);
    }

    // ── 3. Atom Cloud ──
    function createAtomCloud(count) {
        const geo = new THREE.BufferGeometry();
        const positions = new Float32Array(count * 3);
        const colors = new Float32Array(count * 3);

        for (let i = 0; i < count; i++) {
            const r = 1.8 + Math.random() * 8.0;
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            positions[i*3] = r * Math.sin(phi) * Math.cos(theta);
            positions[i*3+1] = r * Math.sin(phi) * Math.sin(theta) * 0.7;
            positions[i*3+2] = r * Math.cos(phi);

            // Color based on topic: blue for finance, purple for code, gold for general
            const col = new THREE.Color(0x00d4ff).lerp(new THREE.Color(0x8b5cf6), Math.random());
            colors[i*3] = col.r;
            colors[i*3+1] = col.g;
            colors[i*3+2] = col.b;
        }
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const mat = new THREE.PointsMaterial({
            size: 0.06,
            vertexColors: true,
            transparent: true,
            opacity: 0.5,
            blending: THREE.AdditiveBlending
        });
        atomCloud = new THREE.Points(geo, mat);
        cosmicGroup.add(atomCloud);
    }

    // ── 4. Create Star Field ──
    function createStarField() {
        const count = 1200;
        const pos = new Float32Array(count * 3);
        for (let i=0; i<count*3; i++) pos[i] = (Math.random() - 0.5) * 70;
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const mat = new THREE.PointsMaterial({
            color: 0x4488ff,
            size: 0.08,
            transparent: true,
            opacity: 0.3,
            blending: THREE.AdditiveBlending
        });
        starField = new THREE.Points(geo, mat);
        scene.add(starField);
    }

    // ── 5. Spiral Point Generation ──
    function getSpiralPosition(index, total) {
        // Create a spiral galaxy pattern
        const arm = index % 2; // two arms
        const armAngle = arm * Math.PI;
        const radius = 1.5 + (index / total) * 6.0; // grow outward
        const angle = index * 0.4 + armAngle + Math.sin(index * 0.1) * 0.3;
        const x = radius * Math.cos(angle);
        const z = radius * Math.sin(angle);
        const y = Math.sin(index * 0.2) * 0.8; // slight vertical undulation
        return { x, y, z };
    }

    // ── 6. Create Neuron ──
    function createNeuron(x, y, z, role, keyword, index) {
        const isAI = role === 'ai';
        const dna = dnaTypeForIndex(index);
        const color = dna.color;

        // Core — shape + color encode the neuron's "DNA type" (10 variants)
        const size = 0.12 + Math.random() * 0.08;
        const coreGeo = dna.geo(size);
        const coreMat = new THREE.MeshStandardMaterial({
            color: color,
            emissive: color,
            emissiveIntensity: 0.8
        });
        const core = new THREE.Mesh(coreGeo, coreMat);
        core.position.set(x, y, z);
        core.userData.role = role;
        core.userData.dnaType = dna.name;
        core.userData.basePos = new THREE.Vector3(x, y, z);
        core.userData.birthTime = performance.now();
        cosmicGroup.add(core);
        neuronNodes.push(core);

        // Data Ring — color indicates who spoke (user vs AI)
        const ringGeo = new THREE.TorusGeometry(0.22, 0.02, 12, 20);
        const ringMat = new THREE.MeshStandardMaterial({
            color: isAI ? 0xffd700 : 0xffffff,
            emissive: isAI ? 0xffd700 : 0x88bbff,
            emissiveIntensity: 0.4,
            transparent: true,
            opacity: 0.7
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.copy(core.position);
        ring.userData.rotationSpeed = 0.6 + Math.random() * 0.5;
        ring.userData.keyword = keyword;
        cosmicGroup.add(ring);
        dataRings.push(ring);

        // Data Sprite Label
        const labelSprite = createLabelSprite(keyword, '#' + color.toString(16).padStart(6, '0'));
        labelSprite.position.copy(core.position);
        labelSprite.position.y += 0.35;
        labelSprite.scale.set(0.5, 0.5, 1);
        cosmicGroup.add(labelSprite);
        core.userData.label = labelSprite;

        // Birth Animation (Explode from center)
        core.scale.set(0.01, 0.01, 0.01);
        ring.scale.set(0.01, 0.01, 0.01);
        labelSprite.scale.set(0.01, 0.01, 0.01);
        const targetPos = new THREE.Vector3(x, y, z);
        const startPos = new THREE.Vector3(0, 0, 0);
        animateBirth(core, ring, labelSprite, startPos, targetPos);

        // Connect to closest neighbors (and add pulse capability)
        connectToNeighbors(core, neuronNodes);
    }

    // ── 7. Birth Animation ──
    function animateBirth(core, ring, label, start, end) {
        const duration = 600;
        const startTime = performance.now();
        function frame() {
            const elapsed = performance.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3);
            
            core.position.lerpVectors(start, end, ease);
            ring.position.copy(core.position);
            label.position.copy(core.position);
            label.position.y += 0.35;

            const s = 0.01 + ease * 0.99;
            core.scale.set(s, s, s);
            ring.scale.set(s, s, s);
            label.scale.set(s*0.6, s*0.6, 1);
            
            if (progress < 1) requestAnimationFrame(frame);
            else {
                core.position.copy(end);
                ring.position.copy(end);
                label.position.copy(end);
                label.position.y += 0.35;
                core.scale.set(1,1,1);
                ring.scale.set(1,1,1);
                label.scale.set(0.5,0.5,1);
            }
        }
        frame();
    }

    // ── 8. Data Label Sprite ──
    function createLabelSprite(text, color) {
        const canvas = document.createElement('canvas');
        canvas.width = 256; canvas.height = 64;
        const ctx = canvas.getContext('2d');
        ctx.shadowColor = color; ctx.shadowBlur = 12;
        ctx.font = 'Bold 22px "JetBrains Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = color;
        ctx.fillText(text, 128, 32);
        const texture = new THREE.CanvasTexture(canvas);
        const mat = new THREE.SpriteMaterial({
            map: texture, transparent: true,
            depthTest: false, blending: THREE.AdditiveBlending
        });
        return new THREE.Sprite(mat);
    }

    // ── 9. Cosmic Connections with Pulse ──
    function connectToNeighbors(newNode, allNodes) {
        if (allNodes.length < 2) return;
        const distances = [];
        for (let i = 0; i < allNodes.length - 1; i++) {
            const d = newNode.position.distanceTo(allNodes[i].position);
            if (d < 4.5) distances.push({ idx: i, dist: d });
        }
        distances.sort((a,b) => a.dist - b.dist);
        const selected = distances.slice(0, 3);
        selected.forEach(t => {
            const p1 = newNode.position; const p2 = allNodes[t.idx].position;
            const pts = [p1.x, p1.y, p1.z, p2.x, p2.y, p2.z];
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
            const mat = new THREE.LineBasicMaterial({
                color: 0x88aaff, transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending
            });
            const line = new THREE.LineSegments(geo, mat);
            cosmicGroup.add(line);
            cosmicLines.push(line);

            // Store for pulse animation
            line.userData.pulse = { startTime: 0, active: false };
            pulseLines.push(line);
        });
    }

    // ── 10. Pulse Network (Idea 1) ──
    function triggerNetworkPulse() {
        const now = performance.now();
        pulseLines.forEach(line => {
            // Randomize pulse start time for wave effect
            line.userData.pulse.startTime = now + Math.random() * 300;
            line.userData.pulse.active = true;
        });
    }

    // ── 11. Ring Memory (Idea 3) ──
    function sendMemoryBeams() {
        // Randomly select a few rings and emit a beam toward black hole
        const numBeams = Math.min(3, dataRings.length);
        const selected = [];
        const indices = new Set();
        while (indices.size < numBeams) {
            const idx = Math.floor(Math.random() * dataRings.length);
            if (!indices.has(idx)) {
                indices.add(idx);
                selected.push(dataRings[idx]);
            }
        }
        selected.forEach(ring => {
            const start = ring.position.clone();
            const end = new THREE.Vector3(0, 0, 0);
            const beamMat = new THREE.LineBasicMaterial({
                color: 0x00d4ff,
                transparent: true,
                opacity: 0.8,
                blending: THREE.AdditiveBlending
            });
            const pts = [start.x, start.y, start.z, end.x, end.y, end.z];
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
            const beam = new THREE.LineSegments(geo, beamMat);
            cosmicGroup.add(beam);
            // Animate beam fade out
            const duration = 800;
            const startTime = performance.now();
            function fadeBeam() {
                const elapsed = performance.now() - startTime;
                const progress = elapsed / duration;
                if (progress < 1) {
                    beam.material.opacity = 0.8 * (1 - progress);
                    requestAnimationFrame(fadeBeam);
                } else {
                    cosmicGroup.remove(beam);
                    beam.geometry.dispose();
                    beam.material.dispose();
                }
            }
            fadeBeam();
        });
    }

    // ── 12. Grow Brain on Message ──
    // The brain starts at 1 neuron and gains exactly 1 new neuron each time the USER speaks.
    // AI replies animate the existing network (pulse + memory beams) without adding neurons.
    //
    // PERF FIX: CONFIG.brain.maxNodes/maxConnections were defined but never enforced,
    // which is exactly what caused "lag after long conversations" — the scene grew a new
    // mesh + ring + label + up to 3 line objects forever, with the animate loop walking
    // every one of them every frame. Past the cap we keep the *displayed* neuron count
    // climbing forever (so intelligence still visibly "grows"), but stop allocating new
    // GPU objects and instead recycle/flash an existing neuron — bounded cost, unbounded
    // feeling of growth.
    let logicalNeuronCount = CONFIG.brain.initialNodes;
    function growCosmicBrain(role, message) {
        const words = message.split(' ').filter(w => w.length > 3);
        const keyword = words.length > 0 ? words[0].toUpperCase() : 'DATA';
        const growth = role === 'user' ? CONFIG.brain.growthUser : CONFIG.brain.growthAI;
        const total = neuronNodes.length;

        for (let i = 0; i < growth; i++) {
            logicalNeuronCount++;
            if (total + i < CONFIG.brain.maxNodes && cosmicLines.length < CONFIG.brain.maxConnections) {
                const pos = getSpiralPosition(total + i, total + growth);
                createNeuron(pos.x, pos.y, pos.z, role, keyword, total + i);
            } else {
                // Cap reached: recycle a random existing neuron instead of growing the scene.
                recycleNeuron(keyword);
            }
        }

        // Update HUD — logical count always climbs, rendered count stays bounded.
        nodeCountDisplay.textContent = logicalNeuronCount.toLocaleString();
        connCountDisplay.textContent = cosmicLines.length.toLocaleString();

        // Trigger pulse network (Idea 1) — happens on every message, growth or not
        triggerNetworkPulse();

        // Send memory beams (Idea 3)
        setTimeout(sendMemoryBeams, 300);
    }

    // Recycle an existing neuron once we're at the render cap: reassign its DNA type/color
    // and give it a bright birth-like flash, so the network still visibly reacts without
    // ever exceeding CONFIG.brain.maxNodes meshes or CONFIG.brain.maxConnections lines.
    const flashingNeurons = [];
    function recycleNeuron(keyword) {
        if (neuronNodes.length === 0) return;
        const node = neuronNodes[Math.floor(Math.random() * neuronNodes.length)];
        const dna = dnaTypeForIndex(Math.floor(Math.random() * 10));
        node.material.color.setHex(dna.color);
        node.material.emissive.setHex(dna.color);
        node.material.emissiveIntensity = 3.5;
        node.userData.dnaType = dna.name;
        node.userData.flashUntil = performance.now() + 500;
        node.userData.flashBaseIntensity = 0.8;
        flashingNeurons.push(node);
        playCameraShot('quickPunch');
    }

    // Decay any recycled-neuron flashes back to baseline. Bounded to whatever is
    // currently flashing (a handful at a time), never the full neuron list.
    function updateFlashingNeurons(now) {
        for (let i = flashingNeurons.length - 1; i >= 0; i--) {
            const node = flashingNeurons[i];
            const remaining = node.userData.flashUntil - now;
            if (remaining <= 0) {
                node.material.emissiveIntensity = node.userData.flashBaseIntensity;
                flashingNeurons.splice(i, 1);
            } else {
                const t = remaining / 500;
                node.material.emissiveIntensity = node.userData.flashBaseIntensity + t * 2.7;
            }
        }
    }

    // ── 13. Random Sphere (for initial seeds) ──
    function randomSpherePoint(minR, maxR) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = minR + (maxR - minR) * Math.random();
        return { x: r * Math.sin(phi) * Math.cos(theta), y: r * Math.sin(phi) * Math.sin(theta), z: r * Math.cos(phi) };
    }

    // ── 14. Animation Loop ──
    function animateCosmic() {
        requestAnimationFrame(animateCosmic);
        const dt = 0.016;
        const time = performance.now() * 0.0005;

        // Rotate Atoms (Accretion)
        if (atomCloud) {
            atomCloud.rotation.y += 0.002;
            atomCloud.rotation.x = Math.sin(time) * 0.02;
        }
        // Rotate Data Rings
        dataRings.forEach((ring, i) => {
            ring.rotation.x += 0.02 * ring.userData.rotationSpeed;
            ring.rotation.y += 0.03 * ring.userData.rotationSpeed;
            ring.material.opacity = 0.5 + Math.sin(time * 2 + i) * 0.2;
        });
        // Rotate Black Hole Disk
        if (accretionDisk) {
            accretionDisk.rotation.y += 0.005;
        }

        // Pulse lines: animate dash offset or color
        const now = performance.now();
        pulseLines.forEach(line => {
            if (line.userData.pulse.active) {
                const elapsed = now - line.userData.pulse.startTime;
                if (elapsed < LINE_PULSE_DURATION) {
                    const progress = elapsed / LINE_PULSE_DURATION;
                    // Brighten and increase opacity
                    line.material.color.setHSL(0.6 - progress * 0.3, 1, 0.5 + progress * 0.5);
                    line.material.opacity = 0.2 + progress * 0.8;
                } else {
                    line.material.color.setHex(0x88aaff);
                    line.material.opacity = 0.15;
                    line.userData.pulse.active = false;
                }
            }
        });

        // Decay recycled-neuron flashes (see recycleNeuron/updateFlashingNeurons)
        updateFlashingNeurons(now);

        // Camera follow/rotate
        if (appState.three.autoRotate) appState.three.orbitTheta += 0.005;
        updateCamera();

        renderer.render(scene, camera);
    }

    // ── Orbit Controls (same as before) ──
    function setupOrbitControls() {
        const el = renderer.domElement;
        el.addEventListener('mousedown', e => {
            appState.three.isDragging = true;
            appState.three.autoRotate = false;
            appState.three.prevMouse = { x: e.clientX, y: e.clientY };
        });
        window.addEventListener('mousemove', e => {
            if (!appState.three.isDragging) return;
            appState.three.orbitTheta -= (e.clientX - appState.three.prevMouse.x) * 0.005;
            appState.three.orbitPhi -= (e.clientY - appState.three.prevMouse.y) * 0.005;
            appState.three.orbitPhi = Math.max(0.12, Math.min(Math.PI - 0.12, appState.three.orbitPhi));
            appState.three.prevMouse.x = e.clientX;
            appState.three.prevMouse.y = e.clientY;
        });
        window.addEventListener('mouseup', () => {
            if (!appState.three.isDragging) return;
            appState.three.isDragging = false;
            setTimeout(() => { if (!appState.three.isDragging) appState.three.autoRotate = true; }, 2500);
        });
        el.addEventListener('wheel', e => {
            e.preventDefault();
            appState.three.orbitRadius = Math.max(6, Math.min(45, appState.three.orbitRadius + e.deltaY * 0.02));
        }, { passive: false });
        el.addEventListener('touchstart', e => {
            if (e.touches.length !== 1) return;
            appState.three.isDragging = true;
            appState.three.autoRotate = false;
            appState.three.prevMouse = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        }, { passive: true });
        el.addEventListener('touchmove', e => {
            if (!appState.three.isDragging || e.touches.length !== 1) return;
            appState.three.orbitTheta -= (e.touches[0].clientX - appState.three.prevMouse.x) * 0.005;
            appState.three.orbitPhi -= (e.touches[0].clientY - appState.three.prevMouse.y) * 0.005;
            appState.three.orbitPhi = Math.max(0.12, Math.min(Math.PI - 0.12, appState.three.orbitPhi));
            appState.three.prevMouse.x = e.touches[0].clientX;
            appState.three.prevMouse.y = e.touches[0].clientY;
        }, { passive: true });
        el.addEventListener('touchend', () => {
            appState.three.isDragging = false;
            setTimeout(() => { if (!appState.three.isDragging) appState.three.autoRotate = true; }, 2500);
        });
    }

    function updateCamera() {
        const sp = Math.sin(appState.three.orbitPhi), cp = Math.cos(appState.three.orbitPhi);
        const st = Math.sin(appState.three.orbitTheta), ct = Math.cos(appState.three.orbitTheta);
        appState.three.camera.position.set(
            appState.three.orbitRadius * sp * ct,
            appState.three.orbitRadius * cp,
            appState.three.orbitRadius * sp * st
        );
        appState.three.camera.lookAt(0, 0, 0);
    }

    // ════════════════════════════════════════════════════════════
    // CINEMATIC CAMERA POOL
    // A small pool of reusable camera "shots". Each one nudges the
    // existing orbitTheta/orbitPhi/orbitRadius camera rig over time
    // with its own easing curve, then hands control back to the
    // ambient auto-rotate. Wired to the app's key steps:
    // user speaks → SenPai thinks → SenPai speaks → response settles,
    // plus one shot per mission sub-task and one for cap-recycled neurons.
    // ════════════════════════════════════════════════════════════
    const EASE = {
        outCubic:  t => 1 - Math.pow(1 - t, 3),
        outQuint:  t => 1 - Math.pow(1 - t, 5),
        inOutSine: t => -(Math.cos(Math.PI * t) - 1) / 2,
    };

    const CAMERA_SHOT_POOL = {
        // Punch in toward the newest neuron when the user speaks
        pushIn:      { dTheta:  0.28, dPhi: -0.10, radiusMul: 0.74, duration: 850,  ease: EASE.outCubic },
        // Slow contemplative orbit while SenPai is thinking
        orbitSweep:  { dTheta:  0.85, dPhi:  0.04, radiusMul: 1.04, duration: 2200, ease: EASE.inOutSine },
        // Low "hero" tilt as the response starts streaming in
        tiltHero:    { dTheta: -0.18, dPhi: -0.28, radiusMul: 0.92, duration: 1000, ease: EASE.outCubic },
        // Pull back to reveal the whole brain once a response completes
        pullReveal:  { dTheta: -0.50, dPhi:  0.18, radiusMul: 1.40, duration: 1500, ease: EASE.outQuint },
        // Wide drifting establishing shot — used between mission steps
        driftWide:   { dTheta:  0.55, dPhi: -0.05, radiusMul: 1.15, duration: 1800, ease: EASE.inOutSine },
        // Quick snap-punch-and-return, used when a neuron is recycled at the growth cap
        quickPunch:  { dTheta:  0.06, dPhi:  0.00, radiusMul: 0.97, duration: 220,  ease: EASE.outCubic, yoyo: true },
    };

    let cinematicRAF = null;
    function playCameraShot(name) {
        const shot = CAMERA_SHOT_POOL[name];
        if (!shot || !appState.three.renderer || appState.three.isDragging) return;
        if (cinematicRAF) cancelAnimationFrame(cinematicRAF);
        appState.three.autoRotate = false;
        appState.three.cinematicActive = true;

        const startTheta = appState.three.orbitTheta;
        const startPhi = appState.three.orbitPhi;
        const startRadius = appState.three.orbitRadius;
        const targetTheta = startTheta + shot.dTheta;
        const targetPhi = Math.max(0.12, Math.min(Math.PI - 0.12, startPhi + shot.dPhi));
        const targetRadius = Math.max(6, Math.min(45, startRadius * shot.radiusMul));

        runCameraTween(startTheta, startPhi, startRadius, targetTheta, targetPhi, targetRadius, shot.duration, shot.ease, () => {
            if (shot.yoyo) {
                // Snap back out for punchy, single-beat moves
                runCameraTween(targetTheta, targetPhi, targetRadius, startTheta, startPhi, startRadius, shot.duration * 0.8, shot.ease, finishCinematic);
            } else {
                finishCinematic();
            }
        });
    }

    function runCameraTween(fromTheta, fromPhi, fromRadius, toTheta, toPhi, toRadius, duration, ease, onDone) {
        const t0 = performance.now();
        function frame(now) {
            if (appState.three.isDragging) { appState.three.cinematicActive = false; cinematicRAF = null; return; }
            const p = Math.min((now - t0) / duration, 1);
            const e = ease(p);
            appState.three.orbitTheta = fromTheta + (toTheta - fromTheta) * e;
            appState.three.orbitPhi = fromPhi + (toPhi - fromPhi) * e;
            appState.three.orbitRadius = fromRadius + (toRadius - fromRadius) * e;
            if (p < 1) {
                cinematicRAF = requestAnimationFrame(frame);
            } else {
                cinematicRAF = null;
                onDone();
            }
        }
        cinematicRAF = requestAnimationFrame(frame);
    }

    function finishCinematic() {
        appState.three.cinematicActive = false;
        setTimeout(() => {
            if (!appState.three.isDragging && !appState.three.cinematicActive) appState.three.autoRotate = true;
        }, 400);
    }

    function onResize() {
        if (!renderer) return;
        const w = brainSection.clientWidth;
        const h = brainSection.clientHeight;
        renderer.setSize(w, h);
        camera.aspect = w / Math.max(h, 1);
        camera.updateProjectionMatrix();
    }
    window.addEventListener('resize', onResize);

    // ════════════════════════════════════════════════════════════
    // TTS
    // ════════════════════════════════════════════════════════════
    let currentUtterance = null;

    function speakText(text) {
        if (!appState.settings.ttsEnabled || !window.speechSynthesis) return;
        stopSpeaking();
        const clean = text.replace(/[*_~`#>|\[\]()]/g, '').replace(/\n+/g, '. ').trim();
        if (!clean) return;
        const utt = new SpeechSynthesisUtterance(clean);
        utt.lang = appState.settings.voiceLang || 'en-US';
        utt.rate = 0.95;
        utt.pitch = 1.0;
        utt.volume = 0.9;
        currentUtterance = utt;
        window.speechSynthesis.speak(utt);
    }

    function stopSpeaking() {
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        currentUtterance = null;
    }

    // ════════════════════════════════════════════════════════════
    // SPEECH RECOGNITION
    // ════════════════════════════════════════════════════════════
    let recognition = null;
    let isRecording = false;
    let finalTranscript = '';

    function initSpeechRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) { micBtn.style.display = 'none'; return; }
        recognition = new SR();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = appState.settings.voiceLang || 'en-US';
        recognition.onresult = ev => {
            let interim = '';
            for (let i = ev.resultIndex; i < ev.results.length; i++) {
                if (ev.results[i].isFinal) finalTranscript += ev.results[i][0].transcript + ' ';
                else interim += ev.results[i][0].transcript;
            }
            chatInput.value = finalTranscript + interim;
            autoResizeInput();
            chatInput.focus();
        };
        recognition.onerror = e => {
            console.error('Speech error:', e.error);
            stopRecording();
            if (e.error === 'not-allowed') showFileToast('Microphone access denied', true);
        };
        recognition.onend = () => {
            if (isRecording) { try { recognition.start(); } catch (_) { stopRecording(); } } else stopRecording();
        };
    }

    function startRecording() {
        if (!recognition) { initSpeechRecognition(); if (!recognition) return; }
        if (isRecording) return;
        finalTranscript = chatInput.value;
        isRecording = true;
        recognition.lang = appState.settings.voiceLang || 'en-US';
        try {
            recognition.start();
            micBtn.classList.add('recording-active');
            { const u = micBtn.querySelector('use'); if (u) u.setAttribute('href', '#icon-stop'); }
            micBtn.title = 'Stop voice input';
            micStatusLabel.style.display = 'flex';
            stateLabel.textContent = 'LISTENING...';
            showFileToast('Listening… speak now');
        } catch (_) { stopRecording(); }
    }

    function stopRecording() {
        isRecording = false;
        micBtn.classList.remove('recording-active');
        { const u = micBtn.querySelector('use'); if (u) u.setAttribute('href', '#icon-mic'); }
        micBtn.title = 'Voice input (Ctrl+M)';
        micStatusLabel.style.display = 'none';
        if (stateLabel.textContent === 'LISTENING...') stateLabel.textContent = 'READY';
        try { if (recognition) recognition.stop(); } catch (_) {}
        hideFileToast();
    }

    function toggleRecording() { isRecording ? stopRecording() : startRecording(); }

    // ════════════════════════════════════════════════════════════
    // FILE HANDLING
    // ════════════════════════════════════════════════════════════
    function handleFiles(files) {
        for (const file of files) {
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = e => {
                    const b64 = e.target.result.split(',')[1];
                    appState.ui.pendingImages.push({ mimeType: file.type, base64Data: b64, fileName: file.name });
                    renderImagePreviews();
                    showFileToast(`Image added: ${file.name}`);
                    setTimeout(hideFileToast, 2000);
                };
                reader.readAsDataURL(file);
            } else if (file.type.startsWith('text/') || /\.(txt|json|csv|xml|md|py|js|html|css|log|sh|yaml|yml|toml)$/i
                .test(file.name)) {
                const reader = new FileReader();
                reader.onload = e => {
                    const text = e.target.result;
                    const ext = file.name.split('.').pop();
                    const block =
                        `\n\nFile: ${file.name}\n\`\`\`${ext}\n${text.substring(0, 3000)}\n\`\`\`${text.length > 3000 ? '\n*(truncated)*' : ''}`;
                    chatInput.value = (chatInput.value + block).trim();
                    autoResizeInput();
                    chatInput.focus();
                    showFileToast(`File loaded: ${file.name}`);
                    setTimeout(hideFileToast, 2500);
                };
                reader.readAsText(file);
            } else {
                showFileToast(`Unsupported: ${file.name}`, true);
                setTimeout(hideFileToast, 2500);
            }
        }
    }

    function renderImagePreviews() {
        imagePreviewContainer.innerHTML = '';
        appState.ui.pendingImages.forEach((img, idx) => {
            const div = document.createElement('div');
            div.className = 'image-preview';
            div.innerHTML =
                `<img src="data:${img.mimeType};base64,${img.base64Data}" alt="${img.fileName}">
                         <button class="remove-img" data-index="${idx}">✕</button>`;
            imagePreviewContainer.appendChild(div);
        });
        imagePreviewContainer.querySelectorAll('.remove-img').forEach(btn => {
            btn.addEventListener('click', e => {
                appState.ui.pendingImages.splice(parseInt(e.target.dataset.index), 1);
                renderImagePreviews();
                if (!appState.ui.pendingImages.length) hideFileToast();
            });
        });
        if (appState.ui.pendingImages.length) showFileToast(`${appState.ui.pendingImages.length} image(s) ready`);
    }

    function clearPendingImages() {
        appState.ui.pendingImages = [];
        imagePreviewContainer.innerHTML = '';
        hideFileToast();
    }

    function showFileToast(msg, isError = false) {
        fileToast.textContent = msg;
        fileToast.className = 'file-toast show' + (isError ? ' error' : '');
    }

    function hideFileToast() { fileToast.className = 'file-toast'; }

    function autoResizeInput() {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
    }

    // ════════════════════════════════════════════════════════════
    // CHAT RENDERING (including code block buttons, feedback, pin, edit, delete, regenerate, continue)
    // ════════════════════════════════════════════════════════════
    let messageIdCounter = 0;

    function addMessage(role, text, opts = {}) {
        const { imageData = null, meta = null, doAnimate = false, isStreaming = false, id = null, pinned = false, feedback = null } = opts;
        const wrapper = document.createElement('div');
        wrapper.classList.add('message-wrapper', role === 'user' ? 'user-wrapper' : 'ai-wrapper');
        // Assign a unique id if not provided
        const msgId = id || 'msg_' + (++messageIdCounter);
        wrapper.dataset.msgId = msgId;

        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', role);
        msgDiv.setAttribute('dir', 'ltr');

        const appendMeta = () => {
            if (!meta) return;
            const md = document.createElement('div');
            md.className = 'message-meta';
            md.innerHTML =
                `<span class="mm-tok">${meta.tokens.toLocaleString()} tok</span><span class="mm-cost">$${meta.cost.toFixed(5)}</span><span class="mm-lat">${meta.latency} ms</span>`;
            wrapper.appendChild(md);
        };

        if (role === 'ai') {
            if (isStreaming) {
                msgDiv.innerHTML = '';
                wrapper.appendChild(msgDiv);
                const actions = document.createElement('div');
                actions.classList.add('message-actions');
                actions.style.opacity = '0';
                actions.innerHTML =
                    `<button class="msg-action-btn copy-btn">Copy</button>
                     <button class="msg-action-btn speak-btn">Speak</button>
                     <button class="msg-action-btn pin-btn">📌</button>
                     <button class="msg-action-btn regenerate-btn">↻ Regenerate</button>
                     <button class="msg-action-btn continue-btn">→ Continue</button>
                     <button class="msg-action-btn feedback-up">👍</button>
                     <button class="msg-action-btn feedback-down">👎</button>
                     <button class="msg-action-btn delete-btn">🗑</button>`;
                wrapper.appendChild(actions);
                messagesContainer.appendChild(wrapper);
                scrollToBottom();
                return { wrapper, msgDiv, actions, id: msgId };
            } else if (doAnimate && text.length > 0) {
                msgDiv.innerHTML = '';
                wrapper.appendChild(msgDiv);
                const actions = createActionButtons(msgId);
                wrapper.appendChild(actions);
                appendMeta();
                messagesContainer.appendChild(wrapper);
                scrollToBottom();
                typewriterEffect(msgDiv, text, () => {
                    setBrainState('idle');
                    setupMessageActions(wrapper, text, msgId);
                    // After render, add syntax highlighting and code buttons
                    setTimeout(() => addCodeBlockButtons(wrapper), 100);
                });
                if (appState.settings.ttsEnabled) setTimeout(() => speakText(text), 400);
            } else {
                msgDiv.innerHTML = renderMarkdown(text);
                wrapper.appendChild(msgDiv);
                const actions = createActionButtons(msgId);
                wrapper.appendChild(actions);
                appendMeta();
                messagesContainer.appendChild(wrapper);
                setupMessageActions(wrapper, text, msgId);
                if (appState.settings.ttsEnabled && text.length < 3000) speakText(text);
                setTimeout(() => addCodeBlockButtons(wrapper), 100);
            }
        } else {
            msgDiv.textContent = text;
            wrapper.appendChild(msgDiv);
            if (imageData && imageData.length) {
                const cont = document.createElement('div');
                cont.classList.add('image-preview-container');
                cont.style.justifyContent = 'flex-end';
                imageData.forEach(img => {
                    const el = document.createElement('div');
                    el.classList.add('image-preview');
                    el.innerHTML =
                        `<img src="data:${img.mimeType};base64,${img.base64Data}" alt="${img.fileName}">`;
                    cont.appendChild(el);
                });
                wrapper.appendChild(cont);
            }
            appendMeta();
            // Add actions for user messages (edit, delete)
            const actions = document.createElement('div');
            actions.classList.add('message-actions');
            actions.innerHTML =
                `<button class="msg-action-btn edit-btn">✎ Edit</button>
                 <button class="msg-action-btn delete-btn">🗑</button>`;
            wrapper.appendChild(actions);
            messagesContainer.appendChild(wrapper);
            setupUserMessageActions(wrapper, text, msgId);
        }
        scrollToBottom();
        return wrapper;
    }

    function createActionButtons(msgId) {
        const actions = document.createElement('div');
        actions.classList.add('message-actions');
        actions.innerHTML =
            `<button class="msg-action-btn copy-btn">Copy</button>
             <button class="msg-action-btn speak-btn">Speak</button>
             <button class="msg-action-btn pin-btn">📌</button>
             <button class="msg-action-btn regenerate-btn">↻ Regenerate</button>
             <button class="msg-action-btn continue-btn">→ Continue</button>
             <button class="msg-action-btn feedback-up">👍</button>
             <button class="msg-action-btn feedback-down">👎</button>
             <button class="msg-action-btn delete-btn">🗑</button>`;
        return actions;
    }

    function setupMessageActions(wrapper, text, msgId) {
        const copyBtn = wrapper.querySelector('.copy-btn');
        const speakBtn = wrapper.querySelector('.speak-btn');
        const pinBtn = wrapper.querySelector('.pin-btn');
        const regenerateBtn = wrapper.querySelector('.regenerate-btn');
        const continueBtn = wrapper.querySelector('.continue-btn');
        const feedbackUp = wrapper.querySelector('.feedback-up');
        const feedbackDown = wrapper.querySelector('.feedback-down');
        const deleteBtn = wrapper.querySelector('.delete-btn');

        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(text).then(() => {
                    copyBtn.textContent = 'Copied';
                    copyBtn.classList.add('copied');
                    setTimeout(() => { copyBtn.textContent = 'Copy';
                        copyBtn.classList.remove('copied'); }, 2000);
                }).catch(() => { copyBtn.textContent = 'Error';
                    setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500); });
            });
        }
        if (speakBtn) {
            speakBtn.addEventListener('click', () => {
                stopSpeaking();
                speakText(text);
                speakBtn.textContent = 'Speaking…';
                setTimeout(() => { speakBtn.textContent = 'Speak'; }, 3000);
            });
        }
        if (pinBtn) {
            pinBtn.addEventListener('click', () => {
                togglePin(msgId);
            });
            // Update pin button state
            if (appState.chat.pinnedMessages.includes(msgId)) {
                pinBtn.textContent = '📌 Pinned';
                pinBtn.classList.add('active-btn');
            } else {
                pinBtn.textContent = '📌';
                pinBtn.classList.remove('active-btn');
            }
        }
        if (regenerateBtn) {
            regenerateBtn.addEventListener('click', () => {
                regenerateMessage(msgId);
            });
        }
        if (continueBtn) {
            continueBtn.addEventListener('click', () => {
                continueMessage(msgId);
            });
        }
        if (feedbackUp) {
            feedbackUp.addEventListener('click', () => {
                setFeedback(msgId, 'up');
            });
        }
        if (feedbackDown) {
            feedbackDown.addEventListener('click', () => {
                setFeedback(msgId, 'down');
            });
        }
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                deleteMessage(msgId);
            });
        }

        // Load existing feedback
        if (appState.feedback[msgId]) {
            if (appState.feedback[msgId] === 'up') feedbackUp.classList.add('active-feedback');
            else if (appState.feedback[msgId] === 'down') feedbackDown.classList.add('active-feedback');
        }
    }

    function setupUserMessageActions(wrapper, text, msgId) {
        const editBtn = wrapper.querySelector('.edit-btn');
        const deleteBtn = wrapper.querySelector('.delete-btn');
        if (editBtn) {
            editBtn.addEventListener('click', () => {
                editUserMessage(msgId);
            });
        }
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                deleteMessage(msgId);
            });
        }
    }

    function addCodeBlockButtons(wrapper) {
        const preElements = wrapper.querySelectorAll('pre');
        preElements.forEach(pre => {
            // Add copy button
            const copyBtn = document.createElement('button');
            copyBtn.className = 'code-copy-btn';
            copyBtn.textContent = 'Copy';
            copyBtn.addEventListener('click', () => {
                const code = pre.querySelector('code')?.textContent || pre.textContent;
                navigator.clipboard.writeText(code).then(() => {
                    copyBtn.textContent = 'Copied!';
                    setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
                }).catch(() => {
                    copyBtn.textContent = 'Error';
                    setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
                });
            });
            pre.appendChild(copyBtn);

            // Add run button only if code is JavaScript
            const codeText = pre.querySelector('code')?.textContent || pre.textContent;
            if (codeText.trim().startsWith('javascript') || pre.querySelector('code')?.className?.includes('javascript')) {
                const runBtn = document.createElement('button');
                runBtn.className = 'code-run-btn';
                runBtn.textContent = '▶ Run';
                runBtn.addEventListener('click', () => {
                    runCode(pre, codeText);
                });
                pre.appendChild(runBtn);
            }
        });
        // Apply syntax highlighting
        if (window.hljs) {
            wrapper.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }
    }

    // ── Sandboxed code execution ──
    // Runs entirely inside a same-page <iframe sandbox="allow-scripts"> with NO
    // allow-same-origin — the frame gets a unique opaque origin and cannot reach this
    // page's DOM, cookies, or localStorage. We never eval()/new Function() in the main
    // page context. Messages back from the frame are matched by identity of
    // ev.source (not by event.origin string, since a sandboxed frame's origin is
    // always the literal "null" and isn't a useful discriminator on its own).
    let codeSandboxFrame = null;
    const sandboxPending = new Map();
    function ensureSandboxFrame() {
        if (codeSandboxFrame) return codeSandboxFrame;
        const frame = document.createElement('iframe');
        frame.id = 'codeSandboxFrame';
        frame.setAttribute('sandbox', 'allow-scripts');
        frame.style.cssText = 'display:none;width:0;height:0;border:0;position:absolute;';
        frame.title = 'sandboxed code runner';
        frame.srcdoc = `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><script>
            window.addEventListener('message', function(ev){
                var data = ev.data || {};
                if (data.type !== 'run') return;
                var logs = [];
                function fmt(a){ if (typeof a === 'string') return a; try { return JSON.stringify(a); } catch(e){ return String(a); } }
                var fakeConsole = {
                    log:   function(){ logs.push({level:'log',   text: Array.prototype.map.call(arguments, fmt).join(' ')}); },
                    error: function(){ logs.push({level:'error', text: Array.prototype.map.call(arguments, fmt).join(' ')}); },
                    warn:  function(){ logs.push({level:'warn',  text: Array.prototype.map.call(arguments, fmt).join(' ')}); }
                };
                var result, errMsg = null;
                try {
                    var fn = new Function('console', data.code);
                    result = fn(fakeConsole);
                } catch (err) {
                    errMsg = (err && err.message) ? err.message : String(err);
                }
                parent.postMessage({ type: 'run-result', id: data.id, logs: logs, result: (result === undefined ? undefined : fmt(result)), error: errMsg }, '*');
            });
        <\/script></body></html>`;
        document.body.appendChild(frame);
        codeSandboxFrame = frame;
        return frame;
    }
    window.addEventListener('message', (ev) => {
        if (!codeSandboxFrame || ev.source !== codeSandboxFrame.contentWindow) return;
        const data = ev.data || {};
        if (data.type !== 'run-result') return;
        const cb = sandboxPending.get(data.id);
        if (cb) { sandboxPending.delete(data.id); cb(data); }
    });
    function runInSandbox(code, callback) {
        const frame = ensureSandboxFrame();
        const id = 'sbx-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
        sandboxPending.set(id, callback);
        const send = () => { try { frame.contentWindow.postMessage({ type: 'run', id, code }, '*'); } catch (e) { callback({ error: 'Sandbox unavailable: ' + e.message, logs: [] }); } };
        if (frame.contentDocument && frame.contentDocument.readyState === 'complete' && frame.contentWindow) send();
        else frame.addEventListener('load', send, { once: true });
    }
    function runCode(pre, codeText) {
        // Remove language marker if present
        let code = codeText;
        if (code.startsWith('javascript')) code = code.slice(10).trim();
        // Create output container
        let outputDiv = pre.parentElement.querySelector('.code-output');
        if (!outputDiv) {
            outputDiv = document.createElement('div');
            outputDiv.className = 'code-output';
            pre.parentElement.insertBefore(outputDiv, pre.nextSibling);
        }
        outputDiv.textContent = 'Running in sandbox…';
        outputDiv.classList.remove('error');
        runInSandbox(code, (data) => {
            const lines = (data.logs || []).map(l => (l.level === 'error' ? 'ERR ' : l.level === 'warn' ? 'WARN ' : '') + l.text);
            if (data.error) {
                outputDiv.textContent = [...lines, 'Error: ' + data.error].join('\n');
                outputDiv.classList.add('error');
            } else {
                if (data.result !== undefined) lines.push('→ ' + data.result);
                outputDiv.textContent = lines.length ? lines.join('\n') : '(no output)';
                outputDiv.classList.remove('error');
            }
        });
    }

    // ── Pin / Unpin ──
    function togglePin(msgId) {
        const index = appState.chat.pinnedMessages.indexOf(msgId);
        if (index !== -1) {
            appState.chat.pinnedMessages.splice(index, 1);
        } else {
            appState.chat.pinnedMessages.push(msgId);
        }
        savePinned();
        renderPinnedMessages();
        // Update pin button in the message
        const wrapper = document.querySelector(`[data-msg-id="${msgId}"]`);
        if (wrapper) {
            const pinBtn = wrapper.querySelector('.pin-btn');
            if (pinBtn) {
                if (appState.chat.pinnedMessages.includes(msgId)) {
                    pinBtn.textContent = '📌 Pinned';
                    pinBtn.classList.add('active-btn');
                } else {
                    pinBtn.textContent = '📌';
                    pinBtn.classList.remove('active-btn');
                }
            }
        }
    }

    function renderPinnedMessages() {
        const list = pinnedMessagesList;
        const area = pinnedArea;
        if (appState.chat.pinnedMessages.length === 0) {
            area.classList.remove('visible');
            return;
        }
        area.classList.add('visible');
        list.innerHTML = '';
        appState.chat.pinnedMessages.forEach(msgId => {
            // Find message in history
            const msg = appState.chat.history.find(m => m.id === msgId);
            if (!msg) return;
            const div = document.createElement('div');
            div.className = 'pinned-message-item';
            const textPreview = msg.text ? msg.text.substring(0, 60) : '(empty)';
            div.innerHTML =
                `<span>${textPreview}</span>
                 <button class="unpin-btn" data-msgid="${msgId}">✕</button>`;
            div.querySelector('.unpin-btn').addEventListener('click', () => {
                togglePin(msgId);
            });
            list.appendChild(div);
        });
    }

    // ── Feedback ──
    function setFeedback(msgId, type) {
        if (appState.feedback[msgId] === type) {
            delete appState.feedback[msgId];
        } else {
            appState.feedback[msgId] = type;
        }
        saveFeedback();
        // Update UI
        const wrapper = document.querySelector(`[data-msg-id="${msgId}"]`);
        if (wrapper) {
            const up = wrapper.querySelector('.feedback-up');
            const down = wrapper.querySelector('.feedback-down');
            if (up) up.classList.toggle('active-feedback', appState.feedback[msgId] === 'up');
            if (down) down.classList.toggle('active-feedback', appState.feedback[msgId] === 'down');
        }
    }

    // ── Delete message ──
    function deleteMessage(msgId) {
        if (!confirm('Delete this message?')) return;
        const wrapper = document.querySelector(`[data-msg-id="${msgId}"]`);
        if (wrapper) wrapper.remove();
        // Remove from history
        const idx = appState.chat.history.findIndex(m => m.id === msgId);
        if (idx !== -1) appState.chat.history.splice(idx, 1);
        // Remove from pinned
        const pinIdx = appState.chat.pinnedMessages.indexOf(msgId);
        if (pinIdx !== -1) appState.chat.pinnedMessages.splice(pinIdx, 1);
        savePinned();
        renderPinnedMessages();
        // Remove feedback
        delete appState.feedback[msgId];
        saveFeedback();
        renderConvList();
    }

    // ── Edit user message ──
    function editUserMessage(msgId) {
        const wrapper = document.querySelector(`[data-msg-id="${msgId}"]`);
        if (!wrapper) return;
        const msgDiv = wrapper.querySelector('.message.user');
        if (!msgDiv) return;
        // Make editable
        msgDiv.contentEditable = true;
        msgDiv.classList.add('editable');
        msgDiv.focus();
        // Place caret at end
        const range = document.createRange();
        range.selectNodeContents(msgDiv);
        range.collapse(false);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);

        const saveEdit = () => {
            msgDiv.contentEditable = false;
            msgDiv.classList.remove('editable');
            const newText = msgDiv.textContent.trim();
            // Update history
            const msg = appState.chat.history.find(m => m.id === msgId);
            if (msg) {
                msg.text = newText;
                // Re-render conversation list
                renderConvList();
            }
        };
        // Save on blur or Enter key (but not shift+Enter)
        msgDiv.addEventListener('blur', saveEdit);
        msgDiv.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                msgDiv.blur();
            }
        });
    }

    // ── Regenerate ──
    function regenerateMessage(msgId) {
        // Find the message and the preceding user message
        const msgIdx = appState.chat.history.findIndex(m => m.id === msgId);
        if (msgIdx === -1) return;
        // Find previous user message
        let userMsgIdx = -1;
        for (let i = msgIdx - 1; i >= 0; i--) {
            if (appState.chat.history[i].role === 'user') {
                userMsgIdx = i;
                break;
            }
        }
        if (userMsgIdx === -1) {
            showFileToast('No user message to regenerate from.', true);
            setTimeout(hideFileToast, 2000);
            return;
        }
        // Remove all messages from after the user message up to and including this AI message
        const removeCount = msgIdx - userMsgIdx;
        const removed = appState.chat.history.splice(userMsgIdx + 1, removeCount);
        // Remove from UI
        const wrappers = messagesContainer.querySelectorAll(`.message-wrapper`);
        // Remove all wrappers after the user message
        let foundUser = false;
        wrappers.forEach(w => {
            const id = w.dataset.msgId;
            const msg = appState.chat.history.find(m => m.id === id);
            if (msg && msg.role === 'user' && id === appState.chat.history[userMsgIdx].id) {
                foundUser = true;
            } else if (foundUser) {
                w.remove();
            }
        });
        // Now send the user message again
        const userMsg = appState.chat.history[userMsgIdx];
        // Re-send the user message (we need to call sendMessage with the user's text)
        // But we need to set chatInput to that text and send
        chatInput.value = userMsg.text || '';
        if (userMsg.images && userMsg.images.length) {
            appState.ui.pendingImages = userMsg.images.map(img => ({ ...img }));
            renderImagePreviews();
        }
        // Clear the user message from history because sendMessage will add it again
        appState.chat.history.splice(userMsgIdx, 1);
        // Remove the user message from UI
        const userWrapper = messagesContainer.querySelector(`[data-msg-id="${userMsg.id}"]`);
        if (userWrapper) userWrapper.remove();
        // Now send
        sendMessage();
    }

    // ── Continue ──
    function continueMessage(msgId) {
        // Find the message and send a "continue" instruction
        const msg = appState.chat.history.find(m => m.id === msgId);
        if (!msg) return;
        // Add a user message "Continue" and send
        chatInput.value = 'Continue';
        sendMessage();
    }

    // ── Typewriter effect ──
    function typewriterEffect(element, fullText, onComplete) {
        let idx = 0;
        const chunk = 6,
            speed = 10;

        function tick() {
            idx += chunk;
            if (idx >= fullText.length) {
                element.innerHTML = renderMarkdown(fullText);
                scrollToBottom();
                if (onComplete) onComplete();
                return;
            }
            element.innerHTML = renderMarkdown(fullText.substring(0, idx));
            scrollToBottom();
            setTimeout(tick, speed);
        }
        tick();
    }

    function addTypingIndicator() {
        const el = document.createElement('div');
        el.classList.add('typing-indicator');
        el.id = 'typingIndicator';
        el.innerHTML = `<span>PROCESSING</span>
                    <svg class="waveform-svg" viewBox="0 0 28 18">
                        <rect class="bar" x="1"  y="7" width="3" height="4"  rx="1.5" fill="#58a6ff"/>
                        <rect class="bar" x="6"  y="4" width="3" height="10" rx="1.5" fill="#58a6ff"/>
                        <rect class="bar" x="11" y="1" width="3" height="16" rx="1.5" fill="#58a6ff"/>
                        <rect class="bar" x="16" y="4" width="3" height="10" rx="1.5" fill="#58a6ff"/>
                        <rect class="bar" x="21" y="7" width="3" height="4"  rx="1.5" fill="#58a6ff"/>
                    </svg>`;
        messagesContainer.appendChild(el);
        scrollToBottom();
        return el;
    }

    function removeTypingIndicator() { const el = document.getElementById('typingIndicator'); if (el) el.remove(); }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            updateScrollButton();
        });
    }

    function updateScrollButton() {
        const near = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 80;
        scrollBottomBtn.classList.toggle('visible', !near);
    }

    // ── Auto-prune history ──
    function pruneHistory() {
        const max = CONFIG.ui.maxHistoryLength;
        while (appState.chat.history.length > max) {
            const removed = appState.chat.history.shift();
            // Remove from UI
            const wrapper = messagesContainer.querySelector(`[data-msg-id="${removed.id}"]`);
            if (wrapper) wrapper.remove();
            // Remove from pinned
            const pinIdx = appState.chat.pinnedMessages.indexOf(removed.id);
            if (pinIdx !== -1) appState.chat.pinnedMessages.splice(pinIdx, 1);
            delete appState.feedback[removed.id];
        }
        savePinned();
        saveFeedback();
        renderPinnedMessages();
        renderConvList();
    }

    // ════════════════════════════════════════════════════════════
    // TABS MANAGEMENT
    // ════════════════════════════════════════════════════════════
    function renderTabs() {
        tabBar.innerHTML = '';
        appState.tabs.tabs.forEach(tab => {
            const div = document.createElement('div');
            div.className = 'tab-item' + (tab.id === appState.tabs.activeTabId ? ' active' : '');
            div.dataset.tabId = tab.id;
            div.innerHTML =
                `<span>${tab.name}</span>
                 <button class="tab-close" data-tabid="${tab.id}">✕</button>`;
            div.addEventListener('click', () => {
                if (div.classList.contains('active')) return;
                switchTab(tab.id);
            });
            div.querySelector('.tab-close').addEventListener('click', (e) => {
                e.stopPropagation();
                closeTab(tab.id);
            });
            tabBar.appendChild(div);
        });
        tabBar.appendChild(tabAddBtn);
        // Ensure add button is always at the end
    }

    function switchTab(tabId) {
        // Save current tab history
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        if (currentTab) {
            currentTab.history = appState.chat.history;
        }
        // Switch
        appState.tabs.activeTabId = tabId;
        const newTab = appState.tabs.tabs.find(t => t.id === tabId);
        if (newTab) {
            appState.chat.history = newTab.history || [];
        }
        // Clear UI and re-render
        messagesContainer.innerHTML = '';
        // Re-render history
        appState.chat.history.forEach(msg => {
            const role = msg.role === 'user' ? 'user' : 'ai';
            addMessage(role, msg.text || '', {
                imageData: msg.images || null,
                doAnimate: false,
                id: msg.id,
                pinned: appState.chat.pinnedMessages.includes(msg.id),
            });
        });
        renderTabs();
        renderPinnedMessages();
        saveTabs();
        setBrainState('idle');
    }

    function addTab(name) {
        const newTab = {
            id: appState.tabs.nextId++,
            name: name || 'Conversation ' + appState.tabs.tabs.length,
            history: [],
        };
        appState.tabs.tabs.push(newTab);
        switchTab(newTab.id);
        saveTabs();
    }

    function closeTab(tabId) {
        if (appState.tabs.tabs.length <= 1) {
            showFileToast('Cannot close the last tab.', true);
            setTimeout(hideFileToast, 2000);
            return;
        }
        const idx = appState.tabs.tabs.findIndex(t => t.id === tabId);
        if (idx === -1) return;
        appState.tabs.tabs.splice(idx, 1);
        if (appState.tabs.activeTabId === tabId) {
            // Switch to another tab
            const nextTab = appState.tabs.tabs[Math.min(idx, appState.tabs.tabs.length - 1)];
            switchTab(nextTab.id);
        } else {
            renderTabs();
        }
        saveTabs();
    }

    // ════════════════════════════════════════════════════════════
    // SEARCH (with regex support)
    // ════════════════════════════════════════════════════════════
    function performSearch(query) {
        if (!query.trim()) {
            searchResultsList.innerHTML = '';
            searchResultsPanel.classList.remove('active');
            searchCount.textContent = '';
            document.querySelectorAll('.message.highlight').forEach(el => el.classList.remove('highlight'));
            return;
        }
        let q;
        const useRegex = appState.ui.searchRegex;
        if (useRegex) {
            try {
                q = new RegExp(query, 'gi');
            } catch (_) {
                q = null;
            }
        } else {
            q = query.toLowerCase().trim();
        }
        const msgs = messagesContainer.querySelectorAll('.message-wrapper');
        const results = [];
        let count = 0;
        msgs.forEach(wrapper => {
            const msg = wrapper.querySelector('.message');
            if (!msg) return;
            const text = msg.textContent;
            let match;
            if (useRegex && q) {
                match = text.match(q);
                if (match) {
                    const preview = text.substring(Math.max(0, match.index - 30), Math.min(text.length, match.index + match[0].length + 30))
                        .replace(/\n/g, ' ');
                    results.push({
                        wrapper,
                        msg,
                        preview,
                        idx: match.index,
                    });
                    count++;
                    msg.classList.add('highlight');
                } else {
                    msg.classList.remove('highlight');
                }
            } else if (!useRegex) {
                const idx = text.toLowerCase().indexOf(q);
                if (idx !== -1) {
                    const preview = text.substring(Math.max(0, idx - 30), Math.min(text.length, idx + q.length + 30))
                        .replace(/\n/g, ' ');
                    results.push({
                        wrapper,
                        msg,
                        preview,
                        idx,
                    });
                    count++;
                    msg.classList.add('highlight');
                } else {
                    msg.classList.remove('highlight');
                }
            } else {
                msg.classList.remove('highlight');
            }
        });
        searchCount.textContent = count > 0 ? `${count} match${count > 1 ? 'es' : ''}` : 'No matches';
        if (count > 0) {
            searchResultsList.innerHTML = '';
            results.forEach((r, i) => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.innerHTML =
                    `<div>🔍 Match #${i+1}</div><div class="sr-preview">…${r.preview}…</div>`;
                div.addEventListener('click', () => {
                    r.wrapper.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    r.msg.style.border = '2px solid var(--accent-blue)';
                    setTimeout(() => { r.msg.style.border = ''; }, 3000);
                    searchResultsPanel.classList.remove('active');
                });
                searchResultsList.appendChild(div);
            });
            searchResultsPanel.classList.add('active');
        } else {
            searchResultsPanel.classList.remove('active');
        }
    }

    function toggleSearch() {
        appState.ui.searchActive = !appState.ui.searchActive;
        searchBar.classList.toggle('active', appState.ui.searchActive);
        if (appState.ui.searchActive) {
            searchInput.focus();
            performSearch(searchInput.value);
        } else {
            searchInput.value = '';
            searchCount.textContent = '';
            searchResultsPanel.classList.remove('active');
            document.querySelectorAll('.message.highlight').forEach(el => el.classList.remove('highlight'));
        }
    }

    // ════════════════════════════════════════════════════════════
    // CONVERSATION MANAGEMENT
    // ════════════════════════════════════════════════════════════
    function saveCurrentConversation() {
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        if (currentTab && currentTab.history.length === 0) return;
        const history = currentTab ? currentTab.history : appState.chat.history;
        if (history.length === 0) return;
        const conv = {
            id: Date.now(),
            date: new Date().toISOString(),
            title: history[0]?.text?.substring(0, 60) || 'Untitled',
            messages: JSON.parse(JSON.stringify(history)),
        };
        appState.chat.allConversations.push(conv);
        saveConversations();
        renderConvList();
    }

    function loadConversation(id) {
        const conv = appState.chat.allConversations.find(c => c.id === id);
        if (!conv) return;
        saveCurrentConversation();
        // Create a new tab for this conversation
        const tabName = conv.title.substring(0, 20);
        addTab(tabName);
        // Load messages into the new tab
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        if (currentTab) {
            currentTab.history = JSON.parse(JSON.stringify(conv.messages));
            // Clear UI and re-render
            messagesContainer.innerHTML = '';
            appState.chat.history = currentTab.history;
            appState.chat.history.forEach(msg => {
                const role = msg.role === 'user' ? 'user' : 'ai';
                addMessage(role, msg.text || '', {
                    imageData: msg.images || null,
                    doAnimate: false,
                    id: msg.id,
                    pinned: appState.chat.pinnedMessages.includes(msg.id),
                });
            });
            renderTabs();
            renderPinnedMessages();
            setBrainState('idle');
        }
        renderConvList();
    }

    function clearChatSilent() {
        stopSpeaking();
        if (appState.chat.abortController) {
            appState.chat.abortController.abort();
            appState.chat.abortController = null;
        }
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        if (currentTab) {
            currentTab.history = [];
        }
        appState.chat.history = [];
        appState.ui.pendingImages = [];
        imagePreviewContainer.innerHTML = '';
        hideFileToast();
        messagesContainer.innerHTML = '';
        setBrainState('idle');
        cancelBtn.style.display = 'none';
        appState.chat.streaming = false;
        renderTabs();
        renderPinnedMessages();
    }

    function renderConvList() {
        convListItems.innerHTML = '';
        if (appState.chat.allConversations.length === 0) {
            convListItems.innerHTML =
                '<div style="color:var(--text-dim);font-size:11px;padding:10px;">No saved conversations.</div>';
            return;
        }
        const sorted = [...appState.chat.allConversations].reverse();
        sorted.forEach(conv => {
            const div = document.createElement('div');
            div.className = 'conv-item';
            const date = new Date(conv.date);
            const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit',
                minute: '2-digit' });
            div.innerHTML =
                `<div style="font-weight:600;">${conv.title}</div><div class="conv-date">${dateStr}</div>`;
            div.addEventListener('click', () => {
                convList.classList.remove('open');
                loadConversation(conv.id);
            });
            convListItems.appendChild(div);
        });
    }

    function exportConversation() {
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        const history = currentTab ? currentTab.history : appState.chat.history;
        if (history.length === 0) {
            showFileToast('No conversation to export', true);
            setTimeout(hideFileToast, 2000);
            return;
        }
        const data = {
            version: '8.0',
            date: new Date().toISOString(),
            settings: { ...appState.settings },
            messages: history,
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `jarvis-conv-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showFileToast('Conversation exported');
        setTimeout(hideFileToast, 2000);
    }

    function exportMarkdown() {
        const currentTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
        const history = currentTab ? currentTab.history : appState.chat.history;
        if (history.length === 0) {
            showFileToast('No conversation to export', true);
            setTimeout(hideFileToast, 2000);
            return;
        }
        let md = `# SenPai Conversation Export\n\n**Date:** ${new Date().toISOString()}\n**Model:** ${appState.settings.model}\n**Provider:** ${appState.settings.provider}\n\n---\n\n`;
        history.forEach(msg => {
            const role = msg.role === 'user' ? '**User**' : '**SenPai**';
            md += `${role}:\n\n${msg.text || ''}\n\n---\n\n`;
        });
        const blob = new Blob([md], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `jarvis-conv-${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(url);
        showFileToast('Markdown exported');
        setTimeout(hideFileToast, 2000);
    }

    // ════════════════════════════════════════════════════════════
    // PROMPT LIBRARY
    // ════════════════════════════════════════════════════════════
    function renderPromptLibrary() {
        const sel = promptLibrarySelect;
        sel.innerHTML = '<option value="">-- Select a saved prompt --</option>';
        appState.settings.promptLibrary.forEach((p, idx) => {
            const opt = document.createElement('option');
            opt.value = idx;
            opt.textContent = p.name;
            sel.appendChild(opt);
        });
    }

    function saveCurrentPrompt() {
        const name = promptNameInput.value.trim();
        if (!name) { showFileToast('Please enter a name for the prompt.', true);
            setTimeout(hideFileToast, 2000); return; }
        const text = systemPromptInput.value.trim();
        if (!text) { showFileToast('System prompt is empty.', true);
            setTimeout(hideFileToast, 2000); return; }
        const existing = appState.settings.promptLibrary.findIndex(p => p.name === name);
        if (existing !== -1) {
            appState.settings.promptLibrary[existing].text = text;
        } else {
            appState.settings.promptLibrary.push({ name, text });
        }
        savePromptLibrary();
        renderPromptLibrary();
        showFileToast(`Prompt "${name}" saved.`);
        setTimeout(hideFileToast, 2000);
    }

    function loadSelectedPrompt() {
        const idx = parseInt(promptLibrarySelect.value);
        if (isNaN(idx) || idx < 0 || idx >= appState.settings.promptLibrary.length) return;
        const p = appState.settings.promptLibrary[idx];
        systemPromptInput.value = p.text;
        showFileToast(`Loaded prompt: "${p.name}"`);
        setTimeout(hideFileToast, 1500);
    }

    function deleteSelectedPrompt() {
        const idx = parseInt(promptLibrarySelect.value);
        if (isNaN(idx) || idx < 0 || idx >= appState.settings.promptLibrary.length) return;
        const name = appState.settings.promptLibrary[idx].name;
        if (!confirm(`Delete prompt "${name}"?`)) return;
        appState.settings.promptLibrary.splice(idx, 1);
        savePromptLibrary();
        renderPromptLibrary();
        showFileToast(`Prompt "${name}" deleted.`);
        setTimeout(hideFileToast, 1500);
    }

    // ════════════════════════════════════════════════════════════
    // COMMAND PALETTE
    // ════════════════════════════════════════════════════════════
    const commands = [
        { name: 'clear', description: 'Clear chat', action: () => { clearChat(); } },
        { name: 'export', description: 'Export conversation as JSON', action: exportConversation },
        { name: 'export md', description: 'Export conversation as Markdown', action: exportMarkdown },
        { name: 'model', description: 'Switch model (e.g. /model gpt-4)', action: (arg) => { if (arg) { appState.settings.model = arg;
                modelDisplay.textContent = arg;
                updateHeaderModelSwitcher();
                saveSettingsToStorage(); } } },
        { name: 'theme', description: 'Change theme (e.g. /theme dracula)', action: (arg) => { if (arg) { applyTheme(arg); } } },
        { name: 'reset tokens', description: 'Reset token counter', action: resetTokenMeter },
        { name: 'save conv', description: 'Save current conversation', action: saveCurrentConversation },
    ];

    function openCommandPalette() {
        commandPalette.classList.add('active');
        cpInput.value = '';
        cpResults.innerHTML = '';
        cpInput.focus();
    }

    function closeCommandPalette() {
        commandPalette.classList.remove('active');
    }

    function filterCommands(query) {
        const q = query.toLowerCase().trim();
        return commands.filter(cmd => cmd.name.includes(q) || cmd.description.toLowerCase().includes(q));
    }

    function renderCommandResults(results) {
        cpResults.innerHTML = '';
        results.forEach((cmd, idx) => {
            const div = document.createElement('div');
            div.className = 'cp-result' + (idx === 0 ? ' selected' : '');
            div.innerHTML = `<span class="cmd-name">/${cmd.name}</span> — ${cmd.description}`;
            div.addEventListener('click', () => {
                executeCommand(cmd);
            });
            cpResults.appendChild(div);
        });
    }

    function executeCommand(cmd, arg) {
        closeCommandPalette();
        if (cmd.action) {
            cmd.action(arg);
        }
    }

    cpInput.addEventListener('input', () => {
        const results = filterCommands(cpInput.value);
        renderCommandResults(results);
    });
    cpInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const selected = cpResults.querySelector('.selected');
            if (selected) {
                const cmdName = selected.querySelector('.cmd-name').textContent.replace('/', '');
                const cmd = commands.find(c => c.name === cmdName);
                if (cmd) {
                    const args = cpInput.value.trim().split(/\s+/);
                    const arg = args.length > 1 ? args.slice(1).join(' ') : null;
                    executeCommand(cmd, arg);
                }
            }
        } else if (e.key === 'Escape') {
            closeCommandPalette();
        } else if (e.key === 'ArrowDown') {
            const selected = cpResults.querySelector('.selected');
            if (selected) {
                selected.classList.remove('selected');
                const next = selected.nextElementSibling;
                if (next) next.classList.add('selected');
            }
        } else if (e.key === 'ArrowUp') {
            const selected = cpResults.querySelector('.selected');
            if (selected) {
                selected.classList.remove('selected');
                const prev = selected.previousElementSibling;
                if (prev) prev.classList.add('selected');
            }
        }
    });

    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            openCommandPalette();
        }
        if (e.key === 'Escape') {
            closeCommandPalette();
        }
    });

    // ════════════════════════════════════════════════════════════
    // API CALLS (with streaming, WebSocket support, and advanced params)
    // ════════════════════════════════════════════════════════════
    function buildOpenAIMessages(userText, imageParts) {
        const messages = [{ role: 'system', content: appState.settings.systemPrompt }];
        const maxContext = appState.settings.slidingWindow || 20;
        const contextEntries = appState.chat.history.slice(-maxContext);
        for (const entry of contextEntries) {
            const role = entry.role === 'user' ? 'user' : 'assistant';
            if (entry.role === 'user' && entry.images && entry.images.length) {
                const parts = [{ type: 'text', text: entry.text || '' }];
                entry.images.forEach(img => parts.push({ type: 'image_url', image_url: { url: `data:${img.mimeType};base64,${img.base64Data}` } }));
                messages.push({ role, content: parts });
            } else {
                messages.push({ role, content: entry.text || '' });
            }
        }
        if (imageParts && imageParts.length) {
            const parts = [{ type: 'text', text: userText || 'Describe this image.' }];
            imageParts.forEach(img => parts.push({ type: 'image_url', image_url: { url: `data:${img.mimeType};base64,${img.base64Data}` } }));
            messages.push({ role: 'user', content: parts });
        } else {
            messages.push({ role: 'user', content: userText || '' });
        }
        return messages;
    }

    async function callOpenAICompatibleStream(userText, imageParts, opts, onChunk, onComplete, onError) {
        const { baseUrl, apiKey, model } = opts;
        const url = baseUrl.replace(/\/$/, '') + '/chat/completions';
        const messages = buildOpenAIMessages(userText, imageParts);
        const body = {
            model,
            messages,
            temperature: appState.settings.temperature,
            max_tokens: appState.settings.maxTokens || 4096,
            stream: true,
        };
        if (appState.settings.topP !== null && appState.settings.topP !== undefined && appState.settings.topP !== '') body.top_p = parseFloat(
            appState.settings.topP);
        if (appState.settings.freqPenalty !== null && appState.settings.freqPenalty !== undefined && appState.settings.freqPenalty !== '')
            body.frequency_penalty = parseFloat(appState.settings.freqPenalty);
        if (appState.settings.presPenalty !== null && appState.settings.presPenalty !== undefined && appState.settings.presPenalty !== '')
            body.presence_penalty = parseFloat(appState.settings.presPenalty);
        // Advanced
        if (appState.settings.stopSequences && appState.settings.stopSequences.length) body.stop = appState.settings.stopSequences;
        if (appState.settings.seed !== null && appState.settings.seed !== undefined && appState.settings.seed !== '') body.seed = parseInt(
            appState.settings.seed);
        if (appState.settings.responseFormat) body.response_format = { type: appState.settings.responseFormat };

        const headers = { 'Content-Type': 'application/json' };
        if (apiKey && apiKey.trim()) {
            headers['Authorization'] = `Bearer ${apiKey.trim()}`;
            headers['HTTP-Referer'] = window.location.origin;
            headers['X-Title'] = 'SenPai Neural Debug Console';
        }
        const resp = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            signal: appState.chat.abortController?.signal,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error?.message || err.message || `HTTP ${resp.status}`);
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        let promptTokens = 0;
        let completionTokens = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;
                    try {
                        const json = JSON.parse(data);
                        const content = json.choices?.[0]?.delta?.content;
                        if (content !== undefined && content !== null) {
                            fullText += content;
                            onChunk(content, fullText);
                        }
                        if (json.usage) {
                            promptTokens = json.usage.prompt_tokens || 0;
                            completionTokens = json.usage.completion_tokens || 0;
                        }
                    } catch (_) {}
                }
            }
        }
        if (!promptTokens && !completionTokens && appState.settings.estimateTokens) {
            promptTokens = estimateTokens(JSON.stringify(messages));
            completionTokens = estimateTokens(fullText);
        }
        onComplete(fullText, promptTokens, completionTokens);
        return { text: fullText, promptTokens, completionTokens };
    }

    async function callOllamaStream(userText, imageParts, onChunk, onComplete, onError) {
        const base = (appState.settings.baseUrl || 'http://localhost:11434').replace(/\/$/, '');
        const messages = buildOpenAIMessages(userText, imageParts);
        const body = {
            model: appState.settings.model,
            messages,
            stream: true,
            options: {
                temperature: appState.settings.temperature,
                num_predict: appState.settings.maxTokens || 4096,
                stop: appState.settings.stopSequences && appState.settings.stopSequences.length ? appState.settings.stopSequences : undefined,
                seed: appState.settings.seed !== null && appState.settings.seed !== '' ? parseInt(appState.settings.seed) : undefined,
            },
        };
        const resp = await fetch(`${base}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: appState.chat.abortController?.signal,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${resp.status}`);
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        let promptTokens = 0;
        let completionTokens = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.trim()) {
                    try {
                        const json = JSON.parse(line);
                        const content = json.message?.content || json.response || '';
                        if (content) {
                            fullText += content;
                            onChunk(content, fullText);
                        }
                        if (json.done) {
                            promptTokens = json.prompt_eval_count || 0;
                            completionTokens = json.eval_count || 0;
                        }
                    } catch (_) {}
                }
            }
        }
        if (!promptTokens && !completionTokens && appState.settings.estimateTokens) {
            promptTokens = estimateTokens(JSON.stringify(messages));
            completionTokens = estimateTokens(fullText);
        }
        onComplete(fullText, promptTokens, completionTokens);
        return { text: fullText, promptTokens, completionTokens };
    }

    // ════════════════════════════════════════════════════════════
    // SEND MESSAGE (with streaming, cancel, brain growth, tabs, auto-prune)
    // ════════════════════════════════════════════════════════════
    async function sendMessage() {
        const text = chatInput.value.trim();
        const hasImages = appState.ui.pendingImages.length > 0;
        if (!text && !hasImages) return;

        if (appState.memory.enabled && text) rememberFrom(text);

        // Trigger Chain-of-Thought if Agent enabled
        if (appState.agent.enabled) {
            runChainOfThought(text);
        }

        const prov = appState.settings.provider;
        const cfg = PROVIDER_DEFAULTS[prov];

        if (cfg.needsKey && (!appState.settings.apiKey || appState.settings.apiKey.trim().length < 6)) {
            addMessage('ai', '⚠️ **Configuration Error**\n\nPlease set a valid API key in [CONFIG].', {});
            return;
        }

        if (prov === 'ollama') {
            try {
                const base = appState.settings.baseUrl || 'http://localhost:11434';
                const test = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(2000) });
                if (!test.ok) throw new Error('not ok');
            } catch (_) {
                addMessage('ai', '⚠️ **Ollama Unreachable**\n\nMake sure Ollama is running locally and the URL is correct in [CONFIG].',
                {});
                return;
            }
        }

        // Cloud image warning
        if (hasImages && (prov === 'openrouter' || prov === 'gemini')) {
            showFileToast('⚠️ Images will be sent to cloud provider.', true);
            setTimeout(hideFileToast, 3000);
        }

        const imagesToSend = [...appState.ui.pendingImages];
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendBtn.disabled = true;
        cancelBtn.style.display = 'flex';
        clearPendingImages();

        // Grow brain on user message
        growCosmicBrain('user', text || 'IMAGE');
        playCameraShot('pushIn');

        // Generate a unique id for user message
        const userMsgId = 'msg_' + (++messageIdCounter);
        addMessage('user', text || '(image sent)', { imageData: imagesToSend, id: userMsgId });
        appState.chat.history.push({ role: 'user', text: text || 'Describe this image.', images: imagesToSend, id: userMsgId });

        const typing = addTypingIndicator();
        setBrainState('thinking');
        playCameraShot('orbitSweep');
        const startTime = performance.now();

        if (appState.chat.abortController) {
            appState.chat.abortController.abort();
        }
        appState.chat.abortController = new AbortController();

        let streamWrapper = null;
        let streamMsgDiv = null;
        let fullResponse = '';
        let promptTokens = 0;
        let completionTokens = 0;
        let chunksCount = 0;
        let errorOccurred = false;
        let aiMsgId = null;

        const onChunk = (chunk, full) => {
            chunksCount++;
            if (!streamWrapper) {
                aiMsgId = 'msg_' + (++messageIdCounter);
                const result = addMessage('ai', '', { isStreaming: true, id: aiMsgId });
                streamWrapper = result.wrapper;
                streamMsgDiv = result.msgDiv;
                removeTypingIndicator();
                setBrainState('speaking');
                playCameraShot('tiltHero');
                cancelBtn.style.display = 'flex';
            }
            if (streamMsgDiv) {
                // Improve markdown rendering: only update if chunk has newlines or significant changes
                // For simplicity, we'll update every time but we can debounce
                streamMsgDiv.innerHTML = renderMarkdown(full);
                scrollToBottom();
            }
        };

        const onComplete = (finalText, pt, ct) => {
            fullResponse = finalText;
            promptTokens = pt || 0;
            completionTokens = ct || 0;
            if (!streamWrapper) {
                aiMsgId = 'msg_' + (++messageIdCounter);
                const result = addMessage('ai', finalText || '(empty response)', { isStreaming: true, id: aiMsgId });
                streamWrapper = result.wrapper;
                streamMsgDiv = result.msgDiv;
                removeTypingIndicator();
                setBrainState('speaking');
                playCameraShot('tiltHero');
            }
            if (streamMsgDiv) {
                streamMsgDiv.innerHTML = renderMarkdown(finalText || '(empty response)');
                // Add code block buttons and highlight
                setTimeout(() => addCodeBlockButtons(streamWrapper), 100);
            }
            const latency = Math.round(performance.now() - startTime);
            const usageRec = recordUsage(promptTokens, completionTokens, latency);
            latencyDisplay.textContent = latency;
            if (streamWrapper) {
                const metaDiv = document.createElement('div');
                metaDiv.className = 'message-meta';
                metaDiv.innerHTML =
                    `<span class="mm-tok">${(promptTokens + completionTokens).toLocaleString()} tok</span><span class="mm-cost">$${usageRec.cost.toFixed(5)}</span><span class="mm-lat">${latency} ms</span>`;
                streamWrapper.appendChild(metaDiv);
                const actions = createActionButtons(aiMsgId);
                streamWrapper.appendChild(actions);
                setupMessageActions(streamWrapper, finalText || '(empty response)', aiMsgId);
            }
            // Add to history
            appState.chat.history.push({ role: 'assistant', text: finalText || '(empty response)', id: aiMsgId });
            setBrainState('idle');
            sendBtn.disabled = false;
            cancelBtn.style.display = 'none';
            appState.chat.abortController = null;
            appState.chat.streaming = false;
            updateConnectionStatus();
            if (linkDot.classList.contains('warning')) {
                linkDot.classList.remove('warning');
                linkLabel.textContent = 'NEURAL LINK: ACTIVE';
            }
            renderConvList();
            scrollToBottom();

            // Grow brain on AI response
            growCosmicBrain('ai', finalText || 'RESPONSE');
            playCameraShot('pullReveal');

            // Auto-prune
            pruneHistory();
        };

        const onError = (err) => {
            errorOccurred = true;
            removeTypingIndicator();
            setBrainState('idle');
            latencyDisplay.textContent = 'ERR';
            if (streamWrapper && streamMsgDiv) {
                streamMsgDiv.innerHTML = renderMarkdown(
                    `🔴 **Request cancelled or error**\n\n\`\`\`\n${err.message}\n\`\`\``);
            } else {
                addMessage('ai', `🔴 **Communication Error**\n\n\`\`\`\n${err.message}\n\`\`\``, {});
            }
            sendBtn.disabled = false;
            cancelBtn.style.display = 'none';
            appState.chat.abortController = null;
            appState.chat.streaming = false;
            linkDot.classList.add('warning');
            linkLabel.textContent = 'TRANSMISSION ERROR';
            scrollToBottom();
        };

        try {
            appState.chat.streaming = true;
            if (prov === 'gemini') {
                const result = await callGemini(text || 'Describe this image.', imagesToSend);
                onComplete(result.text, result.promptTokens, result.completionTokens);
            } else if (prov === 'ollama') {
                await callOllamaStream(text || 'Describe this image.', imagesToSend, onChunk, onComplete,
                onError);
            } else {
                const baseUrl = appState.settings.baseUrl || cfg.baseUrl;
                await callOpenAICompatibleStream(text || 'Describe this image.', imagesToSend, {
                    baseUrl,
                    apiKey: appState.settings.apiKey || '',
                    model: appState.settings.model,
                }, onChunk, onComplete, onError);
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                onError(new Error('Request was cancelled by user.'));
            } else {
                onError(err);
            }
        }
    }

    // Gemini non-stream
    async function callGemini(userText, imageParts) {
        const url =
            `https://generativelanguage.googleapis.com/v1beta/models/${appState.settings.model}:generateContent?key=${appState.settings.apiKey}`;
        const parts = [{ text: userText || 'Describe this image.' }];
        imageParts.forEach(img => parts.push({ inlineData: { mimeType: img.mimeType, data: img.base64Data } }));
        const maxContext = appState.settings.slidingWindow || 20;
        const contextEntries = appState.chat.history.slice(-maxContext);
        const history = contextEntries.map(e => ({
            role: e.role === 'user' ? 'user' : 'model',
            parts: [{ text: e.text || '' }],
        }));
        const body = {
            contents: [...history, { role: 'user', parts }],
            system_instruction: { parts: [{ text: appState.settings.systemPrompt }] },
            generationConfig: {
                temperature: appState.settings.temperature,
                maxOutputTokens: appState.settings.maxTokens || 4096,
            },
        };
        if (appState.settings.topP !== null && appState.settings.topP !== undefined && appState.settings.topP !== '') body.generationConfig
            .topP = parseFloat(appState.settings.topP);
        if (appState.settings.freqPenalty !== null && appState.settings.freqPenalty !== undefined && appState.settings.freqPenalty !== '')
            body.generationConfig.frequencyPenalty = parseFloat(appState.settings.freqPenalty);
        if (appState.settings.presPenalty !== null && appState.settings.presPenalty !== undefined && appState.settings.presPenalty !== '')
            body.generationConfig.presencePenalty = parseFloat(appState.settings.presPenalty);
        if (appState.settings.stopSequences && appState.settings.stopSequences.length) body.generationConfig.stopSequences = appState.settings.stopSequences;
        if (appState.settings.seed !== null && appState.settings.seed !== '' && appState.settings.seed !== undefined) body.generationConfig
            .seed = parseInt(appState.settings.seed);
        if (appState.settings.responseFormat) body.generationConfig.responseMimeType = appState.settings.responseFormat ===
            'json_object' ? 'application/json' : undefined;

        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: appState.chat.abortController?.signal,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error?.message || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        const candidate = data.candidates?.[0];
        if (!candidate?.content?.parts?.length) throw new Error('Empty response from Gemini API.');
        const text = candidate.content.parts.map(p => p.text || '').join('');
        let promptTokens = data.usageMetadata?.promptTokenCount || 0;
        let completionTokens = data.usageMetadata?.candidatesTokenCount || 0;
        if (!promptTokens && !completionTokens && appState.settings.estimateTokens) {
            promptTokens = estimateTokens(JSON.stringify(body));
            completionTokens = estimateTokens(text);
        }
        return { text, promptTokens, completionTokens };
    }

    function estimateTokens(text) {
        if (!text) return 0;
        const codeBlocks = (text.match(/```[\s\S]*?```/g) || []).join('');
        const codeLen = codeBlocks.length;
        const proseLen = Math.max(0, text.length - codeLen);
        return Math.ceil(codeLen / 3.2 + proseLen / 4);
    }

    // Fetch models
    async function fetchModels() {
        const prov = providerSelect.value;
        const cfg = PROVIDER_DEFAULTS[prov];
        modelFetchStatus.className = 'model-fetch-status loading';
        modelFetchStatus.textContent = '↺ Fetching models…';
        try {
            let models = [];
            if (prov === 'ollama') {
                const base = (baseUrlInput.value || cfg.baseUrl).replace(/\/$/, '');
                const resp = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(4000) });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                models = (data.models || []).map(m => m.name || m.model || m);
            } else if (prov === 'lmstudio') {
                const base = (baseUrlInput.value || cfg.baseUrl).replace(/\/$/, '');
                const resp = await fetch(`${base}/models`, { signal: AbortSignal.timeout(4000) });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                models = (data.data || data.models || []).map(m => m.id || m.name || m);
            } else if (prov === 'openrouter') {
                const resp = await fetch('https://openrouter.ai/api/v1/models', {
                    headers: apiKeyInput.value ? { 'Authorization': `Bearer ${apiKeyInput.value}` } : {},
                    signal: AbortSignal.timeout(6000),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                models = (data.data || []).map(m => m.id).sort();
            } else if (prov === 'gemini') {
                const key = apiKeyInput.value.trim();
                if (!key) throw new Error('API key required');
                const resp = await fetch(
                    `https://generativelanguage.googleapis.com/v1beta/models?key=${key}`, { signal: AbortSignal
                        .timeout(6000) }
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                models = (data.models || []).filter(m => m.supportedGenerationMethods?.includes('generateContent'))
                    .map(m => m.name.replace('models/', ''));
            } else {
                throw new Error('Cannot auto-fetch models for this provider');
            }
            if (!models.length) { models = FALLBACK_MODEL_LISTS[prov] || []; }
            populateModelSelect(models);
            modelFetchStatus.className = 'model-fetch-status ok';
            modelFetchStatus.textContent = `✓ ${models.length} models loaded`;
        } catch (err) {
            modelFetchStatus.className = 'model-fetch-status err';
            modelFetchStatus.textContent = `✗ ${err.message} — using built-in list`;
            populateModelSelect(FALLBACK_MODEL_LISTS[prov] || []);
        }
        updateHeaderModelSwitcher();
    }

    // ════════════════════════════════════════════════════════════
    // AGENT VIBE — Chain-of-Thought, Tools, Mission
    // ════════════════════════════════════════════════════════════

    const COT_TEMPLATES = {
        analyze: ['🔍 Analyzing user request…', '📐 Parsing intent and required output format…'],
        memory:  ['🧠 Scanning conversation memory for relevant context…', '📎 Cross-referencing attached files…'],
        tool:    ['🛠 Evaluating available tools for this request…'],
        plan:    ['🗺 Drafting step-by-step response plan…'],
        summarize: ['📝 Summarizing findings before final answer…'],
    };
    let cotStepEls = [];
    function cotReset() {
        const body = document.getElementById('cotBody');
        if (body) body.innerHTML = '';
        cotStepEls = [];
        updateCotCount();
    }
    function updateCotCount() {
        const el = document.getElementById('cotStepCount');
        if (el) el.textContent = cotStepEls.length + ' step' + (cotStepEls.length === 1 ? '' : 's');
    }
    function cotAddStep(icon, text) {
        if (!appState.agent.enabled) return null;
        const body = document.getElementById('cotBody');
        if (!body) return null;
        const row = document.createElement('div');
        row.className = 'cot-step';
        row.innerHTML = `<span class="cot-icon">${icon}</span><span class="cot-text"></span>`;
        body.appendChild(row);
        cotStepEls.push(row);
        updateCotCount();
        body.scrollTop = body.scrollHeight;
        typewriteInto(row.querySelector('.cot-text'), text, () => row.classList.add('done'));
        return row;
    }
    function typewriteInto(el, text, onDone) {
        let i = 0;
        const speed = 12;
        (function tick() {
            if (i <= text.length) {
                el.textContent = text.slice(0, i);
                i++;
                setTimeout(tick, speed);
            } else if (onDone) onDone();
        })();
    }
    function runChainOfThought(userText) {
        if (!appState.agent.enabled) return;
        cotReset();
        const steps = [...COT_TEMPLATES.analyze, ...COT_TEMPLATES.memory];
        if (appState.agent.tools.webSearch || appState.agent.tools.codeRunner || appState.agent.tools.fileExplorer) {
            steps.push(...COT_TEMPLATES.tool);
        }
        steps.push(...COT_TEMPLATES.plan);
        for (const s of steps) {
            cotAddStep('▸', s);
        }
        // Simulate delay for each step
        let idx = 0;
        function processNext() {
            if (idx < steps.length) {
                // Already added all steps, just mark them as done gradually
                const rows = cotStepEls;
                if (rows[idx]) rows[idx].classList.add('done');
                idx++;
                setTimeout(processNext, 300 + Math.random() * 200);
            }
        }
        setTimeout(processNext, 100);
        detectAndActivateTool(userText);
    }

    function detectAndActivateTool(userText) {
        if (!appState.agent.enabled) return;
        const t = (userText || '').toLowerCase();
        const wantsSearch = /\b(latest|current|today|news|price of|weather|who is|search|lookup|202\d)\b/.test(t);
        const wantsCode = /\b(run this|execute|calculate|compute)\b/.test(t) || /```(js|javascript)/.test(t);
        if (wantsSearch) {
            activateTool('webSearch');
            showToolActivationToast('🔎 Activating tool: Web Search');
            runWebSearch(userText);
        } else if (wantsCode) {
            activateTool('codeRunner');
            showToolActivationToast('▶ Activating tool: Code Runner');
        }
    }
    function activateTool(name) {
        appState.agent.tools[name] = true;
        const btn = document.getElementById(
            name === 'webSearch' ? 'toolWebSearchBtn' :
            name === 'codeRunner' ? 'toolCodeRunnerBtn' : 'toolFileExplorerBtn');
        if (btn) btn.classList.add('active');
    }
    function showToolActivationToast(msg) {
        const container = document.getElementById('messagesContainer');
        if (!container) return;
        const el = document.createElement('div');
        el.className = 'tool-activation-toast';
        el.textContent = msg;
        container.appendChild(el);
        scrollToBottom();
    }
    async function runWebSearch(query) {
        try {
            const url = `https://api.duckduckgo.com/?q=${encodeURIComponent(query)}&format=json&no_html=1&skip_disambig=1`;
            const res = await fetch(url);
            const data = await res.json();
            const summary = data.AbstractText || (data.RelatedTopics && data.RelatedTopics[0] &&
                data.RelatedTopics[0].Text) || 'No concise summary available for this query.';
            showToolActivationToast('🔎 Web Search result: ' + summary.slice(0, 220));
        } catch (err) {
            showToolActivationToast('🔎 Web Search failed (network/CORS). Try a direct query in your browser.');
        }
    }
    function runCodeInSandbox(code) {
        const consoleEl = document.createElement('div');
        consoleEl.className = 'code-console';
        consoleEl.textContent = 'Running in sandbox…';
        const container = document.getElementById('messagesContainer');
        if (container) { container.appendChild(consoleEl); scrollToBottom(); }
        runInSandbox(code, (data) => {
            const parts = (data.logs || []).map(l =>
                `<span class="${l.level === 'error' ? 'cc-err' : 'cc-log'}">${escapeHtmlLocal(l.text)}</span>`);
            if (data.error) parts.push(`<span class="cc-err">Error: ${escapeHtmlLocal(data.error)}</span>`);
            else if (data.result !== undefined) parts.push(`<span class="cc-log">→ ${escapeHtmlLocal(data.result)}</span>`);
            if (!parts.length) parts.push('<span class="cc-log">(no output)</span>');
            consoleEl.innerHTML = parts.join('\n');
            scrollToBottom();
        });
    }
    function escapeHtmlLocal(s) {
        return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function renderFileExplorer() {
        const tree = document.getElementById('fileExplorerTree');
        if (!tree) return;
        const files = (appState.chat.history || [])
            .flatMap(m => (m.images || []).map(img => img.fileName || img.name || 'attachment.png'));
        tree.innerHTML = files.length
            ? files.map(f => `<div class="fe-tree-item"><span class="fe-icon">📄</span>${f}</div>`).join('')
            : '<div class="fe-tree-item" style="opacity:0.5;">No attached files in this session.</div>';
    }

    // ── Mission ──
    function decomposeMission(goal) {
        const base = goal.replace(/\s+/g, ' ').trim();
        return [
            `Clarify scope & requirements for: "${base}"`,
            `Research / gather any data or references needed`,
            `Draft the core implementation`,
            `Refine, test, and polish the result`,
            `Summarize the outcome and next steps for the user`,
        ];
    }
    function renderMissionTasks() {
        const list = document.getElementById('missionTaskList');
        if (!list) return;
        list.innerHTML = appState.agent.mission.tasks.map((t, i) => {
            const icon = t.status === 'done' ? '✔' : t.status === 'active' ? '◐' : t.status === 'error' ? '✕' : '○';
            return `<div class="mission-task ${t.status}"><span class="mt-status">${icon}</span><span>${t.text}</span></div>`;
        }).join('');
    }
    async function startMission(goal) {
        appState.agent.mission.active = true;
        appState.agent.mission.goal = goal;
        appState.agent.mission.tasks = decomposeMission(goal).map(text => ({ text, status: 'pending' }));
        appState.agent.mission.currentIndex = -1;
        document.getElementById('missionInputWrap').style.display = 'none';
        renderMissionTasks();
        setBrainState('thinking');
        playCameraShot('orbitSweep');
        const missionShots = ['pushIn', 'driftWide', 'tiltHero', 'orbitSweep', 'pullReveal'];
        for (let i = 0; i < appState.agent.mission.tasks.length; i++) {
            appState.agent.mission.currentIndex = i;
            appState.agent.mission.tasks[i].status = 'active';
            renderMissionTasks();
            playCameraShot(missionShots[i % missionShots.length]);
            await new Promise(res => setTimeout(res, 900 + Math.random() * 700));
            appState.agent.mission.tasks[i].status = 'done';
            renderMissionTasks();
        }
        appState.agent.mission.active = false;
        setBrainState('idle');
        playCameraShot('pullReveal');
        document.getElementById('missionOverlay').classList.remove('open');
        chatInput.value = `Mission complete: "${goal}". Please produce the final combined deliverable based on the sub-tasks we just worked through.`;
        sendMessage();
    }

    // ── Consciousness Bar ──
    const CONSCIOUSNESS_WAVES = {
        idle:            { color: '#58a6ff', freq: 0.5, amp: 5,  speed: 0.02, label: 'IDLE' },
        thinking:        { color: '#d2a8ff', freq: 1.4, amp: 9,  speed: 0.08, label: 'THINKING' },
        speaking:        { color: '#ffd76a', freq: 1.0, amp: 8,  speed: 0.05, label: 'SPEAKING' },
        'agent-processing': { color: '#ff8c42', freq: 2.0, amp: 11, speed: 0.12, label: 'AGENT-PROCESSING' },
    };
    let cbAnimFrame = null, cbPhase = 0;
    function updateConsciousness(state) {
        if (!appState.agent.enabled) return;
        appState.agent.consciousness = state;
        const cfg = CONSCIOUSNESS_WAVES[state] || CONSCIOUSNESS_WAVES.idle;
        const label = document.getElementById('cbStateLabel');
        if (label) {
            label.textContent = cfg.label;
            label.className = 'cb-state cb-' + (state === 'agent-processing' ? 'agent' : state);
        }
        hudOverlay.classList.toggle('agent-processing', state === 'agent-processing');
        drawConsciousnessWave(cfg);
    }
    function drawConsciousnessWave(cfg) {
        const wave = document.getElementById('cbWave');
        if (!wave) return;
        if (cbAnimFrame) cancelAnimationFrame(cbAnimFrame);
        const W = wave.clientWidth || 300, H = 22;
        function frame() {
            cbPhase += cfg.speed;
            let d = `M0,${H/2}`;
            for (let x = 0; x <= W; x += 4) {
                const y = H/2 + Math.sin(x * 0.05 * cfg.freq + cbPhase) * cfg.amp * 0.4
                         + Math.sin(x * 0.02 * cfg.freq + cbPhase * 1.7) * cfg.amp * 0.2;
                d += ` L${x},${y}`;
            }
            wave.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
                <path d="${d}" fill="none" stroke="${cfg.color}" stroke-width="1.6" opacity="0.9"/>
            </svg>`;
            cbAnimFrame = requestAnimationFrame(frame);
        }
        frame();
    }

    function setBrainState(state) {
        appState.brain.mode = state;
        appState.brain.pulsePhase = 0;
        appState.brain.clusterIndex = 0;
        appState.brain.clusterTimer = 0;
        stateLabel.textContent = state === 'speaking' ? 'SPEAKING...' : state === 'thinking' ? 'PROCESSING...' : 'READY';
        updateConsciousness(appState.agent.mission.active ? 'agent-processing' : state);
    }

    // ════════════════════════════════════════════════════════════
    // UI EVENT LISTENERS
    // ════════════════════════════════════════════════════════════
    sendBtn.addEventListener('click', sendMessage);

    chatInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault();
            sendMessage(); return; }
        setTimeout(autoResizeInput, 0);
    });
    chatInput.addEventListener('input', autoResizeInput);

    messagesContainer.addEventListener('scroll', updateScrollButton);
    scrollBottomBtn.addEventListener('click', scrollToBottom);

    micBtn.addEventListener('click', toggleRecording);
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => {
        if (e.target.files?.length) { handleFiles(e.target.files);
            fileInput.value = ''; }
    });

    cancelBtn.addEventListener('click', () => {
        if (appState.chat.abortController) {
            appState.chat.abortController.abort();
            appState.chat.abortController = null;
        }
        cancelBtn.style.display = 'none';
        sendBtn.disabled = false;
        appState.chat.streaming = false;
        removeTypingIndicator();
        setBrainState('idle');
        showFileToast('Request cancelled');
        setTimeout(hideFileToast, 1500);
    });

    voiceToggleBtn.addEventListener('click', () => {
        appState.settings.ttsEnabled = !appState.settings.ttsEnabled;
        updateVoiceToggleUI();
        saveSettingsToStorage();
        if (!appState.settings.ttsEnabled) stopSpeaking();
        showFileToast(appState.settings.ttsEnabled ? 'TTS enabled' : 'TTS disabled');
        setTimeout(hideFileToast, 1500);
    });

    configBtn.addEventListener('click', () => {
        applySettingsToUI();
        settingsOverlay.classList.add('active');
    });
    closeSettings.addEventListener('click', () => settingsOverlay.classList.remove('active'));
    cancelSettingsBtn.addEventListener('click', () => settingsOverlay.classList.remove('active'));
    settingsOverlay.addEventListener('click', e => {
        if (e.target === settingsOverlay) settingsOverlay.classList.remove('active');
    });

    saveSettingsBtn.addEventListener('click', async () => {
        appState.settings.provider = providerSelect.value;
        appState.settings.apiKey = apiKeyInput.value.trim();
        appState.settings.baseUrl = baseUrlInput.value.trim() || PROVIDER_DEFAULTS[appState.settings.provider].baseUrl;
        appState.settings.model = modelSelect.value;
        appState.settings.systemPrompt = systemPromptInput.value;
        appState.settings.temperature = parseFloat(tempSlider.value);
        appState.settings.maxTokens = parseInt(maxTokensInput.value) || 4096;
        appState.settings.topP = topPInput.value !== '' ? parseFloat(topPInput.value) : null;
        appState.settings.freqPenalty = freqPenaltyInput.value !== '' ? parseFloat(freqPenaltyInput.value) : null;
        appState.settings.presPenalty = presPenaltyInput.value !== '' ? parseFloat(presPenaltyInput.value) : null;
        appState.settings.voiceLang = voiceLangSelect.value;
        appState.settings.priceIn = parseFloat(priceInInput.value) || 0;
        appState.settings.priceOut = parseFloat(priceOutInput.value) || 0;
        appState.settings.tokenBudget = parseInt(tokenBudgetInput.value) || 128000;
        appState.settings.contextWindow = parseInt(contextWindowInput.value) || 128000;
        appState.settings.estimateTokens = estimateTokensCheckbox.checked;
        appState.settings.slidingWindow = parseInt(slidingWindowInput.value) || 20;
        // Advanced
        const stopSeq = stopSequencesInput.value.split(',').map(s => s.trim()).filter(s => s);
        appState.settings.stopSequences = stopSeq;
        appState.settings.seed = seedInput.value !== '' ? parseInt(seedInput.value) : null;
        appState.settings.responseFormat = responseFormatSelect.value;
        appState.settings.useWebSocket = useWebSocketCheckbox.checked;
        await saveSettingsToStorage();
        updateConnectionStatus();
        updateVoiceToggleUI();
        updateProviderUI();
        if (recognition) recognition.lang = appState.settings.voiceLang;
        settingsOverlay.classList.remove('active');
        providerDisplay.textContent = PROVIDER_DEFAULTS[appState.settings.provider]?.label.split(' ')[0] || appState.settings.provider;
        modelDisplay.textContent = appState.settings.model || '—';
        renderTokenGauge();
        updateTokenMeterText();
        updateHeaderModelSwitcher();
        showFileToast('Settings saved');
        setTimeout(hideFileToast, 1500);
    });

    providerSelect.addEventListener('change', () => {
        updateProviderUI();
        populateModelSelect(FALLBACK_MODEL_LISTS[providerSelect.value] || []);
        baseUrlInput.dataset.autofilled = '1';
        updateHeaderModelSwitcher();
    });

    toggleApiKey.addEventListener('click', () => {
        const isPw = apiKeyInput.type === 'password';
        apiKeyInput.type = isPw ? 'text' : 'password';
        toggleApiKey.textContent = isPw ? 'HIDE' : 'SHOW';
    });

    tempSlider.addEventListener('input', () => {
        tempDisplay.textContent = parseFloat(tempSlider.value).toFixed(2);
    });

    resetTokenMeterBtn.addEventListener('click', resetTokenMeter);

    clearChatBtn.addEventListener('click', () => {
        if (appState.chat.history.length > 0 && !confirm('Clear entire conversation?')) return;
        saveCurrentConversation();
        clearChatSilent();
        resetTokenMeter();
        // Reset brain? maybe not.
    });

    refreshModelsBtn.addEventListener('click', fetchModels);

    addCustomModelBtn.addEventListener('click', () => {
        const val = customModelInput.value.trim();
        if (!val) return;
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        opt.selected = true;
        modelSelect.insertBefore(opt, modelSelect.firstChild);
        modelSelect.value = val;
        customModelInput.value = '';
        showFileToast(`Model "${val}" added`);
        setTimeout(hideFileToast, 1500);
        updateHeaderModelSwitcher();
    });

    searchToggleBtn.addEventListener('click', toggleSearch);
    searchClose.addEventListener('click', toggleSearch);
    searchInput.addEventListener('input', () => performSearch(searchInput.value));
    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Escape') toggleSearch();
    });
    searchRegexToggle.addEventListener('click', () => {
        appState.ui.searchRegex = !appState.ui.searchRegex;
        searchRegexToggle.classList.toggle('active', appState.ui.searchRegex);
        performSearch(searchInput.value);
    });
    closeSearchResults.addEventListener('click', () => {
        searchResultsPanel.classList.remove('active');
        document.querySelectorAll('.message.highlight').forEach(el => el.classList.remove('highlight'));
        searchCount.textContent = '';
        searchInput.value = '';
    });

    convListBtn.addEventListener('click', () => {
        convList.classList.toggle('open');
        renderConvList();
    });
    document.addEventListener('click', e => {
        if (convList.classList.contains('open') && !convList.contains(e.target) && e.target !== convListBtn) {
            convList.classList.remove('open');
        }
    });
    exportConvBtn.addEventListener('click', exportConversation);
    exportMdBtn.addEventListener('click', exportMarkdown);
    clearAllConvsBtn.addEventListener('click', () => {
        if (appState.chat.allConversations.length === 0) return;
        if (!confirm('Delete all saved conversations?')) return;
        appState.chat.allConversations = [];
        saveConversations();
        renderConvList();
        showFileToast('All conversations cleared');
        setTimeout(hideFileToast, 1500);
    });

    savePromptBtn.addEventListener('click', saveCurrentPrompt);
    loadPromptBtn.addEventListener('click', loadSelectedPrompt);
    deletePromptBtn.addEventListener('click', deleteSelectedPrompt);

    messagesContainer.addEventListener('dragover', e => {
        e.preventDefault();
        messagesContainer.style.boxShadow = 'inset 0 0 0 2px var(--accent-blue)';
    });
    messagesContainer.addEventListener('dragleave', () => { messagesContainer.style.boxShadow = ''; });
    messagesContainer.addEventListener('drop', e => {
        e.preventDefault();
        messagesContainer.style.boxShadow = '';
        if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
    });

    document.addEventListener('keydown', e => {
        if (e.ctrlKey && e.key === 'm') { e.preventDefault();
            toggleRecording(); }
        if (e.ctrlKey && e.key === 'Enter') { e.preventDefault();
            sendMessage(); }
        if (e.key === 'Escape') { settingsOverlay.classList.remove('active');
            convList.classList.remove('open');
            toggleSearch(); }
        if (e.key === 'Escape' && appState.chat.streaming) {
            if (appState.chat.abortController) {
                appState.chat.abortController.abort();
                appState.chat.abortController = null;
                cancelBtn.style.display = 'none';
                sendBtn.disabled = false;
                appState.chat.streaming = false;
                removeTypingIndicator();
                setBrainState('idle');
                showFileToast('Request cancelled');
                setTimeout(hideFileToast, 1500);
            }
        }
    });

    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.settings-tabpanel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.querySelector(`.settings-tabpanel[data-tabpanel="${tab.dataset.tab}"]`).classList.add(
                'active');
        });
    });

    // Agent Vibe: toggle master switch
    const agentToggleBtn = document.getElementById('agentToggleBtn');
    const consciousnessBar = document.getElementById('consciousnessBar');
    const cotPanel = document.getElementById('cotPanel');
    const toolBar = document.getElementById('toolBar');
    agentToggleBtn.addEventListener('click', () => {
        appState.agent.enabled = !appState.agent.enabled;
        agentToggleBtn.classList.toggle('active', appState.agent.enabled);
        agentToggleBtn.classList.toggle('active-btn', appState.agent.enabled);
        const agentLabel = agentToggleBtn.querySelector('span');
        if (agentLabel) agentLabel.textContent = appState.agent.enabled ? 'AGENT: ON' : 'AGENT';
        consciousnessBar.classList.toggle('active', appState.agent.enabled);
        cotPanel.classList.toggle('visible', appState.agent.enabled);
        toolBar.classList.toggle('visible', appState.agent.enabled);
        if (appState.agent.enabled) {
            updateConsciousness('idle');
            cotReset();
            showToolActivationToast('🧠 Agent Vibe activated — chain-of-thought, tools & consciousness monitor online.');
        } else {
            if (cbAnimFrame) cancelAnimationFrame(cbAnimFrame);
        }
    });

    // Agent Vibe: chain-of-thought panel collapse
    document.getElementById('cotPanelHeader').addEventListener('click', () => {
        appState.agent.cotCollapsed = !appState.agent.cotCollapsed;
        cotPanel.classList.toggle('collapsed', appState.agent.cotCollapsed);
    });

    // Agent Vibe: tool buttons
    document.getElementById('toolWebSearchBtn').addEventListener('click', function() {
        appState.agent.tools.webSearch = !appState.agent.tools.webSearch;
        this.classList.toggle('active', appState.agent.tools.webSearch);
        if (appState.agent.tools.webSearch) showToolActivationToast('🔎 Web Search tool armed — will trigger on relevant queries.');
    });
    document.getElementById('toolCodeRunnerBtn').addEventListener('click', function() {
        const lastCode = [...appState.chat.history].reverse()
            .map(m => ((m.text || '').match(/```(?:js|javascript)?\n([\s\S]*?)```/) || [])[1]).find(Boolean);
        if (lastCode) {
            showToolActivationToast('▶ Running last JavaScript code block…');
            runCodeInSandbox(lastCode);
        } else {
            appState.agent.tools.codeRunner = !appState.agent.tools.codeRunner;
            this.classList.toggle('active', appState.agent.tools.codeRunner);
            showToolActivationToast('▶ Code Runner armed — no JS code block found yet in this chat.');
        }
    });
    document.getElementById('toolFileExplorerBtn').addEventListener('click', function() {
        appState.agent.tools.fileExplorer = !appState.agent.tools.fileExplorer;
        this.classList.toggle('active', appState.agent.tools.fileExplorer);
        const panel = document.getElementById('fileExplorerPanel');
        panel.classList.toggle('visible', appState.agent.tools.fileExplorer);
        if (appState.agent.tools.fileExplorer) renderFileExplorer();
    });

    // Mission Manager
    const missionOverlay = document.getElementById('missionOverlay');
    document.getElementById('missionModeBtn').addEventListener('click', () => {
        if (!appState.agent.enabled) {
            agentToggleBtn.click();
        }
        missionOverlay.classList.add('open');
        document.getElementById('missionModeBtn').classList.add('active');
        document.getElementById('missionInputWrap').style.display = 'block';
        document.getElementById('missionGoalInput').value = '';
        document.getElementById('missionTaskList').innerHTML = '';
    });
    document.getElementById('missionCloseBtn').addEventListener('click', () => {
        missionOverlay.classList.remove('open');
        document.getElementById('missionModeBtn').classList.remove('active');
    });
    document.getElementById('missionStartBtn').addEventListener('click', () => {
        const goal = document.getElementById('missionGoalInput').value.trim();
        if (!goal) return;
        startMission(goal);
    });

    // DNA legend toggle
    const dnaLegendToggle = document.getElementById('dnaLegendToggle');
    const dnaLegendPanel = document.getElementById('dnaLegendPanel');
    if (dnaLegendToggle && dnaLegendPanel) {
        dnaLegendToggle.addEventListener('click', () => {
            const open = dnaLegendPanel.classList.toggle('open');
            dnaLegendToggle.setAttribute('aria-expanded', String(open));
            dnaLegendPanel.setAttribute('aria-hidden', String(!open));
        });
    }

    // Zen mode toggle
    zenToggleBtn.addEventListener('click', () => {
        appState.ui.zenMode = !appState.ui.zenMode;
        brainSection.classList.toggle('zen-hidden', appState.ui.zenMode);
        chatPanel.classList.toggle('zen-expanded', appState.ui.zenMode);
        zenToggleBtn.title = appState.ui.zenMode ? 'Exit Zen mode' : 'Zen mode (fullscreen chat)';
        zenToggleBtn.classList.toggle('active-btn', appState.ui.zenMode);
        // Resize Three.js
        if (appState.ui.zenMode) {
            // Hide brain, resize not needed
        } else {
            onResize();
        }
    });

    // Header model switcher
    headerModelSwitcher.addEventListener('change', () => {
        const model = headerModelSwitcher.value;
        appState.settings.model = model;
        modelDisplay.textContent = model;
        // Also update the settings model select
        modelSelect.value = model;
        saveSettingsToStorage();
        showFileToast(`Switched to ${model}`);
        setTimeout(hideFileToast, 1500);
    });

    // Tab add
    // Token meter collapse toggle
    const tmToggle = document.getElementById('tmToggle');
    const tokenMeterEl = document.getElementById('tokenMeter');
    if (tmToggle && tokenMeterEl) {
        tmToggle.addEventListener('click', () => {
            tokenMeterEl.classList.toggle('collapsed');
        });
    }

    tabAddBtn.addEventListener('click', () => {
        addTab('New Chat');
    });

    // Factory reset
    // ── New feature wiring: Memory, Focus, Council, Analytics, Accessibility, Security, Ticker ──
    document.getElementById('memoryBtn')?.addEventListener('click', () => {
        document.getElementById('memoryPopover')?.classList.toggle('open');
        renderMemoryList();
    });
    document.getElementById('memoryPopoverClose')?.addEventListener('click', () => {
        document.getElementById('memoryPopover')?.classList.remove('open');
    });
    document.getElementById('memoryEnabledCheckbox')?.addEventListener('change', (e) => {
        appState.memory.enabled = e.target.checked;
        saveMemory();
    });
    document.getElementById('memoryClearBtn')?.addEventListener('click', () => {
        if (confirm('Forget all remembered topics?')) forgetAllMemory();
    });

    document.getElementById('focusModeBtn')?.addEventListener('click', toggleFocusMode);
    document.getElementById('focusModeCheckbox')?.addEventListener('change', (e) => {
        // This checkbox just documents the feature is available; the header button/shortcut does the toggling.
        if (!e.target.checked && appState.extras.focusMode) toggleFocusMode();
    });

    document.getElementById('councilBtn')?.addEventListener('click', openCouncil);
    document.getElementById('councilCloseBtn')?.addEventListener('click', closeCouncil);
    document.getElementById('councilRunBtn')?.addEventListener('click', runCouncil);
    document.getElementById('councilProviderSelect')?.addEventListener('change', (e) => {
        appState.extras.councilProvider = e.target.value;
        saveExtras();
    });
    document.getElementById('councilApiKeyInput')?.addEventListener('change', (e) => {
        appState.extras.councilApiKey = e.target.value;
        saveExtras();
    });
    document.getElementById('councilBaseUrlInput')?.addEventListener('change', (e) => {
        appState.extras.councilBaseUrl = e.target.value;
        saveExtras();
    });

    document.getElementById('analyticsBtn')?.addEventListener('click', openAnalytics);
    document.getElementById('analyticsCloseBtn')?.addEventListener('click', closeAnalytics);

    document.getElementById('tickerEnabledCheckbox')?.addEventListener('change', (e) => setTickerEnabled(e.target.checked));

    document.getElementById('fontScaleSlider')?.addEventListener('input', (e) => {
        appState.accessibility.fontScale = Number(e.target.value);
        document.getElementById('fontScaleValue').textContent = e.target.value + '%';
        applyAccessibility();
        saveAccessibility();
    });
    document.getElementById('reducedMotionCheckbox')?.addEventListener('change', (e) => {
        appState.accessibility.reducedMotion = e.target.checked;
        applyAccessibility();
        saveAccessibility();
    });
    document.getElementById('highContrastCheckbox')?.addEventListener('change', (e) => {
        appState.accessibility.highContrast = e.target.checked;
        applyAccessibility();
        saveAccessibility();
    });
    document.getElementById('dyslexiaFontCheckbox')?.addEventListener('change', (e) => {
        appState.accessibility.dyslexiaFont = e.target.checked;
        applyAccessibility();
        saveAccessibility();
    });

    document.getElementById('localLockSetBtn')?.addEventListener('click', async () => {
        const pass = document.getElementById('localLockPassInput').value;
        if (!pass || pass.length < 4) { showFileToast('Passphrase must be at least 4 characters', true); setTimeout(hideFileToast, 2000); return; }
        appState.security.localLockHash = await sha256Hex(pass);
        appState.security.localLockEnabled = true;
        saveSecurity();
        updateSecurityUI();
        document.getElementById('localLockPassInput').value = '';
        showFileToast('Local lock enabled on this device');
        setTimeout(hideFileToast, 2000);
    });
    document.getElementById('localLockRemoveBtn')?.addEventListener('click', () => {
        appState.security.localLockEnabled = false;
        appState.security.localLockHash = '';
        saveSecurity();
        updateSecurityUI();
    });

    // Keyboard shortcut: Ctrl/Cmd + . toggles Focus Mode
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === '.') {
            e.preventDefault();
            toggleFocusMode();
        }
    });

    factoryResetBtn.addEventListener('click', () => {
        if (!confirm('This will reset ALL settings, API keys, prompts, and token counters. Are you sure?')) return;
        localStorage.removeItem('senpai_neural_v1');
        localStorage.removeItem('senpai_neural_v1_usage');
        localStorage.removeItem('senpai_neural_v1_convs');
        localStorage.removeItem('senpai_neural_v1_prompts');
        localStorage.removeItem('senpai_neural_v1_tabs');
        localStorage.removeItem('senpai_neural_v1_feedback');
        localStorage.removeItem('senpai_neural_v1_pinned');
        localStorage.removeItem('senpai_neural_v1_brain_nodes');
        localStorage.removeItem('senpai_neural_v1_brain_conns');
        localStorage.removeItem('senpai_neural_v1_memory');
        localStorage.removeItem('senpai_neural_v1_extras');
        localStorage.removeItem('senpai_neural_v1_a11y');
        localStorage.removeItem('senpai_neural_v1_security');
        location.reload();
    });

    // Export/Import profile
    exportProfileBtn.addEventListener('click', () => {
        const data = {
            settings: appState.settings,
            usage: appState.usage,
            promptLibrary: appState.settings.promptLibrary,
            tabs: appState.tabs,
            feedback: appState.feedback,
            pinned: appState.chat.pinnedMessages,
            memory: appState.memory,
            extras: { ...appState.extras, councilApiKey: '' }, // never export the comparison-provider key
            accessibility: appState.accessibility,
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `jarvis-profile-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showFileToast('Profile exported');
        setTimeout(hideFileToast, 2000);
    });

    importProfileBtn.addEventListener('click', () => {
        importProfileInput.click();
    });
    importProfileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (ev) => {
            try {
                const data = JSON.parse(ev.target.result);
                if (data.settings) {
                    // Restore settings (careful with API key)
                    if (data.settings.apiKey) {
                        appState.settings.apiKey = data.settings.apiKey;
                    }
                    delete data.settings.apiKey; // Don't overwrite with empty
                    Object.assign(appState.settings, data.settings);
                    // Restore other data
                    if (data.usage) Object.assign(appState.usage, data.usage);
                    if (data.promptLibrary) appState.settings.promptLibrary = data.promptLibrary;
                    if (data.tabs) appState.tabs = data.tabs;
                    if (data.feedback) appState.feedback = data.feedback;
                    if (data.pinned) appState.chat.pinnedMessages = data.pinned;
                    if (data.memory) Object.assign(appState.memory, data.memory);
                    if (data.extras) Object.assign(appState.extras, data.extras);
                    if (data.accessibility) Object.assign(appState.accessibility, data.accessibility);
                    // Save everything
                    await saveSettingsToStorage();
                    saveUsageToStorage();
                    savePromptLibrary();
                    saveTabs();
                    saveFeedback();
                    savePinned();
                    saveMemory();
                    saveExtras();
                    saveAccessibility();
                    // Reload UI
                    location.reload();
                } else {
                    showFileToast('Invalid profile file.', true);
                    setTimeout(hideFileToast, 2000);
                }
            } catch (err) {
                showFileToast('Error importing profile: ' + err.message, true);
                setTimeout(hideFileToast, 2000);
            }
        };
        reader.readAsText(file);
        importProfileInput.value = '';
    });

    // ════════════════════════════════════════════════════════════
    // INIT
    // ════════════════════════════════════════════════════════════
    function init() {
        loadSettings().then(() => {
            // Ensure we have at least one tab
            if (appState.tabs.tabs.length === 0) {
                addTab('Main');
            } else {
                // Switch to active tab
                const activeTab = appState.tabs.tabs.find(t => t.id === appState.tabs.activeTabId);
                if (!activeTab) {
                    // If active tab not found, switch to first
                    switchTab(appState.tabs.tabs[0].id);
                } else {
                    switchTab(activeTab.id);
                }
            }
            renderTabs();
            renderPinnedMessages();

            try {
                initThreeJS();
            } catch (err) {
                console.error('Three.js init error:', err);
            }

            renderDnaLegend();
            initSpeechRecognition();
            renderTokenGauge();

            try {
                initSenpaiLogoOrb();
            } catch (err) {
                console.error('SenPai CTA logo init error:', err);
            }
            initSenpaiCta();

            // ── New feature init: memory, extras, accessibility, security, PWA ──
            try {
                loadMemory(); loadExtras(); loadAccessibility(); loadSecurity();
                document.getElementById('memoryEnabledCheckbox').checked = appState.memory.enabled;
                renderMemoryList();
                document.getElementById('councilProviderSelect').value = appState.extras.councilProvider || '';
                document.getElementById('councilApiKeyInput').value = appState.extras.councilApiKey || '';
                document.getElementById('councilBaseUrlInput').value = appState.extras.councilBaseUrl || '';
                document.getElementById('tickerEnabledCheckbox').checked = appState.extras.tickerEnabled;
                if (appState.extras.tickerEnabled) setTickerEnabled(true);
                if (appState.extras.focusMode) document.body.classList.add('focus-mode');
                document.getElementById('fontScaleSlider').value = appState.accessibility.fontScale;
                document.getElementById('fontScaleValue').textContent = appState.accessibility.fontScale + '%';
                document.getElementById('reducedMotionCheckbox').checked = appState.accessibility.reducedMotion;
                document.getElementById('highContrastCheckbox').checked = appState.accessibility.highContrast;
                document.getElementById('dyslexiaFontCheckbox').checked = appState.accessibility.dyslexiaFont;
                applyAccessibility();
                updateSecurityUI();
                setupPWAExtra();
            } catch (err) {
                console.error('New-feature init error:', err);
            }

            addMessage('ai',
                '**先輩 SENPAI · NEURAL OS — ELON MUSK EDITION — ONLINE.**\n\n' +
                '🧬 **Living brain:** started at **1 neuron**. Every message you send grows it — ' +
                'watch the counter in the top HUD climb.\n\n' +
                '🎨 **10 DNA types**, one color each — Sensory, Cognitive, Memory, Logic, Emotion, ' +
                'Insight, Language, Creativity, Action, Energy. Open the DNA legend to see them.\n\n' +
                '🌌 **Cosmic Brain:** spiral galaxy growth, pulse network on every message, memory-beam ' +
                'recall, and topic-shifting nebula colors.\n\n' +
                '✅ **All prior features retained:** tabs, command palette, pin/edit/regenerate, ' +
                'regex search, encryption, Zen mode, import/export, and more.\n\n' +
                '🟠 **Agent Vibe** (click AGENT to enable): chain-of-thought, tools, mission mode, consciousness bar.\n\n' +
                '🔹 Ready for command. 🚀', {});

            chatInput.focus();
            updateScrollButton();

            setTimeout(() => {
                if (latencyDisplay.textContent === '--') {
                    latencyDisplay.textContent = Math.round(25 + Math.random() * 30);
                }
            }, 1800);

            console.log('%c先輩 SENPAI %cELON MUSK EDITION',
                'color:#58a6ff;font-size:18px;font-weight:900;font-family:Orbitron,monospace;',
                'color:#ffb347;font-size:18px;font-weight:700;');
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();