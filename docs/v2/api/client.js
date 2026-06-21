/**
 * FARS v2 — REST API Client
 * 封装所有与 server.py 的通信
 */
(function (root) {
  'use strict';

  const BASE = ''; // 同源，server.py 提供静态文件和 API

  // ── Core fetch wrapper ───────────────────────────────────
  async function apiFetch(path, options) {
    const url = BASE + path;
    const opts = Object.assign({
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    }, options);

    const resp = await fetch(url, opts);
    const text = await resp.text();

    let data;
    try { data = JSON.parse(text); }
    catch { data = { error: 'Non-JSON response: ' + text.slice(0, 200) }; }

    if (!resp.ok) {
      const msg = (data && (data.error || data.message)) || `HTTP ${resp.status}`;
      const err = new Error(msg);
      err.status = resp.status;
      err.data = data;
      throw err;
    }

    return data;
  }

  // ── Research / Papers ────────────────────────────────────
  const FARSApi = {

    /* State */
    getResearchState: function () {
      return apiFetch('/api/research/state');
    },

    getResearchRun: function () {
      return apiFetch('/api/research/run');
    },

    /* Branches */
    getBranches: function () {
      return apiFetch('/api/branches');
    },

    createBranch: function (name, reviewContent) {
      return apiFetch('/api/branches', {
        method: 'POST',
        body: JSON.stringify({ name: name, review_content: reviewContent || '' }),
      });
    },

    switchBranch: function (branchId) {
      return apiFetch('/api/branches/switch/' + branchId, { method: 'POST' });
    },

    /* Papers */
    getPapers: function (branchId) {
      const url = '/api/papers' + (branchId ? '?branch_id=' + branchId : '');
      return apiFetch(url);
    },

    getPaper: function (paperId) {
      return apiFetch('/api/papers/' + paperId);
    },

    scorePaper: function (paperId) {
      return apiFetch('/api/papers/' + paperId + '/score', { method: 'POST' });
    },

    improvePaper: function (paperId) {
      return apiFetch('/api/papers/' + paperId + '/improve', { method: 'POST' });
    },

    getFinalStatus: function (paperId) {
      return apiFetch('/api/papers/' + paperId + '/final-status');
    },

    /* Research Control */
    startResearch: function (topic) {
      return apiFetch('/api/generate/start', {
        method: 'POST',
        body: JSON.stringify({ topic: topic || '' }),
      });
    },

    pauseResearch: function () {
      return apiFetch('/api/generate/pause', { method: 'POST' });
    },

    resumeResearch: function () {
      return apiFetch('/api/generate/resume', { method: 'POST' });
    },

    stopResearch: function () {
      return apiFetch('/api/generate/stop', { method: 'POST' });
    },

    generateNext: function (opts) {
      opts = opts || {};
      return apiFetch('/api/generate/next', {
        method: 'POST',
        body: JSON.stringify({ topic: opts.topic || '', branch_id: opts.branch_id }),
      });
    },

    /* Checkpoints */
    getCheckpoints: function () {
      return apiFetch('/api/research/checkpoints');
    },

    resumeCheckpoint: function (researchId) {
      return apiFetch('/api/research/resume/' + researchId, { method: 'POST' });
    },

    /* Research Logs */
    getResearchLogs: function (opts) {
      opts = opts || {};
      let url = '/api/research/logs?limit=' + (opts.limit || 50);
      if (opts.paperId) url += '&paper_id=' + opts.paperId;
      if (opts.researchId) url += '&research_id=' + opts.researchId;
      return apiFetch(url);
    },

    getResearchLogsSummary: function () {
      return apiFetch('/api/research/logs/summary');
    },

    /* Quality Pipeline */
    runQualityPipeline: function (opts) {
      opts = opts || {};
      return apiFetch('/api/quality/pipeline', {
        method: 'POST',
        body: JSON.stringify({
          paper_id: opts.paperId || null,
          content: opts.content || '',
          title: opts.title || '',
          run_ai_detection: opts.runAiDetection !== false,
          run_paper_review: opts.runPaperReview !== false,
          anthropic_api_key: opts.anthropicApiKey || '',
        }),
      });
    },

    detectAI: function (opts) {
      opts = opts || {};
      return apiFetch('/api/quality/detect-ai', {
        method: 'POST',
        body: JSON.stringify({
          content: opts.content || '',
          paper_id: opts.paperId || null,
        }),
      });
    },

    reviewPaper: function (opts) {
      opts = opts || {};
      return apiFetch('/api/quality/review-paper', {
        method: 'POST',
        body: JSON.stringify({
          title: opts.title || '',
          content: opts.content || '',
          paper_id: opts.paperId || null,
          anthropic_api_key: opts.anthropicApiKey || '',
        }),
      });
    },

    getQualityReport: function (paperId) {
      return apiFetch('/api/papers/' + paperId + '/quality-report');
    },

    /* External Review */
    submitExternalReview: function (paperId, email, venue) {
      return apiFetch('/api/papers/' + paperId + '/submit-review', {
        method: 'POST',
        body: JSON.stringify({ email: email, venue: venue || 'ICLR' }),
      });
    },

    getExternalReviewStatus: function (paperId) {
      return apiFetch('/api/papers/' + paperId + '/review-status');
    },

    pollExternalReview: function (paperId, intervalMinutes) {
      return apiFetch('/api/papers/' + paperId + '/poll-review', {
        method: 'POST',
        body: JSON.stringify({ interval_minutes: intervalMinutes || 1 }),
      });
    },

    /* Full Evaluation */
    evaluatePaper: function (paperId, opts) {
      opts = opts || {};
      return apiFetch('/api/papers/' + paperId + '/evaluate', {
        method: 'POST',
        body: JSON.stringify({
          email: opts.email || '',
          venue: opts.venue || 'ICLR',
          internal_threshold: opts.internalThreshold || 7.0,
          external_threshold: opts.externalThreshold || 5.0,
          submit_external: opts.submitExternal || false,
        }),
      });
    },

    /* Literature Review */
    generateLiteratureReview: function (topic) {
      return apiFetch('/api/research/literature-review', {
        method: 'POST',
        body: JSON.stringify({ topic: topic }),
      });
    },

    generateFullPaper: function (topic, template) {
      return apiFetch('/api/research/generate-full', {
        method: 'POST',
        body: JSON.stringify({ topic: topic, template: template || 'icml' }),
      });
    },

    reviewAndRevise: function (paperId, rounds) {
      return apiFetch('/api/research/review-and-revise', {
        method: 'POST',
        body: JSON.stringify({ paper_id: paperId, rounds: rounds || 2 }),
      });
    },

    /* LLM Config */
    getLLMConfig: function () {
      return apiFetch('/api/config/llm');
    },

    updateLLMConfig: function (llm, providers) {
      return apiFetch('/api/config/llm', {
        method: 'POST',
        body: JSON.stringify({ llm: llm || {}, llm_providers: providers || {} }),
      });
    },

    /* Data Registry */
    getDataRegistry: function () {
      return apiFetch('/api/data/registry');
    },

    /* Seed Papers */
    getSeedPapers: function () {
      return apiFetch('/api/seed-papers');
    },

    fetchSeedPapers: function (count) {
      return apiFetch('/api/seed-papers/fetch', {
        method: 'POST',
        body: JSON.stringify({ count: count || 15 }),
      });
    },

    /* Author Network */
    getAuthorNetwork: function () {
      return apiFetch('/api/research/author-network/latest');
    },

    /* History */
    getHistory: function () {
      return apiFetch('/api/history');
    },

    getHistoryDetail: function (recordId) {
      return apiFetch('/api/history/' + recordId);
    },

    /* Download */
    getDownloadList: function (paperId) {
      return apiFetch('/api/download/list?paper_id=' + paperId);
    },

    /* Improvements */
    getImprovements: function (branchId) {
      const url = '/api/improvements' + (branchId ? '?branch_id=' + branchId : '');
      return apiFetch(url);
    },

    saveImprovement: function (branchId, idea, paperId) {
      return apiFetch('/api/improvements', {
        method: 'POST',
        body: JSON.stringify({ branch_id: branchId, idea: idea, paper_id: paperId }),
      });
    },
  };

  // ── Export ────────────────────────────────────────────────
  root.FARSApi = FARSApi;

})(window);
