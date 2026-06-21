/**
 * FARS v2 — Topology Graph Component
 * 作者关系网络 SVG 图 + 缩放/平移 + 节点点击交互
 */
(function (root) {
  'use strict';

  let svgEl = null;
  let transform = { k: 1, x: 0, y: 0 };
  let isDragging = false;
  let dragStart = { x: 0, y: 0 };
  let currentNetwork = null;

  /* ══════════════════════════════════════════
     LOAD & FETCH
  ══════════════════════════════════════════ */
  async function loadTopologyGraph() {
    var container = document.getElementById('topologyContainer');
    if (!container) return;

    container.innerHTML = '<div class="loading-spinner"></div> 加载作者关系网络...';

    try {
      var data = await FARSApi.getAuthorNetwork();
      var network = data.author_network || {};

      if (!network.authors || network.authors.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无作者关系数据' +
          '<br><button class="btn btn-sm btn-outline" onclick="FARSV2.fetchSeedPapers()">获取种子论文</button>' +
          '<br><button class="btn btn-sm btn-outline" onclick="FARSV2Render.topology()">刷新</button>' +
          '</div>';
        return;
      }

      currentNetwork = network;
      renderTopologySVG(container, network);
    } catch (e) {
      var msg = e.message || String(e);
      container.innerHTML = '<div class="empty-state">加载失败: ' + escapeHtml(msg) +
        '<br><button class="btn btn-sm btn-outline" onclick="FARSV2Render.topology()">重试</button></div>';
    }
  }

  /* ══════════════════════════════════════════
     SVG RENDER
  ══════════════════════════════════════════ */
  function renderTopologySVG(container, network) {
    var authors = network.authors || [];
    var institutions = network.institutions || [];
    var collabs = network.collaborations || [];

    var width = container.clientWidth || 800;
    var height = Math.max(450, authors.length * 32 + 120);

    // Circular force layout approximation
    var cx = width / 2;
    var cy = height / 2;
    var radius = Math.min(cx, cy) * 0.55;

    // Author nodes (inner ring)
    var nodes = authors.map(function (a, i) {
      var angle = (2 * Math.PI * i) / authors.length - Math.PI / 2;
      return {
        id: a.id,
        name: a.name,
        role: a.role,
        institution: a.institution || '',
        paperCount: a.paper_count || a.papers_count || 0,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        color: a.role === 'first' ? '#7c6af7' : a.role === 'corresponding' ? '#34d399' : '#60a5fa',
        r: a.role === 'first' ? 9 : 7,
      };
    });

    // Institution nodes (outer ring)
    var instMap = {};
    var instNodes = [];
    var uniqueInst = {};
    nodes.forEach(function (n) {
      if (n.institution && !uniqueInst[n.institution]) {
        uniqueInst[n.institution] = true;
        var idx = instNodes.length;
        var angle = (2 * Math.PI * idx) / Math.max(nodes.length, 1) - Math.PI / 2;
        instNodes.push({
          id: 'inst_' + idx,
          name: n.institution,
          x: cx + radius * 1.45 * Math.cos(angle),
          y: cy + radius * 1.45 * Math.sin(angle),
          color: '#fbbf24',
          r: 5,
          isInstitution: true,
        });
      }
      instMap[n.institution] = instNodes.find(function (i) { return i.name === n.institution; });
    });

    var allNodes = nodes.concat(instNodes);
    var nodeMap = {};
    allNodes.forEach(function (n) { nodeMap[n.id] = n; });

    // Build SVG
    var linesHtml = '';
    collabs.forEach(function (c) {
      var a1 = nodeMap[c.author1];
      var a2 = nodeMap[c.author2];
      if (a1 && a2) {
        var weight = Math.min(c.weight || 1, 4);
        linesHtml += '<line x1="' + a1.x + '" y1="' + a1.y + '" x2="' + a2.x + '" y2="' + a2.y + '" ' +
          'stroke="#2e3350" stroke-width="' + weight + '" opacity="0.55"/>';
      }
    });

    // Institution connections (dashed)
    nodes.forEach(function (n) {
      var inst = instMap[n.institution];
      if (inst) {
        linesHtml += '<line x1="' + n.x + '" y1="' + n.y + '" x2="' + inst.x + '" y2="' + inst.y + '" ' +
          'stroke="#2e3350" stroke-width="0.7" stroke-dasharray="3,3" opacity="0.35"/>';
      }
    });

    var nodeHtml = '';
    allNodes.forEach(function (n) {
      var tooltip = n.isInstitution
        ? n.name
        : n.name + ' (' + n.role + ')\n' + n.institution + '\n论文数: ' + n.paperCount;
      nodeHtml += '<circle ' +
        'class="topo-node' + (n.isInstitution ? ' topo-inst' : '') + '" ' +
        'cx="' + n.x + '" cy="' + n.y + '" r="' + n.r + '" ' +
        'fill="' + n.color + '" ' +
        'data-id="' + n.id + '" ' +
        'data-name="' + escapeHtml(n.name) + '" ' +
        'data-role="' + (n.role || '') + '" ' +
        'data-institution="' + escapeHtml(n.institution || '') + '" ' +
        'data-papers="' + n.paperCount + '" ' +
        'title="' + escapeHtml(tooltip) + '" ' +
        '/>';
      var label = (n.name || '').slice(0, 14);
      var ly = n.isInstitution ? n.y + n.r + 10 : n.y + n.r + 3;
      var lx = n.x + n.r + 3;
      nodeHtml += '<text x="' + lx + '" y="' + ly + '" ' +
        'font-size="' + (n.isInstitution ? '9' : '10') + '" ' +
        'fill="' + (n.isInstitution ? '#8b8fa8' : '#e2e4f0') + '" ' +
        'font-family="Inter,sans-serif" pointer-events="none">' +
        label + '</text>';
    });

    var svg = '<svg id=\"topoSvg\" width=\"100%\" height=\"' + height + '\" ' +
      'xmlns=\"http://www.w3.org/2000/svg\" style=\"background:#1a1d27;border-radius:12px;cursor:grab;user-select:none;\">' +
      '<defs>' +
        '<marker id=\"dot\" viewBox=\"0 0 10 10\" refX=\"8\" refY=\"5\" markerWidth=\"4\" markerHeight=\"4\" orient=\"auto\">' +
        '<circle cx=\"5\" cy=\"5\" r=\"3\" fill=\"#2e3350\"/></marker>' +
        '<filter id=\"glow\"><feGaussianBlur stdDeviation=\"2\" result=\"blur\"/><feMerge><feMergeNode in=\"blur\"/><feMergeNode in=\"SourceGraphic\"/></feMerge></filter>' +
      '</defs>' +
      '<g id=\"topoGroup\">' +
        '<rect width=\"100%\" height=\"' + height + '\" fill=\"transparent\"/>' +
        linesHtml +
        nodeHtml +
      '</g>' +
    '</svg>';

    container.innerHTML = svg;

    // Controls overlay
    var controls = '<div class="topo-controls">' +
      '<button class="btn btn-sm btn-outline" onclick="FARSV2Topo.zoomIn()" title="放大">➕</button>' +
      '<button class="btn btn-sm btn-outline" onclick="FARSV2Topo.zoomOut()" title="缩小">➖</button>' +
      '<button class="btn btn-sm btn-outline" onclick="FARSV2Topo.resetZoom()" title="重置">⟲</button>' +
      '<button class="btn btn-sm btn-outline" onclick="FARSV2Render.topology()" title="刷新">🔄</button>' +
    '</div>';

    // Legend
    var legend = '<div class="topo-legend">' +
      '<span class=\"legend-item\"><span class=\"legend-dot\" style=\"background:#7c6af7\"></span>第一作者</span>' +
      '<span class=\"legend-item\"><span class=\"legend-dot\" style=\"background:#34d399\"></span>通讯作者</span>' +
      '<span class=\"legend-item\"><span class=\"legend-dot\" style=\"background:#60a5fa\"></span>合作作者</span>' +
      '<span class=\"legend-item\"><span class=\"legend-dot\" style=\"background:#fbbf24\"></span>机构</span>' +
    '</div>';

    container.innerHTML = controls + legend + svg + '<div class="topo-detail" id="topoDetail" hidden></div>';

    svgEl = document.getElementById('topoSvg');

    // Zoom/pan
    svgEl.addEventListener('wheel', onWheel, { passive: false });
    svgEl.addEventListener('mousedown', onMouseDown);
    svgEl.addEventListener('mousemove', onMouseMove);
    svgEl.addEventListener('mouseup', onMouseUp);
    svgEl.addEventListener('mouseleave', onMouseUp);

    // Node click → show detail
    svgEl.querySelectorAll('.topo-node').forEach(function (circle) {
      circle.style.cursor = 'pointer';
      circle.addEventListener('click', function (e) {
        e.stopPropagation();
        showNodeDetail({
          id: circle.dataset.id,
          name: circle.dataset.name,
          role: circle.dataset.role,
          institution: circle.dataset.institution,
          paperCount: parseInt(circle.dataset.papers, 10) || 0,
          isInstitution: circle.classList.contains('topo-inst'),
        });
      });
    });

    // Click elsewhere → hide detail
    svgEl.addEventListener('click', function () { hideNodeDetail(); });
  }

  /* ══════════════════════════════════════════
     ZOOM / PAN
  ══════════════════════════════════════════ */
  function applyTransform() {
    var g = document.getElementById('topoGroup');
    if (!g) return;
    g.setAttribute('transform', 'translate(' + transform.x + ',' + transform.y + ') scale(' + transform.k + ')');
  }

  function onWheel(e) {
    e.preventDefault();
    var delta = e.deltaY > 0 ? 0.9 : 1.1;
    var rect = svgEl.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    transform.k = Math.max(0.3, Math.min(4, transform.k * delta));
    transform.x = mx - (mx - transform.x) * delta;
    transform.y = my - (my - transform.y) * delta;
    applyTransform();
  }

  function onMouseDown(e) {
    if (e.target.tagName === 'circle' || e.target.tagName === 'text') return;
    isDragging = true;
    dragStart = { x: e.clientX - transform.x, y: e.clientY - transform.y };
    svgEl.style.cursor = 'grabbing';
  }

  function onMouseMove(e) {
    if (!isDragging) return;
    transform.x = e.clientX - dragStart.x;
    transform.y = e.clientY - dragStart.y;
    applyTransform();
  }

  function onMouseUp() {
    isDragging = false;
    if (svgEl) svgEl.style.cursor = 'grab';
  }

  function zoomIn() { transform.k = Math.min(4, transform.k * 1.2); applyTransform(); }
  function zoomOut() { transform.k = Math.max(0.3, transform.k / 1.2); applyTransform(); }
  function resetZoom() { transform = { k: 1, x: 0, y: 0 }; applyTransform(); }

  /* ══════════════════════════════════════════
     NODE DETAIL
  ══════════════════════════════════════════ */
  function showNodeDetail(node) {
    var detail = document.getElementById('topoDetail');
    if (!detail) return;

    if (node.isInstitution) {
      detail.innerHTML = '<div class=\"topo-detail-card\">' +
        '<div class=\"detail-name\">' + escapeHtml(node.name) + '</div>' +
        '<div class=\"detail-role\">机构节点</div>' +
        '<button class=\"btn btn-sm btn-close-detail\" onclick=\"FARSV2Topo.hideDetail()\">✕</button>' +
      '</div>';
    } else {
      var roleLabel = node.role === 'first' ? '第一作者' : node.role === 'corresponding' ? '通讯作者' : '合作作者';
      detail.innerHTML = '<div class=\"topo-detail-card\">' +
        '<div class=\"detail-name\">' + escapeHtml(node.name) + '</div>' +
        '<div class=\"detail-role\">' + roleLabel + '</div>' +
        '<div class=\"detail-row\">🏛️ ' + escapeHtml(node.institution || '未知机构') + '</div>' +
        '<div class=\"detail-row\">📄 ' + node.paperCount + ' 篇论文</div>' +
        '<button class=\"btn btn-sm btn-close-detail\" onclick=\"FARSV2Topo.hideDetail()\">✕</button>' +
      '</div>';
    }
    detail.removeAttribute('hidden');
  }

  function hideNodeDetail() {
    var detail = document.getElementById('topoDetail');
    if (detail) detail.setAttribute('hidden', '');
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ══════════════════════════════════════════
     EXPORT
  ══════════════════════════════════════════ */
  root.FARSV2Topo = {
    load: loadTopologyGraph,
    zoomIn: zoomIn,
    zoomOut: zoomOut,
    resetZoom: resetZoom,
    showDetail: showNodeDetail,
    hideDetail: hideNodeDetail,
  };

  root.FARSV2Render = root.FARSV2Render || {};
  root.FARSV2Render.topology = loadTopologyGraph;

  /* Auto-load when topology tab is clicked */
  root.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        if (tab.dataset.tab === 'topology') {
          setTimeout(loadTopologyGraph, 80);
        }
      });
    });
  });

})(window);
