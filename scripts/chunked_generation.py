"""
ChunkManager - LLM分块生成与检查点管理
解决LLM输出截断问题，通过状态注入实现断点续生成

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的长文本生成
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, List, Dict, Any, Generator
from enum import Enum
from pathlib import Path


class ChunkState(Enum):
    """分块状态枚举"""
    PENDING = "pending"          # 等待处理
    GENERATING = "generating"    # 正在生成
    PAUSED = "paused"            # 已暂停（等待续写）
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 生成失败


@dataclass
class GenerationCheckpoint:
    """
    生成检查点 - 记录每次分块生成的状态快照
    
    核心思想: 每次生成前记录"已生成内容 + 续写提示"，这样即使中途截断，
    也能从检查点恢复，不丢失任何内容。
    """
    chunk_id: str                    # 分块唯一标识
    chunk_index: int                 # 分块序号（0, 1, 2...）
    state: ChunkState                # 当前状态
    
    # === 核心状态字段 ===
    content: str                     # 已生成的内容
    prompt_suffix: str                # 续写时使用的提示词后缀
    total_tokens_used: int           # 累计使用的token数
    
    # === 上下文管理 ===
    context_summary: str             # 前序内容摘要（用于快速注入）
    last_generated_length: int      # 上次生成的长度
    
    # === 元数据 ===
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    retry_count: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['state'] = self.state.value  # Convert enum to string
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GenerationCheckpoint':
        data['state'] = ChunkState(data['state'])
        return cls(**data)
    
    def compute_fingerprint(self) -> str:
        """计算内容指纹，用于检测内容变化"""
        content_hash = hashlib.md5(self.content.encode()).hexdigest()
        return f"{self.chunk_id}_{self.chunk_index}_{content_hash}"


@dataclass
class GenerationConfig:
    """生成配置"""
    model: str = "MiniMax/MiniMax-Text-01"
    max_tokens_per_chunk: int = 8000      # 每块最大token数（留余量给system prompt）
    overlap_tokens: int = 500             # 重叠token数（用于上下文连贯）
    checkpoint_dir: str = "./checkpoints"  # 检查点存储目录
    enable_streaming: bool = True         # 是否启用流式输出
    temperature: float = 0.7
    top_p: float = 0.95
    request_timeout: int = 120


class ChunkManager:
    """
    分块生成管理器
    
    工作流程:
    1. 将长文本任务分解为多个可管理的分块
    2. 逐块生成内容，在块之间插入[PAUSE]标记
    3. 每次生成后保存检查点
    4. 如果截断，从检查点恢复并续写
    
    示例用法:
        manager = ChunkManager(config)
        
        # 方式1: 生成整个文档
        result = manager.generate(
            system_prompt="你是一个学术论文写作助手",
            user_request="请写一篇关于量化交易的完整论文，包含摘要、引言、文献综述、实验、结论...",
            output_path="./output/paper.txt"
        )
        
        # 方式2: 流式生成（实时显示进度）
        for chunk_result in manager.generate_streaming(prompts):
            print(chunk_result.content, end="", flush=True)
    """
    
    # === 协议标记（Protocol Markers）===
    PAUSE_MARKER = "[PAUSE]"
    CONTINUE_MARKER = "[CONTINUE]"
    CHECKPOINT_MARKER = "[CHECKPOINT]"
    END_MARKER = "[END]"
    
    # 默认续写提示词模板
    DEFAULT_RESUME_PROMPT = """请继续上一段的内容。保持相同的写作风格和学术规范。
上一段结束于: "{last_sentence}"
请继续撰写下一部分内容。"""

    def __init__(self, config: Optional[GenerationConfig] = None):
        self.config = config or GenerationConfig()
        self.checkpoints: List[GenerationCheckpoint] = []
        self.current_chunk_index = 0
        self.total_content = ""
        
        # 确保检查点目录存在
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    
    def split_into_chunks(self, content: str, max_tokens: int) -> List[str]:
        """
        将内容分割成多个分块
        
        策略:
        - 按段落分割（保持语义完整性）
        - 如果段落过长，按句子分割
        - 保留重叠区域以确保上下文连贯
        """
        # 简化版本：按段落分割
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        # 粗略估计：1个中文字 ≈ 1.5 tokens, 1个英文单词 ≈ 1.3 tokens
        def estimate_tokens(text: str) -> int:
            chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            other_chars = len(text) - chinese_chars
            return int(chinese_chars * 1.5 + other_chars * .3)
        
        for para in paragraphs:
            para_tokens = estimate_tokens(para)
            
            if current_tokens + para_tokens > max_tokens and current_chunk:
                chunks.append(current_chunk.strip())
                # 保留最后overlap_tokens的内容作为下一个块的上下文
                overlap_text = self._extract_overlap(current_chunk)
                current_chunk = overlap_text + para
                current_tokens = estimate_tokens(current_chunk)
            else:
                current_chunk += "\n\n" + para if current_chunk else para
                current_tokens += para_tokens
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [content]
    
    def _extract_overlap(self, text: str, num_chars: int = 200) -> str:
        """提取文本末尾的重叠部分"""
        if len(text) <= num_chars:
            return text
        # 尝试在句子边界截断
        overlap = text[-num_chars:]
        # 找到最近的句号或逗号
        for sep in ['。', '！', '？', '，', '. ', '! ', '? ']:
            idx = overlap.find(sep, len(overlap) // 2)
            if idx != -1:
                return overlap[idx + len(sep):]
        return overlap
    
    def save_checkpoint(self, checkpoint: GenerationCheckpoint) -> str:
        """
        保存检查点到磁盘
        
        返回: 检查点文件路径
        """
        checkpoint.updated_at = time.time()
        filepath = Path(self.config.checkpoint_dir) / f"cp_{checkpoint.chunk_id}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 同时更新内存中的检查点列表
        existing_idx = None
        for i, cp in enumerate(self.checkpoints):
            if cp.chunk_id == checkpoint.chunk_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            self.checkpoints[existing_idx] = checkpoint
        else:
            self.checkpoints.append(checkpoint)
        
        return str(filepath)
    
    def load_checkpoint(self, chunk_id: str) -> Optional[GenerationCheckpoint]:
        """从磁盘加载检查点"""
        filepath = Path(self.config.checkpoint_dir) / f"cp_{chunk_id}.json"
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return GenerationCheckpoint.from_dict(data)
    
    def list_checkpoints(self) -> List[GenerationCheckpoint]:
        """列出所有检查点"""
        checkpoints = []
        cp_dir = Path(self.config.checkpoint_dir)
        
        for filepath in cp_dir.glob("cp_*.json"):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                checkpoints.append(GenerationCheckpoint.from_dict(data))
        
        return sorted(checkpoints, key=lambda x: x.chunk_index)
    
    def generate_with_checkpoints(
        self,
        system_prompt: str,
        user_request: str,
        task_id: str,
        api_caller: Callable[[str, str], str]  # (system, user) -> response
    ) -> Generator[GenerationCheckpoint, None, None]:
        """
        使用检查点机制进行分块生成
        
        参数:
            task_id: 任务唯一标识（用于组织检查点文件）
            api_caller: API调用函数，接收(system_prompt, user_prompt)返回生成的文本
        
        使用示例:
            def call_api(system, user):
                return call_minimax_api(system, user)
            
            manager = ChunkManager()
            
            for checkpoint in manager.generate_with_checkpoints(
                system_prompt="你是学术论文写作助手",
                user_request="请写一篇完整的量化交易论文...",
                task_id="paper_001",
                api_caller=call_api
            ):
                print(f"完成第 {checkpoint.chunk_index + 1} 块, 累计tokens: {checkpoint.total_tokens_used}")
        """
        
        task_id_hash = hashlib.md5(task_id.encode()).hexdigest()[:8]
        chunk_index = 0
        accumulated_content = ""
        total_tokens = 0
        
        # 尝试恢复已存在的检查点
        existing_checkpoints = self.list_checkpoints()
        if existing_checkpoints:
            # 找到最后一个完成或暂停的检查点
            for cp in reversed(existing_checkpoints):
                if cp.state in [ChunkState.COMPLETED, ChunkState.PAUSED]:
                    chunk_index = cp.chunk_index + 1
                    accumulated_content = cp.content
                    total_tokens = cp.total_tokens_used
                    break
        
        while True:
            # 构建当前块的提示词
            if chunk_index == 0:
                # 第一个块：完整任务描述
                current_user = user_request
                context_prefix = ""
            else:
                # 后续块：包含前序内容摘要
                context_prefix = self._build_context_prefix(accumulated_content)
                current_user = f"""{context_prefix}

{self.CONTINUE_MARKER}
请继续撰写上一部分未完成的内容。保持写作风格和学术规范的一致性。"""
            
            # 创建当前块的检查点
            checkpoint = GenerationCheckpoint(
                chunk_id=task_id_hash,
                chunk_index=chunk_index,
                state=ChunkState.GENERATING,
                content=accumulated_content,
                prompt_suffix=current_user,
                total_tokens_used=total_tokens,
                context_summary=self._summarize(accumulated_content),
                last_generated_length=len(accumulated_content)
            )
            
            # 保存初始检查点
            self.save_checkpoint(checkpoint)
            
            # 调用API生成内容
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # 构建完整的system prompt，包含写作规范
                    full_system = f"""{system_prompt}

## 生成协议
- 使用 [PAUSE] 标记表示当前块已完成，等待续写指令
- 使用 [END] 标记表示整篇文档已完成
- 保持内容连贯性，确保段落之间衔接自然"""

                    response = api_caller(full_system, current_user)
                    
                    # 检查是否包含暂停标记
                    if self.PAUSE_MARKER in response:
                        response = response.split(self.PAUSE_MARKER)[0].strip()
                    
                    if self.END_MARKER in response:
                        response = response.split(self.END_MARKER)[0].strip()
                        is_final = True
                    else:
                        is_final = False
                    
                    # 更新内容
                    if chunk_index == 0:
                        accumulated_content = response
                    else:
                        accumulated_content += "\n\n" + response
                    
                    total_tokens += self._estimate_tokens(response)
                    
                    # 更新检查点状态
                    checkpoint.content = accumulated_content
                    checkpoint.state = ChunkState.COMPLETED if is_final else ChunkState.PAUSED
                    checkpoint.total_tokens_used = total_tokens
                    checkpoint.last_generated_length = len(response)
                    self.save_checkpoint(checkpoint)
                    
                    yield checkpoint
                    
                    if is_final:
                        return
                    
                    chunk_index += 1
                    break
                    
                except Exception as e:
                    checkpoint.error_message = str(e)
                    checkpoint.retry_count += 1
                    
                    if checkpoint.retry_count >= max_attempts:
                        checkpoint.state = ChunkState.FAILED
                        self.save_checkpoint(checkpoint)
                        raise
                    
                    # 等待后重试
                    time.sleep(2 ** checkpoint.retry_count)
    
    def _build_context_prefix(self, content: str, max_context_chars: int = 1000) -> str:
        """构建上下文前缀"""
        if len(content) <= max_context_chars:
            return f"## 前文内容摘要\n\n{content}\n\n---\n上文结束于此，请继续。"
        
        # 提取最后max_context_chars字符
        recent_content = content[-max_context_chars:]
        
        # 找到段落开头
        for sep in ['\n\n', '\n', ' ']:
            idx = recent_content.find(sep, len(recent_content) // 2)
            if idx != -1:
                recent_content = recent_content[idx + len(sep):]
                break
        
        return f"## 前文内容（最近部分）\n\n{recent_content}\n\n---\n上文结束于此，请继续。"
    
    def _summarize(self, content: str, max_summary_chars: int = 300) -> str:
        """生成内容摘要（简化版，实际应用中可用LLM）"""
        if len(content) <= max_summary_chars:
            return content
        
        # 提取前几句和后几句
        sentences = content.replace('。', '。|').replace('\n', '|').split('|')
        total_len = 0
        summary_parts = []
        
        for s in sentences:
            if total_len + len(s) <= max_summary_chars // 2:
                summary_parts.append(s)
                total_len += len(s)
        
        for s in reversed(sentences):
            if total_len + len(s) <= max_summary_chars:
                summary_parts.insert(0, s)
                total_len += len(s)
        
        return '...'.join(summary_parts)
    
    def _estimate_tokens(self, text: str) -> int:
        """估算token数量"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 1.3)
    
    def merge_chunks(self, checkpoints: List[GenerationCheckpoint]) -> str:
        """合并多个检查点的内容"""
        sorted_cps = sorted(checkpoints, key=lambda x: x.chunk_index)
        return "\n\n".join(cp.content for cp in sorted_cps if cp.state == ChunkState.COMPLETED)
    
    def generate_streaming(
        self,
        system_prompt: str,
        initial_prompt: str,
        api_caller: Callable[[str, str, int], Generator[str, None, None]]
    ) -> Generator[str, None, None]:
        """
        流式生成（实时显示进度）
        
        api_caller 应该是流式API，返回 Generator[str, None, None]
        每yield一个字符串片段，就立即yield给调用方
        同时累积检查点
        """
        accumulated = ""
        chunk_size = 2000  # 每2000字符保存一次检查点
        
        # 初始化检查点
        task_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        checkpoint = GenerationCheckpoint(
            chunk_id=task_id,
            chunk_index=0,
            state=ChunkState.GENERATING,
            content="",
            prompt_suffix=initial_prompt,
            total_tokens_used=0,
            context_summary=""
        )
        
        try:
            for text_chunk in api_caller(system_prompt, initial_prompt, stream=True):
                accumulated += text_chunk
                yield text_chunk
                
                # 定期保存检查点
                if len(accumulated) >= chunk_size:
                    checkpoint.content = accumulated
                    checkpoint.total_tokens_used = self._estimate_tokens(accumulated)
                    checkpoint.state = ChunkState.GENERATING
                    self.save_checkpoint(checkpoint)
            
            # 最终保存
            checkpoint.content = accumulated
            checkpoint.state = ChunkState.COMPLETED
            checkpoint.total_tokens_used = self._estimate_tokens(accumulated)
            self.save_checkpoint(checkpoint)
            
        except Exception as e:
            # 失败时保存当前进度
            checkpoint.content = accumulated
            checkpoint.state = ChunkState.PAUSED
            checkpoint.error_message = str(e)
            self.save_checkpoint(checkpoint)
            raise


# ============================================================
# 集成示例：与MiniMax API配合使用
# ============================================================

class MiniMaxChunkedGenerator:
    """
    MiniMax API 分块生成器
    
    封装MiniMax API调用，自动处理分块和检查点
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.chunk_manager = ChunkManager()
    
    def call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        stream: bool = False
    ) -> Generator[str, None, None] | str:
        """
        调用MiniMax API
        
        返回:
            - 流式模式: Generator[str, None, None]
            - 非流式模式: str
        """
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "MiniMax-Text-01",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "top_p": 0.95,
            "stream": stream
        }
        
        if stream:
            def generate():
                response = requests.post(
                    f"{self.base_url}/text/chatcompletion_v2",
                    headers=headers,
                    json=payload,
                    stream=True
                )
                
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode('utf-8')[6:])
                        if 'choices' in data and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            if 'content' in delta:
                                yield delta['content']
            
            return generate()
        else:
            response = requests.post(
                f"{self.base_url}/text/chatcompletion_v2",
                headers=headers,
                json=payload
            )
            data = response.json()
            return data['choices'][0]['message']['content']
    
    def generate_paper(
        self,
        paper_topic: str,
        sections: List[str],
        output_path: str
    ) -> str:
        """
        生成分段式论文
        
        参数:
            paper_topic: 论文主题
            sections: 论文各节标题列表
            output_path: 输出文件路径
        """
        system_prompt = """你是一位资深的量化交易研究学者，擅长用严谨的学术语言撰写高质量的研究论文。

写作规范:
1. 使用规范的学术中文写作
2. 公式使用LaTeX格式
3. 表格使用标准格式
4. 保持逻辑连贯，论述严谨
5. 在每个主要段落结束时添加 [PAUSE] 标记，等待续写指令"""

        # 构建整体论文提示
        sections_str = "\n".join([f"{i+1}. {s}" for i, s in enumerate(sections)])
        user_request = f"""请撰写一篇关于"{paper_topic}"的完整学术论文。

论文结构:
{sections_str}

请按照上述结构撰写完整的论文。在完成每个主要部分后添加 [PAUSE] 标记。"""

        all_content = []
        
        # 使用分块生成
        for checkpoint in self.chunk_manager.generate_with_checkpoints(
            system_prompt=system_prompt,
            user_request=user_request,
            task_id=f"paper_{hashlib.md5(paper_topic.encode()).hexdigest()[:8]}",
            api_caller=lambda sys, usr: self.call_api(sys, usr, stream=False)
        ):
            if checkpoint.state == ChunkState.COMPLETED:
                all_content.append(checkpoint.content)
        
        # 合并并保存
        final_content = "\n\n".join(all_content)
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        return final_content


# ============================================================
# 演示代码
# ============================================================

if __name__ == "__main__":
    # 演示如何创建和使用ChunkManager
    
    print("=" * 60)
    print("ChunkManager 演示")
    print("=" * 60)
    
    # 1. 创建配置
    config = GenerationConfig(
        model="MiniMax/MiniMax-Text-01",
        max_tokens_per_chunk=8000,
        checkpoint_dir="./demo_checkpoints"
    )
    
    # 2. 创建管理器
    manager = ChunkManager(config)
    
    # 3. 演示：模拟API调用（实际使用时替换为真实API）
    def mock_api_caller(system: str, user: str) -> str:
        """模拟API调用，实际应用中替换为真实API"""
        print(f"\n[模拟API调用]")
        print(f"  System prompt长度: {len(system)} 字符")
        print(f"  User prompt长度: {len(user)} 字符")
        return f"[这是第N块生成的内容...]\n\n[PAUSE]"
    
    # 4. 模拟生成分块
    print("\n演示生成流程:")
    
    task_id = "demo_paper_001"
    
    for checkpoint in manager.generate_with_checkpoints(
        system_prompt="你是学术论文写作助手",
        user_request="请撰写一篇关于量化交易策略的完整论文，包含摘要、引言、实验和结论。",
        task_id=task_id,
        api_caller=mock_api_caller
    ):
        print(f"\n检查点状态:")
        print(f"  块 #{checkpoint.chunk_index + 1}")
        print(f"  状态: {checkpoint.state.value}")
        print(f"  内容长度: {len(checkpoint.content)} 字符")
        print(f"  累计Token: ~{checkpoint.total_tokens_used}")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    
    # 5. 列出所有检查点
    print("\n已保存的检查点文件:")
    for cp in manager.list_checkpoints():
        print(f"  - {cp.chunk_id}_chunk{cp.chunk_index}.json ({cp.state.value})")