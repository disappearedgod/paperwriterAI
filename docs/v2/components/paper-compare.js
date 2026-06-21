/**
 * FARS v2 — Paper Compare Component
 * 多论文卡片横排 + 指标对比表格
 */
(function (root) {
  'use strict';

  var chartInstances = {};

  function render(container) {
    if (!container) return;

    var papers = window.FARSStore.getPapers();

    if (papers.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无论文可对比</div>';
      return;
    }

    var html = '<div class="compare-grid">';
    papers.forEach(function (p) {
      var title = escapeHtml(p.title || p.topic || '论文 #' + p.id);
      var score = p.quality_score;
      var status = !score ? 'pending' : score >= 7 ? 'pass' : 'fail';
      var badge = status === 'pass' ? 'pass' : status === 'fail' ? 'fail' : 'pending';
      var badgeText = status === 'pass' ? '✅ 通过' : status === 'fail' ? '❌ 不合格' : '⏳ 待评估';
      var createdAt = p.created_at ? p.created_at.split('T')[0] : '';
      var scoreDisplay = score != null ? score.toFixed(1) + '/10' : '-';
      var iters = p.iteration_count || 0;
      var branchId = p.branch_id;

      html += '<div class="compare-card" data-paper-id="' + p.id + '">' +
        '<div class="compare-card-header">' +
          '<div class="compare-card-title" title="' + title + '">' + title.slice(0, 50) + (title.length > 50 ? '...' : '') + '</div>' +
          '<span class="compare-badge ' + badge + '">' + badgeText + '</span>' +
        '</div>' +
        '<div class="compare-metrics">' +
          '<div class="compare-metric">' +
            '<span class="compare-metric-label">综合评分</span>' +
            '<span class="compare-metric-value" style="color:' + (score >= 7 ? 'var(--color-success)' : score ? 'var(--color-danger)' : 'var(--color-text-muted)') + '">' + scoreDisplay + '</span>' +
          '</div>' +
          '<div class="compare-metric">' +
            '<span class="compare-metric-label">迭代次数</span>' +
            '<span class="compare-metric-value">' + iters + '</span>' +
          '</div>' +
          '<div class="compare-metric">' +
            '<span class="compare-metric-label">分支ID</span>' +
            '<span class="compare-metric-value">#' + branchId + '</span>' +
          '</div>' +
          '<div class="compare-metric">' +
            '<span class="compare-metric-label">生成日期</span>' +
            '<span class="compare-metric-value" style="font-size:11px">' + createdAt + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">' +
          '<button class="btn btn-sm btn-secondary paper-action" data-action="score" data-id="' + p.id + '">📊 评分</button>' +
          '<button class="btn btn-sm btn-secondary paper-action" data-action="improve" data-id="' + p.id + '">🔧 改进</button>' +
          '<button class="btn btn-sm btn-secondary paper-action" data-action="download" data-id="' + p.id + '">📥 下载</button>' +
        '</div>' +
      '</div>';
    });

    html += '</div>';
    container.innerHTML = html;

    bindCardEvents(container);
  }

  function bindCardEvents(container) {
    container.querySelectorAll('.paper-action').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var action = btn.dataset.action;
        var pid = parseInt(btn.dataset.id, 10);
        handlePaperAction(action, pid);
      });
    });
  }

  async function handlePaperAction(action, paperId) {
    switch (action) {
      case 'score':
        try {
          var result = await FARSApi.scorePaper(paperId);
          window.FARSV2.toast('评分完成: ' + (result.total_score || 'N/A') + '分', 'success');
          window.FARSV2.refresh();
        } catch (e) {
          window.FARSV2.toast('评分失败: ' + e.message, 'error');
        }
        break;

      case 'improve':
        try {
          var impResult = await FARSApi.improvePaper(paperId);
          window.FARSV2.toast('论文改进已生成', 'success');
          window.FARSV2.refresh();
        } catch (e) {
          window.FARSV2.toast('改进失败: ' + e.message, 'error');
        }
        break;

      case 'download':
        try {
          var list = await FARSApi.getDownloadList(paperId);
          var files = list.files || [];
          if (files.length === 0) {
            window.FARSV2.toast('暂无可下载文件', 'info');
            return;
          }
          // Download the first available file
          var firstFile = files.find(function (f) { return f.exists; });
          if (firstFile) {
            window.open(firstFile.url, '_blank');
          }
        } catch (e) {
          window.FARSV2.toast('下载失败: ' + e.message, 'error');
        }
        break;
    }
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ── Expose ── */
  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.paperCompare = render;
  root.FARSV2Render.compare = render;

  root.addEventListener('DOMContentLoaded', function () {
    var panel = document.getElementById('paperCompare');
    if (panel) render(panel);
  });

  /* Re-render when store changes */
  var prevSub = null;
  root.addEventListener('DOMContentLoaded', function () {
    prevSub = window.FARSStore.subscribe(function () {
      var panel = document.getElementById('paperCompare');
      if (panel) render(panel);
    });
  });

})(window);
