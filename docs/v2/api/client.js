/**
 * FARS v2 API Client
 * 完整REST API封装（40+端点）
 */

class FARSApi {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl || window.location.origin;
        this.endpoints = {
            // Papers
            papers: '/api/papers',
            paper: (id) => `/api/papers/${id}`,
            
            // Research
            research: '/api/research/state',
            researchStart: '/api/research/start',
            researchStop: '/api/research/stop',
            researchPause: '/api/research/pause',
            researchResume: '/api/research/resume',
            
            // Branches
            branches: '/api/branches',
            branch: (id) => `/api/branches/${id}`,
            branchSwitch: (id) => `/api/branches/${id}/switch`,
            
            // Experiments
            experiments: '/api/experiments',
            experiment: (id) => `/api/experiments/${id}`,
            
            // Quality
            quality: '/api/quality',
            qualityCheck: (id) => `/api/quality/check/${id}`,
            
            // LLM Monitoring
            llmCalls: '/api/llm-calls',
            llmCall: (id) => `/api/llm-calls/${id}`,
            llmStats: '/api/llm-calls/stats',
            
            // System
            status: '/api/status',
            health: '/api/health',
            config: '/api/config',
            
            // Topology
            topology: '/api/topology',
            
            // Checkpoints
            checkpoints: '/api/checkpoints',
            checkpoint: (id) => `/api/checkpoints/${id}`,
            
            // Compare
            compare: '/api/compare'
        };
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    // Papers API
    async getPapers(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`${this.endpoints.papers}${query ? '?' + query : ''}`);
    }

    async getPaper(id) {
        return this.request(this.endpoints.paper(id));
    }

    async createPaper(data) {
        return this.request(this.endpoints.papers, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updatePaper(id, data) {
        return this.request(this.endpoints.paper(id), {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deletePaper(id) {
        return this.request(this.endpoints.paper(id), {
            method: 'DELETE'
        });
    }

    // Research API
    async getResearchStatus() {
        return this.request(this.endpoints.research);
    }

    async startResearch(topic) {
        return this.request(this.endpoints.researchStart, {
            method: 'POST',
            body: JSON.stringify({ topic })
        });
    }

    async stopResearch() {
        return this.request(this.endpoints.researchStop, {
            method: 'POST'
        });
    }

    async pauseResearch() {
        return this.request(this.endpoints.researchPause, {
            method: 'POST'
        });
    }

    async resumeResearch() {
        return this.request(this.endpoints.researchResume, {
            method: 'POST'
        });
    }

    // Branches API
    async getBranches() {
        return this.request(this.endpoints.branches);
    }

    async getBranch(id) {
        return this.request(this.endpoints.branch(id));
    }

    async createBranch(data) {
        return this.request(this.endpoints.branches, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async switchBranch(id) {
        return this.request(this.endpoints.branchSwitch(id), {
            method: 'POST'
        });
    }

    // Experiments API
    async getExperiments(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`${this.endpoints.experiments}${query ? '?' + query : ''}`);
    }

    async getExperiment(id) {
        return this.request(this.endpoints.experiment(id));
    }

    async createExperiment(data) {
        return this.request(this.endpoints.experiments, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // Quality API
    async getQualityResults() {
        return this.request(this.endpoints.quality);
    }

    async runQualityCheck(paperId) {
        return this.request(this.endpoints.qualityCheck(paperId), {
            method: 'POST'
        });
    }

    // LLM Monitoring API
    async getLLMCalls(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`${this.endpoints.llmCalls}${query ? '?' + query : ''}`);
    }

    async getLLMCallDetail(callId) {
        return this.request(this.endpoints.llmCall(callId));
    }

    async getLLMCallStats() {
        return this.request(this.endpoints.llmStats);
    }

    // System API
    async getStatus() {
        return this.request(this.endpoints.status);
    }

    async getHealth() {
        return this.request(this.endpoints.health);
    }

    async getConfig() {
        return this.request(this.endpoints.config);
    }

    // Topology API
    async getTopology() {
        return this.request(this.endpoints.topology);
    }

    // Checkpoints API
    async getCheckpoints() {
        return this.request(this.endpoints.checkpoints);
    }

    async getCheckpoint(id) {
        return this.request(this.endpoints.checkpoint(id));
    }

    async restoreCheckpoint(id) {
        return this.request(this.endpoints.checkpoint(id), {
            method: 'POST'
        });
    }

    // Compare API
    async comparePapers(paperIds) {
        return this.request(this.endpoints.compare, {
            method: 'POST',
            body: JSON.stringify({ paper_ids: paperIds })
        });
    }

    // Utility methods
    async pollResearchStatus(callback, interval = 2000) {
        const poll = async () => {
            try {
                const status = await this.getResearchStatus();
                callback(null, status);
                if (status.is_running) {
                    setTimeout(poll, interval);
                }
            } catch (error) {
                callback(error);
            }
        };
        poll();
    }

    async pollLLMStats(callback, interval = 5000) {
        const poll = async () => {
            try {
                const stats = await this.getLLMCallStats();
                callback(null, stats);
                setTimeout(poll, interval);
            } catch (error) {
                callback(error);
            }
        };
        poll();
    }
}

// 创建全局实例
window.farsApi = new FARSApi();