#!/usr/bin/env python3
"""
FARS 论文评分与迭代重生成服务器
"""

from flask import Flask, request, jsonify
import os
import json
import re
import requests
from datetime import datetime

app = Flask(__name__, static_folder='docs', static_url_path='')

# MiniMax API配置
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_pro"

# 优先从config.json加载API配置，备选从环境变量，最后检查paperwriterAI的config.local.json
def load_llm_config():
    # 1. 先检查本目录的config.json
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            llm_config = config.get('llm', {})
            if llm_config.get('api_key'):
                return llm_config
    
    # 2. 检查paperwriterAI的config.local.json
    paperwriterAI_config = '/Users/derek/Documents/Github/paperwriterAI/config.local.json'
    if os.path.exists(paperwriterAI_config):
        with open(paperwriterAI_config, 'r', encoding='utf-8') as f:
            config = json.load(f)
            llm_config = config.get('llm', {})
            if llm_config.get('api_key'):
                return llm_config
    
    return {}

LLM_CONFIG = load_llm_config()
MINIMAX_API_KEY = LLM_CONFIG.get('api_key', os.environ.get("MINIMAX_API_KEY", ""))

# 历史记录存储
HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'data', 'grading_history.json')

# 分支研究系统存储
BRANCHES_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_branches.json')
RESEARCH_STATE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_state.json')
PAPERS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'papers')

# 研究日志文件
RESEARCH_LOG_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_log.json')

def ensure_dir(path):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path)

def load_json_file(filepath):
    """加载JSON文件"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def save_json_file(filepath, data):
    """保存JSON文件"""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============ 研究日志函数 ============

def load_research_log() -> dict:
    """加载研究日志"""
    data = load_json_file(RESEARCH_LOG_FILE)
    return data if data else {"logs": [], "current_research": None}

def save_research_log(data: dict):
    """保存研究日志"""
    save_json_file(RESEARCH_LOG_FILE, data)

def add_log_entry(log_type: str, message: str, paper_id: int = None, duration: float = None, metadata: dict = None):
    """添加日志条目"""
    log_data = load_research_log()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": log_type,  # start, pause, resume, stop, generate_start, generate_complete, generate_failed
        "message": message,
        "paper_id": paper_id,
        "duration": duration,  # 秒
        "metadata": metadata or {}
    }
    log_data["logs"].append(entry)
    save_research_log(log_data)
    return entry

def update_current_research(status: str, paper_id: int = None, topic: str = None, start_time: str = None, elapsed: float = None):
    """更新当前研究状态"""
    log_data = load_research_log()
    if log_data["current_research"] is None:
        log_data["current_research"] = {}

    log_data["current_research"].update({
        "status": status,  # idle, running, paused, completed
        "paper_id": paper_id,
        "topic": topic,
        "start_time": start_time or datetime.now().isoformat(),
        "elapsed": elapsed or 0
    })
    save_research_log(log_data)

# ============ 分支管理函数 ============

def load_branches() -> dict:
    """加载分支数据"""
    data = load_json_file(BRANCHES_FILE)
    return data if data else {"branches": [], "current_branch_id": None, "global_settings": {"auto_continue": True, "pause_after_next": False}}

def save_branches(data: dict):
    """保存分支数据"""
    save_json_file(BRANCHES_FILE, data)

def create_branch(name: str, review_content: str = None, parent_branch_id: int = None) -> dict:
    """创建新分支"""
    branches_data = load_branches()
    branch_id = len(branches_data['branches']) + 1

    branch = {
        "id": branch_id,
        "name": name,
        "created_at": datetime.now().isoformat(),
        "review_content": review_content,
        "parent_branch_id": parent_branch_id,
        "paper_ids": [],
        "status": "active",
        "iterations_count": 0
    }

    branches_data['branches'].append(branch)
    branches_data['current_branch_id'] = branch_id
    save_branches(branches_data)

    # 创建分支专属的papers目录
    branch_papers_dir = os.path.join(PAPERS_DIR, f"branch_{branch_id}")
    ensure_dir(branch_papers_dir)

    return branch

def get_current_branch() -> dict:
    """获取当前分支"""
    branches_data = load_branches()
    current_id = branches_data.get('current_branch_id')
    if current_id:
        for branch in branches_data.get('branches', []):
            if branch['id'] == current_id:
                return branch
    return None

# ============ 论文存储函数 ============

def load_papers() -> dict:
    """加载论文数据"""
    data = load_json_file(RESEARCH_STATE_FILE)
    return data if data else {"papers": [], "current_paper_id": None, "generation_queue": [], "is_generating": False, "is_paused": False, "settings": {"auto_continue": True, "pause_after_next": False}}

def save_papers(data: dict):
    """保存论文数据"""
    save_json_file(RESEARCH_STATE_FILE, data)

def get_papers_for_branch(branch_id: int) -> list:
    """获取指定分支的所有论文"""
    papers_data = load_papers()
    return [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch_id]

def save_paper_to_file(paper_id: int, branch_id: int, content: str, title: str = None) -> str:
    """保存论文到文件"""
    branch_papers_dir = os.path.join(PAPERS_DIR, f"branch_{branch_id}")
    ensure_dir(branch_papers_dir)

    # 生成文件名
    if title:
        safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:50]
        filename = f"paper_{paper_id}_{safe_title}.md"
    else:
        filename = f"paper_{paper_id}.md"

    filepath = os.path.join(branch_papers_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath

def ensure_history_dir():
    """确保历史记录目录存在"""
    history_dir = os.path.dirname(HISTORY_FILE)
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)

def load_history() -> list:
    """加载历史记录"""
    ensure_history_dir()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history: list):
    """保存历史记录"""
    ensure_history_dir()
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def add_history_record(record: dict):
    """添加历史记录"""
    history = load_history()
    record['id'] = len(history) + 1
    record['timestamp'] = datetime.now().isoformat()
    history.insert(0, record)  # 最新记录在前
    # 只保留最近100条
    history = history[:100]
    save_history(history)

# 评分标准
SCORING_CRITERIA = """
## 论文评分标准 (0-10分)

### 1. 创新性 (0-3分)
- 0分: 完全重复已有工作，无任何创新
- 1分: 略有改动但核心思想相同
- 2分: 有一定的创新点但不够突出
- 3分: 显著的创新贡献

### 2. 方法论 (0-2分)
- 0分: 方法不明确或不可行
- 1分: 方法基本可行但有缺陷
- 2分: 方法严谨且可复现

### 3. 实验验证 (0-2分)
- 0分: 无实验或实验不充分
- 1分: 有实验但不够全面
- 2分: 实验全面且结果可靠

### 4. 写作质量 (0-2分)
- 0分: 结构混乱，语言不通顺
- 1分: 基本可读但有改进空间
- 2分: 写作专业流畅

### 5. 避免过拟合 (0-1分)
- 0分: 明显过拟合迹象（如仅在特定数据集上有效）
- 1分: 无过拟合迹象，泛化能力良好
"""


def score_paper(paper_content: str) -> dict:
    """使用LLM对论文进行评分"""
    if not MINIMAX_API_KEY:
        # 返回模拟评分
        return {
            "total_score": 6.5,
            "pass": True,
            "criteria": {
                "innovation": {"score": 2, "max": 3, "comment": "有一定的创新点"},
                "methodology": {"score": 1, "max": 2, "comment": "方法基本可行"},
                "experiment": {"score": 1, "max": 2, "comment": "实验基本充分"},
                "writing": {"score": 1.5, "max": 2, "comment": "写作较为流畅"},
                "overfitting": {"score": 1, "max": 1, "comment": "无明显过拟合"}
            },
            "feedback": "论文整体质量良好，建议继续优化实验部分。"
        }

    prompt = f"""
你是一个专业的学术论文评审专家。请对以下论文进行评分和评审。

{SCORING_CRITERIA}

## 待评审论文

{paper_content}

## 输出格式

请严格按以下JSON格式输出评分结果（不要输出任何其他内容）：

{{
    "total_score": 0-10的浮点数,
    "pass": true或false（7分以上通过）,
    "criteria": {{
        "innovation": {{"score": 0-3, "comment": "评审意见"}},
        "methodology": {{"score": 0-2, "comment": "评审意见"}},
        "experiment": {{"score": 0-2, "comment": "评审意见"}},
        "writing": {{"score": 0-2, "comment": "评审意见"}},
        "overfitting": {{"score": 0-1, "comment": "评审意见"}}
    }},
    "feedback": "总体评审意见和改进建议（50字以内）"
}}
"""
    try:
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "minimax-m2.7-highspeed",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        response = requests.post(MINIMAX_API_URL, headers=headers, json=data, timeout=60)
        result = response.json()

        # 解析LLM返回的评分
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        # 提取JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "无法解析评分结果", "raw": content}
    except Exception as e:
        return {"error": str(e)}


def regenerate_paper(paper_content: str, feedback: str, criteria: dict) -> str:
    """根据评审反馈重新生成论文"""
    if not MINIMAX_API_KEY:
        return f"[模拟重生成] 基于反馈优化论文: {feedback[:50]}..."

    # 找出主要问题
    issues = []
    if criteria.get("innovation", {}).get("score", 0) < 2:
        issues.append("创新性不足")
    if criteria.get("methodology", {}).get("score", 0) < 1:
        issues.append("方法论存在缺陷")
    if criteria.get("experiment", {}).get("score", 0) < 1:
        issues.append("实验验证不充分")
    if criteria.get("overfitting", {}).get("score", 0) < 1:
        issues.append("存在过拟合风险")

    issues_text = "；".join(issues) if issues else "整体质量需要提升"

    prompt = f"""
你是一个量化交易领域的学术论文写作专家。请根据评审反馈重新撰写论文。

## 原始论文

{paper_content}

## 评审反馈

总体评分: {criteria.get('total_score', 'N/A')}/10
通过状态: {"通过" if criteria.get('pass') else "不通过"}
主要问题: {issues_text}

各项评分:
- 创新性: {criteria.get('innovation', {}).get('score', 'N/A')}/3 - {criteria.get('innovation', {}).get('comment', '')}
- 方法论: {criteria.get('methodology', {}).get('score', 'N/A')}/2 - {criteria.get('methodology', {}).get('comment', '')}
- 实验验证: {criteria.get('experiment', {}).get('score', 'N/A')}/2 - {criteria.get('experiment', {}).get('comment', '')}
- 写作质量: {criteria.get('writing', {}).get('score', 'N/A')}/2 - {criteria.get('writing', {}).get('comment', '')}
- 避免过拟合: {criteria.get('overfitting', {}).get('score', 'N/A')}/1 - {criteria.get('overfitting', {}).get('comment', '')}

评审建议: {feedback}

## 重写要求

1. **提升创新性**: 确保有明确的研究动机和独特贡献
2. **强化方法论**: 方法必须严谨、可复现、有理论支撑
3. **完善实验验证**: 包含充分的消融实验和对比实验，确保结果可靠性
4. **避免过拟合**: 使用交叉验证、多种市场环境测试、理论分析泛化能力
5. **保证写作质量**: 结构清晰、逻辑连贯、语言专业

请输出一篇完整的新论文（Markdown格式），确保解决上述问题。
"""

    try:
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "minimax-m2.7-highspeed",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }
        response = requests.post(MINIMAX_API_URL, headers=headers, json=data, timeout=120)
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "重生成失败")
    except Exception as e:
        return f"重生成失败: {str(e)}"


def find_related_papers(topic: str, failed_aspects: list) -> list:
    """查找相关论文以改进论文质量"""
    if not MINIMAX_API_KEY:
        return [
            {"title": "相关论文A", "reason": "提供方法论支持"},
            {"title": "相关论文B", "reason": "提供实验验证思路"}
        ]

    prompt = f"""
你是一个量化交易领域的文献专家。请根据以下主题和论文不足之处，推荐可能有所帮助的参考论文。

## 论文主题
{topic}

## 论文不足之处
{', '.join(failed_aspects)}

## 输出格式

请列出3-5篇可能有所帮助的参考论文，每篇包含：
- 论文标题
- 作者/来源
- 为什么有帮助（如何解决论文的不足）
- arXiv ID（如果可获得）

使用中文输出。
"""
    try:
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "minimax-m2.7-highspeed",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        response = requests.post(MINIMAX_API_URL, headers=headers, json=data, timeout=60)
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "未找到相关论文")
    except Exception as e:
        return f"查找失败: {str(e)}"


@app.route('/api/score', methods=['POST'])
def api_score():
    """论文评分API"""
    data = request.json
    paper_content = data.get('paper', '')

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    result = score_paper(paper_content)
    
    # 保存到历史记录
    add_history_record({
        "type": "score",
        "paper_preview": paper_content[:500],
        "paper_full": paper_content,
        "result": result
    })
    
    return jsonify(result)


@app.route('/api/regenerate', methods=['POST'])
def api_regenerate():
    """论文重生成API"""
    data = request.json
    paper_content = data.get('paper', '')
    feedback = data.get('feedback', '')
    criteria = data.get('criteria', {})

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    new_paper = regenerate_paper(paper_content, feedback, criteria)
    
    # 保存到历史记录
    add_history_record({
        "type": "regenerate",
        "original_preview": paper_content[:500],
        "feedback": feedback,
        "criteria": criteria,
        "new_paper_preview": new_paper[:500],
        "new_paper_full": new_paper
    })
    
    return jsonify({"new_paper": new_paper})


@app.route('/api/find_papers', methods=['POST'])
def api_find_papers():
    """查找相关论文API"""
    data = request.json
    topic = data.get('topic', '')
    failed_aspects = data.get('failed_aspects', [])

    if not topic:
        return jsonify({"error": "主题不能为空"}), 400

    papers = find_related_papers(topic, failed_aspects)
    
    # 保存到历史记录
    add_history_record({
        "type": "find_papers",
        "topic": topic,
        "failed_aspects": failed_aspects,
        "related_papers": papers
    })
    
    return jsonify({"related_papers": papers})


@app.route('/api/iterate', methods=['POST'])
def api_iterate():
    """完整迭代流程: 评分 -> 找论文 -> 重生成 -> 再评分"""
    data = request.json
    paper_content = data.get('paper', '')
    topic = data.get('topic', '量化交易策略')
    max_iterations = data.get('max_iterations', 3)

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    results = {
        "iterations": [],
        "final_status": None
    }

    current_paper = paper_content

    for i in range(max_iterations):
        # 评分
        score_result = score_paper(current_paper)

        iteration_result = {
            "iteration": i + 1,
            "score": score_result,
            "paper": current_paper[:200] + "..." if len(current_paper) > 200 else current_paper
        }

        # 检查是否通过
        if score_result.get("pass", False):
            results["final_status"] = "passed"
            results["final_paper"] = current_paper
            results["final_score"] = score_result
            iteration_result["action"] = "通过，无需继续"
            results["iterations"].append(iteration_result)
            break

        # 获取失败原因
        failed_aspects = []
        criteria = score_result.get("criteria", {})
        if criteria.get("innovation", {}).get("score", 0) < 2:
            failed_aspects.append("创新性不足")
        if criteria.get("methodology", {}).get("score", 0) < 1:
            failed_aspects.append("方法论存在缺陷")
        if criteria.get("experiment", {}).get("score", 0) < 1:
            failed_aspects.append("实验验证不充分")
        if criteria.get("overfitting", {}).get("score", 0) < 1:
            failed_aspects.append("存在过拟合风险")

        # 查找相关论文
        related_papers = find_related_papers(topic, failed_aspects)
        iteration_result["related_papers"] = related_papers
        iteration_result["failed_aspects"] = failed_aspects

        # 重生成
        new_paper = regenerate_paper(
            current_paper,
            score_result.get("feedback", ""),
            criteria
        )
        iteration_result["new_paper_preview"] = new_paper[:200] + "..."

        current_paper = new_paper
        iteration_result["action"] = "已重生成，进入下一轮"

        results["iterations"].append(iteration_result)

    if results["final_status"] is None:
        results["final_status"] = "max_iterations_reached"
        results["final_paper"] = current_paper
        results["final_score"] = score_paper(current_paper)
    
    # 保存完整迭代到历史记录
    add_history_record({
        "type": "iterate",
        "initial_paper_preview": paper_content[:500],
        "initial_paper_full": paper_content,
        "topic": topic,
        "max_iterations": max_iterations,
        "results": results
    })
    
    return jsonify(results)


@app.route('/api/history', methods=['GET'])
def api_history():
    """获取历史记录列表"""
    history = load_history()
    # 返回列表形式（不含完整论文内容，节省带宽）
    preview_list = []
    for record in history:
        preview_list.append({
            "id": record.get('id'),
            "timestamp": record.get('timestamp'),
            "type": record.get('type'),
            "paper_preview": record.get('paper_preview', '')[:200] + '...' if record.get('paper_preview') and len(record.get('paper_preview', '')) > 200 else record.get('paper_preview', ''),
            "result_summary": f"评分: {record.get('result', {}).get('total_score', 'N/A')}/10" if record.get('result') else None,
            "topic": record.get('topic', ''),
            "iterations_count": len(record.get('results', {}).get('iterations', [])) if record.get('results') else 0
        })
    return jsonify({"history": preview_list})


@app.route('/api/history/<int:record_id>', methods=['GET'])
def api_history_detail(record_id: int):
    """获取单条历史记录的完整内容"""
    history = load_history()
    for record in history:
        if record.get('id') == record_id:
            return jsonify(record)
    return jsonify({"error": "记录不存在"}), 404


# ============ 分支研究系统 API ============

@app.route('/api/research/state', methods=['GET'])
def api_research_state():
    """获取研究状态"""
    papers_data = load_papers()
    branches_data = load_branches()
    current_branch = get_current_branch()
    log_data = load_research_log()

    # 计算当前论文ID（如果有的话）
    current_paper_id = papers_data.get('current_paper_id')

    # 计算当前论文的标题
    current_paper_title = None
    if current_paper_id:
        for p in papers_data.get('papers', []):
            if p.get('id') == current_paper_id:
                current_paper_title = p.get('title')
                break

    return jsonify({
        "is_generating": papers_data.get('is_generating', False),
        "is_paused": papers_data.get('is_paused', False),
        "settings": papers_data.get('settings', {}),
        "current_branch": current_branch,
        "papers_count": len(papers_data.get('papers', [])),
        "queue_length": len(papers_data.get('generation_queue', [])),
        "all_branches": branches_data.get('branches', []),
        "current_research": log_data.get('current_research'),
        "current_paper_id": current_paper_id,
        "current_paper_title": current_paper_title
    })


@app.route('/api/branches', methods=['GET'])
def api_branches_list():
    """获取所有分支列表"""
    branches_data = load_branches()
    branches = branches_data.get('branches', [])

    # 为每个分支添加论文统计
    papers_data = load_papers()
    for branch in branches:
        branch_papers = [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch['id']]
        branch['papers_count'] = len(branch_papers)
        branch['latest_paper_date'] = branch_papers[-1].get('created_at') if branch_papers else None

    return jsonify({"branches": branches})


# ============ LLM调用记录 API ============

@app.route('/api/llm-calls', methods=['GET'])
def api_llm_calls_list():
    """获取LLM调用记录列表"""
    try:
        from src.core.database import get_connection

        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        agent_name = request.args.get('agent')
        status = request.args.get('status')
        research_id = request.args.get('research_id')

        conn = get_connection()
        cursor = conn.cursor()

        # 构建查询
        query = "SELECT * FROM llm_call_logs WHERE 1=1"
        params = []

        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)

        if status:
            query += " AND status = ?"
            params.append(status)

        if research_id:
            query += " AND research_id = ?"
            params.append(research_id)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        calls = []
        for row in rows:
            calls.append({
                "call_id": row['call_id'],
                "run_id": row['run_id'],
                "research_id": row['research_id'],
                "agent_name": row['agent_name'],
                "method_name": row['method_name'],
                "provider": row['provider'],
                "model": row['model'],
                "prompt_tokens": row['prompt_tokens'],
                "completion_tokens": row['completion_tokens'],
                "total_tokens": row['total_tokens'],
                "latency_ms": row['latency_ms'],
                "status": row['status'],
                "error_message": row['error_message'],
                "created_at": row['created_at']
            })

        # 获取总数
        count_query = "SELECT COUNT(*) as total FROM llm_call_logs WHERE 1=1"
        count_params = []
        if agent_name:
            count_query += " AND agent_name = ?"
            count_params.append(agent_name)
        if status:
            count_query += " AND status = ?"
            count_params.append(status)
        if research_id:
            count_query += " AND research_id = ?"
            count_params.append(research_id)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']

        conn.close()

        return jsonify({
            "calls": calls,
            "total": total,
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/llm-calls/<call_id>', methods=['GET'])
def api_llm_call_detail(call_id: str):
    """获取单条LLM调用详情"""
    try:
        from src.core.database import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM llm_call_logs WHERE call_id = ?", (call_id,))
        row = cursor.fetchone()

        conn.close()

        if not row:
            return jsonify({"error": "调用记录不存在"}), 404

        return jsonify({
            "call_id": row['call_id'],
            "run_id": row['run_id'],
            "research_id": row['research_id'],
            "agent_name": row['agent_name'],
            "method_name": row['method_name'],
            "provider": row['provider'],
            "model": row['model'],
            "system_prompt": row['system_prompt'],
            "user_prompt": row['user_prompt'],
            "full_prompt": row['full_prompt'],
            "completion": row['completion'],
            "prompt_tokens": row['prompt_tokens'],
            "completion_tokens": row['completion_tokens'],
            "total_tokens": row['total_tokens'],
            "latency_ms": row['latency_ms'],
            "status": row['status'],
            "error_message": row['error_message'],
            "error_detail": row['error_detail'],
            "created_at": row['created_at']
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/llm-calls/stats', methods=['GET'])
def api_llm_calls_stats():
    """获取LLM调用统计信息"""
    try:
        from src.core.database import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # 总调用次数
        cursor.execute("SELECT COUNT(*) as total FROM llm_call_logs")
        total_calls = cursor.fetchone()['total']

        # 成功次数
        cursor.execute("SELECT COUNT(*) as success FROM llm_call_logs WHERE status = 'success'")
        success_calls = cursor.fetchone()['success']

        # 失败次数
        cursor.execute("SELECT COUNT(*) as failed FROM llm_call_logs WHERE status = 'failed'")
        failed_calls = cursor.fetchone()['failed']

        # Token使用统计
        cursor.execute("""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms
            FROM llm_call_logs
        """)
        token_stats = cursor.fetchone()

        # 按Agent统计
        cursor.execute("""
            SELECT agent_name, COUNT(*) as call_count,
                   SUM(total_tokens) as tokens,
                   AVG(latency_ms) as avg_latency
            FROM llm_call_logs
            GROUP BY agent_name
            ORDER BY call_count DESC
        """)
        agent_stats = [dict(row) for row in cursor.fetchall()]

        # 按Provider统计
        cursor.execute("""
            SELECT provider, COUNT(*) as call_count,
                   SUM(total_tokens) as tokens,
                   AVG(latency_ms) as avg_latency
            FROM llm_call_logs
            GROUP BY provider
            ORDER BY call_count DESC
        """)
        provider_stats = [dict(row) for row in cursor.fetchall()]

        # 最近24小时的调用趋势
        cursor.execute("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as call_count,
                SUM(total_tokens) as tokens
            FROM llm_call_logs
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)
        trend_stats = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
            "success_rate": round(success_calls / total_calls * 100, 2) if total_calls > 0 else 0,
            "total_prompt_tokens": token_stats['total_prompt_tokens'],
            "total_completion_tokens": token_stats['total_completion_tokens'],
            "total_tokens": token_stats['total_tokens'],
            "avg_latency_ms": round(token_stats['avg_latency_ms'], 2),
            "agent_stats": agent_stats,
            "provider_stats": provider_stats,
            "trend_stats": trend_stats
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/branches', methods=['POST'])
def api_create_branch():
    """创建新分支"""
    data = request.json
    name = data.get('name', f"分支 {datetime.now().strftime('%Y%m%d_%H%M%S')}")
    review_content = data.get('review_content', '')
    parent_branch_id = data.get('parent_branch_id')

    branch = create_branch(name, review_content, parent_branch_id)
    return jsonify({"branch": branch, "message": f"分支 '{name}' 创建成功"})


@app.route('/api/branches/<int:branch_id>', methods=['GET'])
def api_branch_detail(branch_id: int):
    """获取分支详情"""
    branches_data = load_branches()
    branch = None
    for b in branches_data.get('branches', []):
        if b['id'] == branch_id:
            branch = b.copy()
            break

    if not branch:
        return jsonify({"error": "分支不存在"}), 404

    # 获取该分支的论文
    papers_data = load_papers()
    branch_papers = [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch_id]

    branch['papers'] = branch_papers
    return jsonify({"branch": branch})


@app.route('/api/branches/switch/<int:branch_id>', methods=['POST'])
def api_switch_branch(branch_id: int):
    """切换当前分支"""
    branches_data = load_branches()
    for b in branches_data.get('branches', []):
        if b['id'] == branch_id:
            branches_data['current_branch_id'] = branch_id
            save_branches(branches_data)
            return jsonify({"branch": b, "message": f"已切换到分支 '{b['name']}'"})

    return jsonify({"error": "分支不存在"}), 404


@app.route('/api/generate/start', methods=['POST'])
def api_start_generation():
    """开始/继续生成论文"""
    data = request.json or {}

    papers_data = load_papers()
    current_branch = get_current_branch()

    # 检查是否有主题
    topic = data.get('topic', '')
    if not topic and not current_branch:
        return jsonify({"error": "请提供研究主题或创建/选择分支"}), 400

    # 如果有主题且当前分支为空，创建新分支
    if topic and not current_branch:
        branch_name = data.get('branch_name', f"研究_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        review_content = data.get('review_content', '')
        current_branch = create_branch(branch_name, review_content)

    # 添加入队列
    if 'generation_queue' not in papers_data:
        papers_data['generation_queue'] = []

    papers_data['generation_queue'].append({
        "topic": topic or current_branch.get('review_content', '量化交易策略研究'),
        "branch_id": current_branch['id'],
        "added_at": datetime.now().isoformat(),
        "priority": data.get('priority', 'normal')
    })

    papers_data['is_generating'] = True
    papers_data['is_paused'] = False
    save_papers(papers_data)

    return jsonify({
        "message": "已开始生成",
        "queue_length": len(papers_data['generation_queue']),
        "current_branch": current_branch
    })


@app.route('/api/generate/pause', methods=['POST'])
def api_pause_generation():
    """暂停生成 - 生成完下一篇后停止"""
    papers_data = load_papers()
    papers_data['settings']['pause_after_next'] = True
    papers_data['is_paused'] = True
    save_papers(papers_data)

    add_log_entry("pause", "已暂停生成，将在生成下一篇论文后停止")
    update_current_research("paused")

    return jsonify({"message": "已设置暂停，将在生成下一篇论文后停止"})


@app.route('/api/generate/resume', methods=['POST'])
def api_resume_generation():
    """继续生成"""
    papers_data = load_papers()
    papers_data['is_paused'] = False
    papers_data['settings']['pause_after_next'] = False
    save_papers(papers_data)

    add_log_entry("resume", "已继续生成")
    update_current_research("running")

    return jsonify({"message": "已继续生成"})


@app.route('/api/generate/stop', methods=['POST'])
def api_stop_generation():
    """完全停止生成"""
    papers_data = load_papers()
    papers_data['is_generating'] = False
    papers_data['is_paused'] = False
    papers_data['generation_queue'] = []
    save_papers(papers_data)

    add_log_entry("stop", "已完全停止生成")
    update_current_research("idle")

    return jsonify({"message": "已停止生成，清空队列"})


@app.route('/api/generate/next', methods=['POST'])
def api_generate_next():
    """生成下一篇论文（手动触发）"""
    data = request.json or {}
    topic = data.get('topic', '')
    branch_id = data.get('branch_id')

    if not topic:
        return jsonify({"error": "请提供研究主题"}), 400

    # 获取分支
    if not branch_id:
        current_branch = get_current_branch()
        if current_branch:
            branch_id = current_branch['id']
        else:
            # 自动创建新分支
            branch = create_branch(f"研究_{datetime.now().strftime('%Y%m%d_%H%M%S')}", "")
            branch_id = branch['id']

    # 记录开始时间
    start_time = datetime.now()
    add_log_entry("generate_start", f"开始生成论文: {topic}", branch_id=branch_id, metadata={"topic": topic})
    update_current_research("running", paper_id=None, topic=topic, start_time=start_time.isoformat())

    # 创建论文记录
    papers_data = load_papers()
    paper_id = len(papers_data.get('papers', [])) + 1

    # 生成论文内容（这里调用实际的生成逻辑）
    paper_content = generate_paper_content(topic, papers_data.get('papers', []))

    # 计算生成耗时
    duration = (datetime.now() - start_time).total_seconds()

    # 保存论文
    paper_record = {
        "id": paper_id,
        "branch_id": branch_id,
        "topic": topic,
        "content": paper_content,
        "title": extract_title(paper_content),
        "status": "generated",
        "quality_score": None,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "parent_paper_id": None,
        "generation_duration": duration  # 添加耗时记录
    }

    papers_data.setdefault('papers', []).append(paper_record)
    papers_data['current_paper_id'] = paper_id

    # 保存到文件
    filepath = save_paper_to_file(paper_id, branch_id, paper_content, paper_record['title'])
    paper_record['file_path'] = filepath

    save_papers(papers_data)

    # 更新分支统计
    branches_data = load_branches()
    for b in branches_data.get('branches', []):
        if b['id'] == branch_id:
            b['paper_ids'].append(paper_id)
            b['iterations_count'] = b.get('iterations_count', 0) + 1
            break
    save_branches(branches_data)

    # 记录生成完成日志
    add_log_entry("generate_complete", f"论文生成完成 [#{paper_id}]: {paper_record['title']}", paper_id=paper_id, duration=duration)
    update_current_research("completed", paper_id=paper_id, topic=topic, elapsed=duration)

    # 记录到历史
    add_history_record({
        "type": "generate",
        "paper_id": paper_id,
        "branch_id": branch_id,
        "topic": topic,
        "title": paper_record['title'],
        "status": "generated",
        "duration": duration
    })

    return jsonify({
        "paper": paper_record,
        "message": f"论文生成成功 (耗时 {duration:.1f}秒)"
    })


def generate_paper_content(topic: str, existing_papers: list) -> str:
    """生成论文内容"""
    if not MINIMAX_API_KEY:
        return f"""# {topic}

## 摘要

本文提出了一种创新的量化交易策略，旨在解决{topic}领域的关键问题。

## 1. 引言

量化交易在金融领域发挥着越来越重要的作用...

## 2. 方法论

我们提出了一种基于机器学习的交易策略...

## 3. 实验验证

在多个数据集上的实验表明...

## 4. 结论

本文提出的策略在回测中表现优异...
"""

    # 使用MiniMax API生成
    # 重要：严格控制token使用，只使用论文标题列表，不含任何内容摘要
    topic_list = ""
    if existing_papers:
        # 只列出最近3篇论文的主题，完全不包含内容
        recent_papers = existing_papers[-3:]
        topics = [p.get('topic', '未命名') for p in recent_papers]
        topic_list = "\n".join([f"- {t}" for t in topics])

    # 精简的prompt，严格控制长度
    prompt = f"""作为量化交易领域的学术论文写作专家，请根据以下主题生成一篇完整学术论文。

研究主题：{topic}

要求：
1. 论文必须原创，与已有研究有显著区别
2. 使用Markdown格式，包含：摘要、引言、方法论、实验验证、结论
3. 方法论必须严谨、可复现
4. 实验验证必须包含对比实验和消融实验
5. 避免过拟合，使用交叉验证

请直接输出一篇完整学术论文（Markdown格式），不包含其他说明。

"""

    # 如果有历史论文主题，添加但不增加太多token
    if topic_list:
        prompt += f"已有关键主题：\n{topic_list}\n\n请确保新论文与上述主题有显著区别。\n"

    # 严格限制prompt总长度（约15000 token安全范围，为输出留出足够空间）
    max_prompt_len = 10000
    if len(prompt) > max_prompt_len:
        prompt = prompt[:max_prompt_len]

    try:
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "minimax-m2.7-highspeed",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 8192  # 限制输出长度，避免超过总token限制
        }
        response = requests.post(MINIMAX_API_URL, headers=headers, json=data, timeout=120)
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", f"# {topic}\n\n论文生成失败，请重试。")
    except Exception as e:
        return f"# {topic}\n\n论文生成失败: {str(e)}"


def extract_title(content: str) -> str:
    """从内容中提取标题"""
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            return line.lstrip('#').strip()
        elif line and len(line) < 100:
            return line
    return "未命名论文"


# ============ 重新开始（创建新分支）API ============

@app.route('/api/generate/restart', methods=['POST'])
def api_restart_with_new_branch():
    """重新开始 - 上传综述后创建新分支"""
    data = request.json
    review_content = data.get('review_content', '')
    branch_name = data.get('branch_name', f"分支_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    if not review_content:
        return jsonify({"error": "请提供综述内容"}), 400

    # 创建新分支（与历史数据无关）
    branch = create_branch(branch_name, review_content)

    # 重置生成状态
    papers_data = load_papers()
    papers_data['is_generating'] = True
    papers_data['is_paused'] = False
    papers_data['generation_queue'] = []
    save_papers(papers_data)

    return jsonify({
        "branch": branch,
        "message": f"已创建新分支 '{branch_name}'，可开始生成研究论文"
    })


@app.route('/api/papers', methods=['GET'])
def api_papers_list():
    """获取论文列表"""
    branch_id = request.args.get('branch_id', type=int)

    papers_data = load_papers()
    papers = papers_data.get('papers', [])

    if branch_id:
        papers = [p for p in papers if p.get('branch_id') == branch_id]

    # 不返回完整content以节省带宽
    simplified = []
    for p in papers:
        simplified.append({
            "id": p.get('id'),
            "branch_id": p.get('branch_id'),
            "topic": p.get('topic'),
            "title": p.get('title'),
            "status": p.get('status'),
            "quality_score": p.get('quality_score'),
            "iteration_count": p.get('iteration_count'),
            "created_at": p.get('created_at'),
            "content_preview": (p.get('content', '')[:500] + '...') if p.get('content') else ''
        })

    return jsonify({"papers": simplified})


@app.route('/api/papers/<int:paper_id>', methods=['GET'])
def api_paper_detail(paper_id: int):
    """获取论文详情"""
    papers_data = load_papers()
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            return jsonify({"paper": p})

    return jsonify({"error": "论文不存在"}), 404


@app.route('/api/papers/<int:paper_id>/score', methods=['POST'])
def api_score_paper(paper_id: int):
    """对论文进行评分"""
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    score_result = score_paper(paper.get('content', ''))
    paper['quality_score'] = score_result.get('total_score')
    paper['last_score_result'] = score_result

    save_papers(papers_data)

    # 记录到历史
    add_history_record({
        "type": "paper_score",
        "paper_id": paper_id,
        "topic": paper.get('topic'),
        "title": paper.get('title'),
        "result": score_result
    })

    return jsonify({
        "paper_id": paper_id,
        "score": score_result
    })


@app.route('/api/papers/<int:paper_id>/improve', methods=['POST'])
def api_improve_paper(paper_id: int):
    """基于评分改进论文"""
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    score_result = paper.get('last_score_result')
    if not score_result:
        return jsonify({"error": "请先对论文进行评分"}), 400

    # 生成改进版
    improved_content = regenerate_paper(
        paper.get('content', ''),
        score_result.get('feedback', ''),
        score_result.get('criteria', {})
    )

    # 创建新版本论文
    new_paper_id = len(papers_data.get('papers', [])) + 1
    new_paper = {
        "id": new_paper_id,
        "branch_id": paper.get('branch_id'),
        "topic": paper.get('topic'),
        "content": improved_content,
        "title": extract_title(improved_content),
        "status": "improved",
        "quality_score": None,
        "iteration_count": paper.get('iteration_count', 0) + 1,
        "created_at": datetime.now().isoformat(),
        "parent_paper_id": paper_id,
        "improvement_notes": score_result.get('feedback')
    }

    papers_data.setdefault('papers', []).append(new_paper)
    save_papers(papers_data)

    # 保存到文件
    filepath = save_paper_to_file(new_paper_id, new_paper['branch_id'], improved_content, new_paper['title'])
    new_paper['file_path'] = filepath

    # 记录到历史
    add_history_record({
        "type": "improve",
        "original_paper_id": paper_id,
        "new_paper_id": new_paper_id,
        "topic": paper.get('topic'),
        "improvement_notes": score_result.get('feedback')
    })

    return jsonify({
        "original_paper_id": paper_id,
        "new_paper": new_paper,
        "message": "论文改进成功"
    })


# 确保必要目录存在
ensure_dir(PAPERS_DIR)


# ============ 改进思路存储 ============

IMPROVEMENTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'improvements.json')

def load_improvements() -> dict:
    """加载改进思路"""
    return load_json_file(IMPROVEMENTS_FILE) or {}

def save_improvements(data: dict):
    """保存改进思路"""
    save_json_file(IMPROVEMENTS_FILE, data)

@app.route('/api/improvements', methods=['GET'])
def api_get_improvements():
    """获取改进思路"""
    branch_id = request.args.get('branch_id', type=int)
    improvements = load_improvements()

    if branch_id:
        return jsonify({"improvements": improvements.get(str(branch_id), [])})
    return jsonify({"improvements": improvements})

@app.route('/api/improvements', methods=['POST'])
def api_save_improvement():
    """保存改进思路"""
    data = request.json
    branch_id = data.get('branch_id')
    idea = data.get('idea', '')
    source_paper_id = data.get('paper_id')

    if not branch_id or not idea:
        return jsonify({"error": "缺少必要参数"}), 400

    improvements = load_improvements()
    branch_str = str(branch_id)

    if branch_str not in improvements:
        improvements[branch_str] = []

    improvement_record = {
        "id": len(improvements[branch_str]) + 1,
        "idea": idea,
        "paper_id": source_paper_id,
        "created_at": datetime.now().isoformat(),
        "applied": False
    }

    improvements[branch_str].append(improvement_record)
    save_improvements(improvements)

    return jsonify({"improvement": improvement_record, "message": "改进思路已保存"})


# ============ v2 Research Control API ============

@app.route('/api/research/start', methods=['POST'])
def api_research_start():
    data = request.json or {}
    topic = data.get('topic', '量化交易研究')
    branch_data = get_current_branch()
    branch_id = branch_data['id'] if branch_data else 1

    papers_data = load_papers()
    papers_data['is_generating'] = True
    papers_data['is_paused'] = False
    save_papers(papers_data)

    update_current_research("running", topic=topic, start_time=datetime.now().isoformat())
    add_log_entry("start", f"开始研究: {topic}", metadata={"topic": topic, "branch_id": branch_id})

    return jsonify({"message": "研究已启动", "topic": topic, "branch_id": branch_id})

@app.route('/api/research/stop', methods=['POST'])
def api_research_stop():
    papers_data = load_papers()
    papers_data['is_generating'] = False
    papers_data['is_paused'] = False
    save_papers(papers_data)

    update_current_research("idle")
    add_log_entry("stop", "研究已停止")

    return jsonify({"message": "研究已停止"})

@app.route('/api/research/pause', methods=['POST'])
def api_research_pause():
    papers_data = load_papers()
    papers_data['is_paused'] = True
    save_papers(papers_data)

    update_current_research("paused")
    add_log_entry("pause", "研究已暂停")

    return jsonify({"message": "研究已暂停"})

@app.route('/api/research/resume', methods=['POST'])
def api_research_resume():
    papers_data = load_papers()
    papers_data['is_paused'] = False
    save_papers(papers_data)

    update_current_research("running")
    add_log_entry("resume", "研究已恢复")

    return jsonify({"message": "研究已恢复"})


# ============ v2 API 端点 ============

EXPERIMENTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'experiments.json')
QUALITY_FILE = os.path.join(os.path.dirname(__file__), 'data', 'quality_results.json')
CHECKPOINTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'checkpoints.json')

def load_experiments() -> list:
    data = load_json_file(EXPERIMENTS_FILE)
    return data if data else []

def save_experiments(data: list):
    save_json_file(EXPERIMENTS_FILE, data)

def load_quality_results() -> list:
    data = load_json_file(QUALITY_FILE)
    return data if data else []

def save_quality_results(data: list):
    save_json_file(QUALITY_FILE, data)

def load_checkpoints() -> list:
    data = load_json_file(CHECKPOINTS_FILE)
    return data if data else []

def save_checkpoints(data: list):
    save_json_file(CHECKPOINTS_FILE, data)

# --- Status / Config ---

@app.route('/api/status', methods=['GET'])
def api_status():
    papers_data = load_papers()
    branches_data = load_branches()
    log_data = load_research_log()
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "papers_count": len(papers_data.get("papers", [])),
        "branches_count": len(branches_data.get("branches", [])),
        "is_running": papers_data.get("is_generating", False),
        "is_paused": papers_data.get("is_paused", False),
        "current_research": log_data.get("current_research"),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/config', methods=['GET'])
def api_config():
    return jsonify({
        "api_configured": bool(MINIMAX_API_KEY),
        "model": "minimax-m2.7-highspeed",
        "version": "2.0",
        "features": {
            "research": True,
            "branching": True,
            "quality": True,
            "llm_monitoring": True,
            "experiments": True,
            "checkpoints": True,
            "compare": True,
            "topology": True
        }
    })

# --- Experiments ---

@app.route('/api/experiments', methods=['GET'])
def api_get_experiments():
    experiments = load_experiments()
    branch_id = request.args.get('branch_id', type=int)
    if branch_id:
        experiments = [e for e in experiments if e.get('branch_id') == branch_id]
    return jsonify({"experiments": experiments})

@app.route('/api/experiments/<int:exp_id>', methods=['GET'])
def api_get_experiment(exp_id):
    experiments = load_experiments()
    for exp in experiments:
        if exp.get('id') == exp_id:
            return jsonify({"experiment": exp})
    return jsonify({"error": "实验不存在"}), 404

@app.route('/api/experiments', methods=['POST'])
def api_create_experiment():
    data = request.json
    experiments = load_experiments()
    exp_id = len(experiments) + 1
    experiment = {
        "id": exp_id,
        "name": data.get("name", f"实验-{exp_id}"),
        "description": data.get("description", ""),
        "branch_id": data.get("branch_id"),
        "paper_id": data.get("paper_id"),
        "status": "pending",
        "config": data.get("config", {}),
        "results": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    experiments.append(experiment)
    save_experiments(experiments)
    return jsonify({"experiment": experiment, "message": "实验已创建"})

# --- Quality ---

@app.route('/api/quality', methods=['GET'])
def api_get_quality():
    results = load_quality_results()
    return jsonify({"results": results})

@app.route('/api/quality/check/<int:paper_id>', methods=['POST'])
def api_quality_check(paper_id):
    papers_data = load_papers()
    paper = None
    for p in papers_data.get("papers", []):
        if p.get("id") == paper_id:
            paper = p
            break
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    paper_content = paper.get("content", "")
    if not paper_content:
        return jsonify({"error": "论文内容为空"}), 400

    score_result = score_paper(paper_content)

    results = load_quality_results()
    quality_record = {
        "id": len(results) + 1,
        "paper_id": paper_id,
        "paper_title": paper.get("title", "未命名"),
        "score": score_result.get("total_score", 0),
        "passed": score_result.get("pass", False),
        "criteria": score_result.get("criteria", {}),
        "feedback": score_result.get("feedback", ""),
        "check_type": "综合评估",
        "created_at": datetime.now().isoformat()
    }
    results.append(quality_record)
    save_quality_results(results)

    return jsonify({"result": quality_record})

# --- Topology ---

@app.route('/api/topology', methods=['GET'])
def api_topology():
    papers_data = load_papers()
    papers = papers_data.get("papers", [])
    nodes = []
    edges = []
    for p in papers:
        nodes.append({
            "id": str(p.get("id")),
            "label": p.get("title", "未命名"),
            "type": "paper",
            "branch_id": p.get("branch_id"),
            "score": p.get("score", 0)
        })
        if p.get("parent_paper_id"):
            edges.append({
                "source": str(p["parent_paper_id"]),
                "target": str(p.get("id")),
                "type": "improvement"
            })

    branches_data = load_branches()
    for b in branches_data.get("branches", []):
        nodes.append({
            "id": f"branch_{b['id']}",
            "label": b.get("name", f"分支-{b['id']}"),
            "type": "branch"
        })
        if b.get("parent_branch_id"):
            edges.append({
                "source": f"branch_{b['parent_branch_id']}",
                "target": f"branch_{b['id']}",
                "type": "branch_split"
            })

    return jsonify({"nodes": nodes, "edges": edges})

# --- Checkpoints ---

@app.route('/api/checkpoints', methods=['GET'])
def api_get_checkpoints():
    checkpoints = load_checkpoints()
    return jsonify({"checkpoints": checkpoints})

@app.route('/api/checkpoints/<int:cp_id>', methods=['GET'])
def api_get_checkpoint(cp_id):
    checkpoints = load_checkpoints()
    for cp in checkpoints:
        if cp.get("id") == cp_id:
            return jsonify({"checkpoint": cp})
    return jsonify({"error": "断点不存在"}), 404

@app.route('/api/checkpoints', methods=['POST'])
def api_create_checkpoint():
    data = request.json
    checkpoints = load_checkpoints()
    cp_id = len(checkpoints) + 1

    papers_data = load_papers()
    branches_data = load_branches()

    checkpoint = {
        "id": cp_id,
        "name": data.get("name", f"断点-{cp_id}"),
        "description": data.get("description", ""),
        "snapshot": {
            "papers": papers_data,
            "branches": branches_data
        },
        "created_at": datetime.now().isoformat()
    }
    checkpoints.append(checkpoint)
    save_checkpoints(checkpoints)
    return jsonify({"checkpoint": checkpoint, "message": "断点已创建"})

@app.route('/api/checkpoints/<int:cp_id>', methods=['POST'])
def api_restore_checkpoint(cp_id):
    checkpoints = load_checkpoints()
    for cp in checkpoints:
        if cp.get("id") == cp_id:
            snapshot = cp.get("snapshot", {})
            if "papers" in snapshot:
                save_papers(snapshot["papers"])
            if "branches" in snapshot:
                save_branches(snapshot["branches"])
            return jsonify({"message": "断点已恢复", "checkpoint": cp})
    return jsonify({"error": "断点不存在"}), 404

@app.route('/api/checkpoints/<int:cp_id>', methods=['DELETE'])
def api_delete_checkpoint(cp_id):
    checkpoints = load_checkpoints()
    checkpoints = [cp for cp in checkpoints if cp.get("id") != cp_id]
    save_checkpoints(checkpoints)
    return jsonify({"message": "断点已删除"})

# --- Compare ---

@app.route('/api/compare', methods=['POST'])
def api_compare_papers():
    data = request.json
    paper_ids = data.get("paper_ids", [])
    if not paper_ids:
        return jsonify({"error": "请选择要对比的论文"}), 400

    papers_data = load_papers()
    papers = []
    for pid in paper_ids:
        for p in papers_data.get("papers", []):
            if p.get("id") == pid:
                papers.append(p)
                break

    comparisons = []
    for p in papers:
        comparisons.append({
            "id": p.get("id"),
            "title": p.get("title", "未命名"),
            "score": p.get("score", 0),
            "created_at": p.get("created_at"),
            "branch_id": p.get("branch_id"),
            "innovation": p.get("score_details", {}).get("innovation", {}),
            "methodology": p.get("score_details", {}).get("methodology", {}),
            "experiment": p.get("score_details", {}).get("experiment", {}),
            "writing": p.get("score_details", {}).get("writing", {})
        })

    return jsonify({"comparisons": comparisons, "count": len(comparisons)})

# --- Download ---

@app.route('/api/download/<int:paper_id>/<file_type>', methods=['GET'])
def api_download(paper_id, file_type):
    """下载论文文件"""
    papers_data = load_papers()
    paper = None
    for p in papers_data.get("papers", []):
        if p.get("id") == paper_id:
            paper = p
            break
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    from flask import send_file, make_response
    branch_id = paper.get("branch_id", 1)

    if file_type == "content":
        content = paper.get("content", "")
        if not content:
            return jsonify({"error": "内容为空"}), 404
        response = make_response(content)
        title = paper.get("title", f"paper_{paper_id}")
        safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:50]
        response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_title}.md"'
        return response
    elif file_type == "json":
        return jsonify(paper)
    else:
        return jsonify({"error": "不支持的文件类型"}), 400


@app.route('/v2/')
def v2_index():
    return app.send_static_file('v2/index.html')

@app.route('/v2/<path:static_file>')
def v2_static(static_file):
    return app.send_static_file(f'v2/{static_file}')

@app.route('/')
def index():
    return app.send_static_file('fars_dashboard.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


if __name__ == '__main__':
    print("=" * 60)
    print("FARS 论文评分与迭代重生成服务器 (paperwriterAI)")
    print("=" * 60)
    print("API端点:")
    print("  POST /api/score       - 论文评分")
    print("  POST /api/regenerate  - 论文重生成")
    print("  POST /api/find_papers - 查找相关论文")
    print("  POST /api/iterate     - 完整迭代流程")
    print("  POST /api/history     - 获取历史记录列表")
    print("  GET  /api/history/<id> - 获取历史记录详情")
    print("  GET  /v2/             - FARS v2前端")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8081, debug=False, threaded=True)