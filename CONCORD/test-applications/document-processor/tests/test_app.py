from fastapi.testclient import TestClient
from pathlib import Path
from datetime import datetime, timedelta, timezone

from app.main import app
from app.pipeline import admission_pipeline
from app.models import ExecutionResult, IntentRequest, NormalizationResult, Session
from app.registry import EXECUTOR_REGISTRY, NORMALIZER_REGISTRY

client = TestClient(app)

PROJECT_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DOC = PROJECT_DIR / "data" / "sample_docs" / "sample_document.txt"


def _fresh_session(
    session_id: str,
    *,
    trust_tier: int = 1,
    budget_total: int = 1000,
    budget_consumed: int = 0,
    expires_in: timedelta = timedelta(hours=4),
    max_lifetime_in: timedelta = timedelta(hours=8),
    max_extensions: int = 3,
    extensions_count: int = 0,
) -> Session:
    now = datetime.now(timezone.utc)
    session = Session(
        session_id=session_id,
        trust_tier=trust_tier,
        expires_at=now + expires_in,
        budget_total=budget_total,
        budget_consumed=budget_consumed,
        max_lifetime_at=now + max_lifetime_in,
        max_extensions=max_extensions,
        extensions_count=extensions_count,
    )
    admission_pipeline.session_store.sessions[session_id] = session
    return session


def test_list_actions_returns_action_registry():
    response = client.get("/actions")
    assert response.status_code == 200
    actions = response.json()
    assert isinstance(actions, list)
    assert any(action["action_name"] == "document.scan_pdf" for action in actions)


def test_operation_context_for_action():
    response = client.get("/operation-context/document.scan_pdf", params={"session_id": "session-default"})
    assert response.status_code == 200
    body = response.json()
    assert body["action_name"] == "document.scan_pdf"
    assert body["session_id"] == "session-default"
    assert body["budget_remaining"] == 1000
    assert body["trust_sufficient"] is True
    assert "input_schema" in body
    assert "output_schema" in body


def test_budget_status_returns_remaining_budget():
    response = client.get("/budget/status", params={"session_id": "session-default"})
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-default"
    assert body["total"] == 1000
    assert body["remaining"] == 1000


def test_session_refresh_extends_session():
    response = client.post("/session/refresh", json={"session_id": "session-default", "extension_ms": 60000})
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-default"
    assert body["extensions_count"] == 1
    assert body["remaining_extensions"] == 2


def test_budget_estimate_returns_action_cost_and_budget_status():
    response = client.get(
        "/budget/estimate",
        params={"session_id": "session-default", "action_name": "document.scan_pdf"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-default"
    assert body["action_name"] == "document.scan_pdf"
    assert body["cost"] >= 0
    assert body["trust_sufficient"] is True
    assert body["budget_sufficient"] is True
    assert body["can_execute"] is True


def test_intent_submit_scan_pdf_returns_receipt():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": str(SAMPLE_DOC), "max_pages": 2},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "receipt_id" in body
    assert "result" in body
    assert body["result"]["pages_analyzed"] == 2
    assert isinstance(body["result"]["confidence_score"], float)

    receipt_id = body["receipt_id"]
    receipt_response = client.get(f"/receipt/{receipt_id}")
    assert receipt_response.status_code == 200
    receipt_body = receipt_response.json()
    assert receipt_body["receipt_id"] == receipt_id
    assert receipt_body["session_id"] == "session-default"
    assert receipt_body["action_name"] == "document.scan_pdf"
    assert receipt_body["validation_passed"] is True


def test_budget_is_deducted_after_intent_execution():
    before = client.get("/budget/status", params={"session_id": "session-default"}).json()["remaining"]
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.validate_schema",
            "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        },
    )
    assert response.status_code == 200
    after = client.get("/budget/status", params={"session_id": "session-default"}).json()["remaining"]
    assert after == before - 40


def test_intent_submit_invalid_parameters_returns_error():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": 123},
        },
    )

    body = response.json()
    assert body["detail"]["error_code"] == "INVALID_PARAMETERS"
    assert "errors" in body["detail"]["detail"]


def test_intent_submit_with_expired_session_returns_error():
    # Simulate expired session by using a non-existent session
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-expired",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": str(SAMPLE_DOC), "max_pages": 1},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "SESSION_NOT_FOUND"


def test_intent_submit_with_invalid_action_returns_error():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.nonexistent",
            "parameters": {},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "ACTION_NOT_FOUND"


def test_intent_submit_with_insufficient_trust_returns_error():
    session_id = "session-trust-test"
    _fresh_session(session_id, trust_tier=1)

    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.convert_format",
            "parameters": {"document_path": str(SAMPLE_DOC), "target_format": "md"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "TRUST_INSUFFICIENT"


def test_intent_submit_with_guard_failure_returns_error():
    # Use a non-existent file to trigger file_accessible guard failure
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": "/nonexistent/file.txt", "max_pages": 1},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "GUARD_FAILED"


def test_intent_submit_with_idempotency_conflict_returns_error():
    idempotency_key = "test-idempotency-123"
    # First submission
    response1 = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": str(SAMPLE_DOC), "max_pages": 1},
            "idempotency_key": idempotency_key,
        },
    )
    assert response1.status_code == 200

    # Second submission with same key
    response2 = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": str(SAMPLE_DOC), "max_pages": 1},
            "idempotency_key": idempotency_key,
        },
    )
    assert response2.status_code == 400
    body = response2.json()
    assert body["detail"]["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_successful_intent_records_intent_receipt_and_budget_side_effects():
    session_id = "session-stage-side-effects"
    _fresh_session(session_id, budget_total=500)
    request = IntentRequest(
        session_id=session_id,
        action_name="document.validate_schema",
        parameters={"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        idempotency_key="stage-side-effects-key",
    )

    success, response = admission_pipeline.process_intent(request)

    assert success is True
    receipt = admission_pipeline.receipt_store.get(response["receipt_id"])
    assert receipt is not None
    intent = admission_pipeline.intent_store.get(receipt.intent_id)
    assert intent is not None
    assert intent.status == "admitted"
    assert intent.idempotency_key == "stage-side-effects-key"
    assert receipt.session_id == session_id
    assert receipt.action_name == "document.validate_schema"
    assert receipt.validation_passed is True
    assert receipt.cost_deducted == 40
    assert admission_pipeline.session_store.sessions[session_id].budget_consumed == 40


def test_intent_submit_with_missing_executor_returns_error(monkeypatch):
    session_id = "session-missing-executor"
    _fresh_session(session_id)
    executors = dict(EXECUTOR_REGISTRY)
    executors.pop("document.validate_schema")
    monkeypatch.setattr("app.pipeline.EXECUTOR_REGISTRY", executors)

    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.validate_schema",
            "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "EXECUTOR_NOT_FOUND"


def test_intent_submit_with_missing_normalizer_returns_error(monkeypatch):
    session_id = "session-missing-normalizer"
    _fresh_session(session_id)
    normalizers = dict(NORMALIZER_REGISTRY)
    normalizers.pop("document.validate_schema")
    monkeypatch.setattr("app.pipeline.NORMALIZER_REGISTRY", normalizers)

    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.validate_schema",
            "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "NORMALIZER_NOT_FOUND"


def test_intent_submit_with_normalizer_failure_returns_error(monkeypatch):
    session_id = "session-normalizer-failure"
    _fresh_session(session_id)

    def failing_normalizer(raw_output, action_contract):
        return NormalizationResult(success=False, error_detail="forced normalizer failure")

    normalizers = dict(NORMALIZER_REGISTRY)
    normalizers["document.validate_schema"] = failing_normalizer
    monkeypatch.setattr("app.pipeline.NORMALIZER_REGISTRY", normalizers)

    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.validate_schema",
            "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "OUTPUT_NORMALIZATION_FAILED"
    assert body["detail"]["detail"] == "forced normalizer failure"


def test_intent_submit_with_executor_failure_returns_error(monkeypatch):
    session_id = "session-executor-failure"
    _fresh_session(session_id)

    def failing_executor(parameters, session, action_contract):
        return ExecutionResult(
            success=False,
            error_code="EXECUTION_FAILED",
            error_detail="forced executor failure",
        )

    executors = dict(EXECUTOR_REGISTRY)
    executors["document.validate_schema"] = failing_executor
    monkeypatch.setattr("app.pipeline.EXECUTOR_REGISTRY", executors)

    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.validate_schema",
            "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "EXECUTION_FAILED"
    assert body["detail"]["detail"] == "forced executor failure"


def test_budget_exhaustion_blocks_further_intents():
    # Create a fresh session for this test
    session_id = "session-budget-test"
    admission_pipeline.session_store.sessions[session_id] = Session(
        session_id=session_id,
        trust_tier=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        budget_total=1000,
        budget_consumed=0,
        max_lifetime_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    # Submit expensive actions until budget is exhausted (25 * 40 = 1000)
    for i in range(26):
        response = client.post(
            "/intent/submit",
            json={
                "session_id": session_id,
                "action_name": "document.validate_schema",
                "parameters": {"document_path": str(SAMPLE_DOC), "schema_name": "basic"},
            },
        )
        if i < 25:
            assert response.status_code == 200
        else:
            # 26th should fail due to budget exhaustion
            assert response.status_code == 400
            body = response.json()
            assert body["detail"]["error_code"] == "BUDGET_EXCEEDED"


def test_budget_estimate_for_nonexistent_action_returns_error():
    response = client.get(
        "/budget/estimate",
        params={"session_id": "session-default", "action_name": "document.nonexistent"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "ACTION_NOT_FOUND"


def test_budget_status_for_invalid_session_returns_error():
    response = client.get("/budget/status", params={"session_id": "session-invalid"})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "SESSION_NOT_FOUND"


def test_operation_context_for_nonexistent_action_returns_error():
    response = client.get("/operation-context/document.nonexistent", params={"session_id": "session-default"})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "ACTION_NOT_FOUND"


def test_receipt_query_for_nonexistent_receipt_returns_error():
    response = client.get("/receipt/nonexistent-receipt-id")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["error_code"] == "RECEIPT_NOT_FOUND"


def test_session_refresh_exceeding_max_extensions_returns_error():
    session_id = "session-refresh-test"
    admission_pipeline.session_store.sessions[session_id] = Session(
        session_id=session_id,
        trust_tier=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        budget_total=1000,
        budget_consumed=0,
        max_lifetime_at=datetime.now(timezone.utc) + timedelta(hours=8),
        max_extensions=3,
        extensions_count=0,
    )
    # Refresh 3 times (max_extensions = 3)
    for i in range(3):
        response = client.post("/session/refresh", json={"session_id": session_id, "extension_ms": 60000})
        assert response.status_code == 200

    # 4th refresh should fail
    response = client.post("/session/refresh", json={"session_id": session_id, "extension_ms": 60000})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "SESSION_MAX_EXTENSIONS_REACHED"


def test_session_refresh_beyond_max_lifetime_returns_error():
    session_id = "session-refresh-max-lifetime"
    _fresh_session(
        session_id,
        expires_in=timedelta(minutes=10),
        max_lifetime_in=timedelta(minutes=20),
    )

    response = client.post(
        "/session/refresh",
        json={"session_id": session_id, "extension_ms": 15 * 60 * 1000},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "SESSION_MAX_LIFETIME_REACHED"
    assert "traceback" not in str(body["detail"]).lower()


def test_error_response_envelopes_are_stable_and_do_not_leak_tracebacks():
    cases = [
        client.get("/budget/status", params={"session_id": "session-invalid"}),
        client.get("/operation-context/document.nonexistent", params={"session_id": "session-default"}),
        client.get("/receipt/nonexistent-receipt-id"),
        client.post(
            "/intent/submit",
            json={
                "session_id": "session-default",
                "action_name": "document.scan_pdf",
                "parameters": {},
            },
        ),
    ]

    for response in cases:
        assert response.status_code in {400, 404}
        body = response.json()
        assert set(body) == {"detail"}
        assert "error_code" in body["detail"]
        assert "traceback" not in str(body["detail"]).lower()
        assert "Traceback" not in response.text


def test_intent_submit_missing_required_parameters_returns_error():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {},  # Missing document_path
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "INVALID_PARAMETERS"


def test_file_upload_saves_file_and_returns_path():
    # Create a test file content
    test_content = b"This is a test document for upload."
    files = {"file": ("test_doc.txt", test_content, "text/plain")}
    
    response = client.post("/upload", files=files)
    assert response.status_code == 200
    body = response.json()
    assert "file_path" in body
    assert body["filename"] == "test_doc.txt"
    assert body["size"] == len(test_content)
    
    # Verify file was saved
    import os
    assert os.path.exists(body["file_path"])


def test_process_chain_action_executes_all_steps():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.process_chain",
            "parameters": {"document_path": str(SAMPLE_DOC), "target_format": "md"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "receipt_id" in body
    result = body["result"]
    
    # Check that all steps are present
    assert "scan_result" in result
    assert "extract_result" in result
    assert "convert_result" in result
    assert "validate_result" in result
    assert "chain_success" in result
    assert "artifacts" in result
    
    # Check scan result structure
    scan = result["scan_result"]
    assert "pages_analyzed" in scan
    assert "text_content" in scan
    assert "confidence_score" in scan
    
    # Check extract result
    extract = result["extract_result"]
    assert "text" in extract
    assert "word_count" in extract
    
    # Check convert result
    convert = result["convert_result"]
    assert "conversion_success" in convert
    assert "output_path" in convert
    
    # Check validate result
    validate = result["validate_result"]
    assert "valid" in validate
    assert "schema_name" in validate
    
    # Check artifacts
    assert isinstance(result["artifacts"], list)
    assert len(result["artifacts"]) > 0


def test_process_chain_preserves_file_artifacts():
    response = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.process_chain",
            "parameters": {"document_path": str(SAMPLE_DOC), "target_format": "md"},
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    
    # Check that converted file exists
    convert_result = result["convert_result"]
    output_path = convert_result.get("output_path")
    assert output_path
    import os
    assert os.path.exists(output_path)
    
    # Check artifacts list includes the converted file
    artifacts = result["artifacts"]
    assert any(output_path in artifact for artifact in artifacts)


def test_individual_actions_vs_chain_consistency():
    # Run individual actions
    scan_resp = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.scan_pdf",
            "parameters": {"document_path": str(SAMPLE_DOC), "max_pages": 10},
        },
    )
    assert scan_resp.status_code == 200
    scan_result = scan_resp.json()["result"]
    
    extract_resp = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.extract_text",
            "parameters": {"document_path": str(SAMPLE_DOC)},
        },
    )
    assert extract_resp.status_code == 200
    extract_result = extract_resp.json()["result"]
    
    # Run chain
    chain_resp = client.post(
        "/intent/submit",
        json={
            "session_id": "session-default",
            "action_name": "document.process_chain",
            "parameters": {"document_path": str(SAMPLE_DOC), "target_format": "md"},
        },
    )
    assert chain_resp.status_code == 200
    chain_result = chain_resp.json()["result"]
    
    # Compare results
    assert chain_result["scan_result"]["pages_analyzed"] == scan_result["pages_analyzed"]
    assert chain_result["extract_result"]["word_count"] == extract_result["word_count"]


def test_chain_action_with_invalid_file_fails_gracefully():
    # Create a fresh session for this test
    session_id = "session-chain-invalid"
    admission_pipeline.session_store.sessions[session_id] = Session(
        session_id=session_id,
        trust_tier=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        budget_total=1000,
        budget_consumed=0,
        max_lifetime_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.process_chain",
            "parameters": {"document_path": "/nonexistent/file.txt", "target_format": "md"},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "GUARD_FAILED"


def test_chain_action_budget_deduction():
    # Create a fresh session for this test
    session_id = "session-chain-budget"
    admission_pipeline.session_store.sessions[session_id] = Session(
        session_id=session_id,
        trust_tier=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        budget_total=1000,
        budget_consumed=0,
        max_lifetime_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    before = client.get("/budget/status", params={"session_id": session_id}).json()["remaining"]
    response = client.post(
        "/intent/submit",
        json={
            "session_id": session_id,
            "action_name": "document.process_chain",
            "parameters": {"document_path": str(SAMPLE_DOC), "target_format": "md"},
        },
    )
    assert response.status_code == 200
    after = client.get("/budget/status", params={"session_id": session_id}).json()["remaining"]
    assert after == before - 200  # Chain costs 200
