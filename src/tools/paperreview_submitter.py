"""
PaperReview.ai 提交与评分轮询工具
基于 https://github.com/cnfjlhj/paperreview

功能：
1. 提交PDF到paperreview.ai获取预签名URL并上传
2. 确认上传并获取token
3. 轮询评分结果

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的外部论文评分
"""

import json
import time
import requests
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


BASE_URL = "https://paperreview.ai"
PAPERREVIEW_TOKEN_SUFFIX = ".paperreview.token.txt"


@dataclass
class PaperReviewResult:
    """PaperReview.ai 评分结果"""
    success: bool
    overall_score: Optional[float] = None
    sections: Optional[Dict[str, Any]] = None
    title: Optional[str] = None
    venue: Optional[str] = None
    submission_date: Optional[str] = None
    token: Optional[str] = None
    status: Optional[str] = None  # "pending", "ready", "error"
    error: Optional[str] = None
    raw_data: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "overall_score": self.overall_score,
            "sections": self.sections,
            "title": self.title,
            "venue": self.venue,
            "submission_date": self.submission_date,
            "token": self.token,
            "status": self.status,
            "error": self.error,
            "raw_data": self.raw_data,
        }

    @property
    def passed(self) -> bool:
        """评分 > 5 视为通过"""
        return self.success and self.overall_score is not None and self.overall_score > 5


def is_pdf_file(path: Path) -> bool:
    """检查文件是否为PDF"""
    try:
        with path.open("rb") as f:
            header = f.read(8)
        return header.startswith(b"%PDF-")
    except OSError:
        return False


def submit_pdf_to_paperreview(
    pdf_path: str,
    email: str,
    venue: str = "ICLR",
    custom_venue: str = "",
    timeout: float = 60.0
) -> Tuple[Optional[str], Optional[str]]:
    """
    提交PDF到paperreview.ai

    参数:
        pdf_path: PDF文件路径
        email: 提交者邮箱
        venue: 目标会议 (ICLR, NeurIPS, ICML, CVPR, AAAI, IJCAI, ACL, EMNLP, Other)
        custom_venue: 自定义会议名称（当venue为Other时使用）
        timeout: HTTP超时时间

    返回:
        (token, error_message)
        - 成功时: (token, None)
        - 失败时: (None, error_message)
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return None, f"PDF文件不存在: {pdf_path}"

    if not pdf_path.is_file():
        return None, f"不是有效文件: {pdf_path}"

    if not is_pdf_file(pdf_path):
        return None, f"文件不是PDF格式: {pdf_path}"

    size_bytes = pdf_path.stat().st_size
    if size_bytes > 10 * 1024 * 1024:
        print(f"[WARN] PDF大小 {size_bytes} bytes 超过10MB限制，网站可能拒绝")

    selected_venue = custom_venue.strip() if venue == "Other" else venue

    # Step 1: 获取预签名URL
    get_url = f"{BASE_URL}/api/get-upload-url"
    get_payload = {"filename": pdf_path.name, "venue": selected_venue or ""}

    try:
        get_resp = requests.post(get_url, json=get_payload, timeout=timeout)
    except requests.RequestException as e:
        return None, f"网络请求失败: {e}"

    if get_resp.status_code == 429:
        return None, "请求过于频繁(429)，请稍后重试"

    if not get_resp.ok:
        return None, f"获取上传URL失败({get_resp.status_code}): {get_resp.text[:500]}"

    get_data = get_resp.json()
    if not get_data.get("success"):
        return None, f"服务器返回失败: {json.dumps(get_data)[:500]}"

    presigned_url: str = get_data["presigned_url"]
    s3_key: str = get_data["s3_key"]
    presigned_fields: dict = get_data["presigned_fields"]

    # Step 2: 上传到S3
    try:
        with pdf_path.open("rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            s3_resp = requests.post(presigned_url, data=presigned_fields, files=files, timeout=timeout)
    except requests.RequestException as e:
        return None, f"S3上传失败: {e}"

    if not s3_resp.ok:
        return None, f"S3上传失败({s3_resp.status_code}): {s3_resp.text[:500]}"

    # Step 3: 确认上传
    confirm_url = f"{BASE_URL}/api/confirm-upload"
    confirm_form = {"s3_key": s3_key, "venue": selected_venue or "", "email": email}

    try:
        confirm_resp = requests.post(confirm_url, data=confirm_form, timeout=timeout)
    except requests.RequestException as e:
        return None, f"确认上传失败: {e}"

    if confirm_resp.status_code == 429:
        return None, "请求过于频繁(429)，请稍后重试"

    if not confirm_resp.ok:
        return None, f"确认上传失败({confirm_resp.status_code}): {confirm_resp.text[:500]}"

    result = confirm_resp.json()
    token = result.get("token")

    if not token:
        return None, "服务器未返回token"

    # 保存token到文件
    token_path = pdf_path.with_name(pdf_path.name + PAPERREVIEW_TOKEN_SUFFIX)
    token_path.write_text(f"{token}\n", encoding="utf-8")

    return token, None


def poll_review_result(
    token: str,
    pdf_path: str,
    interval_minutes: float = 1.0,
    max_hours: float = 24.0,
    timeout: float = 30.0
) -> PaperReviewResult:
    """
    轮询paperreview.ai获取评分结果

    参数:
        token: 提交时获取的token
        pdf_path: PDF文件路径（用于保存结果）
        interval_minutes: 轮询间隔（分钟）
        max_hours: 最大轮询时间（小时）
        timeout: HTTP超时时间

    返回:
        PaperReviewResult 对象
    """
    url = f"{BASE_URL}/api/review/{token}"
    interval_s = max(5.0, interval_minutes * 60.0)
    deadline = time.time() + max(0.0, max_hours) * 3600.0

    while True:
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.RequestException as e:
            print(f"[WARN] 请求失败: {e}")
            if time.time() >= deadline:
                return PaperReviewResult(
                    success=False,
                    error=f"请求失败且超过最大等待时间: {e}",
                    token=token
                )
            time.sleep(interval_s)
            continue

        status = resp.status_code

        if status == 200:
            # 评分完成
            try:
                data = resp.json()
            except Exception:
                return PaperReviewResult(
                    success=False,
                    error="无法解析返回的JSON",
                    token=token,
                    raw_data={"text": resp.text[:4000]}
                )

            overall_score = data.get("overall_score") or data.get("score") or data.get("rating")
            sections = data.get("sections", {})

            # 转换为 float
            if overall_score is not None:
                try:
                    overall_score = float(overall_score)
                except (ValueError, TypeError):
                    pass

            # 保存结果到文件
            pdf_path_obj = Path(pdf_path)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = pdf_path_obj.parent / f"{pdf_path_obj.name}.paperreview.{stamp}.json"
            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8"
            )

            return PaperReviewResult(
                success=True,
                overall_score=overall_score,
                sections=sections,
                title=data.get("title"),
                venue=data.get("venue"),
                submission_date=data.get("submission_date"),
                token=token,
                status="ready",
                raw_data=data
            )

        elif status == 202:
            # 仍在处理中
            detail = resp.json().get("detail") or resp.json().get("message") if resp.text else None
            print(f"[INFO] PaperReview.ai 仍在处理中 ({detail or '等待中'})，{interval_minutes}分钟后重试...")

            if time.time() >= deadline:
                return PaperReviewResult(
                    success=False,
                    error="超过最大等待时间，评分未完成",
                    token=token,
                    status="pending"
                )

            time.sleep(interval_s)

        else:
            # 其他错误状态
            try:
                error_data = resp.json()
                error_msg = error_data.get("detail") or error_data.get("message") or str(error_data)
            except Exception:
                error_msg = resp.text[:500] if resp.text else f"HTTP {status}"

            return PaperReviewResult(
                success=False,
                error=f"评分请求失败: {error_msg}",
                token=token,
                status="error",
                raw_data={"status": status, "text": resp.text[:1000]}
            )


def check_review_once(token: str, timeout: float = 30.0) -> PaperReviewResult:
    """
    仅检查一次评分状态（不轮询）

    参数:
        token: 提交时获取的token
        timeout: HTTP超时时间

    返回:
        PaperReviewResult 对象
    """
    url = f"{BASE_URL}/api/review/{token}"

    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        return PaperReviewResult(
            success=False,
            error=f"网络请求失败: {e}",
            token=token
        )

    status = resp.status_code

    if status == 200:
        try:
            data = resp.json()
        except Exception:
            return PaperReviewResult(
                success=False,
                error="无法解析返回的JSON",
                token=token
            )

        overall_score = data.get("overall_score") or data.get("score") or data.get("rating")
        if overall_score is not None:
            try:
                overall_score = float(overall_score)
            except (ValueError, TypeError):
                pass

        return PaperReviewResult(
            success=True,
            overall_score=overall_score,
            sections=data.get("sections"),
            title=data.get("title"),
            venue=data.get("venue"),
            submission_date=data.get("submission_date"),
            token=token,
            status="ready",
            raw_data=data
        )

    elif status == 202:
        return PaperReviewResult(
            success=False,
            token=token,
            status="pending",
            error="评分仍在处理中"
        )

    else:
        try:
            error_data = resp.json()
            error_msg = error_data.get("detail") or error_data.get("message") or str(error_data)
        except Exception:
            error_msg = resp.text[:500] if resp.text else f"HTTP {status}"

        return PaperReviewResult(
            success=False,
            error=error_msg,
            token=token,
            status="error"
        )


def load_token_from_file(pdf_path: str) -> Optional[str]:
    """从token文件加载token"""
    pdf_path_obj = Path(pdf_path)
    token_path = pdf_path_obj.with_name(pdf_path_obj.name + PAPERREVIEW_TOKEN_SUFFIX)

    if not token_path.exists():
        return None

    token = token_path.read_text(encoding="utf-8").strip()
    return token if token else None


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PaperReview.ai 提交与评分工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # submit 子命令
    submit_parser = subparsers.add_parser("submit", help="提交PDF到PaperReview.ai")
    submit_parser.add_argument("--pdf", required=True, help="PDF文件路径")
    submit_parser.add_argument("--email", required=True, help="提交者邮箱")
    submit_parser.add_argument("--venue", default="ICLR", help="目标会议")
    submit_parser.add_argument("--custom-venue", default="", help="自定义会议名称")

    # poll 子命令
    poll_parser = subparsers.add_parser("poll", help="轮询评分结果")
    poll_parser.add_argument("--token", help="Token（不提供则从PDF同目录读取）")
    poll_parser.add_argument("--pdf", required=True, help="PDF文件路径")
    poll_parser.add_argument("--interval", type=float, default=1.0, help="轮询间隔（分钟）")
    poll_parser.add_argument("--max-hours", type=float, default=24.0, help="最大等待时间")

    # check 子命令
    check_parser = subparsers.add_parser("check", help="检查评分状态（仅一次）")
    check_parser.add_argument("--token", help="Token")
    check_parser.add_argument("--pdf", required=True, help="PDF文件路径")

    args = parser.parse_args()

    if args.command == "submit":
        token, error = submit_pdf_to_paperreview(
            pdf_path=args.pdf,
            email=args.email,
            venue=args.venue,
            custom_venue=args.custom_venue
        )
        if token:
            print(f"[SUCCESS] 提交成功！Token: {token}")
            print(f"[INFO] Token已保存到: {Path(args.pdf).with_name(Path(args.pdf).name + PAPERREVIEW_TOKEN_SUFFIX)}")
        else:
            print(f"[ERROR] 提交失败: {error}")
            exit(1)

    elif args.command == "poll":
        token = args.token
        if not token:
            token = load_token_from_file(args.pdf)

        if not token:
            print("[ERROR] 未找到token，请先提交PDF")
            exit(1)

        result = poll_review_result(
            token=token,
            pdf_path=args.pdf,
            interval_minutes=args.interval,
            max_hours=args.max_hours
        )

        if result.success:
            print(f"[SUCCESS] 评分完成！分数: {result.overall_score}")
            print(f"[INFO] 通过标准(>5): {'✅ 是' if result.passed else '❌ 否'}")
        else:
            print(f"[INFO] 状态: {result.status}")
            print(f"[WARN] {result.error}")

    elif args.command == "check":
        token = args.token
        if not token:
            token = load_token_from_file(args.pdf)

        if not token:
            print("[ERROR] 未找到token")
            exit(1)

        result = check_review_once(token)
        if result.success:
            print(f"[READY] 评分完成！分数: {result.overall_score}")
            print(f"[INFO] 通过标准(>5): {'✅ 是' if result.passed else '❌ 否'}")
        else:
            print(f"[INFO] 状态: {result.status} - {result.error}")

    else:
        parser.print_help()
