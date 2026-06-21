/**
 * FARS v2 — Checkpoint Manager Component
 * 可视化检查点时间线 + 从断点恢复
 */
(function (root) {
  'use strict';

  async function renderCheckpointList() {
    var container = document.getElementById('checkpointBody');
    if (!container) return;

    container.innerHTML = '<div class="loading-spinner"></div> 加载断点...';

    try {
      var data = await FARSApi.getCheckpoints();
      var checkpoints = data.checkpoints || [];

      if (checkpoints.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无断点记录</div>';
        return;
      }

      var html = '<div class="checkpoint-list">';

      checkpoints.forEach(function (cp) {
        var meta = cp.meta || {};
        var rid = cp.research_id || 'unknown';
        var topic = meta.topic || '';
        var updatedAt = meta.updated_at || meta.created_at || '';
        var date = updatedAt ? updatedAt.split('T')[0] : '';
        var time = updatedAt ? updatedAt.split('T')[1].slice(0, 5) : '';
        var hasCp = cp.has_checkpoint;

        html += '<div class="checkpoint-item">' +
          '<div class="cp-info">' +
            '<div class="cp-id">' + escapeHtml(rid) + '</div>' +
            '<div class="cp-meta">' + escapeHtml(topic) + ' · ' + date + ' ' + time + '</div>' +
          '</div>' +
          '<div style="display:flex;gap:6px;align-items:center">' +
            '<span style="font-size:11px;color:' + (hasCp ? 'var(--color-success)' : 'var(--color-text-dim)') + '">' +
              hasCp ? '✓ 有断点' : '无断点' +
            '</span>' +
            '<button class="btn btn-sm btn-primary cp-resume" data-rid="' + escapeAttr(rid) + '">📍 恢复</button>' +
          '</div>' +
        '</div>';
      });

      html += '</div>';
      container.innerHTML = html;

      // Bind resume events
      container.querySelectorAll('.cp-resume').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var rid = btn.dataset.rid;
          resumeCheckpoint(rid);
        });
      });

    } catch (e) {
      container.innerHTML = '<div class="empty-state">加载失败: ' + e.message + '</div>';
    }
  }

  async function resumeCheckpoint(researchId) {
    if (!confirm('确定要从断点 ' + researchId + ' 恢复研究吗？')) return;

    try {
      var result = await FARSApi.resumeCheckpoint(researchId);
      window.FARSV2.toast('正在从断点恢复研究...', 'success');
      window._closeModal && window._closeModal('modalCheckpoint');
      window.FARSV2.refresh();
    } catch (e) {
      window.FARSV2.toast('恢复失败: ' + e.message, 'error');
    }
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escapeAttr(s) {
    if (!s) return '';
    return String(s).replace(/"/g, '&quot;');
  }

  /* ── Expose ── */
  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.checkpoints = renderCheckpointList;
  root.FARSV2Render.checkpoint = renderCheckpointList; // alias

  root.addEventListener('DOMContentLoaded', function () {
    renderActivityLog();
  });

})(window);
