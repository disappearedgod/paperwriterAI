/**
 * FARS v2 Topology Graph Component
 * 作者关系网络图（SVG）
 */

class TopologyGraph {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.store = window.farsStore;
        this.api = window.farsApi;
        
        this.width = 800;
        this.height = 600;
        this.nodes = [];
        this.edges = [];
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadData();
        this.setupEventListeners();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="topology-container">
                <div class="topology-header">
                    <h3>研究拓扑图</h3>
                    <div class="topology-controls">
                        <button id="zoom-in" class="btn btn-icon" title="放大">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/>
                                <path d="m21 21-4.35-4.35"/>
                                <path d="M11 8v6M8 11h6"/>
                            </svg>
                        </button>
                        <button id="zoom-out" class="btn btn-icon" title="缩小">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/>
                                <path d="m21 21-4.35-4.35"/>
                                <path d="M8 11h6"/>
                            </svg>
                        </button>
                        <button id="reset-view" class="btn btn-icon" title="重置视图">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                                <path d="M3 3v5h5"/>
                            </svg>
                        </button>
                    </div>
                </div>
                
                <div class="topology-graph-container">
                    <svg id="topology-svg" width="100%" height="100%"></svg>
                    
                    <div class="legend">
                        <div class="legend-item">
                            <div class="legend-color" style="background: var(--accent-blue)"></div>
                            <span>假设</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: var(--accent-yellow)"></div>
                            <span>实验</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: var(--accent-green)"></div>
                            <span>成功论文</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: var(--accent-red)"></div>
                            <span>失败论文</span>
                        </div>
                    </div>
                    
                    <div class="node-tooltip" id="node-tooltip"></div>
                </div>
            </div>
        `;
    }
    
    async loadData() {
        try {
            const topologyData = await this.api.getTopology();
            this.nodes = topologyData.nodes || [];
            this.edges = topologyData.edges || [];
            
            this.store.updateTopology({
                nodes: this.nodes,
                edges: this.edges
            });
            
            this.drawGraph();
            
        } catch (error) {
            console.error('Failed to load topology data:', error);
            // Generate demo data
            this.generateDemoData();
            this.drawGraph();
        }
    }
    
    generateDemoData() {
        // Demo nodes
        this.nodes = [
            { id: 1, type: 'hypothesis', title: '注意力机制选股', x: 100, y: 100 },
            { id: 2, type: 'hypothesis', title: '多因子模型', x: 200, y: 150 },
            { id: 3, type: 'experiment', title: '回测实验1', x: 150, y: 250 },
            { id: 4, type: 'experiment', title: '回测实验2', x: 250, y: 300 },
            { id: 5, type: 'paper', title: '成功论文', status: 'successful', x: 300, y: 200 },
            { id: 6, type: 'paper', title: '失败论文', status: 'failed', x: 400, y: 250 }
        ];
        
        // Demo edges
        this.edges = [
            { source: 1, target: 3 },
            { source: 2, target: 4 },
            { source: 3, target: 5 },
            { source: 4, target: 6 }
        ];
        
        this.store.updateTopology({
            nodes: this.nodes,
            edges: this.edges
        });
    }
    
    drawGraph() {
        const svg = document.getElementById('topology-svg');
        svg.innerHTML = '';
        
        // Create zoom group
        const zoomGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        zoomGroup.setAttribute('id', 'zoom-group');
        svg.appendChild(zoomGroup);
        
        // Draw edges
        this.edges.forEach(edge => {
            const sourceNode = this.nodes.find(n => n.id === edge.source);
            const targetNode = this.nodes.find(n => n.id === edge.target);
            
            if (sourceNode && targetNode) {
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', sourceNode.x);
                line.setAttribute('y1', sourceNode.y);
                line.setAttribute('x2', targetNode.x);
                line.setAttribute('y2', targetNode.y);
                line.setAttribute('class', 'edge');
                zoomGroup.appendChild(line);
            }
        });
        
        // Draw nodes
        this.nodes.forEach(node => {
            const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            group.setAttribute('class', 'node');
            group.setAttribute('transform', `translate(${node.x}, ${node.y})`);
            group.setAttribute('data-node-id', node.id);
            
            // Node circle
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('r', '20');
            circle.setAttribute('class', `node-${node.type}${node.type === 'paper' ? `-${node.status}` : ''}`);
            group.appendChild(circle);
            
            // Node label
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('dy', '35');
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('class', 'node-label');
            text.textContent = node.title;
            group.appendChild(text);
            
            zoomGroup.appendChild(group);
            
            // Add hover events
            group.addEventListener('mouseenter', (e) => this.showTooltip(e, node));
            group.addEventListener('mouseleave', () => this.hideTooltip());
            group.addEventListener('click', () => this.onNodeClick(node));
        });
        
        // Set viewBox
        this.updateViewBox();
    }
    
    updateViewBox() {
        const svg = document.getElementById('topology-svg');
        
        if (this.nodes.length === 0) {
            svg.setAttribute('viewBox', '0 0 800 600');
            return;
        }
        
        // Calculate bounding box
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        
        this.nodes.forEach(node => {
            minX = Math.min(minX, node.x);
            minY = Math.min(minY, node.y);
            maxX = Math.max(maxX, node.x);
            maxY = Math.max(maxY, node.y);
        });
        
        // Add padding
        const padding = 50;
        minX -= padding;
        minY -= padding;
        maxX += padding;
        maxY += padding;
        
        // Ensure minimum size
        const width = Math.max(maxX - minX, 400);
        const height = Math.max(maxY - minY, 300);
        
        svg.setAttribute('viewBox', `${minX} ${minY} ${width} ${height}`);
    }
    
    showTooltip(event, node) {
        const tooltip = document.getElementById('node-tooltip');
        tooltip.innerHTML = `
            <div class="tooltip-content">
                <div class="tooltip-title">${node.title}</div>
                <div class="tooltip-type">类型: ${this.getNodeTypeText(node.type)}</div>
                ${node.status ? `<div class="tooltip-status">状态: ${node.status}</div>` : ''}
                <div class="tooltip-id">ID: ${node.id}</div>
            </div>
        `;
        
        // Position tooltip
        const rect = this.container.getBoundingClientRect();
        tooltip.style.left = `${event.clientX - rect.left + 10}px`;
        tooltip.style.top = `${event.clientY - rect.top + 10}px`;
        tooltip.style.display = 'block';
    }
    
    hideTooltip() {
        const tooltip = document.getElementById('node-tooltip');
        tooltip.style.display = 'none';
    }
    
    onNodeClick(node) {
        this.store.showToast(`选择了节点: ${node.title}`, 'info');
    }
    
    getNodeTypeText(type) {
        const typeMap = {
            'hypothesis': '假设',
            'experiment': '实验',
            'paper': '论文'
        };
        return typeMap[type] || type;
    }
    
    setupEventListeners() {
        // Zoom controls
        document.getElementById('zoom-in')?.addEventListener('click', () => {
            this.zoom(1.2);
        });
        
        document.getElementById('zoom-out')?.addEventListener('click', () => {
            this.zoom(0.8);
        });
        
        document.getElementById('reset-view')?.addEventListener('click', () => {
            this.resetView();
        });
        
        // Mouse wheel zoom
        this.container.addEventListener('wheel', (e) => {
            e.preventDefault();
            const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoom(scaleFactor);
        });
        
        // Pan functionality
        let isPanning = false;
        let startPoint = { x: 0, y: 0 };
        let viewBox = { x: 0, y: 0, width: 800, height: 600 };
        
        const svg = document.getElementById('topology-svg');
        
        svg.addEventListener('mousedown', (e) => {
            if (e.target === svg || e.target.classList.contains('edge')) {
                isPanning = true;
                startPoint = { x: e.clientX, y: e.clientY };
                viewBox = this.getViewBox();
                svg.style.cursor = 'grabbing';
            }
        });
        
        svg.addEventListener('mousemove', (e) => {
            if (!isPanning) return;
            
            const dx = e.clientX - startPoint.x;
            const dy = e.clientY - startPoint.y;
            
            const newX = viewBox.x - (dx * viewBox.width / svg.clientWidth);
            const newY = viewBox.y - (dy * viewBox.height / svg.clientHeight);
            
            svg.setAttribute('viewBox', `${newX} ${newY} ${viewBox.width} ${viewBox.height}`);
        });
        
        svg.addEventListener('mouseup', () => {
            isPanning = false;
            svg.style.cursor = 'default';
        });
        
        svg.addEventListener('mouseleave', () => {
            isPanning = false;
            svg.style.cursor = 'default';
        });
    }
    
    zoom(scaleFactor) {
        const svg = document.getElementById('topology-svg');
        const viewBox = this.getViewBox();
        
        const newWidth = viewBox.width / scaleFactor;
        const newHeight = viewBox.height / scaleFactor;
        
        const newX = viewBox.x + (viewBox.width - newWidth) / 2;
        const newY = viewBox.y + (viewBox.height - newHeight) / 2;
        
        svg.setAttribute('viewBox', `${newX} ${newY} ${newWidth} ${newHeight}`);
    }
    
    resetView() {
        this.updateViewBox();
    }
    
    getViewBox() {
        const svg = document.getElementById('topology-svg');
        const viewBox = svg.getAttribute('viewBox');
        
        if (!viewBox) {
            return { x: 0, y: 0, width: 800, height: 600 };
        }
        
        const [x, y, width, height] = viewBox.split(' ').map(Number);
        return { x, y, width, height };
    }
}

// 初始化组件
document.addEventListener('DOMContentLoaded', () => {
    window.topologyGraph = new TopologyGraph('topology-container');
});