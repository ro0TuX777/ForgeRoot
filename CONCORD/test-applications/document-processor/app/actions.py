from app.registry import ActionContract, register_action

DOC_SCAN_INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "document_path": {"type": "string", "description": "Path to the document to analyze."},
        "max_pages": {"type": "integer", "minimum": 0, "default": 0},
        "include_images": {"type": "boolean", "default": False}
    },
    "required": ["document_path"],
    "additionalProperties": False
}

DOC_SCAN_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "pages_analyzed": {"type": "integer"},
        "text_content": {"type": "string"},
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["pages_analyzed", "text_content", "confidence_score"],
    "additionalProperties": False
}

TEXT_EXTRACT_INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "document_path": {"type": "string"},
        "encoding": {"type": "string", "default": "utf-8"}
    },
    "required": ["document_path"],
    "additionalProperties": False
}

TEXT_EXTRACT_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "word_count": {"type": "integer"}
    },
    "required": ["text", "word_count"],
    "additionalProperties": False
}

CONVERT_INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "document_path": {"type": "string"},
        "target_format": {"type": "string", "enum": ["txt", "md", "json"]}
    },
    "required": ["document_path", "target_format"],
    "additionalProperties": False
}

CONVERT_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "conversion_success": {"type": "boolean"},
        "output_path": {"type": "string"},
        "bytes_written": {"type": "integer"},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["conversion_success", "output_path"],
    "additionalProperties": False
}

VALIDATE_INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "document_path": {"type": "string"},
        "schema_name": {"type": "string"}
    },
    "required": ["document_path", "schema_name"],
    "additionalProperties": False
}

VALIDATE_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "errors": {"type": "array", "items": {"type": "string"}},
        "schema_name": {"type": "string"}
    },
    "required": ["valid", "schema_name"],
    "additionalProperties": False
}

PROCESS_CHAIN_INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "document_path": {"type": "string", "description": "Path to the document to process."},
        "target_format": {"type": "string", "enum": ["txt", "md"], "default": "md"}
    },
    "required": ["document_path"],
    "additionalProperties": False
}

PROCESS_CHAIN_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "scan_result": DOC_SCAN_OUTPUT_SCHEMA,
        "extract_result": TEXT_EXTRACT_OUTPUT_SCHEMA,
        "convert_result": CONVERT_OUTPUT_SCHEMA,
        "validate_result": VALIDATE_OUTPUT_SCHEMA,
        "chain_success": {"type": "boolean"},
        "artifacts": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["scan_result", "extract_result", "convert_result", "validate_result", "chain_success"],
    "additionalProperties": False
}


def register_actions() -> None:
    register_action(ActionContract(
        action_name="document.scan_pdf",
        action_family="read",
        minimum_trust_tier=1,
        cost=100,
        cost_category="analysis",
        input_schema=DOC_SCAN_INPUT_SCHEMA,
        output_schema=DOC_SCAN_OUTPUT_SCHEMA,
        guards=["service_healthy", "file_accessible"],
        idempotent=True,
    ))
    register_action(ActionContract(
        action_name="document.extract_text",
        action_family="read",
        minimum_trust_tier=1,
        cost=50,
        cost_category="analysis",
        input_schema=TEXT_EXTRACT_INPUT_SCHEMA,
        output_schema=TEXT_EXTRACT_OUTPUT_SCHEMA,
        guards=["service_healthy", "file_accessible"],
        idempotent=True,
    ))
    register_action(ActionContract(
        action_name="document.convert_format",
        action_family="mutate",
        minimum_trust_tier=2,
        cost=75,
        cost_category="conversion",
        input_schema=CONVERT_INPUT_SCHEMA,
        output_schema=CONVERT_OUTPUT_SCHEMA,
        guards=["service_healthy", "file_accessible"],
        idempotent=False,
    ))
    register_action(ActionContract(
        action_name="document.validate_schema",
        action_family="read",
        minimum_trust_tier=1,
        cost=40,
        cost_category="validation",
        input_schema=VALIDATE_INPUT_SCHEMA,
        output_schema=VALIDATE_OUTPUT_SCHEMA,
        guards=["service_healthy", "file_accessible"],
        idempotent=True,
    ))
    register_action(ActionContract(
        action_name="document.process_chain",
        action_family="mutate",
        minimum_trust_tier=1,  # Changed to 1 to match session
        cost=200,  # Higher cost for chained operation
        cost_category="processing",
        input_schema=PROCESS_CHAIN_INPUT_SCHEMA,
        output_schema=PROCESS_CHAIN_OUTPUT_SCHEMA,
        guards=["service_healthy", "file_accessible"],
        idempotent=False,
    ))
