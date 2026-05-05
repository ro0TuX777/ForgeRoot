import logging
import os
import subprocess
import json
from pathlib import Path
from forgeworks.runner.tokio_baton import RelayBaton
from forgegate.core.evaluate import evaluate

logger = logging.getLogger(__name__)

def run_judge(baton: RelayBaton, directory: str) -> dict:
    """
    Phase 4: The Judge.
    Executes the sandbox tests. 
    On Success -> Transitions to Phase 5 (Finished/Deploy).
    On Failure -> Feeds stderr logic into baton.last_error_log and flags baton for Phase 3 (Retry).
    """
    if not baton.sandbox_directory or not Path(baton.sandbox_directory).exists():
        logger.error("❌ [JUDGE] Sandbox directory missing. Cannot verify.")
        raise ValueError("Missing Phase 3 Sandbox.")

    if os.environ.get("FORGEWORKS_PHASE_STUBS") == "1":
        logger.info("🧪 [JUDGE] Stub mode enabled; skipping sandbox execution.")
        baton.last_error_log = None
        baton.current_phase = 5
        return {"decision": "ALLOW", "reasons": {"triggered_rules": []}}

    logger.info(f"⚖️ [JUDGE] Executing Verification Plan in Sandbox for {baton.ticket_id}")
    sandbox_dir = Path(baton.sandbox_directory)
    test_script_path = sandbox_dir / "test_script.py"
    
    # ForgeGate Sandbox Governance Check
    intent_path = Path(__file__).parents[1] / "forgegate_intents/sam_sandbox_intent/intent/intent_spec.json"
    with open(intent_path, "r") as f:
        intent_spec = json.load(f)
        
    action = {
        "action_id": "execute_sandbox_test",
        "params": {"ticket_id": baton.ticket_id},
        "side_effect": "external_write",
        "risk_tier": "critical"
    }
    
    signals = {
        "values": {
            "sandbox_directory": str(sandbox_dir),
            "entrypoint_script": test_script_path.name
        }
    }
    
    decision = evaluate(intent_spec, action, signals)
    effect = decision.get("decision", "DENY")
    
    if effect in ["DENY", "ESCALATE"]:
        reasons = decision.get("reasons", {}).get("triggered_rules", [])
        logger.error(f"❌ [JUDGE] ForgeGate {effect}: Sandbox Execution blocked. Rules triggered: {reasons}")
        baton.last_error_log = f"ForgeGate Security Blocked Sandbox Execution:\nReason: {reasons}"
        baton.retry_count += 1
        if baton.retry_count >= baton.max_retries:
            baton.current_phase = 99
        else:
            baton.current_phase = 3
        return decision
        
    logger.info("🛡️ [JUDGE] ForgeGate ALLOWED sandbox execution.")

    if not test_script_path.exists():
        logger.warning("⚠️ [JUDGE] No test_script.py found in sandbox. Failing.")
        baton.last_error_log = "No test_script.py was generated. You MUST generate a file with `# filename: test_script.py`"
        baton.retry_count += 1
        baton.current_phase = 3 if baton.retry_count < baton.max_retries else 99
        return decision

    try:
        # Run the test isolated
        result = subprocess.run(
            ["python", "test_script.py"],
            cwd=str(sandbox_dir),
            capture_output=True,
            text=True,
            timeout=10 # Hard sandbox timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ [JUDGE] Sandbox execution PASSED! Zero exit code.")
            baton.last_error_log = None
            # Success: Move to Phase 5 (Deploy/Close)
            baton.current_phase = 5
        else:
            logger.warning(f"❌ [JUDGE] Sandbox execution FAILED! Exit Code: {result.returncode}")
            error_trace = result.stderr if result.stderr else result.stdout
            logger.warning(f"Trace: {error_trace[:500]}")
            
            baton.last_error_log = f"Exit code {result.returncode}.\nSTDOUT/STDERR:\n{error_trace}"
            baton.retry_count += 1
            
            if baton.retry_count >= baton.max_retries:
                logger.error("🚨 [JUDGE] Max retries exhausted. Marking Ticket as Failed permanently.")
                baton.current_phase = 99 # Error state
            else:
                logger.info("🔄 [JUDGE] Kicking baton back to Phase 3 (Builder) for self-correction.")
                # Important: Loop back!
                baton.current_phase = 3
        return decision
                
    except subprocess.TimeoutExpired:
        logger.error("⏳ [JUDGE] Test execution timed out.")
        baton.last_error_log = "Test script execution timed out (infinite loop?)."
        baton.retry_count += 1
        baton.current_phase = 3 if baton.retry_count < baton.max_retries else 99
        return decision
        
    except Exception as e:
        logger.error(f"❌ [JUDGE] Framework execution error: {e}")
        raise

    return decision
