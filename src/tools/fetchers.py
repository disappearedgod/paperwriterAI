"""
FARS - 工具模块
包含论文获取、数据源、回测执行等工具
"""

import os
import re
import json
import requests
import arxiv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import warnings
import uuid
import traceback

# ============== 论文获取工具 ==============

class PaperFetcher:
    """从多个来源获取学术论文"""

    def __init__(self, papers_dir: str = None):
        self.papers_dir = Path(papers_dir) if papers_dir else Path(__file__).parent.parent.parent.parent / "papers"
        self.papers_dir.mkdir(parents=True, exist_ok=True)

    def fetch_from_arxiv(self, query: str, max_results: int = 20, categories: List[str] = None) -> List[Dict]:
        """
        从arXiv获取论文

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            categories: arXiv分类列表，如['q-fin.PM', 'cs.LG']

        Returns:
            论文列表，每篇包含title, authors, abstract, arxiv_id, published等字段
        """
        results = []

        try:
            # 构建搜索查询
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            client = arxiv.Client()
            for paper in client.results(search):
                paper_info = {
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors],
                    "abstract": paper.summary,
                    "arxiv_id": paper.entry_id.split("/")[-1],
                    "published": paper.published.strftime("%Y-%m-%d"),
                    "updated": paper.updated.strftime("%Y-%m-%d"),
                    "categories": paper.categories,
                    "pdf_url": paper.pdf_url,
                    "comment": paper.comment,
                    "journal_ref": paper.journal_ref
                }

                # 如果指定了分类筛选
                if categories:
                    if any(cat in paper.categories for cat in categories):
                        results.append(paper_info)
                else:
                    results.append(paper_info)

        except Exception as e:
            print(f"Error fetching from arXiv: {e}")

        return results

    def fetch_from_semantic_scholar(self, query: str, max_results: int = 20,
                                     fields: List[str] = None) -> List[Dict]:
        """
        从Semantic Scholar获取论文

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            fields: 要获取的字段列表

        Returns:
            论文列表
        """
        if fields is None:
            fields = ["title", "authors", "abstract", "year", "openAccessPdf", "citationCount", "influentialCitationCount"]

        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": ",".join(fields)
        }

        results = []
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            for paper in data.get("data", []):
                results.append({
                    "title": paper.get("title"),
                    "authors": [a["name"] for a in paper.get("authors", [])],
                    "abstract": paper.get("abstract"),
                    "year": paper.get("year"),
                    "open_access_pdf": paper.get("openAccessPdf"),
                    "arxiv_id": paper.get("arxivId"),
                    "citation_count": paper.get("citationCount", 0),
                    "influential_citation_count": paper.get("influentialCitationCount", 0)
                })

        except Exception as e:
            print(f"Error fetching from Semantic Scholar: {e}")

        return results

    def download_paper_pdf(self, arxiv_id: str, filename: str = None) -> Optional[str]:
        """下载arXiv论文PDF"""
        if filename is None:
            filename = f"{arxiv_id}.pdf"

        pdf_path = self.papers_dir / filename

        if pdf_path.exists():
            return str(pdf_path)

        try:
            paper = next(arxiv.Search(id_list=[arxiv_id]).results())
            paper.download_pdf(dirpath=self.papers_dir, filename=filename)
            return str(pdf_path)
        except Exception as e:
            print(f"Error downloading PDF: {e}")
            return None

    def parse_paper_to_json(self, paper_info: Dict) -> Dict:
        """将论文信息解析为结构化JSON"""
        return {
            "paper_id": paper_info.get("arxiv_id", ""),
            "title": paper_info.get("title", ""),
            "authors": paper_info.get("authors", []),
            "year": paper_info.get("year") or paper_info.get("published", "")[:4],
            "arxiv_id": paper_info.get("arxiv_id", ""),
            "url": f"https://arxiv.org/abs/{paper_info.get('arxiv_id', '')}",
            "pdf_url": f"https://arxiv.org/pdf/{paper_info.get('arxiv_id', '')}.pdf",
            "abstract": self._clean_text(paper_info.get("abstract", "")),
            "methodology": "",
            "key_contributions": [],
            "status": "unread",
            "notes": "",
            "created_at": datetime.now().isoformat()
        }

    def _clean_text(self, text: str) -> str:
        """清理文本中的特殊字符"""
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('\n', ' ').strip()
        return text


# ============== 市场数据工具 ==============

class MarketDataFetcher:
    """获取市场数据"""

    def __init__(self):
        self.yfinance_available = False
        self.akshare_available = False

        try:
            import yfinance as yf
            self.yf = yf
            self.yfinance_available = True
        except ImportError:
            warnings.warn("yfinance not installed. Run: pip install yfinance")

        try:
            import akshare as ak
            self.ak = ak
            self.akshare_available = True
        except ImportError:
            warnings.warn("akshare not installed. Run: pip install akshare")

    def get_us_stock_data(self, symbol: str, start: str, end: str = None,
                          interval: str = "1d") -> Optional[Dict]:
        """获取美股数据"""
        if not self.yfinance_available:
            return None

        try:
            ticker = self.yf.Ticker(symbol)
            df = ticker.history(start=start, end=end, interval=interval)

            if df.empty:
                return None

            return {
                "symbol": symbol,
                "data": df.to_dict(orient="records"),
                "columns": list(df.columns),
                "start_date": str(df.index[0].date()),
                "end_date": str(df.index[-1].date()),
                "count": len(df)
            }
        except Exception as e:
            print(f"Error fetching US stock data: {e}")
            return None

    def get_ashare_data(self, symbol: str, start_date: str, end_date: str = None,
                        adjust: str = "qfq") -> Optional[Dict]:
        """获取A股数据"""
        if not self.akshare_available:
            return None

        try:
            # symbol如 "000001" (平安银行)
            df = self.ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                         start_date=start_date, adjust=adjust)

            if df.empty:
                return None

            return {
                "symbol": symbol,
                "data": df.to_dict(orient="records"),
                "columns": list(df.columns),
                "start_date": str(df.iloc[0]['日期']),
                "end_date": str(df.iloc[-1]['日期']),
                "count": len(df)
            }
        except Exception as e:
            print(f"Error fetching A-share data: {e}")
            return None

    def get_index_data(self, symbol: str, start: str, end: str = None) -> Optional[Dict]:
        """获取指数数据"""
        # 尝试yfinance
        if self.yfinance_available:
            try:
                return self.get_us_stock_data(symbol, start, end)
            except:
                pass

        # 尝试akshare (A股指数)
        if self.akshare_available:
            # 转换指数代码
            index_map = {
                "000300.SS": "000300",  # CSI300
                "000001.SS": "000001",  #上证指数
                "399001.SZ": "399001",  # 深证成指
            }

            ashare_symbol = index_map.get(symbol, symbol)
            return self.get_ashare_data(ashare_symbol, start.replace("-", ""), end.replace("-", "") if end else None)

        return None

    def get_multiple_stocks(self, symbols: List[str], start: str, end: str = None) -> Dict:
        """批量获取多只股票数据"""
        results = {}
        for symbol in symbols:
            data = self.get_us_stock_data(symbol, start, end)
            if data:
                results[symbol] = data
        return results


"""
FARS - 工具模块
包含论文获取、数据源、回测执行等工具
增强版：支持Ollama本地模型作为备选
"""

import os
import re
import json
import requests
import arxiv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import warnings

# ============== LLM调用工具 ==============

class LLMCaller:
    """调用大语言模型，支持多Provider自动切换"""

    def __init__(self, provider: str = "openai", model: str = "gpt-4o",
                 api_key: str = None, base_url: str = None,
                 fallback_providers: List[dict] = None,
                 agent_name: str = None, method_name: str = None,
                 run_id: str = None, research_id: str = None):
        """
        初始化LLM调用器

        Args:
            provider: 主provider (openai|anthropic|deepseek|minimax|ollama)
            model: 模型名称
            api_key: API密钥
            base_url: 自定义API地址
            fallback_providers: 备用provider列表，如 [{"provider": "ollama", "model": "gemma4"}]
            agent_name: 调用此LLM的Agent名称
            method_name: 调用此LLM的方法名称
            run_id: 当前运行ID
            research_id: 当前研究ID
        """
        self.primary_provider = provider
        self.primary_model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.fallback_providers = fallback_providers or []
        self.last_error = None
        self.agent_name = agent_name
        self.method_name = method_name
        self.run_id = run_id
        self.research_id = research_id
        self._call_history = []

    def _log_llm_call(self, provider: str, model: str, system_prompt: str,
                      user_prompt: str, full_prompt: str, completion: str,
                      prompt_tokens: int, completion_tokens: int, total_tokens: int,
                      latency_ms: int, status: str, error_message: str = None,
                      error_detail: str = None):
        """记录LLM调用到JSON文件"""
        try:
            call_id = f"LLM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"

            call_record = {
                "call_id": call_id,
                "run_id": self.run_id,
                "research_id": self.research_id,
                "agent_name": self.agent_name,
                "method_name": self.method_name,
                "provider": provider,
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "full_prompt": full_prompt,
                "completion": completion,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "status": status,
                "error_message": error_message,
                "error_detail": error_detail,
                "created_at": datetime.now().isoformat()
            }

            # 保存到JSON文件
            history_file = Path(__file__).resolve().parent.parent.parent / "data" / "llm_call_logs.json"
            history_file.parent.mkdir(parents=True, exist_ok=True)

            calls = []
            if history_file.exists():
                try:
                    calls = json.loads(history_file.read_text(encoding='utf-8'))
                except Exception:
                    calls = []

            calls.append(call_record)

            # 限制历史记录数量（最多1000条）
            if len(calls) > 1000:
                calls = calls[-1000:]

            history_file.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')

            # 同时保存到内存历史
            self._call_history.append({
                "call_id": call_id,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "status": status,
                "created_at": datetime.now().isoformat()
            })

        except Exception as e:
            print(f"[LLMCaller] 记录LLM调用失败: {e}")
            traceback.print_exc()

    def call(self, prompt: str, system_prompt: str = None,
             temperature: float = 0.7, max_tokens: int = 4096) -> Optional[str]:
        """
        调用LLM，自动尝试主provider，失败时切换备选

        Returns:
            LLM回复文本，失败返回None
        """
        start_time = datetime.now()

        # 先尝试主provider
        result, tokens, error = self._call_provider_with_stats(self.primary_provider, self.primary_model,
                                     prompt, system_prompt, temperature, max_tokens)
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        if result:
            self._log_llm_call(
                self.primary_provider, self.primary_model, system_prompt,
                prompt, f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
                result, tokens.get("prompt_tokens", 0), tokens.get("completion_tokens", 0),
                tokens.get("total_tokens", 0), latency_ms, "success"
            )
            return result

        # 尝试每个备选provider
        for fallback in self.fallback_providers:
            fb_provider = fallback.get("provider")
            fb_model = fallback.get("model")
            fb_api_key = fallback.get("api_key", self.api_key)
            fb_base_url = fallback.get("base_url")

            print(f"[LLMCaller] 主provider失败，尝试备用: {fb_provider}/{fb_model}")
            start_time = datetime.now()
            result, tokens, fallback_error = self._call_provider_with_stats(fb_provider, fb_model,
                                         prompt, system_prompt, temperature, max_tokens,
                                         api_key=fb_api_key, base_url=fb_base_url)
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            if result:
                print(f"[LLMCaller] 备用provider成功: {fb_provider}/{fb_model}")
                self._log_llm_call(
                    fb_provider, fb_model, system_prompt,
                    prompt, f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
                    result, tokens.get("prompt_tokens", 0), tokens.get("completion_tokens", 0),
                    tokens.get("total_tokens", 0), latency_ms, "success"
                )
                return result

        print(f"[LLMCaller] 所有provider均失败，最后错误: {self.last_error}")

        # 记录失败的调用
        self._log_llm_call(
            self.primary_provider, self.primary_model, system_prompt,
            prompt, f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
            None, 0, 0, 0, latency_ms, "failed",
            error_message=self.last_error,
            error_detail=traceback.format_exc()
        )
        return None

    def _call_provider_with_stats(self, provider: str, model: str,
                                   prompt: str, system_prompt: str = None,
                                   temperature: float = 0.7, max_tokens: int = 4096,
                                   api_key: str = None, base_url: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用指定provider并返回统计信息"""
        api_key = api_key or self.api_key
        base_url = base_url or self.base_url

        try:
            if provider == "openai":
                return self._call_openai_with_stats(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "anthropic":
                return self._call_anthropic_with_stats(model, prompt, system_prompt, temperature, max_tokens, api_key)
            elif provider == "deepseek":
                return self._call_deepseek_with_stats(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "minimax":
                return self._call_minimax_with_stats(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "ollama":
                return self._call_ollama_with_stats(model, prompt, system_prompt, temperature, max_tokens, base_url)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] {provider} 调用失败: {e}")
            return None, {}, str(e)

    def _call_provider(self, provider: str, model: str,
                       prompt: str, system_prompt: str = None,
                       temperature: float = 0.7, max_tokens: int = 4096,
                       api_key: str = None, base_url: str = None) -> Optional[str]:
        """调用指定provider"""
        api_key = api_key or self.api_key
        base_url = base_url or self.base_url

        try:
            if provider == "openai":
                return self._call_openai(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "anthropic":
                return self._call_anthropic(model, prompt, system_prompt, temperature, max_tokens, api_key)
            elif provider == "deepseek":
                return self._call_deepseek(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "minimax":
                return self._call_minimax(model, prompt, system_prompt, temperature, max_tokens, api_key, base_url)
            elif provider == "ollama":
                return self._call_ollama(model, prompt, system_prompt, temperature, max_tokens, base_url)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] {provider} 调用失败: {e}")
            return None

    def _call_openai_with_stats(self, model: str, prompt: str, system_prompt: str = None,
                                temperature: float = 0.7, max_tokens: int = 4096,
                                api_key: str = None, base_url: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用OpenAI API并返回统计信息"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            tokens = {
                "prompt_tokens": getattr(response, 'usage', {}).get('prompt_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion_tokens": getattr(response, 'usage', {}).get('completion_tokens', 0) if hasattr(response, 'usage') else 0,
                "total_tokens": getattr(response, 'usage', {}).get('total_tokens', 0) if hasattr(response, 'usage') else 0
            }
            return response.choices[0].message.content, tokens, None
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] OpenAI API错误: {e}")
            return None, {}, str(e)

    def _call_anthropic_with_stats(self, model: str, prompt: str, system_prompt: str = None,
                                   temperature: float = 0.7, max_tokens: int = 4096,
                                   api_key: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用Anthropic API并返回统计信息"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            messages = []
            if system_prompt:
                messages.append({"role": "user", "content": system_prompt + "\n\n" + prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            response = client.messages.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            tokens = {
                "prompt_tokens": getattr(response, 'usage', {}).get('input_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion_tokens": getattr(response, 'usage', {}).get('output_tokens', 0) if hasattr(response, 'usage') else 0,
                "total_tokens": (getattr(response, 'usage', {}).get('input_tokens', 0) if hasattr(response, 'usage') else 0) +
                               (getattr(response, 'usage', {}).get('output_tokens', 0) if hasattr(response, 'usage') else 0)
            }
            return response.content[0].text, tokens, None
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] Anthropic API错误: {e}")
            return None, {}, str(e)

    def _call_deepseek_with_stats(self, model: str, prompt: str, system_prompt: str = None,
                                  temperature: float = 0.7, max_tokens: int = 4096,
                                  api_key: str = None, base_url: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用DeepSeek API并返回统计信息"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url or "https://api.deepseek.com")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            tokens = {
                "prompt_tokens": getattr(response, 'usage', {}).get('prompt_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion_tokens": getattr(response, 'usage', {}).get('completion_tokens', 0) if hasattr(response, 'usage') else 0,
                "total_tokens": getattr(response, 'usage', {}).get('total_tokens', 0) if hasattr(response, 'usage') else 0
            }
            return response.choices[0].message.content, tokens, None
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] DeepSeek API错误: {e}")
            return None, {}, str(e)

    def _call_minimax_with_stats(self, model: str, prompt: str, system_prompt: str = None,
                                 temperature: float = 0.7, max_tokens: int = 4096,
                                 api_key: str = None, base_url: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用MiniMax API并返回统计信息"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url or "https://minnimax.chat/v1")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            # MiniMax 推理模式可能返回 content=null，实际内容在 reasoning 里
            if content is None and hasattr(response.choices[0].message, 'reasoning'):
                content = response.choices[0].message.reasoning

            tokens = {
                "prompt_tokens": getattr(response, 'usage', {}).get('prompt_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion_tokens": getattr(response, 'usage', {}).get('completion_tokens', 0) if hasattr(response, 'usage') else 0,
                "total_tokens": getattr(response, 'usage', {}).get('total_tokens', 0) if hasattr(response, 'usage') else 0
            }
            return content, tokens, None
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] MiniMax API错误: {e}")
            return None, {}, str(e)

    def _call_ollama_with_stats(self, model: str, prompt: str, system_prompt: str = None,
                                temperature: float = 0.7, max_tokens: int = 4096,
                                base_url: str = None) -> Tuple[Optional[str], Dict, Optional[str]]:
        """调用Ollama本地模型并返回统计信息"""
        try:
            import os
            from openai import OpenAI
            # Ollama不需要真正的API key，但OpenAI客户端需要非空值
            os.environ.setdefault('OPENAI_API_KEY', 'ollama')
            client = OpenAI(base_url=base_url or "http://localhost:11434/v1")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            tokens = {
                "prompt_tokens": getattr(response, 'usage', {}).get('prompt_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion_tokens": getattr(response, 'usage', {}).get('completion_tokens', 0) if hasattr(response, 'usage') else 0,
                "total_tokens": getattr(response, 'usage', {}).get('total_tokens', 0) if hasattr(response, 'usage') else 0
            }
            return response.choices[0].message.content, tokens, None
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] Ollama API错误: {e}")
            return None, {}, str(e)

    def _call_openai(self, model: str, prompt: str, system_prompt: str = None,
                     temperature: float = 0.7, max_tokens: int = 4096,
                     api_key: str = None, base_url: str = None) -> Optional[str]:
        """调用OpenAI API"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return response.choices[0].message.content
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] OpenAI API错误: {e}")
            return None

    def _call_anthropic(self, model: str, prompt: str, system_prompt: str = None,
                        temperature: float = 0.7, max_tokens: int = 4096,
                        api_key: str = None) -> Optional[str]:
        """调用Anthropic API"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            messages = []
            if system_prompt:
                messages.append({"role": "user", "content": system_prompt + "\n\n" + prompt})
            else:
                messages.append({"role": "user", "content": prompt})

            response = client.messages.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return response.content[0].text
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] Anthropic API错误: {e}")
            return None

    def _call_deepseek(self, model: str, prompt: str, system_prompt: str = None,
                       temperature: float = 0.7, max_tokens: int = 4096,
                       api_key: str = None, base_url: str = None) -> Optional[str]:
        """调用DeepSeek API"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url or "https://api.deepseek.com")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return response.choices[0].message.content
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] DeepSeek API错误: {e}")
            return None

    def _call_minimax(self, model: str, prompt: str, system_prompt: str = None,
                      temperature: float = 0.7, max_tokens: int = 4096,
                      api_key: str = None, base_url: str = None) -> Optional[str]:
        """调用MiniMax API (https://minnimax.chat/v1)"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url or "https://minnimax.chat/v1")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            # MiniMax 推理模式可能返回 content=null，实际内容在 reasoning 里
            if content is None and hasattr(response.choices[0].message, 'reasoning'):
                content = response.choices[0].message.reasoning
            return content
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] MiniMax API错误: {e}")
            return None

    def _call_ollama(self, model: str, prompt: str, system_prompt: str = None,
                     temperature: float = 0.7, max_tokens: int = 4096,
                     base_url: str = None) -> Optional[str]:
        """调用Ollama本地模型"""
        try:
            import os
            from openai import OpenAI
            # Ollama不需要真正的API key，但OpenAI客户端需要非空值
            os.environ.setdefault('OPENAI_API_KEY', 'ollama')
            client = OpenAI(base_url=base_url or "http://localhost:11434/v1")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return response.choices[0].message.content
        except Exception as e:
            self.last_error = str(e)
            print(f"[LLMCaller] Ollama API错误: {e}")
            return None

    def test_connection(self, provider: str = None, model: str = None) -> Dict:
        """测试LLM连接

        Returns:
            {"success": bool, "provider": str, "model": str, "error": str}
        """
        p = provider or self.primary_provider
        m = model or self.primary_model

        result = self._call_provider(p, m, "Hello, respond with 'OK' if you can read this.",
                                     temperature=0.1, max_tokens=10)
        return {
            "success": result is not None,
            "provider": p,
            "model": m,
            "response": result,
            "error": self.last_error
        }


# ============== 代码执行工具 ==============

class CodeExecutor:
    """在沙箱环境中执行Python代码"""

    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    def execute(self, code: str, globals_dict: dict = None,
                locals_dict: dict = None) -> Tuple[bool, str, Optional[dict]]:
        """
        执行Python代码

        Args:
            code: Python代码字符串
            globals_dict: 全局变量字典
            locals_dict: 局部变量字典

        Returns:
            (success: bool, output: str, result_dict: dict)
        """
        import io
        import sys
        from contextlib import redirect_stdout, redirect_stderr

        if globals_dict is None:
            globals_dict = {}
        if locals_dict is None:
            locals_dict = {}

        # 创建捕获输出的StringIO
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, globals_dict, locals_dict)

            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()

            combined_output = stdout_output
            if stderr_output:
                combined_output += "\n[STDERR]\n" + stderr_output

            return True, combined_output, locals_dict

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            return False, error_msg, None


# ============== 因子库 ==============

ALPHA_CATEGORIES = {
    "Momentum": ["趋势动量", "价格动量", "成交量动量"],
    "MeanReversion": ["均值回归", "反转", "套利"],
    "Volatility": ["波动率", "布林带", "ATR"],
    "Fundamental": ["基本面", "财务指标", "估值"],
    "Growth": ["成长", "增长", "变化率"],
    "Sentiment": ["情绪", "新闻", "社交媒体"],
    "Market": ["市场结构", "流动性", "订单簿"]
}


# 101 Formulaic Alphas中的部分模板 (来自Kakushadze, 2016)
FORMULAIC_ALPHA_TEMPLATES = [
    {"id": "alpha_001", "formula": "(rank(ts_argmax(signed_power(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)", "category": "Momentum"},
    {"id": "alpha_002", "formula": "(-1 * correlation(rank(delta(log(volume), 2)), rank((close - open) / open), 6))", "category": "MeanReversion"},
    {"id": "alpha_003", "formula": "(-1 * correlation(rank(open), rank(volume), 10))", "category": "Market"},
    {"id": "alpha_004", "formula": "(-1 * Ts_Rank(rank(low), 9))", "category": "MeanReversion"},
    {"id": "alpha_005", "formula": "(rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))", "category": "Sentiment"},
]