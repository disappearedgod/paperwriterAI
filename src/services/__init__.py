# Quality Pipeline Services
from .ai_detector import (
    detect_ai_text,
    detect_paper_ai_content,
    detect_text_segments,
    check_fast_detect_installed,
    FastDetectResult,
)
from .paper_reviewer import (
    local_review,
    review_paper_sections,
    PaperReviewResult as LocalReviewResult,
    PaperReviewResult,
)
