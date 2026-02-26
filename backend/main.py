import os
import io
import json
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from contextlib import asynccontextmanager
from typing import List, Optional
from backend.models.schemas import (TitleRequest, TitleResponse, WordRequest, 
                                   ApprovalRequest, ApprovalAction, BatchApproval, AdminLogin)
from backend.services.similarity_engine import verify_title, load_existing_titles
from backend.services.rules_checker import load_disallowed_words
from backend.services.evaluation_service import TitleEvaluationService
from backend.database import (init_db, add_disallowed_word, delete_disallowed_word, 
                              get_comprehensive_stats, search_db_full, get_disallowed_words,
                              submit_approval_request, get_pending_requests, get_all_requests,
                              approve_request, reject_request, get_temp2_titles,
                              create_batch_upload, add_batch_result, update_batch_status,
                              get_batch_results, get_batch_analytics, approve_batch_titles,
                              verify_admin_password, get_admin_config, set_admin_config, get_connection,
                              check_rejected_history, insert_rejected_title, get_rejected_titles,
                              insert_temp2_with_evaluation, update_rejected_retry_status)

security = HTTPBasic()

# Global in-memory list for last 10 submissions
RECENT_SUBMISSIONS = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="PRGI Title Validator", 
    description="Unified Editorial Title Verification System",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/verify-title", response_model=TitleResponse)
async def api_verify_title(request: TitleRequest):
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    
    try:
        # Use new evaluation service with weighted scoring and auto-routing
        eval_result = TitleEvaluationService.evaluate_title(request.title.strip())
        
        # Auto-routing logic based on score
        decision = eval_result["decision"]
        score = eval_result["score"]
        title = eval_result["title"]
        normalized_title = eval_result["normalized_title"]
        metrics = eval_result["metrics"]
        verification_result = eval_result["verification_result"]
        rejection_history = eval_result["rejection_history"]
        
        # Route based on decision
        if decision == "AUTO_REJECT":
            # Insert into rejected_titles table
            insert_rejected_title(
                title=title,
                normalized_title=normalized_title,
                evaluation_score=score,
                rejection_reason=f"Automatic rejection: Score {score:.1f}% below threshold (30%)",
                rejection_type="AUTO",
                verification_data=eval_result
            )
            print(f"✗ AUTO_REJECT: {title} (Score: {score:.1f}%)")
            
        elif decision == "PENDING_ADMIN":
            # Submit for admin approval
            request_id = submit_approval_request(
                title=title,
                submitted_by="User",
                verification_data=eval_result
            )
            print(f"⏳ PENDING_ADMIN: {title} (Score: {score:.1f}%, Request ID: {request_id})")
            
        elif decision == "AUTO_APPROVED":
            # Auto-approve to temp2
            temp2_id = insert_temp2_with_evaluation(
                title=title,
                approved_by="SYSTEM",
                evaluation_score=score,
                evaluation_metrics=metrics
            )
            print(f"✓ AUTO_APPROVED: {title} (Score: {score:.1f}%, Temp2 ID: {temp2_id})")
        
        # Build enhanced response
        message = TitleEvaluationService.get_decision_message(
            decision, 
            score, 
            rejection_history["is_rejected"]
        )
        
        # Map new decision to old verdict format for backward compatibility
        verdict_map = {
            "AUTO_APPROVED": "APPROVED",
            "PENDING_ADMIN": "PENDING",
            "AUTO_REJECT": "REJECTED"
        }
        verdict = verdict_map.get(decision, "PENDING")
        
        # Store in recent submissions (limit 10) with new format
        RECENT_SUBMISSIONS.insert(0, {
            "title": title,
            "verdict": decision,
            "probability": score,
            "decision": decision
        })
        if len(RECENT_SUBMISSIONS) > 10:
            RECENT_SUBMISSIONS.pop()
        
        # Return original TitleResponse format extended with new fields
        response_dict = dict(verification_result)  # Convert to new dict
        response_dict.update({
            "approval_probability": score,  # Update old field for backward compatibility
            "verdict": verdict,  # Map to old format
            "evaluation_score": score,
            "decision": decision,
            "evaluation_metrics": metrics,
            "rejection_history": rejection_history,
            "message": message
        })
        
        return response_dict
        
    except Exception as e:
        # Fallback to old verification logic if evaluation fails
        print(f"⚠️ Evaluation service failed: {e}. Falling back to legacy verification.")
        result = verify_title(request.title.strip())
        
        # Store in recent submissions with old format
        RECENT_SUBMISSIONS.insert(0, {
            "title": result["title"],
            "verdict": result["verdict"],
            "probability": result["approval_probability"]
        })
        if len(RECENT_SUBMISSIONS) > 10:
            RECENT_SUBMISSIONS.pop()
            
        return result

@app.get("/api/search")
async def api_search(request: Request):
    params = dict(request.query_params)
    return search_db_full(params)

@app.get("/api/stats")
async def api_stats():
    return get_comprehensive_stats()

@app.get("/api/recent")
async def api_recent():
    return RECENT_SUBMISSIONS

@app.get("/api/disallowed-words")
async def api_get_words():
    return get_disallowed_words()

@app.post("/api/disallowed-words")
async def api_add_word(request: WordRequest):
    word = request.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")
    add_disallowed_word(word)
    return {"message": f"Word '{word}' added", "words": get_disallowed_words()}

@app.delete("/api/disallowed-words/{word}")
async def api_delete_word(word: str):
    delete_disallowed_word(word)
    return {"message": f"Word '{word}' removed", "words": get_disallowed_words()}

# ── ADMIN & APPROVAL ENDPOINTS ──

@app.post("/api/approval-request")
async def api_submit_approval_request(request: ApprovalRequest):
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    
    request_id = submit_approval_request(
        request.title.strip(), 
        request.submitted_by,
        request.verification_data
    )
    return {"message": "Request submitted successfully", "request_id": request_id}

@app.get("/api/admin/requests")
async def api_get_all_requests():
    return get_all_requests()

@app.get("/api/admin/pending-requests")
async def api_get_pending_requests():
    return get_pending_requests()

@app.post("/api/admin/approve")
async def api_approve_request(action: ApprovalAction):
    success = approve_request(action.request_id, action.admin_name, action.comment)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"message": "Request approved and added to temp2 database"}

@app.post("/api/admin/reject")
async def api_reject_request(action: ApprovalAction):
    success = reject_request(action.request_id, action.admin_name, action.comment)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"message": "Request rejected"}

@app.post("/api/admin/batch-approve")
async def api_batch_approve(request: dict):
    """Approve multiple requests at once"""
    request_ids = request.get('request_ids', [])
    admin_name = request.get('admin_name', 'admin')
    
    approved_count = 0
    for req_id in request_ids:
        if approve_request(req_id, admin_name, "Batch approval"):
            approved_count += 1
    
    return {"approved_count": approved_count, "message": f"Approved {approved_count} requests"}

@app.post("/api/admin/batch-reject")
async def api_batch_reject(request: dict):
    """Reject multiple requests at once"""
    request_ids = request.get('request_ids', [])
    reason = request.get('reason', 'Batch rejection')
    
    rejected_count = 0
    for req_id in request_ids:
        if reject_request(req_id, 'admin', reason):
            rejected_count += 1
    
    return {"rejected_count": rejected_count, "message": f"Rejected {rejected_count} requests"}

@app.post("/api/admin/batch-approve-all-requests")
async def api_batch_approve_all_requests(request: dict):
    """Approve all pending requests"""
    admin_name = request.get('admin_name', 'admin')
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM approval_requests WHERE status = 'pending'")
        pending_ids = [row[0] for row in cursor.fetchall()]
        
        approved_count = 0
        for req_id in pending_ids:
            if approve_request(req_id, admin_name, "Batch approve all"):
                approved_count += 1
        
        return {"approved_count": approved_count, "message": f"Approved {approved_count} pending requests"}
    finally:
        conn.close()

@app.post("/api/admin/batch-reject-all-requests")
async def api_batch_reject_all_requests(request: dict):
    """Reject all pending requests"""
    reason = request.get('reason', 'Batch rejection')
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM approval_requests WHERE status = 'pending'")
        pending_ids = [row[0] for row in cursor.fetchall()]
        
        rejected_count = 0
        for req_id in pending_ids:
            if reject_request(req_id, 'admin', reason):
                rejected_count += 1
        
        return {"rejected_count": rejected_count, "message": f"Rejected {rejected_count} pending requests"}
    finally:
        conn.close()

@app.get("/api/admin/temp2")
async def api_get_temp2():
    return get_temp2_titles()

# ── REJECTED TITLES ENDPOINTS ──

@app.get("/api/admin/rejected-titles")
async def api_get_rejected_titles(limit: int = 100, offset: int = 0):
    """Get all rejected titles for admin view"""
    return get_rejected_titles(limit=limit, offset=offset)

@app.post("/api/admin/rejected-titles/{rejected_id}/allow-retry")
async def api_allow_retry(rejected_id: int, request: dict):
    """Allow a rejected title to be resubmitted"""
    retry_allowed = request.get("retry_allowed", True)
    success = update_rejected_retry_status(rejected_id, retry_allowed)
    
    if success:
        return {"message": f"Retry status updated for rejected title ID {rejected_id}"}
    else:
        raise HTTPException(status_code=404, detail="Rejected title not found")

@app.get("/api/admin/rejected-titles/search")
async def api_search_rejected(title: str):
    """Search rejected titles by title"""
    from backend.database import get_connection
    import sqlite3
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    normalized = title.strip().upper()
    cursor.execute('''
    SELECT id, title, rejection_reason, evaluation_score, rejected_date, rejection_type, retry_allowed
    FROM rejected_titles 
    WHERE normalized_title LIKE ?
    ORDER BY rejected_date DESC
    LIMIT 50
    ''', (f'%{normalized}%',))
    
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

# ── BATCH PROCESSING ENDPOINTS ──

@app.post("/api/batch/upload")
async def api_batch_upload(file: UploadFile = File(...)):
    print(f"\n{'='*60}")
    print(f"📥 BATCH UPLOAD REQUEST RECEIVED")
    print(f"{'='*60}")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    print(f"📄 File: {file.filename}")
    
    # Read file content
    content = await file.read()
    print(f"📊 File size: {len(content):,} bytes")
    
    try:
        # Determine file type and read accordingly
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        elif file.filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
        elif file.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(content), engine='xlrd')
        elif file.filename.endswith('.txt'):
            df = pd.DataFrame({'title': content.decode('utf-8').strip().split('\n')})
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV, XLS, XLSX, or TXT")
        
        # Get titles column (try different common column names)
        title_col = None
        
        # If only one column exists, use it
        if len(df.columns) == 1:
            title_col = df.columns[0]
        else:
            # Try to find title column by name
            possible_cols = ['Title Name', 'title', 'Title', 'TITLE', 'name', 'Name', 'publication', 'Title-Name', 'Publication Name']
            
            for col in possible_cols:
                if col in df.columns:
                    title_col = col
                    break
            
            if title_col is None:
                # If no exact match, try case-insensitive partial match
                for col in df.columns:
                    if 'title' in col.lower() or 'name' in col.lower():
                        title_col = col
                        break
            
            if title_col is None:
                # Use second column (first is usually ID/code) or first column
                title_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        
        titles = df[title_col].dropna().astype(str).tolist()
        
        # Clean titles: remove empty strings and whitespace-only entries
        titles = [t.strip() for t in titles if t and str(t).strip() and str(t).strip().lower() not in ['nan', 'none', '']]
        
        if not titles:
            raise HTTPException(status_code=400, detail="No titles found in file")
        
        print(f"✅ Detected column: '{title_col}'")
        print(f"📋 Total unique titles: {len(titles):,}")
        print(f"⏳ Starting verification...\n")
        
        # Create batch upload record
        batch_id = create_batch_upload(file.filename, len(titles))
        
        # Process each title with error handling
        import time
        start_time = time.time()
        processed = 0
        errors = 0
        
        for idx, title in enumerate(titles, 1):
            if title and title.strip():
                try:
                    result = verify_title(title.strip())
                    add_batch_result(batch_id, title.strip(), result)
                    processed += 1
                    
                    # Log progress every 100 titles with ETA
                    if processed % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        remaining = (len(titles) - processed) / rate if rate > 0 else 0
                        print(f"⏳ {processed:,}/{len(titles):,} titles | {rate:.1f} titles/sec | ETA: {int(remaining)}s | {errors} errors")
                        
                except Exception as e:
                    print(f"❌ Error: '{title}' - {e}")
                    errors += 1
                    # Continue processing even if one fails
                    continue
        
        update_batch_status(batch_id, 'completed')
        
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"✅ BATCH COMPLETE!")
        print(f"⏱️  Time: {total_time:.1f}s ({len(titles)/total_time:.1f} titles/sec)")
        print(f"✔️  Processed: {processed:,}/{len(titles):,}")
        print(f"❌ Errors: {errors}")
        print(f"{'='*60}\n")
        
        return {
            "message": "Batch upload completed",
            "batch_id": batch_id,
            "total_titles": len(titles),
            "processed": processed,
            "errors": errors
        }
    
    except Exception as e:
        print(f"\n❌ BATCH FAILED: {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.post("/api/batch/upload-text")
async def api_batch_upload_text(request: dict):
    print(f"\n{'='*60}")
    print(f"📝 TEXT BATCH UPLOAD STARTED")
    print(f"{'='*60}\n")
    
    try:
        titles = request.get('titles', [])
        if not titles:
            raise HTTPException(status_code=400, detail="No titles provided")
        
        # Clean titles
        titles = [t.strip() for t in titles if t and t.strip()]
        total_titles = len(titles)
        
        print(f"📋 Total titles: {total_titles:,}")
        print(f"⏳ Starting verification...\n")
        
        # Create batch upload record
        batch_id = create_batch_upload("text_input.txt", total_titles)
        
        # Process each title
        import time
        start_time = time.time()
        processed = 0
        errors = 0
        
        for idx, title in enumerate(titles, 1):
            try:
                result = verify_title(title)
                add_batch_result(batch_id, title, result)
                processed += 1
                
                # Log progress every 100 titles
                if processed % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = (total_titles - processed) / rate if rate > 0 else 0
                    print(f"⏳ {processed:,}/{total_titles:,} titles | {rate:.1f} titles/sec | ETA: {int(remaining)}s | {errors} errors")
                    
            except Exception as e:
                print(f"❌ Error: '{title}' - {e}")
                errors += 1
                continue
        
        update_batch_status(batch_id, 'completed')
        
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"✅ TEXT BATCH COMPLETE!")
        print(f"⏱️  Time: {total_time:.1f}s ({total_titles/total_time:.1f} titles/sec)")
        print(f"✔️  Processed: {processed:,}/{total_titles:,}")
        print(f"❌ Errors: {errors}")
        print(f"{'='*60}\n")
        
        return {
            "message": "Batch upload completed",
            "batch_id": batch_id,
            "total_titles": total_titles,
            "processed": processed,
            "errors": errors
        }
    
    except Exception as e:
        print(f"\n❌ TEXT BATCH FAILED: {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Error processing text: {str(e)}")

@app.get("/api/batch/{batch_id}/results")
async def api_get_batch_results(batch_id: int):
    return get_batch_results(batch_id)

@app.get("/api/batch/{batch_id}/analytics")
async def api_get_batch_analytics(batch_id: int):
    return get_batch_analytics(batch_id)

@app.post("/api/batch/{batch_id}/approve")
async def api_approve_batch(batch_id: int, approval: BatchApproval):
    approve_batch_titles(batch_id, approval.title_ids, approval.admin_name)
    return {"message": f"Approved {len(approval.title_ids)} titles"}

@app.post("/api/batch/{batch_id}/request-approval")
async def api_batch_request_approval(batch_id: int):
    results = get_batch_results(batch_id)
    request_ids = []
    
    for result in results:
        if result['status'] == 'pending':
            request_id = submit_approval_request(
                result['title'],
                f"Batch Upload #{batch_id}",
                result.get('verification_data')
            )
            request_ids.append(request_id)
    
    return {
        "message": "Batch sent for admin approval",
        "total_requests": len(request_ids)
    }

# ── ADMIN AUTHENTICATION & CONFIG ──

@app.post("/api/admin/login")
async def api_admin_login(login: AdminLogin):
    if verify_admin_password(login.username, login.password):
        return {"message": "Login successful", "username": login.username}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/admin/config/acceptance-ratio")
async def api_get_acceptance_ratio():
    ratio = get_admin_config('acceptance_ratio')
    return {"acceptance_ratio": int(ratio) if ratio else 60}

@app.post("/api/admin/config/acceptance-ratio")
async def api_set_acceptance_ratio(ratio: int):
    if ratio < 0 or ratio > 100:
        raise HTTPException(status_code=400, detail="Ratio must be between 0 and 100")
    set_admin_config('acceptance_ratio', str(ratio))
    return {"message": "Acceptance ratio updated", "acceptance_ratio": ratio}

@app.post("/api/admin/batch-approve-all")
async def api_batch_approve_all(request: dict):
    """Approve all titles from temp2 database"""
    admin_name = request.get('admin_name', 'admin')
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get all titles from temp2
        cursor.execute("SELECT title FROM temp2")
        titles = [row[0] for row in cursor.fetchall()]
        
        # Move each to original database
        approved_count = 0
        for title in titles:
            cursor.execute("INSERT OR REPLACE INTO titles (title) VALUES (?)", (title,))
            approved_count += 1
        
        # Clear temp2
        cursor.execute("DELETE FROM temp2")
        conn.commit()
        
        return {"approved_count": approved_count, "message": f"Approved {approved_count} titles"}
    finally:
        conn.close()

@app.post("/api/admin/batch-reject-all")
async def api_batch_reject_all():
    """Reject (delete) all titles from temp2 database"""
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM temp2")
        deleted_count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM temp2")
        conn.commit()
        
        return {"deleted_count": deleted_count, "message": f"Rejected {deleted_count} titles"}
    finally:
        conn.close()

@app.post("/api/admin/batch-approve-by-score")
async def api_batch_approve_by_score(request: dict):
    """Approve titles from temp2 with score >= min_score"""
    title_ids = request.get('title_ids', [])
    admin_name = request.get('admin_name', 'admin')
    min_score = request.get('min_score', 40)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        approved_count = 0
        for title_id in title_ids:
            # Get title from temp2
            cursor.execute("SELECT title FROM temp2 WHERE id = ?", (title_id,))
            result = cursor.fetchone()
            if result:
                title = result[0]
                # Move to original database
                cursor.execute("INSERT OR REPLACE INTO titles (title) VALUES (?)", (title,))
                # Remove from temp2
                cursor.execute("DELETE FROM temp2 WHERE id = ?", (title_id,))
                approved_count += 1
        
        conn.commit()
        
        return {
            "approved_count": approved_count, 
            "message": f"Approved {approved_count} titles with score >={min_score}%"
        }
    finally:
        conn.close()

