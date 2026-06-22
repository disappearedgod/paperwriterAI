/**
 * FARS v2 Quality Panel Component
 * AI检测+论文评审
 */

class QualityPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.qualityResults = [];
        this.selectedResult = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="quality-panel">
                <div class="panel-header">
                    <h3>质量评估</h3>
                    <div class="panel-actions">
                        <button id="run-quality-check" class="btn btn-primary">运行质量检查</button>
                        <button id="refresh-quality" class="btn btn-secondary">刷新</button>
                    </div>
                </div>
                
                <div class="quality-layout">
                    <div class="quality-list">
                        <div class="list-header">
                            <h4>评估结果</h4>
                            <span class="result-count" id="quality-count">0 个结果</span>
                        </div>
                        <div id="quality-list" class="quality-list">
                            <div class="loading">
                                <div class="spinner"></div>
                                <span>加载中...</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="quality-detail" id="quality-detail">
                        <div class="empty-state">
                            <p>选择一个评估结果查看详情</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            const qualityData = await this.api.getQualityResults();
            this.qualityResults = qualityData.results || [];
            
            this.store.updateQuality({
                results: this.qualityResults
            });
            
            this.updateQualityList();
            
        } catch (error) {
            console.error('Failed to load quality data:', error);
            this.store.showToast('加载质量数据失败', 'error');
        }
    }
    
    updateQualityList() {
        const listContainer = document.getElementById('quality-list');
        const countElement = document.getElementById('quality-count');
        
        countElement.textContent = `${this.qualityResults.length} 个结果`;
        
        if (this.qualityResults.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无评估结果</p>
                </div>
            `;
            return;
        }
        
        listContainer.innerHTML = this.qualityResults.map(result => `
            <div class="quality-item ${result.id === this.selectedResult?.id ? 'selected' : ''}" 
                 data-result-id="${result.id}">
                <div class="quality-header">
                    <div class="quality-title">${result.paper_title || '未命名论文'}</div>
                    <div class="quality-score ${this.getScoreClass(result.score)}">${result.score || 0}</div>
                </div>
                <div class="quality-meta">
                    <span class="quality-type">${result.check_type || '综合评估'}</span>
                    <span class="quality-date">${this.formatDate(result.created_at)}</span>
                </div>
            </div>
        `).join('');
        
        // Add click handlers
        listContainer.querySelectorAll('.quality-item').forEach(item => {
            item.addEventListener('click', () => {
                const resultId = item.dataset.resultId;
                this.selectResult(resultId);
            });
        });
    }
    
    selectResult(resultId) {
        this.selectedResult = this.qualityResults.find(r => r.id === resultId);
        this.updateQualityDetail();
    }
    
    updateQualityDetail() {
        const detailContainer = document.getElementById('quality-detail');
        
        if (!this.selectedResult) {
            detailContainer.innerHTML = `
                <div class="empty-state">
                    <p>选择一个评估结果查看详情</p>
                </div>
            `;
            return;
        }
        
        const result = this.selectedResult;
        
        detailContainer.innerHTML = `
            <div class="detail-container">
                <div class="detail-header">
                    <h4>${result.paper_title || '未命名论文'}</h4>
                    <div class="detail-actions">
                        <button class="btn btn-secondary btn-sm">导出报告</button>
                        <button class="btn btn-primary btn-sm">重新评估</button>
                    </div>
                </div>
                
                <div class="quality-overview">
                    <div class="score-card large">
                        <div class="score-value ${this.getScoreClass(result.score)}">${result.score || 0}</div>
                        <div class="score-label">综合评分</div>
                    </div>
                    
                    <div class="score-breakdown">
                        <div class="score-item">
                            <div class="score-label">AI检测</div>
                            <div class="score-bar">
                                <div class="score-fill" style="width: ${result.ai_detection_score || 0}%"></div>
                            </div>
                            <div class="score-value">${result.ai_detection_score || 0}%</div>
                        </div>
                        <div class="score-item">
                            <div class="score-label">学术规范</div>
                            <div class="score-bar">
                                <div class="score-fill" style="width: ${result.academic_score || 0}%"></div>
                            </div>
                            <div class="score-value">${result.academic_score || 0}%</div>
                        </div>
                        <div class="score-item">
                            <div class="score-label">创新性</div>
                            <div class="score-bar">
                                <div class="score-fill" style="width: ${result.innovation_score || 0}%"></div>
                            </div>
                            <div class="score-value">${result.innovation_score || 0}%</div>
                        </div>
                        <div class="score-item">
                            <div class="score-label">完整性</div>
                            <div class="score-bar">
                                <div class="score-fill" style="width: ${result.completeness_score || 0}%"></div>
                            </div>
                            <div class="score-value">${result.completeness_score || 0}%</div>
                        </div>
                    </div>
                </div>
                
                <div class="quality-details">
                    <div class="detail-tabs">
                        <button class="tab-btn active" data-tab="ai-detection">AI检测</button>
                        <button class="tab-btn" data-tab="peer-review">同行评审</button>
                        <button class="tab-btn" data-tab="recommendations">改进建议</button>
                    </div>
                    
                    <div class="detail-content">
                        <div id="ai-detection-content" class="tab-content active">
                            <div class="detection-results">
                                <div class="detection-header">
                                    <h5>AI生成内容检测</h5>
                                    <div class="detection-status ${result.ai_detected ? 'detected' : 'clean'}">
                                        ${result.ai_detected ? '检测到AI生成内容' : '未检测到AI生成内容'}
                                    </div>
                                </div>
                                <div class="detection-details">
                                    <div class="detail-item">
                                        <span class="label">置信度:</span>
                                        <span class="value">${result.ai_confidence || 0}%</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="label">检测模型:</span>
                                        <span class="value">${result.ai_model || 'Fast-DetectGPT'}</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="label">检测时间:</span>
                                        <span class="value">${this.formatDateTime(result.ai_detection_time)}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div id="peer-review-content" class="tab-content">
                            <div class="peer-review">
                                <div class="review-summary">
                                    <h5>同行评审摘要</h5>
                                    <p>${result.peer_review_summary || '暂无同行评审摘要'}</p>
                                </div>
                                <div class="review-comments">
                                    <h5>评审意见</h5>
                                    ${this.renderReviewComments(result.peer_review_comments || [])}
                                </div>
                            </div>
                        </div>
                        
                        <div id="recommendations-content" class="tab-content">
                            <div class="recommendations">
                                <h5>改进建议</h5>
                                ${this.renderRecommendations(result.recommendations || [])}
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
    
    renderReviewComments(comments) {
        if (comments.length === 0) {
            return '<p class="no-comments">暂无评审意见</p>';
        }
        
        return comments.map(comment => `
            <div class="review-comment">
                <div class="comment-header">
                    <span class="commenter">${comment.reviewer || '匿名评审'}</span>
                    <span class="comment-date">${this.formatDate(comment.date)}</span>
                </div>
                <div class="comment-content">${comment.content}</div>
                <div class="comment-rating">
                    <span>评分: ${comment.rating || 'N/A'}</span>
                </div>
            </div>
        `).join('');
    }
    
    renderRecommendations(recommendations) {
        if (recommendations.length === 0) {
            return '<p class="no-recommendations">暂无改进建议</p>';
        }
        
        return recommendations.map((rec, index) => `
            <div class="recommendation-item">
                <div class="recommendation-number">${index + 1}</div>
                <div class="recommendation-content">
                    <div class="recommendation-title">${rec.title}</div>
                    <div class="recommendation-description">${rec.description}</div>
                    <div class="recommendation-priority ${rec.priority}">优先级: ${rec.priority}</div>
                </div>
            </div>
        `).join('');
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
    
    getScoreClass(score) {
        if (score >= 80) return 'excellent';
        if (score >= 60) return 'good';
        if (score >= 40) return 'fair';
        return 'poor';
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
            (qualityState) => {
                this.updateUI(qualityState);
            },
            (state) => state.quality
        );
    }
    
    updateUI(qualityState) {
        if (qualityState.results !== this.qualityResults) {
            this.qualityResults = qualityState.results;
            this.updateQualityList();
        }
    }
    
    setupEventListeners() {
        // Run quality check button
        document.getElementById('run-quality-check')?.addEventListener('click', () => {
            this.store.showToast('运行质量检查功能开发中', 'info');
        });
        
        // Refresh button
        document.getElementById('refresh-quality')?.addEventListener('click', () => {
            this.loadData();
        });
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.qualityPanel = new QualityPanel('quality-container');
});
