/**
 * FARS v2 — Pipeline View Component
 * 5阶段横向流水线 + 实时状态轮询 + 阶段详情展开
 */
(function (root) {
  'use strict';

  const PHASES = [
    { id: 'ideation',   label: 'Ideation',   icon: '💡', desc: '文献阅读与假设生成',   detail: 'Agent分析种子论文，提取研究空白，生成假设' },
    { id: 'planning',   label: 'Planning',   icon: '📋', desc: '实验计划制定',         detail: '设计实验方案：数据、因子、基准、回测周期' },
    { id: 'experiment', label: 'Experiment', icon: '🔬', desc: '因子挖掘与回测',       detail: '执行代码生成、运行回测、收集指标' },
    { id: 'writing',    label: 'Writing',    icon: '✍️',  desc: '论文撰写',            detail: '生成Introduction/Method/Experiment/Conclusion' },
    { id: 'review',     label: 'Review',     icon: '✅', desc: '质量评审',             detail: 'AI痕迹检测 + 论文结构化评审 + 综合报告' },
  ];

  const POLL_INTERVAL = 5000;
  let pollTimer = null;
  let expandedPhase = null;

  /* ── Activity log state ── */
  let activityLogs = [];
  let activityStream = null;

  /* RENDER */
  function renderPipelineView() {
    var container = document.getElementById('pipelineView');
    if (!container) return;

    var activity = window.FARSStore.getActivity();
    var currentPhase = activity.phase || 'idle';
    var progress = activity.progress || 0;

    var html = '<div class="pipeline-stages">';

    PHASES.forEach(function (phase, idx) {
      var isActive = phase.id === currentPhase;
      var isCompleted = window.FARSStore.isPhaseCompleted(phase.id);
      var isExpanded = expandedPhase === phase.id;

      var cls = 'pipeline-stage phase-' + phase.id;
      if (isActive) cls += ' active';
      if (isCompleted) cls += ' completed';
      if (isExpanded) cls += ' expanded';

      var progressFill = isActive ? Math.round(progress * 100) + '%' : (isCompleted ? '100%' : '0%');

      html += '<div class="' + cls + '" data-phase="' + phase.id + '">';

      html += '<div class="stage-header" onclick="FARSV2Pipeline.togglePhase(\'' + phase.id + '\')">';
      html += '<span class="stage-icon">' + phase.icon + '</span>';
      html += '<span class="stage-name">' + phase.label + '</span>';
      html += '<span class="stage-badge">';
      if (isCompleted) html += '<span class="badge badge-success">✓ 完成</span>';
      else if (isActive) html += '<span class="badge badge-active">进行中</span>';
      else html += '<span class="badge badge-idle">待执行</span>';
      html += '</span>';
      html += '<span class="stage-toggle">' + (isExpanded ? '▼' : '▶') + '</span>';
      html += '</div>';

      html += '<div class="stage-progress-bar">';
      html += '<div class="stage-progress-fill" style="width:' + progressFill + '"></div>';
      html += '</div>';

      if (isExpanded) {
        html += '<div class="stage-detail">';
        html += '<p class="stage-detail-desc">' + phase.detail + '</p>';
        if (isActive && activity.message) {
          html += '<div class="stage-detail-msg">📌 ' + escapeHtml(activity.message) + '</div>';
        }
        if (isCompleted) {
          html += '<button class="btn btn-sm btn-outline stage-action" onclick="FARSV2Pipeline.viewPhaseResult(\'' + phase.id + '\')">查看结果</button>';
        }
        html += '</div>';
      }

      if (idx < PHASES.length - 1) {
        var connectorClass = 'stage-connector';
        if (isCompleted) connectorClass += ' completed';
        html += '<div class="' + connectorClass + '"><span class="connector-line"></span><span class="connector-arrow">▶</span></div>';
      }

      html += '</div>';
    });

    html += '</div>';
    container.innerHTML = html;
  }

  function renderPipelineMini() {
    var container = document.getElementById('pipelineMini');
    if (!container) return;

    var currentPhase = window.FARSStore.getPhase();
    var html = '';

    PHASES.forEach(function (phase, idx) {
      var cls = 'pipeline-mini-dot';
      if (phase.id === currentPhase) cls += ' active';
      else if (window.FARSStore.isPhaseCompleted(phase.id)) cls += ' completed';
      html += '<div class="' + cls + '" title="' + phase.label + '"></div>';
      if (idx < PHASES.length - 1) {
        html += '<div class="pipeline-mini-connector' + (window.FARSStore.isPhaseCompleted(phase.id) ? ' completed' : '') + '"></div>';
      }
    });

    container.innerHTML = html;
  }

  function renderActivityLog() {
    var container = document.getElementById('activityLog');
    if (!container) return;

    var activity = window.FARSStore.getActivity();
    var phaseLabel = PHASES.find(function (p) { return p.id === activity.phase; });
    var phaseName = phaseLabel ? phaseLabel.label + ' ' + phaseLabel.icon : '';

    var html = '<div class="activity-header">';
    html += '<div class="activity-phase">' + phaseName + '</div>';
    html += '<div class="activity-meta">';
    html += '<span class="activity-time">' + formatTime(activity.timestamp) + '</span>';
    html += '<span class="activity-progress">' + Math.round((activity.progress || 0) * 100) + '%</span>';
    html += '</div></div>';

    if (activity.message) {
      html += '<div class="activity-message">' + escapeHtml(activity.message) + '</div>';
    }

    var logs = window.FARSStore.getState().recentLogs || [];
    if (logs.length > 0) {
      html += '<div class="activity-logs">';
      logs.slice(0, 20).forEach(function (log) {
        html += '<div class="log-entry log-' + (log.level || 'info') + '">';
        html += '<span class="log-time">' + formatTime(log.timestamp || log.time) + '</span>';
        html += '<span class="log-msg">' + escapeHtml(log.message || log.msg || '') + '</span>';
        html += '</div>';
      });
      html += '</div>';
    } else if (!activity.message) {
      html += '<div class="empty-state">等待开始...</div>';
    }

    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
  }

  function renderPipelineControls() {
    var state = window.FARSStore.getState();
    var btnStart = document.getElementById('btnStartResearch');
    var btnPause = document.getElementById('btnPauseResearch');
    var btnStop = document.getElementById('btnStopResearch');

    if (btnStart) btnStart.disabled = state.isGenerating;
    if (btnPause) {
      btnPause.disabled = !state.isGenerating;
      btnPause.textContent = state.isPaused ? '▶ 恢复' : '⏸️ 暂停';
    }
    if (btnStop) btnStop.disabled = !state.isGenerating && !state.isPaused;
  }

  function renderAll() {
    renderPipelineView();
    renderPipelineMini();
    renderActivityLog();
    renderPipelineControls();
  }

  /* POLLING */
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollActivity, POLL_INTERVAL);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollActivity() {
    try {
      var summary = await FARSApi.getResearchLogsSummary();
      if (summary && summary.activity) {
        var a = summary.activity;
        window.FARSStore._state.researchActivity = {
          phase: a.phase || 'idle',
          message: a.message || a.current_step || '',
          progress: a.progress || 0,
          timestamp: a.timestamp || new Date().toISOString(),
        };
      }
      var logs = await FARSApi.getResearchLogs({ limit: 30 });
      if (logs) {
        if (logs.logs) window.FARSStore.setLogs(logs.logs);
        else if (Array.isArray(logs)) window.FARSStore.setLogs(logs);
      }
      renderAll();
    } catch (e) {
      console.warn('[FARSV2Pipeline] poll error:', e);
    }
  }

  /* PUBLIC API */
  function togglePhase(phaseId) {
    expandedPhase = (expandedPhase === phaseId) ? null : phaseId;
    renderPipelineView();
  }

  function viewPhaseResult(phaseId) {
    var tabMap = { ideation: 'pipeline', planning: 'experiments', experiment: 'experiments', writing: 'pipeline', review: 'quality' };
    var tab = tabMap[phaseId] || 'pipeline';
    var tabEl = document.querySelector('.tab[data-tab="' + tab + '"]');
    if (tabEl) tabEl.click();
  }

  function switchTab(tabName) {
    var tabEl = document.querySelector('.tab[data-tab="' + tabName + '"]');
    if (tabEl) tabEl.click();
  }

  /* INIT */
  function init() {
    window.FARSStore.subscribe(function (prev, next) {
      if (prev.researchActivity !== next.researchActivity ||
          prev.recentLogs !== next.recentLogs ||
          prev.isGenerating !== next.isGenerating ||
          prev.isPaused !== next.isPaused) {
        renderAll();
      }
    });

    window.FARSStore.subscribe(function (prev, next) {
      if (next.isGenerating && !prev.isGenerating) startPolling();
      else if (!next.isGenerating && prev.isGenerating) { stopPolling(); pollActivity(); }
    });

    renderAll();
    var state = window.FARSStore.getState();
    if (state.isGenerating) startPolling();
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
  }

  function formatTime(ts) {
    if (!ts) return '';
    try { return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
    catch (e) { return String(ts).slice(11, 19); }
  }

  root.FARSV2Pipeline = {
    togglePhase: togglePhase,
    viewPhaseResult: viewPhaseResult,
    switchTab: switchTab,
    render: renderAll,
    startPolling: startPolling,
    stopPolling: stopPolling,
    pollActivity: pollActivity,
  };

  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.pipeline = renderPipelineView;
  root.FARSV2Render.pipelineMini = renderPipelineMini;
  root.FARSV2Render.activity = renderActivityLog;
  root.FARSV2Render.pipelineControls = renderPipelineControls;

  root.addEventListener('DOMContentLoaded', init);

})(window);
