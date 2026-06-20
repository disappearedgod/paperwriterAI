#!/bin/bash
#
# Fast-DetectGPT 安装脚本
# AI 痕迹检测工具 (ICLR 2024)
#
# 用法: bash setup-fast-detectgpt.sh [--model MODEL]
#
# 模型选项:
#   gpt-neo-2.7B  (默认, 最小, CPU可用)
#   gpt-j-6B      (中等, 推荐GPU)
#   Llama3-8B     (最佳, 需要GPU)
#   Llama3-8B-Instruct (指令微调版)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor/fast-detect-gpt"
MODEL="${1:-gpt-neo-2.7B}"

# macOS兼容: 使用可写目录创建虚拟环境
VENV_DIR="/tmp/fast-detectgpt-venv"
PIP_CACHE_DIR="/tmp/fast-detectgpt-pip-cache"

echo "================================================"
echo "  Fast-DetectGPT 安装脚本 (macOS)"
echo "  目标模型: $MODEL"
echo "================================================"

# 1. 检查 vendor 目录
if [ ! -d "$VENDOR_DIR" ]; then
    echo "[ERROR] fast-detect-gpt 未找到，请先运行:"
    echo "  git submodule update --init --recursive"
    echo "  或手动: git clone https://github.com/baoguangsheng/fast-detect-gpt vendor/fast-detect-gpt"
    exit 1
fi

cd "$VENDOR_DIR"

# 2. 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "[INFO] Python 版本: $PYTHON_VERSION"

# 3. 检查 GPU (macOS 使用 mps 或 CPU)
echo "[INFO] 检查 GPU/加速器..."
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "[INFO] NVIDIA GPU 检测到"
    GPU_TYPE="cuda"
elif sysctl -n machdep.cpu.brand_string 2>/dev/null | grep -q "Apple"; then
    echo "[INFO] Apple Silicon/Mac GPU 检测到 (Metal)"
    GPU_TYPE="mps"
else
    echo "[INFO] 使用 CPU 计算"
    GPU_TYPE="cpu"
fi

# 4. 创建虚拟环境（使用可写目录）
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] 创建虚拟环境到 $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "[INFO] 激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 5. 安装 PyTorch（根据 GPU 类型）
echo "[INFO] 安装 PyTorch (GPU类型: $GPU_TYPE)..."
if [ "$GPU_TYPE" = "cuda" ]; then
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    echo "[INFO] GPU 显存: ${GPU_MEMORY}MB"
    if [ "$GPU_MEMORY" -lt 40000 ]; then
        echo "[WARNING] 显存 < 40GB，部分大模型可能无法运行"
    fi
elif [ "$GPU_TYPE" = "mps" ]; then
    echo "[INFO] 安装 macOS Metal GPU 版 PyTorch..."
    pip install torch torchvision torchaudio
else
    echo "[INFO] 安装 CPU 版本 PyTorch..."
    pip install torch torchvision torchaudio
fi

# 6. 运行官方安装脚本
if [ -f "setup.sh" ]; then
    echo "[INFO] 运行官方 setup.sh..."
    bash setup.sh
else
    echo "[INFO] 安装 requirements.txt..."
    pip install -r requirements.txt
fi

# 7. 下载模型
echo "[INFO] 下载模型: $MODEL"
mkdir -p models

case "$MODEL" in
    gpt-neo-2.7B)
        echo "[INFO] 模型 gpt-neo-2.7B 将通过 transformers 自动下载"
        python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
            AutoTokenizer.from_pretrained('EleutherAI/gpt-neo-2.7B'); \
            AutoModelForCausalLM.from_pretrained('EleutherAI/gpt-neo-2.7B')"
        ;;
    gpt-j-6B)
        echo "[INFO] 模型 gpt-j-6B 将通过 transformers 自动下载"
        python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
            AutoTokenizer.from_pretrained('EleutherAI/gpt-j-6B'); \
            AutoModelForCausalLM.from_pretrained('EleutherAI/gpt-j-6B')"
        ;;
    Llama3-8B)
        echo "[INFO] Llama3-8B 需要 HuggingFace 授权"
        echo "[INFO] 请确保已登录 HuggingFace: huggingface-cli login"
        echo "[INFO] 或手动下载: https://huggingface.co/meta-llama/Meta-Llama-3-8B"
        python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
            tok = AutoTokenizer.from_pretrained('meta-llama/Meta-Llama-3-8B', token='YOUR_TOKEN'); \
            model = AutoModelForCausalLM.from_pretrained('meta-llama/Meta-Llama-3-8B', token='YOUR_TOKEN')"
        ;;
    Llama3-8B-Instruct)
        echo "[INFO] Llama3-8B-Instruct 需要 HuggingFace 授权"
        python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
            tok = AutoTokenizer.from_pretrained('meta-llama/Meta-Llama-3-8B-Instruct', token='YOUR_TOKEN'); \
            model = AutoModelForCausalLM.from_pretrained('meta-llama/Meta-Llama-3-8B-Instruct', token='YOUR_TOKEN')"
        ;;
esac

# 8. 测试
echo "[INFO] 测试检测功能..."
echo "This is a test sentence written by a human." | python3 scripts/local_infer.py --sampling_model_name "$MODEL" || true

echo ""
echo "================================================"
echo "  安装完成！"
echo "================================================"
echo ""
echo "使用方法:"
echo "  # 激活环境"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "  # 直接运行"
echo "  python scripts/local_infer.py --sampling_model_name $MODEL"
echo ""
echo "  # 在 Python 中调用"
echo "  import sys; sys.path.insert(0, '$SCRIPT_DIR/src/services')"
echo "  from ai_detector import detect_ai_text"
echo "  result = detect_ai_text('your text here')"
echo ""
echo "或在 paperwriterAI 中直接调用:"
echo "  from src.services.ai_detector import detect_ai_text, detect_paper_ai_content"
echo ""
