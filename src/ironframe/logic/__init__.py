"""Logic skills - Toulmin, CQoT, fallacy detection as Python modules."""

from ironframe.logic.toulmin_v1_0 import (
    ToulminArgument,
    parse_toulmin_from_text,
    toulmin_prompt,
    toulmin_validation_prompt,
)
from ironframe.logic.cqot_v1_0 import (
    CQoTResult,
    QuestionResult,
    cqot_prompt,
    cqot_validation_prompt,
    evaluate_argument,
)
from ironframe.logic.fallacy_v1_0 import (
    fallacy_check_prompt,
    full_audit_prompt,
    get_detection_questions,
    get_fallacy,
    list_by_category,
    search_fallacies,
)

