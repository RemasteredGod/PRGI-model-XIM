"""
Title Evaluation Service - Implements weighted scoring and auto-routing logic
"""
import json
import re
from typing import Dict, Any
from backend.services.similarity_engine import verify_title
from backend.database import check_rejected_history


class TitleEvaluationService:
    """
    Service for evaluating title submissions with weighted scoring formula.
    
    Formula: finalScore = (1 - maxSimilarity) * 0.45 + 
                          ruleCompliance * 0.30 + 
                          prefixSuffix * 0.15 + 
                          combination * 0.10
    
    Auto-routing:
    - score < 30%: AUTO_REJECT → rejected_titles
    - 30% <= score <= 60%: PENDING_ADMIN → approval_requests
    - score > 60%: AUTO_APPROVED → temp2
    """
    
    # Result caching with TTL (5 minutes)
    _cache = {}
    _cache_ttl = 300  # seconds
    
    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for consistent comparison"""
        # Remove special characters and extra spaces
        normalized = re.sub(r'[^\w\s]', '', title)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip().upper()
    
    @staticmethod
    def _get_cache_key(title: str) -> str:
        """Generate cache key from title"""
        import hashlib
        return hashlib.md5(title.encode()).hexdigest()
    
    @classmethod
    def _get_from_cache(cls, title: str) -> Dict[str, Any]:
        """Get evaluation result from cache if available and not expired"""
        import time
        cache_key = cls._get_cache_key(title)
        
        if cache_key in cls._cache:
            result, timestamp = cls._cache[cache_key]
            if time.time() - timestamp < cls._cache_ttl:
                return result
            else:
                # Cache expired, remove it
                del cls._cache[cache_key]
        
        return None
    
    @classmethod
    def _save_to_cache(cls, title: str, result: Dict[str, Any]):
        """Save evaluation result to cache"""
        import time
        cache_key = cls._get_cache_key(title)
        cls._cache[cache_key] = (result, time.time())
    
    @classmethod
    def evaluate_title(cls, title: str, submitted_by: str = "User") -> Dict[str, Any]:
        """
        Main evaluation function that processes a title submission.
        
        Returns:
        {
            "title": original_title,
            "normalized_title": normalized,
            "score": final_score (0-100),
            "decision": "AUTO_REJECT" | "PENDING_ADMIN" | "AUTO_APPROVED",
            "metrics": {
                "max_similarity": 0.0-1.0,
                "rule_compliance": 0.0-1.0,
                "prefix_suffix": 0.0-1.0,
                "combination": 0.0-1.0
            },
            "verification_result": TitleResponse object,
            "rejection_history": {...}
        }
        """
        # Check cache first
        cached_result = cls._get_from_cache(title)
        if cached_result:
            return cached_result
        
        # Normalize title
        normalized_title = cls._normalize_title(title)
        
        # Check rejection history
        rejection_history = check_rejected_history(title)
        
        # Run existing verification checks
        verification_result = verify_title(title)
        
        # Extract scores from verification checks
        checks = verification_result["checks"]
        
        # Calculate maxCosineSimilarity from phonetic, fuzzy, semantic scores
        phonetic_score = checks.get("phonetic", {}).get("score", 0) / 100.0
        fuzzy_score = checks.get("fuzzy", {}).get("score", 0) / 100.0
        semantic_score = checks.get("semantic_cl", {}).get("score", 0) / 100.0
        
        max_cosine_similarity = max(phonetic_score, fuzzy_score, semantic_score)
        
        # Calculate ruleComplianceScore (higher is better, so invert violation count)
        rules = checks.get("rules", {})
        violation_count = rules.get("violation_count", 0)
        warning_count = rules.get("warning_count", 0)
        
        # Normalize: 0 violations = 1.0, 10+ violations = 0.0
        rule_compliance_score = max(0.0, 1.0 - (violation_count / 10.0))
        
        # Calculate prefixSuffixScore (1.0 if no warnings, 0.5 if some, 0.0 if many)
        if warning_count == 0:
            prefix_suffix_score = 1.0
        elif warning_count <= 2:
            prefix_suffix_score = 0.5
        else:
            prefix_suffix_score = 0.0
        
        # Calculate combinationScore (1.0 if no combination violation, 0.0 if yes)
        has_combination = rules.get("has_combination", False)
        combination_score = 0.0 if has_combination else 1.0
        
        # Apply weighted formula
        final_score = (
            (1.0 - max_cosine_similarity) * 0.45 +
            rule_compliance_score * 0.30 +
            prefix_suffix_score * 0.15 +
            combination_score * 0.10
        ) * 100.0  # Convert to percentage
        
        # Determine decision based on score thresholds
        if final_score < 30:
            decision = "AUTO_REJECT"
        elif 30 <= final_score <= 60:
            decision = "PENDING_ADMIN"
        else:
            decision = "AUTO_APPROVED"
        
        # Override decision if already rejected (but allow retry if permitted)
        if rejection_history["is_rejected"] and not rejection_history.get("retry_allowed", True):
            decision = "AUTO_REJECT"
            final_score = min(final_score, 20)  # Cap score for blocked resubmissions
        
        # Build evaluation result
        evaluation_result = {
            "title": title,
            "normalized_title": normalized_title,
            "score": round(final_score, 2),
            "decision": decision,
            "metrics": {
                "max_similarity": round(max_cosine_similarity, 4),
                "rule_compliance": round(rule_compliance_score, 4),
                "prefix_suffix": round(prefix_suffix_score, 4),
                "combination": round(combination_score, 4)
            },
            "verification_result": verification_result,
            "rejection_history": rejection_history,
            "submitted_by": submitted_by
        }
        
        # Save to cache
        cls._save_to_cache(title, evaluation_result)
        
        return evaluation_result
    
    @staticmethod
    def get_decision_message(decision: str, score: float, is_previously_rejected: bool = False) -> str:
        """Generate user-friendly message based on decision"""
        if decision == "AUTO_REJECT":
            if is_previously_rejected:
                return f"⛔ Title rejected (Score: {score:.1f}%). This title was previously rejected and is not allowed for resubmission."
            else:
                return f"⛔ Title automatically rejected (Score: {score:.1f}%). The title is too similar to existing titles or violates registration rules."
        
        elif decision == "PENDING_ADMIN":
            return f"⏳ Pending admin review (Score: {score:.1f}%). Your submission requires manual review by an administrator."
        
        elif decision == "AUTO_APPROVED":
            return f"✅ Title automatically approved (Score: {score:.1f}%). The title has been added to the system for final admin confirmation."
        
        return "Unknown decision status"
