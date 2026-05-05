import logging
import os
import re
from pathlib import Path
from forgeworks.runner.tokio_baton import RelayBaton
from forgeworks.core_engines import get_model_manager_integration
from forgeworks.core_engines.config.model_config_manager import ModelConfigManager

logger = logging.getLogger(__name__)

def parse_code_blocks(response_text: str) -> dict[str, str]:
    """Extracts markdown code blocks annotated with filenames."""
    # Matches ```python\n# filename: script.py\n<code...>```
    # Or just standard blocks if we prompt it strictly
    files = {}
    
    # Try to find specific filename tags
    blocks = re.split(r'```(?:python|py)?', response_text)
    for block in blocks[1:]: # skip first text before block
        if '```' in block:
            code_content = block.split('```')[0].strip()
            # Try to grab filename from first line comment
            first_line = code_content.split('\n')[0]
            if 'filename:' in first_line.lower() or 'file:' in first_line.lower():
                filename = first_line.split(':')[1].strip()
                files[filename] = code_content
            elif 'test_' in code_content:
                files['test_script.py'] = code_content
            else:
                files['main.py'] = code_content
    return files

def run_builder(baton: RelayBaton, directory: str) -> None:
    """
    Phase 3: The Builder.
    Consumes the strict SpecContract. Generates the code and test script.
    If it's a retry, reads the failure diagnostics to self-correct.
    """
    contract = baton.get_spec_contract()
    hypothesis = baton.get_hypothesis()
    
    if not contract or not hypothesis:
        logger.error("❌ [BUILDER] Missing Phase 1 or 2 artifacts.")
        raise ValueError("Cannot run build without SpecContract and Hypothesis.")

    logger.info(f"🏗️ [BUILDER] Generating code for ticket: {baton.ticket_id} (Attempt {baton.retry_count + 1})")
    
    # Set up sandbox
    workspace_root = Path(directory) / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    sandbox_dir = workspace_root / f"{baton.ticket_id}_sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    baton.sandbox_directory = str(sandbox_dir)

    if os.environ.get("FORGEWORKS_PHASE_STUBS") == "1":
        (sandbox_dir / "main.py").write_text("def run():\n    return 'ok'\n")
        (sandbox_dir / "test_script.py").write_text("def test_stub():\n    assert True\n")
        logger.info("🧪 [BUILDER] Stub mode enabled; wrote main.py and test_script.py.")
        return
    
    retry_context = ""
    if baton.last_error_log:
        retry_context = f"""
        [CRITICAL: PREVIOUS ATTEMPT FAILED]
        The Judge (Phase 4) rejected your previous code. Fix these errors:
        {baton.last_error_log}
        """

    prompt = f"""
    You are the SAM v2 Phase 3 Builder (qwen3-coder).
    Write the implementation and the test script for the following ticket exactly as specified by the Legislator's SpecContract.
    
    [TICKET INTENT]
    {baton.ticket_intent}
    
    [HYPOTHESIS]
    {hypothesis.approach_summary}
    
    [STRICT CONSTRAINTS (SpecContract)]
    Allowed Imports: {', '.join(contract.allowed_imports)}
    Prohibited: {', '.join(contract.prohibited_actions)}
    Architecture Rules: {contract.architecture_rules}
    
    [VERIFICATION PLAN]
    {contract.verification_plan}
    {retry_context}
    
    Provide TWO python code blocks. 
    On the absolute first line of each block, add a comment # filename: <name>.py
    Block 1: # filename: main.py
    Block 2: # filename: test_script.py
    """
    
    manager = get_model_manager_integration()
    cfg = ModelConfigManager().load_config()
    # Ideally switch to coder model here `manager.switch_model("frob/qwen3-coder-next...")` but using active for safety via manager abstraction
    
    try:
        response_text = manager.generate(
            prompt,
            temperature=0.1,
            num_ctx=cfg.get("max_context_length", 4096),
            max_tokens=cfg.get("max_tokens", 800),
            stream=True,
            raw=True,
        )
        files = parse_code_blocks(response_text)
        
        # Fallback if parsing missed exact names
        if not files:
            files['main.py'] = "# Failed to parse code blocks\n" + response_text
            files['test_script.py'] = "def test_fail(): assert False, 'No tests parsed'"
            
        for name, content in files.items():
            file_path = sandbox_dir / name
            with open(file_path, 'w') as f:
                f.write(content)
            logger.info(f"💾 [BUILDER] Wrote {name} to {file_path}")
            
        logger.info(f"✅ [BUILDER] Phase 3 Complete. Emitted code to sandbox. Yielding RAM.")
        
    except Exception as e:
        logger.error(f"❌ [BUILDER] Phase 3 Failed: {e}")
        raise
