/**
 * FARS v2 — Central State Store
 * 所有组件共享的单一数据源
 */
(function (root) {
  'use strict';

  const PHASES = ['ideation', 'planning', 'experiment', 'writing', 'review'];

  const FARSStore = {
    _state: {
      // Research state
      isGenerating: false,
      isPaused: false,
      currentBranch: null,
      currentBranchId: null,
      branches: [],
      papers: [],
      hypotheses: [],
      experiments: [],
      runs: [],
      currentRun: null,
      researchActivity: { phase: 'idle', message: '等待开始', progress: 0 },
      queueLength: 0,
      workflow: {},

      // Stats derived from papers
      stats: {
        papersTotal: 0,
        papersGenerated: 0,
        hypothesesTotal: 0,
        experimentsTotal: 0,
        avgScore: null,
      },

      // Quality
      qualityReports: {},   // paperId -> report
      aiDetectionResults: {}, // paperId -> result

      // Logs
      recentLogs: [],

      // Timestamp
      updatedAt: null,
    },

    listeners: [],

    /* ── Get full state ── */
    getState: function () {
      return this._state;
    },

    /* ── Get subset ── */
    getPhase: function () {
      return this._state.researchActivity.phase || 'idle';
    },

    getPapers: function () {
      return this._state.papers || [];
    },

    getBranches: function () {
      return this._state.branches || [];
    },

    getCurrentBranch: function () {
      return this._state.currentBranch;
    },

    getActivity: function () {
      return this._state.researchActivity;
    },

    getStats: function () {
      return this._state.stats;
    },

    getQualityReport: function (paperId) {
      return this._state.qualityReports[paperId];
    },

    /* ── Set full state (called after API fetch) ── */
    setState: function (data) {
      const prev = this._state;
      const next = Object.assign({}, prev, {
        isGenerating: !!data.is_generating,
        isPaused: !!data.is_paused,
        currentBranch: data.current_branch || null,
        currentBranchId: data.current_branch_id || null,
        branches: data.all_branches || [],
        papers: data.papers || [],
        hypotheses: data.hypotheses || [],
        experiments: data.experiments || [],
        runs: data.runs || [],
        currentRun: data.current_run || null,
        researchActivity: data.research_activity || { phase: 'idle', message: '等待开始', progress: 0 },
        queueLength: data.queue_length || 0,
        workflow: data.workflow || {},

        // Derive stats
        stats: deriveStats(data.papers || [], data.hypotheses || [], data.experiments || []),

        updatedAt: new Date().toISOString(),
      });

      this._state = next;
      this._notify(prev, next);
    },

    /* ── Add / update a paper ── */
    upsertPaper: function (paper) {
      const papers = this._state.papers.slice();
      const idx = papers.findIndex(function (p) { return p.id === paper.id; });
      if (idx >= 0) {
        papers[idx] = Object.assign({}, papers[idx], paper);
      } else {
        papers.push(paper);
      }
      this._state = Object.assign({}, this._state, {
        papers: papers,
        stats: deriveStats(papers, this._state.hypotheses, this._state.experiments),
      });
      this._notify(this._state, this._state);
    },

    /* ── Set quality report ── */
    setQualityReport: function (paperId, report) {
      const qr = Object.assign({}, this._state.qualityReports);
      qr[paperId] = report;
      this._state = Object.assign({}, this._state, { qualityReports: qr });
    },

    /* ── Set AI detection result ── */
    setAIDetectionResult: function (paperId, result) {
      const ad = Object.assign({}, this._state.aiDetectionResults);
      ad[paperId] = result;
      this._state = Object.assign({}, this._state, { aiDetectionResults: ad });
    },

    /* ── Set logs ── */
    setLogs: function (logs) {
      this._state = Object.assign({}, this._state, { recentLogs: logs.slice(0, 50) });
    },

    /* ── Subscribe ── */
    subscribe: function (fn) {
      this.listeners.push(fn);
      return function () {
        var i = this.listeners.indexOf(fn);
        if (i >= 0) this.listeners.splice(i, 1);
      }.bind(this);
    },

    _notify: function (prev, next) {
      this.listeners.forEach(function (fn) {
        try { fn(prev, next); } catch (e) { console.error('[FARSStore] listener error:', e); }
      });
    },

    /* ── Helpers ── */
    isPhaseActive: function (phase) {
      return this.getPhase() === phase;
    },

    isPhaseCompleted: function (phase) {
      var currentPhase = this.getPhase();
      var idx = PHASES.indexOf(phase);
      var currentIdx = PHASES.indexOf(currentPhase);
      return idx < currentIdx;
    },

    getPhaseIndex: function (phase) {
      return PHASES.indexOf(phase);
    },

    getPaperById: function (id) {
      return this._state.papers.find(function (p) { return p.id === id; });
    },

    PHASES: PHASES,
  };

  /* ── Stats derivation ── */
  function deriveStats(papers, hypotheses, experiments) {
    var generated = papers.filter(function (p) { return p.status === 'generated'; });
    var scored = papers.filter(function (p) { return p.quality_score != null; });
    var scores = scored.map(function (p) { return parseFloat(p.quality_score); }).filter(function (s) { return !isNaN(s); });
    var avg = scores.length > 0 ? scores.reduce(function (a, b) { return a + b; }, 0) / scores.length : null;

    return {
      papersTotal: papers.length,
      papersGenerated: generated.length,
      hypothesesTotal: hypotheses.length,
      experimentsTotal: experiments.length,
      avgScore: avg !== null ? Math.round(avg * 10) / 10 : null,
    };
  }

  /* ── Export ── */
  root.FARSStore = FARSStore;

})(window);
