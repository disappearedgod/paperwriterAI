"""
FARS - Literature Review Engine (STORM-style)
文献综述引擎：集成多视角生成、深度问题提问、证据收集
"""

import json
import re
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None


class LiteratureReviewEngine:
    """
    文献综述引擎 (STORM + GPT Researcher 风格)

    Phase 1: Pre-writing (调研阶段)
    - Perspective Generation (视角生成)
    - Question Asking (问题生成)
    - Evidence Collection (证据收集)
    - Outline Generation (大纲生成)

    Phase 2: Writing (写作阶段)
    - Section-by-section Generation
    - Citation Integration (引用整合)
    """

    def __init__(self, api_key: str = None, api_url: str = None, model: str = None):
        """
        初始化文献综述引擎

        Args:
            api_key: MiniMax API密钥
            api_url: MiniMax API地址
            model: 模型名称
        """
        import os as _os
        # 从config.json读取配置
        _cfg_file = _os.path.join(_os.path.dirname(__file__), '..', '..', 'config.json')
        _llm_cfg = {}
        if _os.path.exists(_cfg_file):
            with open(_cfg_file, 'r') as _f:
                _llm_cfg = json.load(_f).get('llm', {})

        self.api_key = api_key or _llm_cfg.get('api_key', '') or _os.environ.get("MINIMAX_API_KEY", "")
        self.api_url = api_url or _llm_cfg.get('base_url', 'https://minnimax.chat/v1')
        self.model = model or _llm_cfg.get('model', 'MiniMax-M2.7')

    def _call_llm(self, prompt: str, temperature: float = 0.7,
                  max_output_tokens: int = 4096) -> Optional[str]:
        """
        调用MiniMax LLM

        Args:
            prompt: 输入提示
            temperature: 温度参数
            max_output_tokens: 最大输出token数

        Returns:
            LLM回复文本
        """
        if not self.api_key:
            return self._fallback_response(prompt)

        if requests is None:
            return self._fallback_response(prompt)

        try:
            # 估算token
            estimated_input_tokens = len(prompt) // 3
            safe_max_tokens = min(max_output_tokens, 150000 - estimated_input_tokens)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_completion_tokens": safe_max_tokens
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=120
            )
            result = response.json()

            if "error" in result:
                print(f"[LiteratureReviewEngine] LLM API error: {result['error']}")
                return None

            return result.get("choices", [{}])[0].get("message", {}).get("content")

        except Exception as e:
            print(f"[LiteratureReviewEngine] LLM call failed: {e}")
            return None

    def _fallback_response(self, prompt: str) -> str:
        """当API不可用时的降级响应"""
        return json.dumps({
            "status": "fallback",
            "message": "API not available"
        }, ensure_ascii=False)

    def _parse_json_response(self, response: str) -> Dict:
        """
        解析LLM的JSON响应

        Args:
            response: LLM原始响应

        Returns:
            解析后的字典
        """
        if not response:
            return {}

        # 尝试提取JSON块
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # 尝试直接解析
        try:
            return json.loads(response)
        except:
            pass

        # 返回原始文本
        return {"raw": response}

    # ==================== Perspective Generation ====================

    def generate_perspectives(self, topic: str, num_perspectives: int = 5) -> List[Dict]:
        """
        生成研究视角 (STORM Phase 1.1-1.2)

        Args:
            topic: 研究主题
            num_perspectives: 视角数量

        Returns:
            视角列表
        """
        prompt = f"""## 任务: 生成研究视角

针对主题: {topic}

请从多个学术视角分析该主题，生成 {num_perspectives} 个视角，每个视角需包含:
1. 视角名称 (如: 机器学习、量化金融、行为金融学)
2. 核心研究问题 (2-3个)
3. 相关方法论
4. 潜在贡献

### 视角类型

1. **方法论视角**: 该主题涉及的方法/算法
2. **应用视角**: 实际应用场景和效果
3. **评估视角**: 如何评估/验证
4. **比较视角**: 与现有方法对比
5. **局限性视角**: 已知问题和改进空间

### 输出格式

请输出JSON格式结果:
```json
{{
  "perspectives": [
    {{
      "name": "视角名称",
      "research_questions": ["问题1", "问题2", "问题3"],
      "methodology": "相关方法论",
      "potential_contribution": "潜在贡献"
    }}
  ]
}}
```"""

        response = self._call_llm(prompt, temperature=0.7, max_output_tokens=4096)
        parsed = self._parse_json_response(response)

        perspectives = parsed.get("perspectives", [])
        if not perspectives:
            # 降级：返回默认视角
            perspectives = self._default_perspectives(topic)

        return perspectives

    def _default_perspectives(self, topic: str) -> List[Dict]:
        """返回默认视角"""
        return [
            {
                "name": "方法论视角",
                "research_questions": [
                    f"针对{topic}有哪些主要方法论？",
                    f"哪些机器学习算法适合解决{topic}？"
                ],
                "methodology": "机器学习、深度学习、强化学习",
                "potential_contribution": "方法创新"
            },
            {
                "name": "应用视角",
                "research_questions": [
                    f"{topic}在实际交易中如何应用？"
                ],
                "methodology": "策略设计、回测验证",
                "potential_contribution": "实践价值"
            },
            {
                "name": "评估视角",
                "research_questions": [
                    f"如何评估{topic}的效果？"
                ],
                "methodology": "多维度评估框架",
                "potential_contribution": "评估标准"
            }
        ]

    # ==================== Question Asking ====================

    def generate_questions(self, topic: str, perspective: Dict) -> List[Dict]:
        """
        生成深度研究问题 (STORM Phase 1.2)

        Args:
            topic: 研究主题
            perspective: 视角信息

        Returns:
            问题列表
        """
        prompt = f"""## 任务: 生成深度研究问题

主题: {topic}
视角: {perspective.get('name', '')}

请为上述视角生成 5-8 个深度研究问题，这些问题应该:
1. 探索该视角下的关键争议
2. 寻求具体的证据和数据
3. 引导发现主题的深层联系

### 问题类型

- **背景问题**: 关于主题基本事实的问题
- **比较问题**: 与其他方法/观点的异同
- **因果问题**: 原因和结果的关系
- **评估问题**: 优缺点和适用性

### 输出格式

请输出JSON格式:
```json
{{
  "perspective": "{perspective.get('name', '')}",
  "questions": [
    {{
      "type": "问题类型",
      "question": "问题内容",
      "expected_answer_type": "期望的答案类型"
    }}
  ]
}}
```"""

        response = self._call_llm(prompt, temperature=0.5, max_output_tokens=4096)
        parsed = self._parse_json_response(response)

        questions = parsed.get("questions", [])
        if not questions and "research_questions" in perspective:
            # 从视角中提取问题
            questions = [
                {"type": "背景问题", "question": q, "expected_answer_type": "事实性答案"}
                for q in perspective.get("research_questions", [])
            ]

        return questions

    # ==================== Evidence Collection ====================

    def collect_evidence(self, topic: str, questions: List[Dict],
                         existing_papers: List[Dict] = None) -> Dict[str, Any]:
        """
        收集证据 (STORM Phase 1.3)

        Args:
            topic: 研究主题
            questions: 问题列表
            existing_papers: 已有论文列表

        Returns:
            证据字典 {问题: 答案/证据}
        """
        evidence = {}

        for q in questions:
            question_text = q.get("question", "")
            if not question_text:
                continue

            # 为每个问题生成回答
            prompt = f"""## 任务: 回答研究问题并提供证据

主题: {topic}
问题: {question_text}
问题类型: {q.get('type', '背景问题')}

请提供一个全面、有据可查的回答，包含:
1. 直接回答问题
2. 支持该回答的证据或数据
3. 相关的学术引用（如果知道）

### 回答格式

请用中文回答，保持学术风格。"""

            answer = self._call_llm(prompt, temperature=0.7, max_output_tokens=2048)

            evidence[question_text] = {
                "answer": answer or "（暂无足够信息）",
                "type": q.get("type", "背景问题"),
                "source": "LLM-generated"
            }

        return evidence

    def collect_evidence_from_papers(self, topic: str,
                                     papers: List[Dict]) -> str:
        """
        从已有论文中收集证据

        Args:
            topic: 研究主题
            papers: 论文列表

        Returns:
            综合证据文本
        """
        if not papers:
            return ""

        # 构建论文摘要文本
        paper_summaries = []
        for i, paper in enumerate(papers[:10]):  # 限制最多10篇
            summary = f"[{i+1}] {paper.get('title', '未知标题')}"
            if paper.get('abstract'):
                summary += f"\n   摘要: {paper['abstract'][:300]}..."
            if paper.get('methodology'):
                summary += f"\n   方法: {paper['methodology']}"
            paper_summaries.append(summary)

        papers_text = "\n\n".join(paper_summaries)

        prompt = f"""## 任务: 基于已有文献生成综述性回答

研究主题: {topic}

已有文献:
{papers_text}

任务要求:
1. 综合上述文献，总结该主题的主要研究方向
2. 指出各文献之间的关系和差异
3. 识别研究空白和争议点
4. 提出潜在的研究机会

请用中文撰写一段300-500字的综述性回答，包含学术引用格式。"""

        response = self._call_llm(prompt, temperature=0.7, max_output_tokens=4096)
        return response or "（暂无文献证据）"

    # ==================== Outline Generation ====================

    def generate_outline(self, topic: str, perspectives: List[Dict],
                         evidence: Dict) -> Dict:
        """
        生成论文大纲 (STORM Phase 1.4)

        Args:
            topic: 研究主题
            perspectives: 视角列表
            evidence: 证据字典

        Returns:
            结构化大纲
        """
        # 构建证据摘要
        evidence_summary = []
        for q, a in evidence.items():
            if isinstance(a, dict):
                evidence_summary.append(f"Q: {q}\nA: {a.get('answer', '')}")
            else:
                evidence_summary.append(f"Q: {q}\nA: {a}")

        evidence_text = "\n\n".join(evidence_summary[:10])  # 限制长度

        prompt = f"""## 任务: 生成论文大纲

主题: {topic}

视角分析:
{json.dumps(perspectives, ensure_ascii=False, indent=2)}

收集到的证据:
{evidence_text}

请生成一个完整的论文大纲，包含:
1. 摘要 (Abstract)
2. 引言 (Introduction) - 包含研究背景、动机、贡献
3. 文献综述 (Literature Review) - 分类讨论相关工作
4. 方法论 (Methodology) - 详细描述方法
5. 实验/验证 (Experiments/Validation)
6. 结果分析 (Results)
7. 讨论 (Discussion)
8. 结论 (Conclusion)

### 输出格式

```json
{{
  "outline": {{
    "title": "论文标题",
    "sections": [
      {{
        "name": "章节名称",
        "subsections": ["子节1", "子节2"],
        "key_points": ["要点1", "要点2"]
      }}
    ],
    "total_estimated_words": 8000
  }}
}}
```"""

        response = self._call_llm(prompt, temperature=0.5, max_output_tokens=4096)
        parsed = self._parse_json_response(response)

        outline = parsed.get("outline", {})
        if not outline:
            outline = self._default_outline(topic)

        return outline

    def _default_outline(self, topic: str) -> Dict:
        """返回默认大纲"""
        return {
            "title": f"基于{topic}的量化交易策略研究",
            "sections": [
                {"name": "Abstract", "subsections": [], "key_points": ["问题", "方法", "结论"]},
                {"name": "Introduction", "subsections": ["Background", "Motivation", "Contributions"],
                 "key_points": ["研究背景", "研究动机", "主要贡献"]},
                {"name": "Literature Review", "subsections": [], "key_points": ["相关工作分类"]},
                {"name": "Methodology", "subsections": ["Model", "Algorithm"], "key_points": ["方法描述"]},
                {"name": "Experiments", "subsections": [], "key_points": ["实验设计"]},
                {"name": "Results", "subsections": [], "key_points": ["结果分析"]},
                {"name": "Conclusion", "subsections": [], "key_points": ["总结", "未来工作"]}
            ],
            "total_estimated_words": 8000
        }

    # ==================== Literature Review Section ====================

    def generate_literature_review_section(self, topic: str,
                                            evidence: Dict,
                                            outline: Dict = None) -> str:
        """
        生成文献综述章节 (STORM Writing Phase)

        Args:
            topic: 研究主题
            evidence: 证据字典
            outline: 可选的大纲

        Returns:
            LaTeX格式的文献综述章节
        """
        # 构建证据文本
        evidence_parts = []
        for q, a in evidence.items():
            if isinstance(a, dict):
                evidence_parts.append(f"**问题**: {q}\n\n**回答**: {a.get('answer', '')}")
            else:
                evidence_parts.append(f"**问题**: {q}\n\n**回答**: {a}")

        evidence_text = "\n\n".join(evidence_parts)

        prompt = f"""## 任务: 撰写文献综述章节 (LaTeX格式)

主题: {topic}

### 收集到的证据

{evidence_text}

### 任务要求

1. **结构化综述**: 按照主题流派/方法论分类组织
2. **批判性分析**: 总结各流派的优势和局限
3. **研究空白**: 明确当前研究的不足
4. **引用标注**: 使用 [1], [2], [3] 格式标注参考来源

### 章节结构

1. 概述该领域的发展历程
2. 分类讨论主要流派/方法
3. 分析各方法的优缺点
4. 指出研究空白和争议点
5. 引出本文的创新点

### 输出格式

请直接输出LaTeX源码，包含:
- \\section{{Literature Review}}
- 分类小节
- 引用标注
- 总结段落

请直接输出LaTeX源码，不需要其他说明。"""

        response = self._call_llm(prompt, temperature=0.7, max_output_tokens=8192)
        return response or self._default_literature_review(topic)

    def _default_literature_review(self, topic: str) -> str:
        """返回默认文献综述"""
        return rf"""\section{{Literature Review}}
\label{{sec:lit_review}}

\subsection{{研究背景}}

{topic}是量化交易领域的重要研究方向。近年来，随着机器学习和深度学习技术的发展，该领域取得了显著进展。

\subsection{{主要方法}}

\subsubsection*{{传统量化方法}}
传统量化方法主要包括多因子模型、均值回归策略和动量策略等。

\subsubsection*{{机器学习方法}}
随着AlphaPortfolio等工作的提出，基于机器学习的量化策略研究日益成熟。

\subsubsection*{{深度学习方法}}
Transformer、注意力机制等深度学习技术被广泛应用于量化预测。

\subsection*{{研究空白}}

现有研究在以下方面存在不足:
\begin{{enumerate}}
\item 数据利用效率有待提高
\item 模型可解释性不足
\item 策略稳健性需要进一步验证
\end{{enumerate}}

\subsection*{{本文贡献}}

本文针对上述问题，提出以下创新点:
\begin{{enumerate}}
\item 提出新的因子挖掘方法
\item 构建可解释的策略框架
\item 设计稳健的回测验证流程
\end{{enumerate}}
"""

    # ==================== Full Pipeline ====================

    def generate(self, topic: str, existing_papers: List[Dict] = None,
                 num_perspectives: int = 5) -> Dict[str, Any]:
        """
        完整文献综述生成流程 (STORM-style)

        Args:
            topic: 研究主题
            existing_papers: 已有论文列表
            num_perspectives: 视角数量

        Returns:
            包含perspectives, questions, evidence, outline, literature_review的字典
        """
        result = {
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "status": "in_progress",
            "phases": {}
        }

        # Phase 1: Perspective Generation
        print(f"[LiteratureReviewEngine] Phase 1: Generating {num_perspectives} perspectives...")
        perspectives = self.generate_perspectives(topic, num_perspectives)
        result["phases"]["perspective_generation"] = {
            "status": "completed",
            "count": len(perspectives)
        }
        result["perspectives"] = perspectives

        # Phase 2: Question Asking (对每个视角生成问题)
        print("[LiteratureReviewEngine] Phase 2: Generating questions for each perspective...")
        all_questions = []
        for persp in perspectives:
            questions = self.generate_questions(topic, persp)
            all_questions.extend(questions)

        result["phases"]["question_asking"] = {
            "status": "completed",
            "count": len(all_questions)
        }
        result["questions"] = all_questions

        # Phase 3: Evidence Collection
        print("[LiteratureReviewEngine] Phase 3: Collecting evidence...")
        evidence = self.collect_evidence(topic, all_questions, existing_papers)

        # 如果有已有论文，也从中提取证据
        if existing_papers:
            paper_evidence = self.collect_evidence_from_papers(topic, existing_papers)
            evidence["_from_existing_papers"] = paper_evidence

        result["phases"]["evidence_collection"] = {
            "status": "completed",
            "count": len(evidence)
        }
        result["evidence"] = evidence

        # Phase 4: Outline Generation
        print("[LiteratureReviewEngine] Phase 4: Generating outline...")
        outline = self.generate_outline(topic, perspectives, evidence)
        result["phases"]["outline_generation"] = {
            "status": "completed"
        }
        result["outline"] = outline

        # Phase 5: Literature Review Section
        print("[LiteratureReviewEngine] Phase 5: Generating literature review section...")
        lit_review = self.generate_literature_review_section(topic, evidence, outline)
        result["phases"]["literature_review_generation"] = {
            "status": "completed"
        }
        result["literature_review"] = lit_review

        result["status"] = "completed"
        return result


# ==================== Review-Revision Loop (GPT Researcher-style) ====================

class ReviewReviser:
    """
    Review-Revision循环 (GPT Researcher风格)

    核心机制:
    - Reviewer: 评审论文质量，提出修改意见
    - Reviser: 根据修改意见修订论文
    - 最多4轮循环
    """

    def __init__(self, api_key: str = None, api_url: str = None):
        self.lit_engine = LiteratureReviewEngine(api_key, api_url)

    def _call_llm(self, prompt: str, temperature: float = 0.7,
                  max_output_tokens: int = 4096) -> Optional[str]:
        return self.lit_engine._call_llm(prompt, temperature, max_output_tokens)

    def review(self, title: str, content: str) -> Dict:
        """
        评审论文

        Args:
            title: 论文标题
            content: 论文内容

        Returns:
            评审结果
        """
        prompt = f"""## 任务: 评审论文质量

请评审以下论文章节:

### 论文标题
{title}

### 待评审内容
{content}

### 评审维度

1. **学术严谨性** (1-10)
   - 方法论是否合理
   - 论证是否有逻辑

2. **创新性** (1-10)
   - 是否有新贡献
   - 与现有工作如何区分

3. **完整性** (1-10)
   - 章节是否完整
   - 是否有遗漏重要方面

4. **可读性** (1-10)
   - 表达是否清晰
   - 结构是否合理

5. **引用质量** (1-10)
   - 引用是否相关
   - 是否有必要的背景引用

### 输出格式

请输出JSON格式:
```json
{{
  "overall_score": 7.5,
  "dimension_scores": {{
    "rigor": 7,
    "novelty": 8,
    "completeness": 7,
    "readability": 8,
    "citation_quality": 7
  }},
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["弱点1", "弱点2"],
  "revision_suggestions": [
    {{
      "location": "具体位置",
      "issue": "问题描述",
      "suggestion": "修改建议"
    }}
  ]
}}
```"""

        response = self._call_llm(prompt, temperature=0.3, max_output_tokens=4096)

        # 尝试解析JSON
        try:
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response or '', re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            if response:
                return json.loads(response)
        except:
            pass

        return {
            "overall_score": 5.0,
            "dimension_scores": {},
            "strengths": [],
            "weaknesses": ["无法解析评审结果"],
            "revision_suggestions": []
        }

    def revise(self, original_content: str, review_result: Dict) -> str:
        """
        根据评审意见修订论文

        Args:
            original_content: 原文
            review_result: 评审结果

        Returns:
            修订后的内容
        """
        # 构建修订提示
        suggestions_text = json.dumps(review_result.get("revision_suggestions", []),
                                     ensure_ascii=False, indent=2)

        prompt = f"""## 任务: 修订论文

### 原文
{original_content}

### 评审意见

整体评分: {review_result.get('overall_score', 'N/A')}

优点:
{chr(10).join(['- ' + s for s in review_result.get('strengths', [])])}

需要改进的地方:
{chr(10).join(['- ' + w for w in review_result.get('weaknesses', [])])}

具体修改建议:
{suggestions_text}

### 任务要求

根据评审意见修订论文内容，确保:
1. 解决所有提出的问题
2. 保持论文整体一致性
3. 不引入新的问题

请直接输出修订后的完整内容 (LaTeX 格式)。"""

        response = self._call_llm(prompt, temperature=0.5, max_output_tokens=8192)
        return response or original_content

    def loop(self, content: str, title: str = "论文标题",
             max_rounds: int = 4, min_score: float = 8.0) -> Dict[str, Any]:
        """
        执行Review-Revision循环

        Args:
            content: 论文内容
            title: 论文标题
            max_rounds: 最大轮次
            min_score: 达标分数

        Returns:
            包含最终内容和迭代历史的结果
        """
        history = []
        current_content = content
        current_title = title

        for round_num in range(1, max_rounds + 1):
            print(f"[ReviewReviser] Round {round_num}/{max_rounds}")

            # Review
            review_result = self.review(current_title, current_content)
            history.append({
                "round": round_num,
                "review": review_result,
                "content_before": current_content
            })

            score = review_result.get("overall_score", 0)
            print(f"[ReviewReviser] Round {round_num} score: {score}")

            # 检查是否达标
            if score >= min_score:
                print(f"[ReviewReviser] Score {score} >= {min_score}, stopping")
                break

            # 如果还有修改建议，执行修订
            if review_result.get("revision_suggestions"):
                current_content = self.revise(current_content, review_result)
                history[-1]["content_after"] = current_content
            else:
                print("[ReviewReviser] No more suggestions, stopping")
                break

        return {
            "final_content": current_content,
            "final_score": history[-1]["review"].get("overall_score", 0) if history else 0,
            "rounds_completed": len(history),
            "history": history
        }


# ==================== Factory Functions ====================

def create_literature_review_engine() -> LiteratureReviewEngine:
    """创建文献综述引擎实例"""
    return LiteratureReviewEngine()


def create_review_reviser() -> ReviewReviser:
    """创建评审修订器实例"""
    return ReviewReviser()
