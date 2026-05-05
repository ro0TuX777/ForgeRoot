import logging
import os
from typing import Any
from forgeworks.runner.tokio_baton import RelayBaton, ValidatedHypothesis

logger = logging.getLogger(__name__)

def run_scout(baton: RelayBaton, directory: str) -> None:
    """
    Phase 1: The Scout.
    Uses the "Thinking" model to deeply analyze the intent and propose a ValidatedHypothesis.
    """
    logger.info(f"🔍 [SCOUT] Analyzing ticket intent: {baton.ticket_intent}")
    
    # In a full implementation, we would query EchoFrame here for Best Match 
    # examples of previous Successful Hypotheses to shove into the prompt.
    echoframe_snippets = [] # Stub
    
    prompt = f"""
    You are the SAM v2 Phase 1 Scout.
    Your job is to read the user ticket intent, evaluate the codebase requirements, and propose a ValidatedHypothesis.
    
    Ticket Intent:
    {baton.ticket_intent}
    
    Return a JSON object exactly matching this schema:
    {{
        "approach_summary": "High level description of what needs to be built",
        "identified_components": ["list", "of", "modules"],
        "risk_assessment": "Any architectural risks",
        "confidence_score": 0.95
    }}
    """
    
    if os.environ.get("FORGEWORKS_PHASE_STUBS") == "1":
        hypothesis = ValidatedHypothesis(
            approach_summary=f"Stubbed hypothesis for {baton.ticket_intent}",
            identified_components=["stub_component"],
            risk_assessment="stub",
            confidence_score=0.5,
        )
        baton.save_hypothesis(hypothesis, directory)
        logger.info("🧪 [SCOUT] Stub mode enabled; hypothesis written without LLM.")
        return

    # 1. Spin up the LLM (Reasoning model preferred here)
    from forgeworks.core_engines import get_model_manager_integration
    from forgeworks.core_engines.config.model_config_manager import ModelConfigManager
    manager = get_model_manager_integration()
    cfg = ModelConfigManager().load_config()
    
    try:
        response_text = manager.generate(
            prompt,
            temperature=0.0,
            num_ctx=cfg.get("max_context_length", 4096),
            max_tokens=cfg.get("max_tokens", 800),
            stream=True,
            raw=True,
        )
        
        # 2. Extract JSON (Using regex or simple parser, bypassing complex Pydantic parsing for safety)
        import json, re
        match = re.search(r'\{.*\}', response_text.replace('\n', ' '), re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            # Fallback if standard json block missing
            data = {
                "approach_summary": response_text[:100],
                "identified_components": ["unknown"],
                "risk_assessment": "Failed to parse JSON",
                "confidence_score": 0.5
            }
            
        hypothesis = ValidatedHypothesis(**data)
        
        # 3. Save Hypothesis to disk (The Baton Pass)
        baton.save_hypothesis(hypothesis, directory)
        logger.info(f"✅ [SCOUT] Phase 1 Complete. Yielding RAM.")
        
    except Exception as e:
        logger.error(f"❌ [SCOUT] Phase 1 Failed: {e}")
        raise
