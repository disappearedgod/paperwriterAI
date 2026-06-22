/**
 * FARS v2 Experiment Panel Component
 * 实验日志+代码+回测
 */

class ExperimentPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.experiments = [];
        this.selectedExperiment = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="experiment-panel">
                <div class="panel-header">
                    <h3>实验管理</h3>
                    <div class="panel-actions">
                        <button id="new-experiment" class="btn btn-primary">新建实验</button>
                        <button id="refresh-experiments" class="btn btn-secondary">刷新</button>
                    </div>
                </div>
                
                <div class="experiment-layout">
                    <div class="experiment-list">
                        <div class="list-header">
                            <h4>实验列表</h4>
                            <span class="experiment-count" id="experiment-count">0 个实验</span>
                        </div>
                        <div id="experiments-list" class="experiments-list">
                            <div class="loading">
                                <div class="spinner"></div>
                                <span>加载中...</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="experiment-detail" id="experiment-detail">
                        <div class="empty-state">
                            <p>选择一个实验查看详情</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            const experimentsData = await this.api.getExperiments();
            this.experiments = experimentsData.experiments || [];
            
            this.store.updateExperiments({
                list: this.experiments
            });
            
            this.updateExperimentList();
            
        } catch (error) {
            console.error('Failed to load experiments:', error);
            this.store.showToast('加载实验数据失败', 'error');
        }
    }
    
    updateExperimentList() {
        const listContainer = document.getElementById('experiments-list');
        const countElement = document.getElementById('experiment-count');
        
        countElement.textContent = `${this.experiments.length} 个实验`;
        
        if (this.experiments.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无实验数据</p>
                </div>
            `;
            return;
        }
        
        listContainer.innerHTML = this.experiments.map(experiment => `
            <div class="experiment-item ${experiment.id === this.selectedExperiment?.id ? 'selected' : ''}" 
                 data-experiment-id="${experiment.id}">
                <div class="experiment-header">
                    <div class="experiment-title">${experiment.title || '未命名实验'}</div>
                    <div class="experiment-status ${experiment.status}">${this.getStatusText(experiment.status)}</div>
                </div>
                <div class="experiment-meta">
                    <span class="experiment-id">ID: ${experiment.id}</span>
                    <span class="experiment-date">${this.formatDate(experiment.created_at)}</span>
                </div>
            </div>
        `).join('');
        
        // Add click handlers
        listContainer.querySelectorAll('.experiment-item').forEach(item => {
            item.addEventListener('click', () => {
                const experimentId = item.dataset.experimentId;
                this.selectExperiment(experimentId);
            });
        });
    }
    
    selectExperiment(experimentId) {
        this.selectedExperiment = this.experiments.find(e => e.id === experimentId);
        this.store.updateExperiments({ currentId: experimentId });
        this.updateExperimentDetail();
    }
    
    updateExperimentDetail() {
        const detailContainer = document.getElementById('experiment-detail');
        
        if (!this.selectedExperiment) {
            detailContainer.innerHTML = `
                <div class="empty-state">
                    <p>选择一个实验查看详情</p>
                </div>
            `;
            return;
        }
        
        const experiment = this.selectedExperiment;
        
        detailContainer.innerHTML = `
            <div class="detail-container">
                <div class="detail-header">
                    <h4>${experiment.title || '未命名实验'}</h4>
                    <div class="detail-actions">
                        <button class="btn btn-secondary btn-sm">编辑</button>
                        <button class="btn btn-danger btn-sm">删除</button>
                    </div>
                </div>
                
                <div class="detail-tabs">
                    <button class="tab-btn active" data-tab="overview">概览</button>
                    <button class="tab-btn" data-tab="code">代码</button>
                    <button class="tab-btn" data-tab="logs">日志</button>
                    <button class="tab-btn" data-tab="backtest">回测</button>
                </div>
                
                <div class="detail-content">
                    <div id="overview-content" class="tab-content active">
                        <div class="overview-grid">
                            <div class="overview-item">
                                <label>状态</label>
                                <span class="status-badge ${experiment.status}">${this.getStatusText(experiment.status)}</span>
                            </div>
                            <div class="overview-item">
                                <label>创建时间</label>
                                <span>${this.formatDateTime(experiment.created_at)}</span>
                            </div>
                            <div class="overview-item">
                                <label>更新时间</label>
                                <span>${this.formatDateTime(experiment.updated_at)}</span>
                            </div>
                            <div class="overview-item">
                                <label>描述</label>
                                <span>${experiment.description || '无描述'}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div id="code-content" class="tab-content">
                        <div class="code-editor">
                            <div class="editor-header">
                                <span>实验代码</span>
                                <button class="btn btn-sm btn-primary">运行</button>
                            </div>
                            <pre class="code-block"><code>${experiment.code || '# 实验代码\nimport pandas as pd\nimport numpy as np\n\n# 在此编写实验代码'}</code></pre>
                        </div>
                    </div>
                    
                    <div id="logs-content" class="tab-content">
                        <div class="logs-container">
                            <div class="logs-header">
                                <span>实验日志</span>
                                <button class="btn btn-sm btn-secondary">清除</button>
                            </div>
                            <div class="logs-content">
                                <div class="log-entry">
                                    <span class="log-time">[2026-06-20 12:00:00]</span>
                                    <span class="log-level info">INFO</span>
                                    <span class="log-message">实验开始</span>
                                </div>
                                <div class="log-entry">
                                    <span class="log-time">[2026-06-20 12:00:05]</span>
                                    <span class="log-level info">INFO</span>
                                    <span class="log-message">数据加载完成</span>
                                </div>
                                <div class="log-entry">
                                    <span class="log-time">[2026-06-20 12:00:10]</span>
                                    <span class="log-level warning">WARN</span>
                                    <span class="log-message">检测到异常值</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div id="backtest-content" class="tab-content">
                        <div class="backtest-container">
                            <div class="backtest-header">
                                <span>回测结果</span>
                                <button class="btn btn-sm btn-primary">运行回测</button>
                            </div>
                            <div class="backtest-results">
                                <div class="result-card">
                                    <div class="result-value success">+12.5%</div>
                                    <div class="result-label">年化收益率</div>
                                </div>
                                <div class="result-card">
                                    <div class="result-value">1.25</div>
                                    <div class="result-label">夏普比率</div>
                                </div>
                                <div class="result-card">
                                    <div class="result-value warning">-8.2%</div>
                                    <div class="result-label">最大回撤</div>
                                </div>
                            </div>
                            <div class="backtest-chart">
                                <div class="chart-placeholder">回测图表将在此显示</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Setup tab switching
        detailContainer.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                this.switchTab(tab);
            });
        });
    }
    
    switchTab(tabName) {
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // Update active tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}-content`);
        });
    }
    
    getStatusText(status) {
        const statusMap = {
            'running': '运行中',
            'completed': '已完成',
            'failed': '失败',
            'pending': '待处理',
            'paused': '已暂停'
        };
        return statusMap[status] || status;
    }
    
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
    
    subscribeToState() {
        this.store.subscribe(
            (experimentsState) => {
                this.updateUI(experimentsState);
            },
            (state) => state.experiments
        );
    }
    
    updateUI(experimentsState) {
        if (experimentsState.list !== this.experiments) {
            this.experiments = experimentsState.list;
            this.updateExperimentList();
        }
    }
    
    setupEventListeners() {
        // New experiment button
        document.getElementById('new-experiment')?.addEventListener('click', () => {
            this.store.showToast('创建新实验功能开发中', 'info');
        });
        
        // Refresh button
        document.getElementById('refresh-experiments')?.addEventListener('click', () => {
            this.loadData();
        });
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.experimentPanel = new ExperimentPanel('experiments-container');
});
