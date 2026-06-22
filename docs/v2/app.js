/**
 * FARS v2 Main Application
 * 主应用入口
 */

class FARSApp {
    constructor() {
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadInitialData();
        this.setupTheme();
        this.setupToastContainer();
        this.startPolling();
    }
    
    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.target.dataset.tab;
                this.switchTab(tabName);
            });
        });
        
        // Theme toggle
        document.getElementById('theme-toggle')?.addEventListener('click', () => {
            this.store.toggleTheme();
        });
        
        // Settings button
        document.getElementById('settings-btn')?.addEventListener('click', () => {
            this.store.showToast('设置功能开发中', 'info');
        });
        
        // Modal close
        document.getElementById('modal-close')?.addEventListener('click', () => {
            this.closeModal();
        });
        
        // Modal overlay click
        document.getElementById('modal-overlay')?.addEventListener('click', (e) => {
            if (e.target.id === 'modal-overlay') {
                this.closeModal();
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
    }
    
    async loadInitialData() {
        try {
            this.store.setLoading(true);
            
            // Load system status
            const status = await this.api.getStatus();
            console.log('System status:', status);
            
            // Load initial data for components
            await Promise.all([
                this.loadResearchData(),
                this.loadPapersData(),
                this.loadBranchesData()
            ]);
            
            this.store.showToast('系统加载完成', 'success');
            
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.store.showToast('系统加载失败: ' + error.message, 'error');
        } finally {
            this.store.setLoading(false);
        }
    }
    
    async loadResearchData() {
        try {
            const researchData = await this.api.getResearchStatus();
            this.store.updateResearch({
                isRunning: researchData.is_running || false,
                isPaused: researchData.is_paused || false,
                currentTopic: researchData.current_topic,
                startTime: researchData.start_time,
                elapsed: researchData.elapsed || 0,
                selfHeal: researchData.self_heal || null,
                lastActiveAt: researchData.last_active_at || null,
                stallSeconds: researchData.stall_seconds == null ? null : Number(researchData.stall_seconds)
            });
        } catch (error) {
            console.error('Failed to load research data:', error);
        }
    }
    
    async loadPapersData() {
        try {
            const papersData = await this.api.getPapers();
            this.store.updatePapers({
                list: papersData.papers || [],
                totalCount: papersData.total || 0
            });
        } catch (error) {
            console.error('Failed to load papers data:', error);
        }
    }
    
    async loadBranchesData() {
        try {
            const branchesData = await this.api.getBranches();
            this.store.updateBranches({
                list: branchesData.branches || [],
                currentId: branchesData.current_branch_id
            });
        } catch (error) {
            console.error('Failed to load branches data:', error);
        }
    }
    
    switchTab(tabName) {
        // Update active tab button
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });
        
        // Update active tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}-tab`);
        });
        
        // Update store
        this.store.setActiveTab(tabName);
        
        // Trigger component refresh if needed
        this.refreshComponent(tabName);
    }
    
    refreshComponent(tabName) {
        // Components will handle their own refresh via state subscriptions
        console.log(`Switched to tab: ${tabName}`);
    }
    
    setupTheme() {
        const theme = this.store.getState().ui.theme;
        document.documentElement.setAttribute('data-theme', theme);
    }
    
    setupToastContainer() {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }
        
        // Subscribe to toasts
        this.store.subscribe(
            (toasts) => {
                this.renderToasts(toasts);
            },
            (state) => state.ui.toasts
        );
    }
    
    renderToasts(toasts) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        
        container.innerHTML = toasts.map(toast => `
            <div class="toast ${toast.type}" data-toast-id="${toast.id}">
                <div class="toast-content">
                    <div class="toast-message">${toast.message}</div>
                    <button class="toast-close" onclick="farsApp.removeToast(${toast.id})">×</button>
                </div>
            </div>
        `).join('');
    }
    
    removeToast(id) {
        this.store.removeToast(id);
    }
    
    showModal(title, content) {
        const modalOverlay = document.getElementById('modal-overlay');
        const modalTitle = document.getElementById('modal-title');
        const modalBody = document.getElementById('modal-body');
        
        if (modalOverlay && modalTitle && modalBody) {
            modalTitle.textContent = title;
            modalBody.innerHTML = content;
            modalOverlay.classList.remove('hidden');
        }
    }
    
    closeModal() {
        const modalOverlay = document.getElementById('modal-overlay');
        if (modalOverlay) {
            modalOverlay.classList.add('hidden');
        }
    }
    
    showLoading(message = '加载中...') {
        this.store.setLoading(true);
        this.store.showToast(message, 'info');
    }
    
    hideLoading() {
        this.store.setLoading(false);
    }

    startPolling() {
        setInterval(() => {
            this.loadResearchData();
        }, 2000);
    }
    
    // Utility methods
    formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-CN');
    }
    
    formatDateTime(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN');
    }
    
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    window.farsApp = new FARSApp();

    console.log('FARS v2 application initialized');

    // Initialize all components
    window.pipelineView = new PipelineView('pipeline-container');
    window.researchSidebar = new ResearchSidebar('research-container');
    window.topologyGraph = new TopologyGraph('topology-container');
    window.experimentPanel = new ExperimentPanel('experiments-container');
    window.qualityPanel = new QualityPanel('quality-container');
    window.paperCompare = new PaperCompare('compare-container');
    window.checkpointManager = new CheckpointManager('checkpoints-container');
    window.llmMonitor = new LLMMonitor('llm-monitor-container');

    // Show welcome message
    setTimeout(() => {
        window.farsStore.showToast('欢迎使用 FARS v2 全自动科研系统', 'info');
    }, 1000);
});
