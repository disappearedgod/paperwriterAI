/**
 * FARS v2 Checkpoint Manager Component
 * 断点时间线
 */

class CheckpointManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.checkpoints = [];
        this.selectedCheckpoint = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="checkpoint-manager">
                <div class="panel-header">
                    <h3>断点管理</h3>
                    <div class="panel-actions">
                        <button id="create-checkpoint" class="btn btn-primary">创建断点</button>
                        <button id="refresh-checkpoints" class="btn btn-secondary">刷新</button>
                    </div>
                </div>
                
                <div class="checkpoint-layout">
                    <div class="checkpoint-timeline">
                        <div class="timeline-header">
                            <h4>断点时间线</h4>
                            <span class="checkpoint-count" id="checkpoint-count">0 个断点</span>
                        </div>
                        <div id="checkpoint-timeline" class="checkpoint-timeline">
                            <div class="loading">
                                <div class="spinner"></div>
                                <span>加载中...</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="checkpoint-detail" id="checkpoint-detail">
                        <div class="empty-state">
                            <p>选择一个断点查看详情</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            const checkpointsData = await this.api.getCheckpoints();
            this.checkpoints = checkpointsData.checkpoints || [];
            
            this.store.updateCheckpoints({
                list: this.checkpoints
            });
            
            this.updateCheckpointTimeline();
            
        } catch (error) {
            console.error('Failed to load checkpoints:', error);
            this.store.showToast('加载断点数据失败', 'error');
        }
    }
    
    updateCheckpointTimeline() {
        const timelineContainer = document.getElementById('checkpoint-timeline');
        const countElement = document.getElementById('checkpoint-count');
        
        countElement.textContent = `${this.checkpoints.length} 个断点`;
        
        if (this.checkpoints.length === 0) {
            timelineContainer.innerHTML = `
                <div class="empty-state">
                    <p>暂无断点数据</p>
                </div>
            `;
            return;
        }
        
        // Sort checkpoints by timestamp
        const sortedCheckpoints = [...this.checkpoints].sort((a, b) => 
            new Date(b.timestamp) - new Date(a.timestamp)
        );
        
        timelineContainer.innerHTML = `
            <div class="timeline">
                ${sortedCheckpoints.map((checkpoint, index) => `
                    <div class="timeline-item ${checkpoint.id === this.selectedCheckpoint?.id ? 'selected' : ''}" 
                         data-checkpoint-id="${checkpoint.id}">
                        <div class="timeline-marker ${this.getMarkerType(checkpoint.type)}">
                            <div class="marker-dot"></div>
                            ${index < sortedCheckpoints.length - 1 ? '<div class="marker-line"></div>' : ''}
                        </div>
                        <div class="timeline-content">
                            <div class="checkpoint-header">
                                <div class="checkpoint-title">${checkpoint.title || '未命名断点'}</div>
                                <div class="checkpoint-type ${checkpoint.type}">${this.getTypeText(checkpoint.type)}</div>
                            </div>
                            <div class="checkpoint-meta">
                                <span class="checkpoint-time">${this.formatDateTime(checkpoint.timestamp)}</span>
                                <span class="checkpoint-size">${this.formatSize(checkpoint.size)}</span>
                            </div>
                            <div class="checkpoint-description">${checkpoint.description || '无描述'}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        // Add click handlers
        timelineContainer.querySelectorAll('.timeline-content').forEach((content, index) => {
            content.addEventListener('click', () => {
                const checkpoint = sortedCheckpoints[index];
                this.selectCheckpoint(checkpoint);
            });
        });
    }
    
    selectCheckpoint(checkpoint) {
        this.selectedCheckpoint = checkpoint;
        this.updateCheckpointDetail();
    }
    
    updateCheckpointDetail() {
        const detailContainer = document.getElementById('checkpoint-detail');
        
        if (!this.selectedCheckpoint) {
            detailContainer.innerHTML = `
                <div class="empty-state">
                    <p>选择一个断点查看详情</p>
                </div>
            `;
            return;
        }
        
        const checkpoint = this.selectedCheckpoint;
        
        detailContainer.innerHTML = `
            <div class="detail-container">
                <div class="detail-header">
                    <h4>${checkpoint.title || '未命名断点'}</h4>
                    <div class="detail-actions">
                        <button class="btn btn-secondary btn-sm">编辑</button>
                        <button class="btn btn-primary btn-sm">恢复</button>
                        <button class="btn btn-danger btn-sm">删除</button>
                    </div>
                </div>
                
                <div class="checkpoint-overview">
                    <div class="overview-grid">
                        <div class="overview-item">
                            <label>类型</label>
                            <span class="type-badge ${checkpoint.type}">${this.getTypeText(checkpoint.type)}</span>
                        </div>
                        <div class="overview-item">
                            <label>创建时间</label>
                            <span>${this.formatDateTime(checkpoint.timestamp)}</span>
                        </div>
                        <div class="overview-item">
                            <label>大小</label>
                            <span>${this.formatSize(checkpoint.size)}</span>
                        </div>
                        <div class="overview-item">
                            <label>描述</label>
                            <span>${checkpoint.description || '无描述'}</span>
                        </div>
                    </div>
                </div>
                
                <div class="checkpoint-contents">
                    <div class="contents-header">
                        <h5>包含内容</h5>
                    </div>
                    <div class="contents-list">
                        ${this.renderContentsList(checkpoint.contents || [])}
                    </div>
                </div>
                
                <div class="checkpoint-logs">
                    <div class="logs-header">
                        <h5>断点日志</h5>
                    </div>
                    <div class="logs-content">
                        ${this.renderLogs(checkpoint.logs || [])}
                    </div>
                </div>
            </div>
        `;
    }
    
    renderContentsList(contents) {
        if (contents.length === 0) {
            return '<p class="no-contents">暂无内容</p>';
        }
        
        return contents.map(content => `
            <div class="content-item">
                <div class="content-icon">${this.getContentIcon(content.type)}</div>
                <div class="content-info">
                    <div class="content-name">${content.name}</div>
                    <div class="content-meta">
                        <span class="content-type">${content.type}</span>
                        <span class="content-size">${this.formatSize(content.size)}</span>
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    renderLogs(logs) {
        if (logs.length === 0) {
            return '<p class="no-logs">暂无日志</p>';
        }
        
        return logs.map(log => `
            <div class="log-entry">
                <span class="log-time">[${this.formatDateTime(log.timestamp)}]</span>
                <span class="log-level ${log.level}">${log.level.toUpperCase()}</span>
                <span class="log-message">${log.message}</span>
            </div>
        `).join('');
    }
    
    getContentIcon(type) {
        const iconMap = {
            'paper': '📄',
            'experiment': '⚗️',
            'hypothesis': '💡',
            'code': '💻',
            'data': '📊'
        };
        return iconMap[type] || '📁';
    }
    
    getTypeText(type) {
        const typeMap = {
            'manual': '手动',
            'auto': '自动',
            'milestone': '里程碑',
            'error': '错误恢复'
        };
        return typeMap[type] || type;
    }
    
    formatSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatDateTime(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN');
    }
    
    subscribeToState() {
        this.store.subscribe(
            (state) => {
                this.updateUI(state.checkpoints);
            },
            (state) => state.checkpoints
        );
    }
    
    updateUI(checkpointsState) {
        if (checkpointsState.list !== this.checkpoints) {
            this.checkpoints = checkpointsState.list;
            this.updateCheckpointTimeline();
        }
    }
    
    setupEventListeners() {
        // Create checkpoint button
        document.getElementById('create-checkpoint')?.addEventListener('click', () => {
            this.store.showToast('创建断点功能开发中', 'info');
        });
        
        // Refresh button
        document.getElementById('refresh-checkpoints')?.addEventListener('click', () => {
            this.loadData();
        });
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.checkpointManager = new CheckpointManager('checkpoints-container');
});