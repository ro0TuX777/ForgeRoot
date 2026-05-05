from fastapi import FastAPI, HTTPException, UploadFile, File
from pathlib import Path

from app.models import IntentRequest, Receipt, Session, SessionRefreshRequest
from app.pipeline import admission_pipeline
from app.registry import ACTION_REGISTRY
from app.sample_data import create_sample_documents

app = FastAPI(
    title="CONCORD Document Processor Test App",
    version="0.1.0",
    description="FastAPI test harness for CONCORD integration using a document processing domain.",
)

create_sample_documents()


@app.post("/intent/submit")
async def submit_intent(request: IntentRequest):
    success, response = admission_pipeline.process_intent(request)
    if not success:
        raise HTTPException(status_code=400, detail=response)
    return response


@app.get("/actions")
async def list_actions():
    return [action.model_dump() for action in ACTION_REGISTRY.values()]


@app.get("/operation-context/{action_name}")
async def get_operation_context(action_name: str, session_id: str):
    success, response = admission_pipeline.get_operation_context(session_id, action_name)
    if not success:
        raise HTTPException(status_code=400, detail=response)
    return response


@app.get("/budget/status")
async def get_budget_status(session_id: str):
    success, response = admission_pipeline.get_budget_status(session_id)
    if not success:
        raise HTTPException(status_code=400, detail=response)
    return response


@app.post("/session/refresh")
async def refresh_session(request: SessionRefreshRequest):
    success, response = admission_pipeline.refresh_session(request.session_id, request.extension_ms)
    if not success:
        raise HTTPException(status_code=400, detail=response)
    return response


@app.get("/budget/estimate")
async def get_budget_estimate(session_id: str, action_name: str):
    success, response = admission_pipeline.get_budget_estimate(session_id, action_name)
    if not success:
        raise HTTPException(status_code=400, detail=response)
    return response


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Save uploaded file to a temporary location
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / file.filename
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"file_path": str(file_path), "filename": file.filename, "size": len(content)}


@app.get("/receipt/{receipt_id}")
async def get_receipt(receipt_id: str):
    success, response = admission_pipeline.get_receipt(receipt_id)
    if not success:
        raise HTTPException(status_code=404, detail=response)
    return response


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    session = admission_pipeline.session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": "SESSION_NOT_FOUND"})
    return session.dict()
