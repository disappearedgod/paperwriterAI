/**
 * FARS v2 — Experiment Panel Component
 * 回测日志流式展示 + 代码高亮 + 收益曲线
 */
(function (root) {
  'use strict';

  var currentPaperId = null;
  var currentTab = 'log';

  function render(container) {
    if (!container) return;
    container.innerHTML = getHTML();
    bindEvents(container);
  }

  function getHTML() {
    return '<div class="experiment-tabs">' +
      '<button class="exp-tab active" data-exp-tab="log">📄 日志</button>' +
      '<button class="exp-tab" data-exp-tab="code">💻 代码</button>' +
      '<button class="exp-tab" data-exp-tab="backtest">📈 回测</button>' +
    '</div>' +
    '<div class="experiment-content" id="expContent">' +
      '<div class="empty-state">选择一篇论文查看实验详情</div>' +
    '</div>';
  }

  function bindEvents(container) {
    container.querySelectorAll('.exp-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        container.querySelectorAll('.exp-tab').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentTab = btn.dataset.expTab;
        loadTabContent(currentPaperId);
      });
    });
  }

  async function loadTabContent(paperId) {
    currentPaperId = paperId;
    var content = document.getElementById('expContent');
    if (!content) return;

    if (!paperId) {
      content.innerHTML = '<div class="empty-state">选择一篇论文查看实验详情</div>';
      return;
    }

    content.innerHTML = '<div class="loading-spinner"></div> 加载中...';

    try {
      var paper = await FARSApi.getPaper(paperId);
      var artifacts = paper.paper && paper.paper.artifacts ? paper.paper.artifacts : {};

      if (currentTab === 'log') {
        await renderLog(content, paperId);
      } else if (currentTab === 'code') {
        await renderCode(content, artifacts);
      } else if (currentTab === 'backtest') {
        await renderBacktest(content, artifacts);
      }
    } catch (e) {
      content.innerHTML = '<div class="empty-state">加载失败: ' + e.message + '</div>';
    }
  }

  async function renderLog(content, paperId) {
    try {
      var logs = await FARSApi.getResearchLogs({ paperId: paperId, limit: 100 });
      var entries = logs.logs || [];

      if (entries.length === 0) {
        content.innerHTML = '<div class="empty-state">暂无实验日志</div>';
        return;
      }

      var html = '<div class="experiment-log-view">';
      entries.forEach(function (log) {
        var time = log.timestamp ? log.timestamp.split('T')[1].slice(0, 8) : '';
        var phase = log.status || 'info';
        var msg = log.message || '';
        html += '<div class="log-entry">' +
          '<span class="log-time">' + time + '</span>' +
          '<span class="log-phase" style="color:var(--color-primary)">' + phase + '</span>' +
          '<span class="log-msg">' + escapeHtml(msg) + '</span>' +
        '</div>';
      });
      html += '</div>';
      content.innerHTML = html;
    } catch (e) {
      content.innerHTML = '<div class="empty-state">日志加载失败: ' + e.message + '</div>';
    }
  }

  async function renderCode(content, artifacts) {
    var codePath = artifacts.code || artifacts.experiment_code || '';
    if (!codePath) {
      content.innerHTML = '<div class="empty-state">暂无实验代码</div>';
      return;
    }

    try {
      var resp = await fetch(codePath);
      var text = await resp.text();
      var highlighted = highlightPython(text);
      content.innerHTML = '<div class="experiment-log-view" style="max-height:500px;overflow:auto;">' +
        '<pre style="margin:0"><code>' + highlighted + '</code></pre>' +
        '<div style="margin-top:8px;text-align:right">' +
          '<button class="btn btn-sm btn-secondary" onclick="navigator.clipboard.writeText(document.querySelector(\'code\').textContent);FARSV2.toast(\'已复制\',\'success\')">📋 复制</button>' +
        '</div>' +
      '</div>';
    } catch (e) {
      content.innerHTML = '<div class="empty-state">代码加载失败: ' + e.message + '</div>';
    }
  }

  async function renderBacktest(content, artifacts) {
    var backtestPath = artifacts.backtest_results || artifacts.backtest || '';

    if (!backtestPath) {
      content.innerHTML = '<div class="empty-state">暂无回测结果</div>';
      return;
    }

    try {
      var resp = await fetch(backtestPath);
      var data = await resp.json();
      var html = '<div class="backtest-chart-container">' +
        '<div style="margin-bottom:12px;font-weight:600">回测结果</div>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">';

      var metrics = [
        { label: '年化收益率', value: data.annual_return ? (data.annual_return * 100).toFixed(2) + '%' : '-' },
        { label: '夏普比率', value: data.sharpe_ratio ? data.sharpe_ratio.toFixed(3) : '-' },
        { label: '最大回撤', value: data.max_drawdown ? (data.max_drawdown * 100).toFixed(2) + '%' : '-' },
        { label: '胜率', value: data.win_rate ? (data.win_rate * 100).toFixed(1) + '%' : '-' },
        { label: '盈亏比', value: data.profit_factor || '-' },
        { label: '交易次数', value: data.total_trades || '0' },
      ];

      metrics.forEach(function (m) {
        html += '<div class="dim-card">' +
          '<div class="dim-name">' + m.label + '</div>' +
          '<div class="dim-score' + (m.label === '年化收益率' && m.value !== '-' && parseFloat(m.value) > 0 ? ' pass' : '') + '">' + m.value + '</div>' +
        '</div>';
      });

      html += '</div></div>';
      content.innerHTML = html;
    } catch (e) {
      content.innerHTML = '<div class="empty-state">回测结果加载失败: ' + e.message + '</div>';
    }
  }

  /* ── Python syntax highlighter (simplified) ── */
  function highlightPython(code) {
    var keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 'return', 'import', 'from', 'as', 'try', 'except', 'with', 'yield', 'lambda', 'pass', 'break', 'continue', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is'];
    var builtins = ['print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'open', 'sorted', 'enumerate', 'zip', 'map', 'filter', 'any', 'all', 'sum', 'min', 'max', 'abs'];

    function esc(s) {
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    var lines = code.split('\n');
    var result = lines.map(function (line) {
      var out = '';
      var remaining = line;
      var tokenRe = /^(\s+)?([\w]+)(\()?/;
      while (remaining.length > 0) {
        var m = remaining.match(tokenRe);
        if (!m) {
          out += esc(remaining[0]);
          remaining = remaining.slice(1);
          continue;
        }
        var word = m[2];
        var after = m[3] || '';
        if (keywords.indexOf(word) >= 0) {
          out += '<span style="color:#c678dd">' + esc(word) + '</span>' + esc(after);
        } else if (builtins.indexOf(word) >= 0) {
          out += '<span style="color:#e5c07b">' + esc(word) + '</span>' + esc(after);
        } else if (/^\d/.test(word)) {
          out += '<span style="color:#d19a66">' + esc(word) + '</span>' + esc(after);
        } else {
          out += esc(word) + esc(after);
        }
        remaining = remaining.slice(m[0].length);
      }
      return out;
    });

    return result.join('\n');
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ── Expose for paper click ── */
  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.experiment = {
    render: render,
    loadPaper: loadTabContent,
  };
  // Also expose as direct function (for TAB_RENDERS)
  root.FARSV2Render.experimentPanel = function(paperId) {
    if (paperId) loadTabContent(paperId);
    else render(document.getElementById('experimentPanel') || document.querySelector('.experiment-panel'));
  };

  root.addEventListener('DOMContentLoaded', function () {
    var panel = document.getElementById('experimentPanel');
    if (panel) render(panel);
  });

})(window);
