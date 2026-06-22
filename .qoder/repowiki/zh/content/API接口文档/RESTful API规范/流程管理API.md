# 流程管理API

<cite>
**本文档引用的文件**
- [server.py](file://server.py)
- [API_SPEC.md](file://docs/API_SPEC.md)
- [research_runner.py](file://src/core/research_runner.py)
- [data_registry.py](file://src/core/data_registry.py)
- [workflow.py](file://src/workflow.py)
- [main.py](file://src/main.py)
</cite>

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构概览](#架构概览)
5. [详细组件分析](#详细组件分析)
6. [依赖分析](#依赖分析)
7. [性能考虑](#性能考虑)
8. [故障排除指南](#故障排除指南)
9. [结论](#结论)

## 简介
本文档为FARS系统的流程管理API提供完整的技术规范，涵盖完整流程运行、状态查询、流程取消等核心功能。系统采用Flask作为Web框架，支持实时WebSocket通信，提供从文献检索到论文生成的全流程自动化管理。

## 项目结构
FARS系统采用模块化架构设计，主要包含以下核心模块：

```mermaid
graph TB
subgraph "Web层"
Flask[Flask应用]
Routes[路由处理]
WS[WebSocket服务]
end
subgraph "核心业务层"
Runner[ResearchRunner]
Workflow[工作流控制器]
Pipeline[质量流水线]
end
subgraph "数据层"
Registry[数据注册表]
State[状态管理]
Storage[文件存储]
end
subgraph "工具层"
LLM[LLM调用器]
Reviewer[论文评审器]
Detector[AI检测器]
end
Flask --> Routes
Routes --> Runner
Runner --> Workflow
Runner --> Pipeline
Runner --> Registry
Pipeline --> LLM
Pipeline --> Reviewer
Pipeline --> Detector
Registry --> Storage
```

**图表来源**
- [server.py:1-100](file://server.py#L1-L100)
- [research_runner.py:1-50](file://src/core/research_runner.py#L1-L50)

**章节来源**
- [server.py:1-100](file://server.py#L1-L100)
- [API_SPEC.md:1-50](file://docs/API_SPEC.md#L1-L50)

## 核心组件

### 流程管理核心接口
系统提供完整的流程生命周期管理能力：

| 接口类型 | HTTP方法 | 路径 | 功能描述 |
|---------|---------|------|----------|
| 运行完整流程 | POST | `/api/pipeline/run` | 启动完整研究流程，包含文献检索、假设生成、实验执行、论文生成 |
| 获取流程状态 | GET | `/api/pipeline/{pipeline_id}` | 查询指定流程的当前状态和进度 |
| 取消流程 | POST | `/api/pipeline/{pipeline_id}/cancel` | 取消正在执行的流程 |

### 请求参数规范
完整流程运行接口的请求体参数：

| 参数名称 | 类型 | 必填 | 默认值 | 描述 |
|---------|------|------|--------|------|
| query | string | 是 | - | 搜索关键词，用于文献检索 |
| max_papers | integer | 否 | 5 | 最大文献数量限制 |
| target_universe | string | 否 | "A-share" | 目标市场范围 |
| generate_paper | boolean | 否 | true | 是否生成论文 |

### 响应结构
流程状态响应包含完整的阶段信息：

```json
{
  "success": true,
  "data": {
    "pipeline_id": "pipe_20260620_001",
    "status": "running",
    "stages": {
      "ideation": {"status": "completed", "progress": 1.0},
      "planning": {"status": "running", "progress": 0.5},
      "experiment": {"status": "pending", "progress": 0},
      "writing": {"status": "pending", "progress": 0}
    }
  }
}
```

**章节来源**
- [API_SPEC.md:336-380](file://docs/API_SPEC.md#L336-L380)

## 架构概览

### 系统架构图
```mermaid
sequenceDiagram
participant Client as 客户端
participant API as API网关
participant Runner as ResearchRunner
participant LLM as LLM服务
participant Storage as 存储层
Client->>API : POST /api/pipeline/run
API->>Runner : kickoff(topic, branch_id)
Runner->>Storage : 初始化状态
Runner->>LLM : 文献检索
LLM-->>Runner : 返回文献列表
Runner->>LLM : 假设生成
LLM-->>Runner : 返回假设
Runner->>LLM : 论文生成
LLM-->>Runner : 返回论文
Runner->>Storage : 更新状态
API-->>Client : 返回流程ID和初始状态
loop 实时监控
Client->>API : GET /api/pipeline/{id}
API-->>Client : 返回当前状态
end
```

**图表来源**
- [research_runner.py:301-428](file://src/core/research_runner.py#L301-L428)
- [server.py:5280-5338](file://server.py#L5280-L5338)

### 流程阶段映射
系统将完整流程划分为四个核心阶段：

| 阶段标识 | 阶段名称 | 阶段描述 | 预期状态 |
|---------|---------|---------|---------|
| ideation | 想法生成 | 文献综述和假设生成 | completed |
| planning | 规划阶段 | 实验设计和准备工作 | running |
| experiment | 实验执行 | 实际实验和数据分析 | pending |
| writing | 论文写作 | 论文生成和优化 | pending |

**章节来源**
- [research_runner.py:239-276](file://src/core/research_runner.py#L239-L276)

## 详细组件分析

### ResearchRunner核心类
ResearchRunner是流程管理的核心控制器，负责协调整个研究流程的执行：

```mermaid
classDiagram
class ResearchRunner {
-load_papers : Callable
-save_papers : Callable
-load_workflow : Callable
-save_workflow : Callable
-create_paper : Callable
-add_log : Callable
+is_running() bool
+kickoff(topic, branch_id, resume) Dict
-_run_pipeline(topic, branch_id) None
-_set_activity(phase, message, progress) None
-_sync_stage_experiments(papers, phase) None
-_gate() bool
}
class ResearchRunner {
+_run_writing_resume(topic, branch_id) None
+_build_literature_review(topic) Dict
+_build_hypotheses(workflow, topic, run_id) List
+_build_experiments(topic, run_id, created_at) List
}
ResearchRunner --> ResearchRunner : "协调各阶段执行"
```

**图表来源**
- [research_runner.py:278-566](file://src/core/research_runner.py#L278-L566)

### 状态管理系统
系统采用分层状态管理模式，确保流程状态的一致性和可追踪性：

```mermaid
flowchart TD
Start([流程启动]) --> InitState["初始化状态<br/>- current_run<br/>- research_activity<br/>- experiments"]
InitState --> SetActivity["设置活动状态<br/>- phase<br/>- progress<br/>- message"]
SetActivity --> SyncExperiments["同步实验状态<br/>- stage_phases映射<br/>- 状态转换"]
SyncExperiments --> GateCheck{"门控检查<br/>- stop_requested<br/>- is_paused<br/>- is_generating"}
GateCheck --> |允许| NextStage["进入下一阶段"]
GateCheck --> |阻止| Wait["等待条件满足"]
NextStage --> UpdateMetrics["更新运行指标<br/>- LLM使用统计<br/>- 时间统计"]
UpdateMetrics --> SaveState["保存状态到持久化存储"]
SaveState --> SetActivity
Wait --> GateCheck
```

**图表来源**
- [research_runner.py:630-641](file://src/core/research_runner.py#L630-L641)
- [research_runner.py:567-582](file://src/core/research_runner.py#L567-L582)

### 实时通信协议
系统支持WebSocket实时状态推送，提供四种消息类型：

| 消息类型 | 数据结构 | 描述 |
|---------|---------|------|
| stage_update | `{type: "stage_update", stage: string, progress: number, message: string}` | 阶段进度更新 |
| stage_complete | `{type: "stage_complete", stage: string, message: string}` | 阶段完成通知 |
| error | `{type: "error", message: string, code: string}` | 错误状态通知 |
| complete | `{type: "complete", message: string, result: object}` | 流程完成通知 |

**章节来源**
- [API_SPEC.md:410-434](file://docs/API_SPEC.md#L410-L434)

### 进度计算机制
系统采用多维度进度计算模型：

```mermaid
flowchart LR
subgraph "阶段权重"
Ideation[想法生成 25%]
Planning[规划阶段 25%]
Experiment[实验执行 35%]
Writing[论文写作 15%]
end
subgraph "进度计算"
BaseProgress["基础进度<br/>= 阶段完成度 × 权重"]
StageProgress["阶段内进度<br/>= 当前步骤/总步骤"]
CombinedProgress["综合进度<br/>= Σ(基础进度 + 阶段内进度)"]
end
Ideation --> BaseProgress
Planning --> BaseProgress
Experiment --> BaseProgress
Writing --> BaseProgress
BaseProgress --> CombinedProgress
```

**图表来源**
- [research_runner.py:583-629](file://src/core/research_runner.py#L583-L629)

**章节来源**
- [research_runner.py:719-735](file://src/core/research_runner.py#L719-L735)

### 取消和异常处理
系统提供完善的流程控制和异常处理机制：

```mermaid
sequenceDiagram
participant Client as 客户端
participant API as API服务
participant Runner as ResearchRunner
participant Storage as 存储
Client->>API : POST /api/pipeline/{id}/cancel
API->>Runner : 设置停止标志
Runner->>Storage : 更新状态为"stopped"
Runner->>Runner : 检查门控条件
alt 流程可中断
Runner->>Runner : 正常终止
Runner->>Storage : 记录取消原因
API-->>Client : 返回取消成功
else 流程不可中断
Runner->>Runner : 等待当前操作完成
Runner->>Storage : 记录中断状态
API-->>Client : 返回等待终止
end
```

**图表来源**
- [research_runner.py:630-641](file://src/core/research_runner.py#L630-L641)

**章节来源**
- [research_runner.py:630-641](file://src/core/research_runner.py#L630-L641)

## 依赖分析

### 核心依赖关系
```mermaid
graph TB
subgraph "外部依赖"
Flask[Flask 2.0+]
Requests[Requests库]
PyMongo[MongoDB驱动]
WebSocket[WebSocket协议]
end
subgraph "内部模块"
Server[server.py]
Runner[research_runner.py]
Data[data_registry.py]
Tools[quality_pipeline.py]
end
subgraph "数据存储"
Papers[papers_state.json]
Workflow[research_state.json]
Branches[research_branches.json]
end
Server --> Flask
Server --> Runner
Server --> Data
Server --> Tools
Runner --> Data
Tools --> Papers
Tools --> Workflow
Tools --> Branches
```

**图表来源**
- [server.py:22-53](file://server.py#L22-L53)
- [data_registry.py:11-22](file://src/core/data_registry.py#L11-L22)

### 数据流分析
系统采用事件驱动的数据流架构：

```mermaid
flowchart TD
subgraph "输入层"
User[用户请求]
Config[配置文件]
Seed[种子文献]
end
subgraph "处理层"
Parser[请求解析]
Validator[参数验证]
Executor[流程执行]
Monitor[状态监控]
end
subgraph "输出层"
Response[响应数据]
Logs[日志记录]
Artifacts[产物文件]
end
User --> Parser
Config --> Validator
Seed --> Executor
Parser --> Validator
Validator --> Executor
Executor --> Monitor
Monitor --> Response
Monitor --> Logs
Monitor --> Artifacts
```

**图表来源**
- [server.py:5280-5338](file://server.py#L5280-L5338)
- [data_registry.py:48-97](file://src/core/data_registry.py#L48-L97)

**章节来源**
- [data_registry.py:48-97](file://src/core/data_registry.py#L48-L97)

## 性能考虑
- **并发处理**: 系统支持多线程并发执行，避免阻塞操作
- **缓存机制**: 关键数据采用内存缓存，减少磁盘I/O
- **异步处理**: 长耗时操作采用异步执行，提高响应速度
- **资源管理**: 合理的资源清理和垃圾回收机制

## 故障排除指南

### 常见问题诊断
1. **流程卡死**: 检查LLM服务连接状态和API密钥配置
2. **状态不同步**: 验证数据库连接和文件权限
3. **WebSocket连接失败**: 确认防火墙设置和代理配置
4. **内存泄漏**: 监控进程内存使用情况，定期重启服务

### 错误码对照表
| 错误码 | HTTP状态 | 描述 | 处理建议 |
|-------|---------|------|---------|
| VALIDATION_ERROR | 400 | 参数验证失败 | 检查请求参数格式 |
| UNAUTHORIZED | 401 | 未授权访问 | 验证认证信息 |
| FORBIDDEN | 403 | 权限不足 | 检查用户权限 |
| NOT_FOUND | 404 | 资源不存在 | 确认资源ID正确性 |
| INTERNAL_ERROR | 500 | 服务器内部错误 | 查看服务日志 |
| LLM_ERROR | 500 | LLM调用失败 | 检查LLM服务状态 |

**章节来源**
- [API_SPEC.md:383-407](file://docs/API_SPEC.md#L383-L407)

## 结论
FARS流程管理API提供了完整的自动化研究工作流解决方案，具备良好的扩展性和可靠性。系统采用模块化设计，支持实时状态监控和灵活的流程控制，能够满足复杂研究场景的需求。通过合理的架构设计和完善的错误处理机制，确保了系统的稳定运行和用户体验。