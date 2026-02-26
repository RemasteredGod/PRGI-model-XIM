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

class TitleResponse(BaseModel):
    title: str
    approval_probability: float
    verdict: str
    rejection_reasons: List[str]
    priority_matches: List[PriorityGroup]
    checks: Dict[str, Any]

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
