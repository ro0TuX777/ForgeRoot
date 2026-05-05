import logging
import os
import shutil
import json
from pathlib import Path
from forgeworks.runner.tokio_baton import RelayBaton
from forgegate.core.evaluate import evaluate

logger = logging.getLogger(__name__)

def run_deployer(baton: RelayBaton, directory: str, shadow: bool = False) -> dict:
    """
    Phase 5: The Deployer.
    Takes the verified sandbox files and copies them into the true SAM codebase architecture.
    Marks the ticket as DONE.
    """
    if not baton.sandbox_directory or not Path(baton.sandbox_directory).exists():
        logger.error("❌ [DEPLOYER] Sandbox directory missing. Cannot deploy.")
        raise ValueError("Missing Phase 3 Sandbox verification.")

    if os.environ.get("FORGEWORKS_PHASE_STUBS") == "1":
        logger.info("🧪 [DEPLOYER] Stub mode enabled; skipping deployment.")
        return {"decision": "ALLOW", "reasons": {"triggered_rules": []}}

    logger.info(f"🚀 [DEPLOYER] Beginning integration deployment for ticket: {baton.ticket_id}")
    
    # 1. Determine Target Location
    # For now, we will deploy the features into a dedicated `deployments` folder.
    # A full mapping could use `hypothesis.identified_components` to graft it straight into `sam.core.*`
    deploy_dir = Path(__file__).parents[3] / "results" / baton.ticket_id
    deploy_dir.mkdir(parents=True, exist_ok=True)
    
    sandbox_dir = Path(baton.sandbox_directory)
    
    # 2. ForgeGate Governance Check
    intent_path = Path(__file__).parents[1] / "forgegate_intents/sam_deploy_intent/intent/intent_spec.json"
    with open(intent_path, "r") as f:
        intent_spec = json.load(f)
        
    action = {
        "action_id": "deploy_verified_artifact",
        "params": {"ticket_id": baton.ticket_id},
        "side_effect": "write",
        "risk_tier": "high"
    }
    
    signals = {
        "values": {
            "target_directory": str(deploy_dir),
            "is_verified": baton.current_phase == 5 # Phase 4 Judge sets it to 5 on success
        }
    }
    
    decision = evaluate(intent_spec, action, signals)
    
    effect = decision.get("decision", "DENY")
    if effect in ["DENY", "ESCALATE"]:
        reasons = decision.get("reasons", {}).get("triggered_rules", [])
        logger.error(f"❌ [DEPLOYER] ForgeGate {effect}: Deployment blocked. Rules triggered: {reasons}")
        raise PermissionError(f"ForgeGate blocked deployment: {effect}")
        
    logger.info("🛡️ [DEPLOYER] ForgeGate ALLOWED the deployment.")
    
    # 3. Copy the verified artifacts
    try:
        deployed_files = []
        if shadow:
            logger.info("🕶️ [DEPLOYER] Shadow mode enabled; skipping file copy.")
        else:
            for file_path in sandbox_dir.iterdir():
                if file_path.is_file():
                    dest_path = deploy_dir / file_path.name
                    shutil.copy2(file_path, dest_path)
                    deployed_files.append(dest_path.name)
                    
            logger.info(f"✅ [DEPLOYER] Successfully installed components: {deployed_files} to {deploy_dir}")
        
    except Exception as e:
        logger.error(f"❌ [DEPLOYER] Failed to marshal files from Sandbox to Deployment: {e}")
        raise

    return decision
