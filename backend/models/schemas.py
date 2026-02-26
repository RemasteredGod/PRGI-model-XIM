from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class TitleRequest(BaseModel):
    title: str

class SimilarityResult(BaseModel):
    existing_title: str
    match_percentage: float
    match_type: str

class PriorityGroup(BaseModel):
    priority: int
    label: str
    matches: List[SimilarityResult]

class EvaluationMetrics(BaseModel):
    """Breakdown of evaluation scoring metrics"""
    max_similarity: float
    rule_compliance: float
    prefix_suffix: float
    combination: float

class RejectionHistory(BaseModel):
    """History of rejections for a title"""
    is_rejected: bool
    count: int
    last_rejected: Optional[str] = None
    reasons: List[str] = []
    rejection_type: Optional[str] = None
    retry_allowed: bool = True

class TitleResponse(BaseModel):
    title: str
    approval_probability: float
    verdict: str
    rejection_reasons: List[str]
    priority_matches: List[PriorityGroup]
    checks: Dict[str, Any]
    # New evaluation fields (optional for backward compatibility)
    evaluation_score: Optional[float] = None
    decision: Optional[str] = None
    evaluation_metrics: Optional[Dict[str, float]] = None
    rejection_history: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class WordRequest(BaseModel):
    word: str

class ApprovalRequest(BaseModel):
    title: str
    submitted_by: Optional[str] = "User"
    verification_data: Optional[Dict[str, Any]] = None

class ApprovalAction(BaseModel):
    request_id: int
    admin_name: Optional[str] = "Admin"
    comment: Optional[str] = ""

class BatchApproval(BaseModel):
    title_ids: List[int]
    admin_name: Optional[str] = "Admin"

class AdminLogin(BaseModel):
    username: str
    password: str
