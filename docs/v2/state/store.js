/**
 * FARS v2 State Management
 * 集中状态管理（订阅/发布）
 */

class FARSStore {
    constructor() {
        this.state = {
            // Research state
            research: {
                isRunning: false,
                isPaused: false,
                currentTopic: null,
                startTime: null,
                elapsed: 0,
                selfHeal: null,
                lastActiveAt: null,
                stallSeconds: null
            },
            
            // Papers state
            papers: {
                list: [],
                currentId: null,
                totalCount: 0
            },
            
            // Branches state
            branches: {
                list: [],
                currentId: null
            },
            
            // Experiments state
            experiments: {
                list: [],
                currentId: null
            },
            
            // Quality state
            quality: {
                results: [],
                lastCheck: null
            },
            
            // LLM Monitoring state
            llmMonitoring: {
                calls: [],
                stats: null,
                selectedCall: null
            },
            
            // Topology state
            topology: {
                nodes: [],
                edges: []
            },
            
            // Checkpoints state
            checkpoints: {
                list: [],
                currentId: null
            },
            
            // UI state
            ui: {
                activeTab: 'pipeline',
                theme: localStorage.getItem('fars-theme') || 'dark',
                isLoading: false,
                toasts: []
            }
        };
        
        this.subscribers = new Map();
        this.history = [];
        this.maxHistorySize = 50;
    }
    
    // Get state
    getState() {
        return this.state;
    }
    
    // Get specific state slice
    getSlice(sliceName) {
        return this.state[sliceName];
    }
    
    // Update state
    setState(updater) {
        const prevState = { ...this.state };
        const newState = typeof updater === 'function' ? updater(this.state) : updater;
        
        // Deep merge
        this.state = this.deepMerge(this.state, newState);
        
        // Save history
        this.history.push({
            timestamp: Date.now(),
            prevState,
            newState: this.state
        });
        
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        }
        
        // Notify subscribers
        this.notifySubscribers(prevState, this.state);
    }
    
    // Subscribe to state changes
    subscribe(callback, selector) {
        const id = Symbol();
        this.subscribers.set(id, { callback, selector });
        
        return () => {
            this.subscribers.delete(id);
        };
    }
    
    // Notify subscribers
    notifySubscribers(prevState, newState) {
        this.subscribers.forEach(({ callback, selector }) => {
            if (selector) {
                const prevSlice = selector(prevState);
                const newSlice = selector(newState);
                if (prevSlice !== newSlice) {
                    callback(newSlice, prevSlice);
                }
            } else {
                callback(newState, prevState);
            }
        });
    }
    
    // Deep merge objects
    deepMerge(target, source) {
        const result = { ...target };
        
        for (const key of Object.keys(source)) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else {
                result[key] = source[key];
            }
        }
        
        return result;
    }
    
    // Update research state
    updateResearch(updates) {
        this.setState(state => ({
            ...state,
            research: {
                ...state.research,
                ...updates
            }
        }));
    }
    
    // Update papers state
    updatePapers(updates) {
        this.setState(state => ({
            ...state,
            papers: {
                ...state.papers,
                ...updates
            }
        }));
    }
    
    // Update branches state
    updateBranches(updates) {
        this.setState(state => ({
            ...state,
            branches: {
                ...state.branches,
                ...updates
            }
        }));
    }
    
    // Update experiments state
    updateExperiments(updates) {
        this.setState(state => ({
            ...state,
            experiments: {
                ...state.experiments,
                ...updates
            }
        }));
    }
    
    // Update quality state
    updateQuality(updates) {
        this.setState(state => ({
            ...state,
            quality: {
                ...state.quality,
                ...updates
            }
        }));
    }
    
    // Update LLM monitoring state
    updateLLMMonitoring(updates) {
        this.setState(state => ({
            ...state,
            llmMonitoring: {
                ...state.llmMonitoring,
                ...updates
            }
        }));
    }
    
    // Update topology state
    updateTopology(updates) {
        this.setState(state => ({
            ...state,
            topology: {
                ...state.topology,
                ...updates
            }
        }));
    }
    
    // Update checkpoints state
    updateCheckpoints(updates) {
        this.setState(state => ({
            ...state,
            checkpoints: {
                ...state.checkpoints,
                ...updates
            }
        }));
    }
    
    // Update UI state
    updateUI(updates) {
        this.setState(state => ({
            ...state,
            ui: {
                ...state.ui,
                ...updates
            }
        }));
    }
    
    // Show toast notification
    showToast(message, type = 'info', duration = 3000) {
        const id = Date.now();
        const toast = { id, message, type, timestamp: Date.now() };
        
        this.setState(state => ({
            ...state,
            ui: {
                ...state.ui,
                toasts: [...state.ui.toasts, toast]
            }
        }));
        
        // Auto remove after duration
        setTimeout(() => {
            this.removeToast(id);
        }, duration);
        
        return id;
    }
    
    // Remove toast notification
    removeToast(id) {
        this.setState(state => ({
            ...state,
            ui: {
                ...state.ui,
                toasts: state.ui.toasts.filter(t => t.id !== id)
            }
        }));
    }
    
    // Toggle theme
    toggleTheme() {
        const newTheme = this.state.ui.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('fars-theme', newTheme);
        this.updateUI({ theme: newTheme });
        document.documentElement.setAttribute('data-theme', newTheme);
    }
    
    // Set active tab
    setActiveTab(tab) {
        this.updateUI({ activeTab: tab });
    }
    
    // Set loading state
    setLoading(isLoading) {
        this.updateUI({ isLoading });
    }
    
    // Get history
    getHistory() {
        return this.history;
    }
    
    // Undo last action
    undo() {
        if (this.history.length > 0) {
            const lastChange = this.history.pop();
            this.state = lastChange.prevState;
            this.notifySubscribers(lastChange.newState, this.state);
        }
    }
    
    // Reset state
    reset() {
        const defaultState = this.getDefaultState();
        this.setState(defaultState);
    }
    
    getDefaultState() {
        return {
            research: {
                isRunning: false,
                isPaused: false,
                currentTopic: null,
                startTime: null,
                elapsed: 0
            },
            papers: {
                list: [],
                currentId: null,
                totalCount: 0
            },
            branches: {
                list: [],
                currentId: null
            },
            experiments: {
                list: [],
                currentId: null
            },
            quality: {
                results: [],
                lastCheck: null
            },
            llmMonitoring: {
                calls: [],
                stats: null,
                selectedCall: null
            },
            topology: {
                nodes: [],
                edges: []
            },
            checkpoints: {
                list: [],
                currentId: null
            },
            ui: {
                activeTab: 'pipeline',
                theme: localStorage.getItem('fars-theme') || 'dark',
                isLoading: false,
                toasts: []
            }
        };
    }
}

// 创建全局实例
window.farsStore = new FARSStore();

// 初始化主题
document.documentElement.setAttribute('data-theme', window.farsStore.getState().ui.theme);
