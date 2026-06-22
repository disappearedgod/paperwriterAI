/**
 * FARS v2 Paper Compare Component
 * 多论文对比
 */

class PaperCompare {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.selectedPapers = [];
        this.comparisonResults = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="paper-compare">
                <div class="panel-header">
                    <h3>论文对比</h3>
                    <div class="panel-actions">
                        <button id="compare-papers" class="btn btn-primary" disabled>对比选中论文</button>
                        <button id="clear-selection" class="btn btn-secondary">清除选择</button>
                    </div>
                </div>
                
                <div class="compare-layout">
                    <div class="paper-selection">
                        <div class="selection-header">
                            <h4>选择论文进行对比</h4>
                            <span class="selection-count" id="selection-count">已选择 0 篇</span>
                        </div>
                        <div id="paper-list" class="paper-list">
                            <div class="loading">
                                <div class="spinner"></div>
                                <span>加载中...</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="compare-results" id="compare-results">
                        <div class="empty-state">
                            <p>选择2-4篇论文进行对比分析</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            const papersData = await this.api.getPapers();
            this.papers = papersData.papers || [];
            
            this.store.updatePapers({
                list: this.papers
            });
            
            this.updatePaperList();
            
        } catch (error) {
            console.error('Failed to load papers:', error);
            this.store.showToast('加载论文数据失败', 'error');
        }
    }
    
    updatePaperList() {
        const listContainer = this.container.querySelector('#paper-list');
        
        if (!this.papers || this.papers.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无论文数据</p>
                </div>
            `;
            return;
        }
        
        listContainer.innerHTML = this.papers.map(paper => `
            <div class="paper-item ${this.isSelected(paper.id) ? 'selected' : ''}" 
                 data-paper-id="${paper.id}">
                <div class="paper-checkbox">
                    <input type="checkbox" ${this.isSelected(paper.id) ? 'checked' : ''}>
                </div>
                <div class="paper-info">
                    <div class="paper-title">${paper.title || '未命名论文'}</div>
                    <div class="paper-meta">
                        <span class="paper-id">ID: ${paper.id}</span>
                        <span class="paper-status ${paper.status}">${this.getStatusText(paper.status)}</span>
                    </div>
                    ${paper.paper_kind === 'reference_analysis' && paper.source_links && (paper.source_links.arxiv_url || paper.source_links.pdf_url)
                        ? `<div class="paper-meta" style="margin-top: 4px;">
                            <span style="opacity:.8;">原论文:</span>
                            ${paper.source_links.arxiv_url ? `<a href="${paper.source_links.arxiv_url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">arXiv</a>` : ''}
                            ${paper.source_links.pdf_url ? `<a href="${paper.source_links.pdf_url}" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="margin-left:8px;">PDF</a>` : ''}
                          </div>`
                        : ''}
                </div>
            </div>
        `).join('');
        
        // Add click handlers
        listContainer.querySelectorAll('.paper-item').forEach(item => {
            item.addEventListener('click', () => {
                const paperId = item.dataset.paperId;
                this.togglePaperSelection(paperId);
            });
        });
        
        // Update compare button state
        this.updateCompareButton();
    }
    
    isSelected(paperId) {
        return this.selectedPapers.includes(paperId);
    }
    
    togglePaperSelection(paperId) {
        const index = this.selectedPapers.indexOf(paperId);
        if (index === -1) {
            this.selectedPapers.push(paperId);
        } else {
            this.selectedPapers.splice(index, 1);
        }
        
        this.updatePaperList();
        this.updateSelectionCount();
        this.updateCompareButton();
    }
    
    updateSelectionCount() {
        const countElement = this.container.querySelector('#selection-count');
        countElement.textContent = `已选择 ${this.selectedPapers.length} 篇`;
    }
    
    updateCompareButton() {
        const compareBtn = this.container.querySelector('#compare-papers');
        compareBtn.disabled = this.selectedPapers.length < 2;
    }
    
    async runComparison() {
        if (this.selectedPapers.length < 2) {
            this.store.showToast('请选择至少2篇论文进行对比', 'warning');
            return;
        }
        
        try {
            this.store.setLoading(true);
            
            const result = await this.api.comparePapers(this.selectedPapers);
            this.comparisonResults = result;
            
            this.updateComparisonResults();
            this.store.showToast('对比分析完成', 'success');
            
        } catch (error) {
            console.error('Failed to compare papers:', error);
            this.store.showToast('对比分析失败: ' + error.message, 'error');
        } finally {
            this.store.setLoading(false);
        }
    }
    
    updateComparisonResults() {
        const resultsContainer = this.container.querySelector('#compare-results');
        
        if (!this.comparisonResults) {
            resultsContainer.innerHTML = `
                <div class="empty-state">
                    <p>选择2-4篇论文进行对比分析</p>
                </div>
            `;
            return;
        }
        
        const results = this.comparisonResults;
        
        resultsContainer.innerHTML = `
            <div class="comparison-container">
                <div class="comparison-header">
                    <h4>对比分析结果</h4>
                    <div class="comparison-actions">
                        <button class="btn btn-secondary btn-sm">导出报告</button>
                        <button class="btn btn-primary btn-sm">保存对比</button>
                    </div>
                </div>
                
                <div class="comparison-summary">
                    <div class="summary-card">
                        <div class="summary-value">${results.papers_compared || 0}</div>
                        <div class="summary-label">对比论文数</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-value">${results.avg_score || 0}</div>
                        <div class="summary-label">平均评分</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-value">${results.best_paper?.title || 'N/A'}</div>
                        <div class="summary-label">最佳论文</div>
                    </div>
                </div>
                
                <div class="comparison-table">
                    <table>
                        <thead>
                            <tr>
                                <th>指标</th>
                                ${results.papers?.map(paper => `<th>${paper.title || '论文'}</th>`).join('') || ''}
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>综合评分</td>
                                ${results.papers?.map(paper => `<td>${paper.score || 0}</td>`).join('') || ''}
                            </tr>
                            <tr>
                                <td>AI检测分数</td>
                                ${results.papers?.map(paper => `<td>${paper.ai_score || 0}%</td>`).join('') || ''}
                            </tr>
                            <tr>
                                <td>学术规范</td>
                                ${results.papers?.map(paper => `<td>${paper.academic_score || 0}%</td>`).join('') || ''}
                            </tr>
                            <tr>
                                <td>创新性</td>
                                ${results.papers?.map(paper => `<td>${paper.innovation_score || 0}%</td>`).join('') || ''}
                            </tr>
                            <tr>
                                <td>完整性</td>
                                ${results.papers?.map(paper => `<td>${paper.completeness_score || 0}%</td>`).join('') || ''}
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="comparison-charts">
                    <div class="chart-container">
                        <h5>评分雷达图</h5>
                        <div class="chart-placeholder">雷达图将在此显示</div>
                    </div>
                    <div class="chart-container">
                        <h5>评分对比柱状图</h5>
                        <div class="chart-placeholder">柱状图将在此显示</div>
                    </div>
                </div>
                
                <div class="comparison-insights">
                    <h5>对比洞察</h5>
                    <div class="insights-content">
                        ${results.insights?.map(insight => `
                            <div class="insight-item">
                                <div class="insight-title">${insight.title}</div>
                                <div class="insight-description">${insight.description}</div>
                            </div>
                        `).join('') || '<p>暂无对比洞察</p>'}
                    </div>
                </div>
            </div>
        `;
    }
    
    clearSelection() {
        this.selectedPapers = [];
        this.comparisonResults = null;
        
        this.updatePaperList();
        this.updateSelectionCount();
        this.updateComparisonResults();
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
    
    subscribeToState() {
        this.store.subscribe(
            (papersState) => {
                this.updateUI(papersState);
            },
            (state) => state.papers
        );
    }
    
    updateUI(papersState) {
        if (papersState.list !== this.papers) {
            this.papers = papersState.list;
            this.updatePaperList();
        }
    }
    
    setupEventListeners() {
        // Compare button
        this.container.querySelector('#compare-papers')?.addEventListener('click', () => {
            this.runComparison();
        });
        
        // Clear selection button
        this.container.querySelector('#clear-selection')?.addEventListener('click', () => {
            this.clearSelection();
        });
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.paperCompare = new PaperCompare('compare-container');
});
