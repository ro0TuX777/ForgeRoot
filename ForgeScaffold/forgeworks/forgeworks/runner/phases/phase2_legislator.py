import logging
import os
import subprocess
from typing import Any
from forgeworks.runner.tokio_baton import RelayBaton, SpecContract

logger = logging.getLogger(__name__)

def get_installed_packages() -> list[str]:
    """Runs `pip freeze` to detect allowed external dependencies for the sandbox."""
    try:
        result = subprocess.run(["pip", "freeze"], capture_output=True, text=True)
        packages = []
        for line in result.stdout.split('\n'):
            if '==' in line:
                packages.append(line.split('==')[0].strip())
        return packages
    except Exception as e:
        logger.warning(f"Failed to fetch pip freeze: {e}")
        return ["requests", "pandas", "numpy"] # Fallbacks

def run_legislator(baton: RelayBaton, directory: str) -> None:
    """
    Phase 2: The Legislator.
    Determines the "Laws" the Coder must follow.
    Generates a formal SpecContract (YAML) outlining strict constraints 
    and the TDD verification plan.
    """
    hypothesis = baton.get_hypothesis()
    if not hypothesis:
        logger.error("❌ [LEGISLATOR] Cannot run Phase 2: Hypothesis is missing.")
        raise ValueError("Missing ValidatedHypothesis from Phase 1.")
        
    logger.info(f"👨‍⚖️ [LEGISLATOR] Drafting rules for component: {hypothesis.identified_components}")
    
    if os.environ.get("FORGEWORKS_PHASE_STUBS") == "1":
        contract = SpecContract(
            allowed_imports=["os", "json"],
            prohibited_actions=["No network access"],
            verification_plan="Run test_script.py and require exit code 0.",
            architecture_rules="Stub rules.",
        )
        baton.save_spec_contract(contract, directory)
        logger.info("🧪 [LEGISLATOR] Stub mode enabled; spec contract written without LLM.")
        return

    installed_packages = get_installed_packages()
    
    prompt = f"""
    You are the SAM v2 Phase 2 Legislator.
    Your job is to take the ValidatedHypothesis from Phase 1 and draft a strict SpecContract for the Builder.

    The Builder runs in a constrained environment. It will write Python code and a test_script.py based on your verification plan.

    Hypothesis Summary:
    {hypothesis.approach_summary}
    
    Installed Environment Packages (The Builder may ONLY import these, no other external libraries):
    {', '.join(installed_packages[:20])}... and standard library.
    
    Return a YAML object exactly matching this schema:
    allowed_imports:
      - os
      - json
    prohibited_actions:
      - "Do not make actual network calls, use mocks."
      - "Do not use threads"
    verification_plan: |
      1. Write dummy test_script.py
      2. Test the parsing logic
      3. Ensure exit code 0
    architecture_rules: "Strictly adhere to SOLID principles."
    """
    
    # 1. Spin up the LLM
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
        
        # 2. Extract YAML logic (simple stub for demonstration)
        import yaml, re
        # Find yaml block
        yaml_match = re.search(r'```yaml(.*?)```', response_text, re.DOTALL)
        if yaml_match:
            data = yaml.safe_load(yaml_match.group(1))
        else:
            # Fallback
            data = {
                "allowed_imports": ["os", "json", "pandas"],
                "prohibited_actions": ["No open internet access"],
                "verification_plan": "Generate test_script.py, mock external APIs, assert exit code 0.",
                "architecture_rules": "No global state."
            }
        # Normalize fields to SpecContract types
        arch_rules = data.get("architecture_rules")
        if isinstance(arch_rules, list):
            data["architecture_rules"] = "\n".join(str(item) for item in arch_rules)
        elif arch_rules is None:
            data["architecture_rules"] = ""

        ver_plan = data.get("verification_plan")
        if isinstance(ver_plan, list):
            data["verification_plan"] = "\n".join(str(item) for item in ver_plan)
        elif ver_plan is None:
            data["verification_plan"] = ""

        contract = SpecContract(**data)
        
        # 3. Save SpecContract to disk (The Baton Pass)
        baton.save_spec_contract(contract, directory)
        logger.info(f"✅ [LEGISLATOR] Phase 2 Complete. Yielding RAM.")
        
    except Exception as e:
        logger.error(f"❌ [LEGISLATOR] Phase 2 Failed: {e}")
        raise
