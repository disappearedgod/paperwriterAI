/**
 * FARS v2 LLM Monitor Component
 * LLM调用监控面板
 */

class LLMMonitor {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.llmCalls = [];
        this.selectedCall = null;
        this.stats = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
        this.setupAutoRefresh();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="llm-monitor">
                <div class="panel-header">
                    <h3>LLM调用监控</h3>
                    <div class="panel-actions">
                        <button id="refresh-llm" class="btn btn-secondary">刷新</button>
                        <button id="clear-logs" class="btn btn-danger btn-sm">清除日志</button>
                    </div>
                </div>
                
                <div class="monitor-stats">
                    <div class="llm-stats-grid">
                        <div class="stat-card">
                            <div class="stat-value" id="total-calls">0</div>
                            <div class="stat-label">总调用次数</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value success" id="success-rate">0%</div>
                            <div class="stat-label">成功率</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" id="total-tokens">0</div>
                            <div class="stat-label">总Token数</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value warning" id="avg-latency">0ms</div>
                            <div class="stat-label">平均延迟</div>
                        </div>
                    </div>
                </div>
                
                <div class="monitor-layout">
                    <div class="calls-list">
                        <div class="list-header">
                            <h4>调用记录</h4>
                            <div class="list-filters">
                                <select id="call-filter" class="select-input">
                                    <option value="all">全部</option>
                                    <option value="success">成功</option>
                                    <option value="failed">失败</option>
                                    <option value="pending">进行中</option>
                                </select>
                            </div>
                        </div>
                        <div id="calls-list" class="llm-calls-list">
                            <div class="loading">
                                <div class="spinner"></div>
                                <span>加载中...</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="call-detail" id="call-detail">
                        <div class="empty-state">
                            <p>选择一个调用记录查看详情</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            // Load stats
            this.stats = await this.api.getLLMCallStats();
            this.updateStats();
            
            // Load calls
            const callsData = await this.api.getLLMCalls();
            this.llmCalls = callsData.calls || [];
            
            this.store.updateLLMMonitoring({
                calls: this.llmCalls,
                stats: this.stats
            });
            
            this.updateCallsList();
            
        } catch (error) {
            console.error('Failed to load LLM data:', error);
            this.store.showToast('加载LLM监控数据失败', 'error');
        }
    }
    
    updateStats() {
        if (!this.stats) return;
        
        document.getElementById('total-calls').textContent = this.stats.total_calls || 0;
        document.getElementById('success-rate').textContent = `${this.stats.success_rate || 0}%`;
        document.getElementById('total-tokens').textContent = this.stats.total_tokens || 0;
        document.getElementById('avg-latency').textContent = `${this.stats.avg_latency || 0}ms`;
    }
    
    updateCallsList() {
        const listContainer = document.getElementById('calls-list');
        const filter = document.getElementById('call-filter')?.value || 'all';
        
        let filteredCalls = this.llmCalls;
        if (filter === 'success') {
            filteredCalls = this.llmCalls.filter(call => call.status === 'success');
        } else if (filter === 'failed') {
            filteredCalls = this.llmCalls.filter(call => call.status === 'failed');
        } else if (filter === 'pending') {
            filteredCalls = this.llmCalls.filter(call => call.status === 'pending');
        }
        
        if (filteredCalls.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无调用记录</p>
                </div>
            `;
            return;
        }
        
        listContainer.innerHTML = filteredCalls.map(call => `
            <div class="llm-call-row ${call.id === this.selectedCall?.id ? 'selected' : ''}" 
                 data-call-id="${call.id}">
                <div class="llm-call-header">
                    <div class="llm-call-method">${call.method || '未知方法'}</div>
                    <div class="llm-call-status ${call.status}">${this.getStatusText(call.status)}</div>
                </div>
                <div class="llm-call-stats">
                    <span>Token: ${call.total_tokens || 0}</span>
                    <span>延迟: ${call.latency || 0}ms</span>
                    <span>${this.formatTime(call.timestamp)}</span>
                </div>
                ${call.error ? `<div class="llm-call-error">错误: ${call.error}</div>` : ''}
            </div>
        `).join('');
        
        // Add click handlers
        listContainer.querySelectorAll('.llm-call-row').forEach(row => {
            row.addEventListener('click', () => {
                const callId = row.dataset.callId;
                this.selectCall(callId);
            });
        });
    }
    
    selectCall(callId) {
        this.selectedCall = this.llmCalls.find(c => c.id === callId);
        this.store.updateLLMMonitoring({ selectedCall: this.selectedCall });
        this.updateCallDetail();
    }
    
    updateCallDetail() {
        const detailContainer = document.getElementById('call-detail');
        
        if (!this.selectedCall) {
            detailContainer.innerHTML = `
                <div class="empty-state">
                    <p>选择一个调用记录查看详情</p>
                </div>
            `;
            return;
        }
        
        const call = this.selectedCall;
        
        detailContainer.innerHTML = `
            <div class="detail-container">
                <div class="detail-header">
                    <h4>${call.method || '未知方法'}</h4>
                    <div class="detail-actions">
                        <button class="btn btn-secondary btn-sm">复制请求</button>
                        <button class="btn btn-primary btn-sm">重试</button>
                    </div>
                </div>
                
                <div class="call-overview">
                    <div class="overview-grid">
                        <div class="overview-item">
                            <label>状态</label>
                            <span class="status-badge ${call.status}">${this.getStatusText(call.status)}</span>
                        </div>
                        <div class="overview-item">
                            <label>调用时间</label>
                            <span>${this.formatDateTime(call.timestamp)}</span>
                        </div>
                        <div class="overview-item">
                            <label>延迟</label>
                            <span>${call.latency || 0}ms</span>
                        </div>
                        <div class="overview-item">
                            <label>Token使用</label>
                            <span>${call.total_tokens || 0}</span>
                        </div>
                    </div>
                </div>
                
                <div class="call-details">
                    <div class="detail-tabs">
                        <button class="tab-btn active" data-tab="request">请求</button>
                        <button class="tab-btn" data-tab="response">响应</button>
                        <button class="tab-btn" data-tab="tokens">Token详情</button>
                        <button class="tab-btn" data-tab="error">错误信息</button>
                    </div>
                    
                    <div class="detail-content">
                        <div id="request-content" class="tab-content active">
                            <div class="request-content">
                                <div class="content-header">
                                    <h5>请求内容</h5>
                                    <button class="btn btn-sm btn-secondary">复制</button>
                                </div>
                                <pre class="content-block"><code>${this.formatJSON(call.request)}</code></pre>
                            </div>
                        </div>
                        
                        <div id="response-content" class="tab-content">
                            <div class="response-content">
                                <div class="content-header">
                                    <h5>响应内容</h5>
                                    <button class="btn btn-sm btn-secondary">复制</button>
                                </div>
                                <pre class="content-block"><code>${this.formatJSON(call.response)}</code></pre>
                            </div>
                        </div>
                        
                        <div id="tokens-content" class="tab-content">
                            <div class="tokens-content">
                                <div class="token-breakdown">
                                    <div class="token-item">
                                        <div class="token-label">提示词Token</div>
                                        <div class="token-value">${call.prompt_tokens || 0}</div>
                                    </div>
                                    <div class="token-item">
                                        <div class="token-label">完成Token</div>
                                        <div class="token-value">${call.completion_tokens || 0}</div>
                                    </div>
                                    <div class="token-item">
                                        <div class="token-label">总Token</div>
                                        <div class="token-value">${call.total_tokens || 0}</div>
                                    </div>
                                </div>
                                <div class="token-chart">
                                    <div class="chart-placeholder">Token使用图表将在此显示</div>
                                </div>
                            </div>
                        </div>
                        
                        <div id="error-content" class="tab-content">
                            <div class="error-content">
                                ${call.error ? `
                                    <div class="error-details">
                                        <div class="error-message">${call.error}</div>
                                        <div class="error-stack">${call.error_stack || '无堆栈信息'}</div>
                                    </div>
                                ` : `
                                    <div class="no-error">无错误信息</div>
                                `}
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
    
    formatJSON(data) {
        if (!data) return '无数据';
        try {
            if (typeof data === 'string') {
                return JSON.stringify(JSON.parse(data), null, 2);
            }
            return JSON.stringify(data, null, 2);
        } catch (e) {
            return typeof data === 'string' ? data : JSON.stringify(data);
        }
    }
    
    getStatusText(status) {
        const statusMap = {
            'success': '成功',
            'failed': '失败',
            'pending': '进行中',
            'timeout': '超时'
        };
        return statusMap[status] || status;
    }
    
    formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString('zh-CN');
    }
    
    formatDateTime(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN');
    }
    
    subscribeToState() {
        this.store.subscribe(
            (llmMonitoringState) => {
                this.updateUI(llmMonitoringState);
            },
            (state) => state.llmMonitoring
        );
    }
    
    updateUI(llmMonitoringState) {
        if (llmMonitoringState.calls !== this.llmCalls) {
            this.llmCalls = llmMonitoringState.calls;
            this.updateCallsList();
        }
        
        if (llmMonitoringState.stats !== this.stats) {
            this.stats = llmMonitoringState.stats;
            this.updateStats();
        }
    }
    
    setupEventListeners() {
        // Refresh button
        document.getElementById('refresh-llm')?.addEventListener('click', () => {
            this.loadData();
        });
        
        // Clear logs button
        document.getElementById('clear-logs')?.addEventListener('click', () => {
            this.store.showToast('清除日志功能开发中', 'info');
        });
        
        // Filter change
        document.getElementById('call-filter')?.addEventListener('change', () => {
            this.updateCallsList();
        });
    }
    
    setupAutoRefresh() {
        // Auto-refresh every 30 seconds
        setInterval(() => {
            this.loadData();
        }, 30000);
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.llmMonitor = new LLMMonitor('llm-monitor-container');
});
