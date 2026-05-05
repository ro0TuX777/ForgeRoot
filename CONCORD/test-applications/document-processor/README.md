# CONCORD Document Processor Test Application

This is a reference implementation demonstrating CONCORD v0.5 integration in a document processing application.

## Overview

The application provides a FastAPI-based document processing service with CONCORD admission pipeline integration. It supports:

- Individual document actions (scan, extract, convert, validate)
- Chained multi-step workflows
- File upload and artifact preservation
- Budget and trust tier management
- Comprehensive validation and error handling

## Architecture

```
app/
├── main.py          # FastAPI routes and endpoints
├── actions.py       # ActionContract definitions
├── executors.py     # Business logic execution
├── normalizers.py   # Output normalization
├── pipeline.py      # CONCORD admission pipeline
├── guards.py        # Pre-execution guards
├── models.py        # Pydantic models
├── registry.py      # Action registry
└── sample_data.py   # Test data
```

## Key CONCORD Features Demonstrated

### Admission Pipeline
- Session management with trust tiers and budgets
- Action validation against JSON Schema Draft 2020-12
- Guard evaluation with parameter-independent checks
- Receipt minting and validation

### Planning Endpoints
- `/operation-context/{action_name}` - Live feasibility assessment
- `/budget-status` - Current session budget
- `/budget-estimate/{action_name}` - Cost estimation
- `/session-refresh` - Session extension

### Runtime Endpoints
- `/actions` - Available actions registry
- `/intent` - Execute actions through pipeline
- `/receipt/{receipt_id}` - Query execution results
- `/upload` - File ingestion for workflows

## Running the Application

### Prerequisites
- Python 3.9+
- Dependencies: `pip install -r requirements.txt`

### Start Server
```bash
uvicorn app.main:app --reload
```

### Run Tests
```bash
pytest tests/test_app.py -v
```

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Test Coverage

The application includes 25 comprehensive tests covering:
- Happy path execution
- Error conditions (invalid parameters, expired sessions, budget exhaustion)
- Edge cases (guard failures, idempotency conflicts)
- File-based workflows and artifact preservation
- Chained action execution

## CONCORD Integration Notes

This implementation demonstrates:
- Application-agnostic pipeline integration
- JSON Schema compliance for all contracts
- Proper error handling and validation
- Session state management
- Budget and trust tier enforcement
- File artifact handling in workflows

See the CONCORD documentation files for detailed specifications and integration guidance.
