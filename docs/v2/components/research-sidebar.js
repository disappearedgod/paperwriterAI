/**
 * FARS v2 — Research Sidebar Component
 * 研究统计卡片 + 假设列表 + 论文列表（响应式订阅）
 */
(function (root) {
  'use strict';

  /* ── Stats Cards ── */
  function renderStatsCards() {
    var container = document.getElementById('statsCards');
    if (!container) return;

    var stats = window.FARSStore.getStats();
    var state = window.FARSStore.getState();

    var html =
      '<div class="stat-card">' +
        '<div class="stat-value">' + stats.papersTotal + '</div>' +
        '<div class="stat-label">论文总数</div>' +
      '</div>' +
      '<div class="stat-card">' +
        '<div class="stat-value">' + stats.papersGenerated + '</div>' +
        '<div class="stat-label">已生成</div>' +
      '</div>' +
      '<div class="stat-card">' +
        '<div class="stat-value">' + stats.hypothesesTotal + '</div>' +
        '<div class="stat-label">假设数</div>' +
      '</div>' +
      '<div class="stat-card">' +
        '<div class="stat-value">' + (stats.avgScore !== null ? stats.avgScore + '分' : '-') + '</div>' +
        '<div class="stat-label">平均分</div>' +
      '</div>';

    container.innerHTML = html;
  }

  /* ── Hypothesis List ── */
  function renderHypothesisList() {
    var container = document.getElementById('hypothesisList');
    if (!container) return;

    var hyps = window.FARSStore.getState().hypotheses || [];
    if (hyps.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无假设</div>';
      return;
    }

    var currentBranchId = window.FARSStore.getCurrentBranchId();
    var html = '';
    hyps.slice(0, 10).forEach(function (h) {
      var text = h.hypothesis || h.text || h.content || '假设';
      var label = (text + '').slice(0, 60);
      var score = h.score != null ? '<span class="hyp-score">' + h.score.toFixed(2) + '</span>' : '';
      var statusIcon = h.status === 'validated' ? '✅' : h.status === 'rejected' ? '❌' : '🔬';
      html += '<div class="hyp-item" title="' + escapeHtml(label) + '">' +
        statusIcon + ' ' + escapeHtml(label) + score +
      '</div>';
    });

    if (hyps.length > 10) {
      html += '<div class="list-more">还有 ' + (hyps.length - 10) + ' 个假设...</div>';
    }

    container.innerHTML = html;
  }

  /* ── Paper List ── */
  function renderPaperList() {
    var container = document.getElementById('paperList');
    if (!container) return;

    var papers = window.FARSStore.getPapers();
    if (papers.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无论文</div>';
      return;
    }

    var currentBranchId = window.FARSStore.getCurrentBranchId();
    var html = '';
    papers.slice(0, 20).forEach(function (p) {
      var isActive = p.branch_id === currentBranchId;
      var title = (p.title || p.topic || '论文 #' + p.id).slice(0, 38);
      var statusIcon = p.status === 'generated' ? '✅' : p.status === 'failed' ? '❌' : '⏳';
      var score = p.quality_score != null ? '<span class="paper-score">' + p.quality_score.toFixed(1) + '</span>' : '';
      var branchTag = p.branch_id && p.branch_id !== currentBranchId ? '<span class="branch-tag">B' + p.branch_id + '</span>' : '';

      html += '<div class="paper-item' + (isActive ? ' active' : '') + '" ' +
        'data-paper-id="' + p.id + '" ' +
        'title="' + escapeHtml(title) + '">' +
        statusIcon + ' ' + escapeHtml(title) +
        score + branchTag +
      '</div>';
    });

    if (papers.length > 20) {
      html += '<div class="list-more">还有 ' + (papers.length - 20) + ' 篇论文...</div>';
    }

    container.innerHTML = html;

    container.querySelectorAll('.paper-item').forEach(function (el) {
      el.addEventListener('click', function () {
        var pid = parseInt(el.dataset.paperId, 10);
        if (window.FARSV2 && window.FARSV2.showPaperDetail) {
          window.FARSV2.showPaperDetail(pid);
        } else {
          window.FARSV2Pipeline.switchTab('experiments');
        }
      });
    });
  }

  /* ── Branch List ── */
  function renderBranchList() {
    var container = document.getElementById('branchList');
    if (!container) return;

    var branches = window.FARSStore.getBranches();
    var currentId = window.FARSStore.getCurrentBranchId();

    if (branches.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无分支</div>';
      return;
    }

    var html = '';
    branches.forEach(function (b) {
      var isActive = b.id === currentId;
      var count = b.papers_count !== undefined ? ' (' + b.papers_count + ')' : '';
      html += '<div class="branch-item' + (isActive ? ' active' : '') + '" ' +
        'data-branch-id="' + b.id + '">' +
        (isActive ? '👉 ' : '') + escapeHtml(b.name || '分支 #' + b.id) + count +
      '</div>';
    });

    container.innerHTML = html;

    container.querySelectorAll('.branch-item').forEach(function (el) {
      el.addEventListener('click', async function () {
        var bid = parseInt(el.dataset.branchId, 10);
        try {
          await FARSApi.switchBranch(bid);
          if (window.FARSV2) {
            window.FARSV2.toast('已切换到分支', 'success');
            window.FARSV2.refresh();
          }
        } catch (e) {
          if (window.FARSV2) window.FARSV2.toast('切换失败: ' + e.message, 'error');
        }
      });
    });
  }

  function renderAll() {
    renderStatsCards();
    renderHypothesisList();
    renderPaperList();
    renderBranchList();
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function init() {
    // Subscribe to store changes — re-render when papers, hypotheses, branches, or branch changes
    window.FARSStore.subscribe(function (prev, next) {
      if (prev.papers !== next.papers ||
          prev.hypotheses !== next.hypotheses ||
          prev.branches !== next.branches ||
          prev.currentBranchId !== next.currentBranchId ||
          prev.stats !== next.stats) {
        renderAll();
      }
    });

    renderAll();
  }

  /* ── Export ── */
  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.sidebar = renderAll;
  root.FARSV2Render.stats = renderStatsCards;
  root.FARSV2Render.papers = renderPaperList;
  root.FARSV2Render.hypotheses = renderHypothesisList;
  root.FARSV2Render.branches = renderBranchList;

  root.addEventListener('DOMContentLoaded', init);

})(window);
