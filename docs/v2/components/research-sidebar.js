/**
 * FARS v2 Research Sidebar Component
 * 统计卡片+假设+论文列表
 */

class ResearchSidebar {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="research-sidebar">
                <div class="sidebar-header">
                    <h3>研究概览</h3>
                    <button id="refresh-research" class="btn btn-icon" title="刷新">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M23 4v6h-6M1 20v-6h6"/>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                    </button>
                </div>
                
                <div class="sidebar-stats">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value" id="total-papers">0</div>
                            <div class="stat-label">论文总数</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value success" id="successful-papers">0</div>
                            <div class="stat-label">成功论文</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value failed" id="failed-papers">0</div>
                            <div class="stat-label">失败论文</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value warning" id="total-hypotheses">0</div>
                            <div class="stat-label">假设数量</div>
                        </div>
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="section-header">
                        <h4>研究假设</h4>
                        <button id="add-hypothesis" class="btn btn-sm btn-primary">添加</button>
                    </div>
                    <div id="hypothesis-list" class="hypothesis-list">
                        <div class="loading">
                            <div class="spinner"></div>
                            <span>加载中...</span>
                        </div>
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="section-header">
                        <h4>论文列表</h4>
                        <div class="section-actions">
                            <select id="paper-filter" class="select-input">
                                <option value="all">全部</option>
                                <option value="successful">成功</option>
                                <option value="failed">失败</option>
                                <option value="pending">待处理</option>
                            </select>
                        </div>
                    </div>
                    <div id="paper-list" class="paper-list">
                        <div class="loading">
                            <div class="spinner"></div>
                            <span>加载中...</span>
                        </div>
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="section-header">
                        <h4>研究进度</h4>
                    </div>
                    <div class="research-progress">
                        <div class="progress-info">
                            <span>当前阶段:</span>
                            <span id="current-stage">等待开始</span>
                        </div>
                        <div class="progress-info">
                            <span>运行时间:</span>
                            <span id="run-time">00:00:00</span>
                        </div>
                        <div class="progress-info">
                            <span>完成度:</span>
                            <span id="completion-rate">0%</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            // Load papers
            const papersData = await this.api.getPapers();
            this.store.updatePapers({
                list: papersData.papers || [],
                totalCount: papersData.total || 0
            });
            
            // Load research status
            const researchData = await this.api.getResearchStatus();
            this.store.updateResearch({
                isRunning: researchData.is_running || false,
                isPaused: researchData.is_paused || false,
                currentTopic: researchData.current_topic,
                startTime: researchData.start_time,
                elapsed: researchData.elapsed || 0
            });
            
            // Update stats
            this.updateStats(papersData);
            
        } catch (error) {
            console.error('Failed to load research data:', error);
            this.store.showToast('加载研究数据失败', 'error');
        }
    }
    
    updateStats(papersData) {
        const papers = papersData.papers || [];
        
        document.getElementById('total-papers').textContent = papers.length;
        document.getElementById('successful-papers').textContent = 
            papers.filter(p => p.status === 'successful').length;
        document.getElementById('failed-papers').textContent = 
            papers.filter(p => p.status === 'failed').length;
        
        // For demo purposes, assume some hypotheses
        document.getElementById('total-hypotheses').textContent = Math.floor(papers.length * 0.3);
    }
    
    subscribeToState() {
        this.store.subscribe(
            (state) => {
                this.updateUI(state);
            },
            (state) => state
        );
    }
    
    updateUI(state) {
        // Update research progress
        const research = state.research;
        
        document.getElementById('current-stage').textContent = 
            research.isRunning ? (research.isPaused ? '已暂停' : '进行中') : '等待开始';
        
        if (research.startTime) {
            const startTime = new Date(research.startTime);
            const now = new Date();
            const elapsed = Math.floor((now - startTime) / 1000);
            document.getElementById('run-time').textContent = this.formatTime(elapsed);
        }
        
        // Update completion rate
        const papers = state.papers.list || [];
        const completed = papers.filter(p => p.status === 'completed').length;
        const total = papers.length;
        const rate = total > 0 ? Math.round((completed / total) * 100) : 0;
        document.getElementById('completion-rate').textContent = `${rate}%`;
        
        // Update paper list
        this.updatePaperList(state.papers.list, state.ui.paperFilter);
        
        // Update hypothesis list (simulated)
        this.updateHypothesisList();
    }
    
    updatePaperList(papers, filter = 'all') {
        const listContainer = document.getElementById('paper-list');
        
        if (!papers || papers.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无论文数据</p>
                </div>
            `;
            return;
        }
        
        let filteredPapers = papers;
        if (filter === 'successful') {
            filteredPapers = papers.filter(p => p.status === 'successful');
        } else if (filter === 'failed') {
            filteredPapers = papers.filter(p => p.status === 'failed');
        } else if (filter === 'pending') {
            filteredPapers = papers.filter(p => p.status === 'pending');
        }
        
        listContainer.innerHTML = filteredPapers.map(paper => `
            <div class="paper-item" data-paper-id="${paper.id}">
                <div class="paper-header">
                    <div class="paper-title">${paper.title || '未命名论文'}</div>
                    <div class="paper-status ${paper.status}">${this.getStatusText(paper.status)}</div>
                </div>
                <div class="paper-meta">
                    <span class="paper-id">ID: ${paper.id}</span>
                    <span class="paper-date">${this.formatDate(paper.created_at)}</span>
                </div>
            </div>
        `).join('');
        
        // Add click handlers
        listContainer.querySelectorAll('.paper-item').forEach(item => {
            item.addEventListener('click', () => {
                const paperId = item.dataset.paperId;
                this.store.updatePapers({ currentId: paperId });
                this.store.showToast(`选择了论文 ${paperId}`, 'info');
            });
        });
    }
    
    updateHypothesisList() {
        const listContainer = document.getElementById('hypothesis-list');
        
        // Simulated hypotheses for demo
        const hypotheses = [
            { id: 1, title: '基于注意力机制的量化选股策略', status: 'testing', confidence: 0.75 },
            { id: 2, title: '多因子模型在A股市场的有效性', status: 'validated', confidence: 0.82 },
            { id: 3, title: '深度学习在期货预测中的应用', status: 'pending', confidence: 0.68 }
        ];
        
        listContainer.innerHTML = hypotheses.map(hypothesis => `
            <div class="hypothesis-item" data-hypothesis-id="${hypothesis.id}">
                <div class="hypothesis-header">
                    <div class="hypothesis-title">${hypothesis.title}</div>
                    <div class="hypothesis-status ${hypothesis.status}">${this.getHypothesisStatusText(hypothesis.status)}</div>
                </div>
                <div class="hypothesis-confidence">
                    <span>置信度:</span>
                    <div class="confidence-bar">
                        <div class="confidence-fill" style="width: ${hypothesis.confidence * 100}%"></div>
                    </div>
                    <span class="confidence-value">${Math.round(hypothesis.confidence * 100)}%</span>
                </div>
            </div>
        `).join('');
    }
    
    getStatusText(status) {
        const statusMap = {
            'successful': '成功',
            'failed': '失败',
            'pending': '待处理',
            'completed': '已完成',
            'running': '进行中'
        };
        return statusMap[status] || status;
    }
    
    getHypothesisStatusText(status) {
        const statusMap = {
            'testing': '测试中',
            'validated': '已验证',
            'pending': '待验证',
            'rejected': '已拒绝'
        };
        return statusMap[status] || status;
    }
    
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-CN');
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.researchSidebar = new ResearchSidebar('research-container');
});