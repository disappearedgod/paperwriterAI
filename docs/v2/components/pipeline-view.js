/**
 * FARS v2 Pipeline View Component
 * 5阶段流水线可视化
 */

class PipelineView {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.stages = [
            { id: 'ideation', name: 'Ideation', title: '创意构思', icon: '💡', description: '论文阅读与假设生成' },
            { id: 'planning', name: 'Planning', title: '计划制定', icon: '📋', description: '实验计划制定' },
            { id: 'experiment', name: 'Experiment', title: '实验执行', icon: '⚗️', description: '实验执行与错误自愈' },
            { id: 'writing', name: 'Writing', title: '论文撰写', icon: '✍️', description: '论文撰写' },
            { id: 'quality', name: 'Quality', title: '质量评估', icon: '📝', description: 'AI检测+论文评审' }
        ];
        
        this.init();
    }
    
    init() {
        this.render();
        this.setupEventListeners();
        this.subscribeToState();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="pipeline-container">
                <div class="pipeline-header">
                    <h2>研究流水线</h2>
                    <div class="pipeline-controls">
                        <button id="start-research" class="btn btn-primary">开始研究</button>
                        <button id="resume-research" class="btn btn-primary" style="display:none;">继续</button>
                        <button id="recover-research" class="btn btn-primary" style="display:none;">恢复后台线程</button>
                        <button id="pause-research" class="btn btn-secondary" disabled>暂停</button>
                        <button id="stop-research" class="btn btn-danger" disabled>停止</button>
                    </div>
                </div>

                <div id="self-heal-banner" class="panel" style="display:none; padding:12px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; gap:12px; align-items:center;">
                        <div id="self-heal-text" style="line-height:1.35;"></div>
                        <button id="self-heal-recover" class="btn btn-secondary">恢复后台线程</button>
                    </div>
                </div>
                
                <div class="pipeline-stages">
                    ${this.stages.map(stage => this.renderStage(stage)).join('')}
                </div>
                
                <div class="pipeline-progress">
                    <div class="progress-bar">
                        <div id="progress-fill" class="progress-fill" style="width: 0%"></div>
                    </div>
                    <div class="progress-text">
                        <span id="progress-percentage">0%</span>
                        <span id="progress-status">等待开始</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderStage(stage) {
        const state = this.store.getSlice('research');
        const stageStatus = this.getStageStatus(stage.id, state);
        
        return `
            <div class="pipeline-stage ${stage.id}" data-stage="${stage.id}">
                <div class="stage-header">
                    <div class="stage-title">
                        <span class="stage-icon">${stage.icon}</span>
                        <span class="stage-name">${stage.title}</span>
                    </div>
                    <div class="stage-status ${stageStatus}">${this.getStatusText(stageStatus)}</div>
                </div>
                <div class="stage-content">
                    <p class="stage-description">${stage.description}</p>
                    <div class="stage-progress">
                        <div class="stage-progress-bar">
                            <div class="stage-progress-fill" style="width: ${this.getStageProgress(stage.id, state)}%"></div>
                        </div>
                        <span class="stage-progress-text">${this.getStageProgress(stage.id, state)}%</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    getStageStatus(stageId, researchState) {
        if (!researchState.isRunning) return 'pending';
        
        const currentStageIndex = this.stages.findIndex(s => s.id === stageId);
        const activeStageIndex = this.getActiveStageIndex(researchState);
        
        if (currentStageIndex < activeStageIndex) return 'completed';
        if (currentStageIndex === activeStageIndex) return 'active';
        return 'pending';
    }
    
    getActiveStageIndex(researchState) {
        // This would be determined by actual research progress
        // For now, simulate based on elapsed time
        if (!researchState.isRunning) return -1;
        
        const elapsed = researchState.elapsed || 0;
        const stageDuration = 30; // seconds per stage for demo
        
        return Math.min(Math.floor(elapsed / stageDuration), this.stages.length - 1);
    }
    
    getStageProgress(stageId, researchState) {
        if (!researchState.isRunning) return 0;
        
        const stageIndex = this.stages.findIndex(s => s.id === stageId);
        const activeStageIndex = this.getActiveStageIndex(researchState);
        
        if (stageIndex < activeStageIndex) return 100;
        if (stageIndex > activeStageIndex) return 0;
        
        // Calculate progress within current stage
        const elapsed = researchState.elapsed || 0;
        const stageDuration = 30;
        const stageElapsed = elapsed % stageDuration;
        
        return Math.min(Math.round((stageElapsed / stageDuration) * 100), 100);
    }
    
    getStatusText(status) {
        const statusMap = {
            'pending': '等待中',
            'active': '进行中',
            'completed': '已完成',
            'failed': '失败'
        };
        return statusMap[status] || status;
    }
    
    setupEventListeners() {
        // Start research button
        this.container.querySelector('#start-research').addEventListener('click', async () => {
            try {
                await this.api.startResearch('默认研究主题');
                await this.refreshResearchState();
                this.store.showToast('研究已开始', 'success');
            } catch (error) {
                this.store.showToast('启动研究失败: ' + error.message, 'error');
            }
        });

        this.container.querySelector('#resume-research').addEventListener('click', async () => {
            try {
                await this.api.resumeResearch();
                await this.refreshResearchState();
                this.store.showToast('已继续', 'success');
            } catch (error) {
                this.store.showToast('继续失败: ' + error.message, 'error');
            }
        });

        this.container.querySelector('#recover-research').addEventListener('click', async () => {
            try {
                await this.api.resumeResearch();
                await this.refreshResearchState();
                this.store.showToast('已恢复后台线程', 'success');
            } catch (error) {
                this.store.showToast('恢复失败: ' + error.message, 'error');
            }
        });
        
        // Pause research button
        this.container.querySelector('#pause-research').addEventListener('click', async () => {
            try {
                await this.api.pauseResearch();
                await this.refreshResearchState();
                this.store.showToast('研究已暂停', 'info');
            } catch (error) {
                this.store.showToast('暂停研究失败: ' + error.message, 'error');
            }
        });
        
        // Stop research button
        this.container.querySelector('#stop-research').addEventListener('click', async () => {
            try {
                await this.api.stopResearch();
                await this.refreshResearchState();
                this.store.showToast('研究已停止', 'warning');
            } catch (error) {
                this.store.showToast('停止研究失败: ' + error.message, 'error');
            }
        });

        this.container.querySelector('#self-heal-recover').addEventListener('click', async () => {
            try {
                await this.api.resumeResearch();
                await this.refreshResearchState();
                this.store.showToast('已恢复后台线程', 'success');
            } catch (error) {
                this.store.showToast('恢复失败: ' + error.message, 'error');
            }
        });
    }

    async refreshResearchState() {
        const researchData = await this.api.getResearchStatus();
        this.store.updateResearch({
            isRunning: researchData.is_running || researchData.is_generating || false,
            isPaused: researchData.is_paused || false,
            currentTopic: researchData.current_topic || null,
            startTime: researchData.start_time || null,
            elapsed: researchData.elapsed || 0,
            selfHeal: researchData.self_heal || null,
            lastActiveAt: researchData.last_active_at || null,
            stallSeconds: researchData.stall_seconds == null ? null : Number(researchData.stall_seconds)
        });
    }
    
    subscribeToState() {
        this.store.subscribe(
            (researchState) => {
                this.updateUI(researchState);
            },
            (state) => state.research
        );
    }
    
    updateUI(researchState) {
        // Update button states
        const startBtn = this.container.querySelector('#start-research');
        const resumeBtn = this.container.querySelector('#resume-research');
        const recoverBtn = this.container.querySelector('#recover-research');
        const pauseBtn = this.container.querySelector('#pause-research');
        const stopBtn = this.container.querySelector('#stop-research');
        const banner = this.container.querySelector('#self-heal-banner');
        const bannerText = this.container.querySelector('#self-heal-text');
        
        const heal = researchState.selfHeal || null;
        const showRecover = !!(heal && (heal.reason === 'runner_not_running' || heal.type === 'startup_self_heal' || heal.type === 'stall_auto_pause'));

        if (researchState.isPaused) {
            startBtn.style.display = 'none';
            pauseBtn.style.display = 'none';
            resumeBtn.style.display = showRecover ? 'none' : '';
            recoverBtn.style.display = showRecover ? '' : 'none';
            stopBtn.style.display = '';

            pauseBtn.disabled = true;
            stopBtn.disabled = false;
            resumeBtn.disabled = false;
            recoverBtn.disabled = false;
        } else if (researchState.isRunning) {
            startBtn.style.display = 'none';
            resumeBtn.style.display = 'none';
            recoverBtn.style.display = 'none';
            pauseBtn.style.display = '';
            stopBtn.style.display = '';

            pauseBtn.disabled = false;
            stopBtn.disabled = false;
        } else {
            startBtn.style.display = '';
            resumeBtn.style.display = 'none';
            recoverBtn.style.display = 'none';
            pauseBtn.style.display = '';
            stopBtn.style.display = '';

            startBtn.disabled = false;
            pauseBtn.disabled = true;
            stopBtn.disabled = true;
        }

        if (banner && bannerText) {
            if (researchState.isPaused && showRecover) {
                const reason = heal.reason || heal.type || '';
                const msg = heal.message || heal.title || '';
                const lastActive = researchState.lastActiveAt ? `最后活跃: ${researchState.lastActiveAt}` : '';
                const stall = researchState.stallSeconds == null ? '' : `停滞: ${researchState.stallSeconds}s`;
                const extra = [lastActive, stall].filter(Boolean).join(' · ');
                bannerText.textContent = `检测到后台线程异常已暂停（${reason}${msg ? `：${msg}` : ''}）${extra ? ` · ${extra}` : ''}`;
                banner.style.display = '';
            } else {
                banner.style.display = 'none';
            }
        }
        
        // Update progress bar
        const progressFill = this.container.querySelector('#progress-fill');
        const progressPercentage = this.container.querySelector('#progress-percentage');
        const progressStatus = this.container.querySelector('#progress-status');
        
        const progress = this.calculateOverallProgress(researchState);
        progressFill.style.width = `${progress}%`;
        progressPercentage.textContent = `${progress}%`;
        
        if (researchState.isRunning) {
            progressStatus.textContent = researchState.isPaused ? '已暂停' : '进行中';
        } else {
            progressStatus.textContent = '等待开始';
        }
        
        // Update stage statuses
        this.stages.forEach(stage => {
            const stageElement = this.container.querySelector(`[data-stage="${stage.id}"]`);
            if (stageElement) {
                const status = this.getStageStatus(stage.id, researchState);
                const statusElement = stageElement.querySelector('.stage-status');
                const progressFill = stageElement.querySelector('.stage-progress-fill');
                const progressText = stageElement.querySelector('.stage-progress-text');
                
                statusElement.className = `stage-status ${status}`;
                statusElement.textContent = this.getStatusText(status);
                
                const stageProgress = this.getStageProgress(stage.id, researchState);
                progressFill.style.width = `${stageProgress}%`;
                progressText.textContent = `${stageProgress}%`;
            }
        });
    }
    
    calculateOverallProgress(researchState) {
        if (!researchState.isRunning) return 0;
        
        let totalProgress = 0;
        this.stages.forEach(stage => {
            totalProgress += this.getStageProgress(stage.id, researchState);
        });
        
        return Math.round(totalProgress / this.stages.length);
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.pipelineView = new PipelineView('pipeline-container');
});
