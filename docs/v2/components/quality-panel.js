/**
 * FARS v2 — Quality Panel Component
 * 集成 AI 痕迹检测 + 论文评审结果
 */
(function (root) {
  'use strict';

  var selectedPaperId = null;
  var radarChart = null;

  function render(container) {
    if (!container) return;
    var papers = window.FARSStore.getPapers();
    var paperOptions = papers.map(function (p) {
      return '<option value="' + p.id + '">' + (p.title || p.topic || '论文 #' + p.id) + '</option>';
    }).join('');

    container.innerHTML =
      '<div class="quality-section">' +
        '<div class="quality-section-title">选择论文</div>' +
        '<div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">' +
          '<select id="qpPaperSelect" style="flex:1">' +
            '<option value="">-- 选择论文 --</option>' +
            paperOptions +
          '</select>' +
          '<button class="btn btn-primary" id="qpLoadBtn">加载报告</button>' +
        '</div>' +
      '</div>' +

      '<div class="quality-section" id="qpAIDetection" style="display:none">' +
        '<div class="quality-section-title">🔍 AI 痕迹检测 (Fast-DetectGPT)</div>' +
        '<div id="qpAIDetectionContent"></div>' +
      '</div>' +

      '<div class="quality-section" id="qpPaperReview" style="display:none">' +
        '<div class="quality-section-title">📋 论文结构化评审 (Claude)</div>' +
        '<div id="qpPaperReviewContent"></div>' +
      '</div>' +

      '<div class="quality-section" id="qpFullPipeline" style="display:none">' +
        '<div class="quality-section-title">🚀 完整质量报告</div>' +
        '<div id="qpFullPipelineContent"></div>' +
      '</div>';

    bindEvents(container);
  }

  function bindEvents(container) {
    document.getElementById('qpLoadBtn').addEventListener('click', function () {
      var pid = parseInt(document.getElementById('qpPaperSelect').value, 10);
      if (!pid) { window.FARSV2.toast('请选择论文', 'error'); return; }
      selectedPaperId = pid;
      loadQualityPanel(pid);
    });
  }

  async function loadQualityPanel(paperId) {
    var aiSection = document.getElementById('qpAIDetection');
    var reviewSection = document.getElementById('qpPaperReview');
    var pipelineSection = document.getElementById('qpFullPipeline');

    aiSection.style.display = 'none';
    reviewSection.style.display = 'none';
    pipelineSection.style.display = 'none';

    // Run full pipeline
    var pipelineContent = document.getElementById('qpFullPipelineContent');
    pipelineContent.innerHTML = '<div class="loading-spinner"></div> 正在运行质量流水线...';
    pipelineSection.style.display = 'block';

    try {
      var paper = await FARSApi.getPaper(paperId);
      var content = (paper.paper && paper.paper.content) ? paper.paper.content : '';

      if (!content) {
        pipelineContent.innerHTML = '<div class="empty-state">论文内容为空</div>';
        return;
      }

      var result = await FARSApi.runQualityPipeline({
        paperId: paperId,
        title: paper.paper && paper.paper.title ? paper.paper.title : '',
      });

      var report = result.report || {};

      // Display AI Detection
      renderAIDetection(document.getElementById('qpAIDetectionContent'), report.ai_detection);
      aiSection.style.display = 'block';

      // Display Paper Review
      if (report.paper_review) {
        renderPaperReview(document.getElementById('qpPaperReviewContent'), report.paper_review);
        reviewSection.style.display = 'block';
      }

      // Display Full Report
      renderFullReport(pipelineContent, report);

    } catch (e) {
      pipelineContent.innerHTML = '<div class="empty-state">质量流水线执行失败: ' + e.message + '</div>';
    }
  }

  function renderAIDetection(container, detection) {
    if (!detection) {
      container.innerHTML = '<div class="empty-state">AI 检测未运行</div>';
      return;
    }

    var prob = detection.ai_probability || 0;
    var risk = detection.risk_level || 'unknown';
    var color = risk === 'high' ? 'var(--color-danger)' : risk === 'medium' ? 'var(--color-warning)' : 'var(--color-success)';

    container.innerHTML = '<div class="ai-detection-result">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
        '<span>AI 生成概率</span>' +
        '<span style="font-weight:700;font-size:18px;color:' + color + '">' + (prob * 100).toFixed(1) + '%</span>' +
      '</div>' +
      '<div class="detection-probability-bar risk-' + risk + '">' +
        '<div class="detection-probability-fill" style="width:' + (prob * 100) + '%"></div>' +
      '</div>' +
      '<div style="margin-top:8px;font-size:12px;color:var(--color-text-muted)">' +
        '风险级别: <span style="color:' + color + ';font-weight:600">' + risk.toUpperCase() + '</span> · ' +
        '置信度: ' + ((detection.confidence || 0) * 100).toFixed(0) + '%' +
      '</div>' +
      (detection.suspicious_segments && detection.suspicious_segments.length > 0 ?
        '<div class="suspicious-segments"><div style="font-size:11px;color:var(--color-text-dim);margin-bottom:4px">可疑段落:</div>' +
        detection.suspicious_segments.slice(0, 3).map(function (s) {
          return '<div class="suspicious-seg">' + escapeHtml(String(s).slice(0, 120)) + '</div>';
        }).join('') + '</div>' : ''
      ) +
      '<div style="margin-top:8px;font-size:11px;color:var(--color-text-dim)">' +
        '检测模型: ' + (detection.model_used || 'unknown') + ' · ' +
        '耗时: ' + ((detection.detection_time_ms || 0) / 1000).toFixed(1) + 's' +
      '</div>' +
    '</div>';
  }

  function renderPaperReview(container, review) {
    var dims = [
      { label: '创新性', key: 'originality_score' },
      { label: '严谨性', key: 'reproducibility_score' },
      { label: '价值', key: 'merit_score' },
      { label: '清晰度', key: 'clarity_score' },
      { label: '实用性', key: 'utility_score' },
    ];

    var dimsHtml = dims.map(function (d) {
      var score = review[d.key] || 0;
      var pass = score >= 6;
      return '<div class="dim-card">' +
        '<div class="dim-name">' + d.label + '</div>' +
        '<div class="dim-score' + (pass ? ' pass' : ' fail') + '">' + score.toFixed(1) + '/10</div>' +
      '</div>';
    }).join('');

    var overall = review.overall_score || 0;

    container.innerHTML =
      '<div style="margin-bottom:16px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
          '<span style="font-weight:600">综合评分</span>' +
          '<span style="font-size:28px;font-weight:700;color:' + (overall >= 6 ? 'var(--color-success)' : 'var(--color-danger)') + '">' + overall.toFixed(1) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="quality-dimensions">' + dimsHtml + '</div>' +
      (review.strengths && review.strengths.length > 0 ?
        '<div style="margin-top:16px"><div style="font-size:11px;color:var(--color-success);font-weight:600;margin-bottom:4px">优势</div>' +
        review.strengths.map(function (s) { return '<div style="font-size:12px;color:var(--color-text-muted)">• ' + escapeHtml(s) + '</div>'; }).join('') + '</div>' : ''
      ) +
      (review.weaknesses && review.weaknesses.length > 0 ?
        '<div style="margin-top:12px"><div style="font-size:11px;color:var(--color-danger);font-weight:600;margin-bottom:4px">不足</div>' +
        review.weaknesses.map(function (w) { return '<div style="font-size:12px;color:var(--color-text-muted)">• ' + escapeHtml(w) + '</div>'; }).join('') + '</div>' : ''
      ) +
      '<div style="margin-top:12px;font-size:11px;color:var(--color-text-dim)">评审模型: ' + (review.reviewer_model || 'unknown') + '</div>';
  }

  function renderFullReport(container, report) {
    var qr = report.quality_report || {};
    var aiScore = qr.total_score || 0;
    var status = qr.status || (aiScore >= 7 ? 'pass' : 'fail');

    // Build radar chart data from paper review dimensions
    var dims = [
      { label: '创新性', key: 'originality_score' },
      { label: '严谨性', key: 'reproducibility_score' },
      { label: '价值',   key: 'merit_score' },
      { label: '清晰度', key: 'clarity_score' },
      { label: '实用性', key: 'utility_score' },
    ];
    var review = report.paper_review || {};
    var radarLabels = dims.map(function(d) { return d.label; });
    var radarData = dims.map(function(d) { return review[d.key] || 0; });

    container.innerHTML =
      '<div class="quality-radar-container" style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">' +
        '<div style="flex:0 0 300px">' +
          '<canvas id="qualityRadarCanvas" width="300" height="300"></canvas>' +
        '</div>' +
        '<div style="flex:1;min-width:200px">' +
          '<div style="margin-bottom:12px">综合质量评分</div>' +
          '<div style="font-size:48px;font-weight:700;color:' + (aiScore >= 7 ? 'var(--color-success)' : 'var(--color-warning)') + '">' + aiScore.toFixed(1) + '</div>' +
          '<div style="font-size:12px;color:var(--color-text-muted);margin-top:4px">满分10分</div>' +
          '<div style="margin-top:16px">' +
            '<div class="compare-badge ' + status + '" style="display:inline-block;font-size:14px;padding:6px 20px;border-radius:20px">' +
              (status === 'pass' ? '✅ 达到发表标准' : '⚠️ 建议修改后提交') +
            '</div>' +
          '</div>' +
          '<div style="margin-top:16px;font-size:12px;color:var(--color-text-dim)">' +
            '<div>📊 AI痕迹: ' + ((report.ai_detection && report.ai_detection.ai_probability) ? (report.ai_detection.ai_probability * 100).toFixed(1) + '%' : '未检测') + '</div>' +
            '<div>📝 论文评审: ' + (review.overall_score ? review.overall_score.toFixed(1) + '/10' : '未评审') + '</div>' +
            '<div>🔍 模型: ' + (report.ai_detection && report.ai_detection.model_used || '-') + '</div>' +
          '</div>' +
        '</div>' +
      '</div>';

    // Render radar chart after DOM update
    setTimeout(function() {
      renderRadarChart('qualityRadarCanvas', radarLabels, radarData);
    }, 50);
  }

  function renderRadarChart(canvasId, labels, data) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;
    var ctx = canvas.getContext('2d');
    new Chart(ctx, {
      type: 'radar',
      data: {
        labels: labels,
        datasets: [{
          label: '质量评分',
          data: data,
          backgroundColor: 'rgba(124, 106, 247, 0.2)',
          borderColor: 'rgba(124, 106, 247, 0.9)',
          borderWidth: 2,
          pointBackgroundColor: 'rgba(124, 106, 247, 1)',
          pointRadius: 4,
        }]
      },
      options: {
        responsive: false,
        plugins: { legend: { display: false } },
        scales: {
          r: {
            min: 0, max: 10,
            ticks: { stepSize: 2, color: '#8b8fa8', backdropColor: 'transparent' },
            gridColor: 'rgba(46, 51, 80, 0.8)',
            pointLabels: { color: '#e2e4f0', font: { size: 11 } }
          }
        }
      }
    });
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ── Expose ── */
  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.quality = {
    render: render,
    load: loadQualityPanel,
  };
  root.FARSV2Render.qualityPanel = function() {
    render(document.getElementById('qualityPanel'));
  };

  root.addEventListener('DOMContentLoaded', function () {
    var panel = document.getElementById('qualityPanel');
    if (panel) render(panel);
  });

})(window);
