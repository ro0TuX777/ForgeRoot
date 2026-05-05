"""
Core Engines UI Reference Implementation
=========================================

This is a REFERENCE implementation showing how SAM renders the Core Engines
model-selection interface using Streamlit. Use this as a guide for integrating
the Core Engines into your own application's UI.

Original source: app/memory_center.py → render_core_engines_integrated()

Key Integration Patterns:
    1. Import ModelConfigManager to query Ollama and load/save config
    2. Display model selection dropdowns for each role (reasoning, code, general, vision, embedding)
    3. Provide load/unload controls per model
    4. Save configuration to models.conf and sync to SmartModelSelector
"""

import streamlit as st
import logging
import time

logger = logging.getLogger(__name__)


def render_core_engines_ui():
    """
    Render Core Engines UI in a Streamlit application.
    
    Prerequisites:
        - Ollama must be running on localhost:11434
        - config/models.conf must exist with model role assignments
        - ModelConfigManager must be importable
    
    This function demonstrates:
        - Querying Ollama for available models
        - Displaying active/loaded models with unload controls
        - 5-column model selector (reasoning, code, general, vision, embedding)
        - Load/stop buttons per model
        - Save/refresh/reset configuration controls
    """
    st.header("🔧 Core Engines")
    st.markdown("*Configure model selection for different query types*")

    try:
        # STEP 1: Import and initialize the config manager
        # In your app, adjust this import path to match your project structure
        from services.model_config_manager import get_model_config_manager
        
        config_manager = get_model_config_manager()
        
        # STEP 2: Get available Ollama models
        ollama_models = config_manager.get_ollama_models(force_refresh=False)
        model_names = [m['name'] for m in ollama_models]
        
        # Check Ollama connection
        ollama_status = "✅ Connected" if ollama_models else "❌ Offline"
        
        # Display connection status
        col_status1, col_status2, col_refresh = st.columns([2, 1, 1])
        with col_status1:
            st.markdown("### 🔗 Ollama Connection")
        with col_status2:
            if ollama_models:
                st.success(ollama_status)
            else:
                st.error(ollama_status)
        with col_refresh:
            if st.button("🔄 Refresh", use_container_width=True):
                config_manager.get_ollama_models(force_refresh=True)
                st.rerun()
        
        if not ollama_models:
            st.warning("⚠️ Ollama is not responding. Ensure Ollama is running on localhost:11434")
            st.code("ollama serve", language="bash")
            return
        
        st.markdown(f"*Found {len(ollama_models)} models*")
        st.markdown("---")
        
        # STEP 3: Display active (loaded) models
        st.markdown("### 📊 Active Models")
        st.caption("*Currently loaded in Ollama memory*")
        
        active_models = config_manager.get_active_models()
        
        if active_models:
            for model in active_models:
                col_name, col_size, col_action = st.columns([3, 2, 1])
                with col_name:
                    st.markdown(f"🟢 **{model.get('name', 'Unknown')}**")
                with col_size:
                    size_gb = model.get('size', 0) / (1024**3)
                    st.caption(f"💾 {size_gb:.2f} GB")
                with col_action:
                    if st.button(f"⏹️ Stop", key=f"unload_{model.get('name')}", use_container_width=True):
                        with st.spinner(f"Unloading {model.get('name')}..."):
                            if config_manager.unload_model(model.get('name')):
                                st.success(f"✅ Unloaded {model.get('name')}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to unload {model.get('name')}")
        else:
            st.info("ℹ️ No models currently loaded")
        
        st.markdown("---")
        
        # STEP 4: Load current configuration
        current_config = config_manager.load_config()
        
        # STEP 5: Model role selection (5 columns)
        st.markdown("### 🎯 Smart Model Selection")
        st.markdown("*Select different models for different types of queries*")
        
        # Initialize session state
        if 'model_selections' not in st.session_state:
            st.session_state.model_selections = {
                'reasoning': current_config.get('reasoning_model', ''),
                'code': current_config.get('code_model', ''),
                'general': current_config.get('general_model', ''),
                'vision': current_config.get('vision_model', ''),
                'embedding': current_config.get('embedding_model', ''),
            }
        
        # Define roles with labels and descriptions
        roles = [
            ("reasoning", "🧠 Reasoning Model", "For complex analysis, problem-solving"),
            ("code", "💻 Code Model", "For code generation, debugging"),
            ("general", "💬 General Model", "For simple chat, general queries"),
            ("vision", "👁️ Vision Model", "For image analysis, OCR"),
            ("embedding", "🧩 Embedding Model", "For vectorization, semantic search"),
        ]
        
        columns = st.columns(len(roles))
        
        for col, (role_key, label, description) in zip(columns, roles):
            with col:
                st.markdown(f"**{label}**")
                st.caption(description)
                
                current_value = st.session_state.model_selections[role_key]
                try:
                    idx = model_names.index(current_value) if current_value in model_names else 0
                except:
                    idx = 0
                
                selected = st.selectbox(
                    f"Select {role_key} model:",
                    options=model_names,
                    index=idx,
                    key=f"{role_key}_model_select",
                    label_visibility="collapsed"
                )
                
                # Show model details
                details = next((m for m in ollama_models if m['name'] == selected), None)
                if details:
                    st.caption(f"Family: {details.get('family', 'Unknown')}")
                    st.caption(f"Size: {details.get('size', 0) / (1024**3):.1f} GB")
                
                # Status indicator
                status = config_manager.check_model_status(selected)
                icon = "🟢" if status.get('loaded') else "⚫"
                text = "Running" if status.get('loaded') else "Stopped"
                st.caption(f"{icon} {text}")
                
                st.session_state.model_selections[role_key] = selected
        
        st.markdown("---")
        
        # STEP 6: Save / Refresh / Reset controls
        col_save, col_refresh, col_reset = st.columns(3)
        
        with col_save:
            if st.button("💾 Save Configuration", type="primary", use_container_width=True):
                new_config = {
                    'reasoning_model': st.session_state.model_selections['reasoning'],
                    'code_model': st.session_state.model_selections['code'],
                    'general_model': st.session_state.model_selections['general'],
                    'vision_model': st.session_state.model_selections['vision'],
                    'default_model': st.session_state.model_selections['general'],
                }
                if config_manager.save_config(new_config):
                    config_manager.sync_to_smart_selector()
                    st.success("✅ Configuration saved and applied!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Failed to save configuration")
        
        with col_refresh:
            if st.button("🔄 Refresh Models", use_container_width=True):
                config_manager.get_ollama_models(force_refresh=True)
                st.success("✅ Model list refreshed")
                st.rerun()
        
        with col_reset:
            if st.button("↩️ Reset to Current", use_container_width=True):
                st.session_state.model_selections = {
                    'reasoning': current_config.get('reasoning_model', ''),
                    'code': current_config.get('code_model', ''),
                    'general': current_config.get('general_model', ''),
                    'vision': current_config.get('vision_model', ''),
                    'embedding': current_config.get('embedding_model', ''),
                }
                st.success("✅ Reset to saved configuration")
                st.rerun()
        
        # STEP 7: Help section
        with st.expander("ℹ️ How Model Selection Works"):
            st.markdown("""
            **Smart Model Selection** automatically chooses the best model for each query:
            
            - **Reasoning Model**: Complex analysis, problem-solving, tool execution
            - **Code Model**: Code generation, debugging, technical documentation
            - **General Model**: Simple chat, general questions, fallback
            - **Vision Model**: Image analysis, OCR, document parsing
            - **Embedding Model**: Document vectorization, semantic search
            
            Changes take effect immediately after saving — no restart required!
            """)
        
    except Exception as e:
        st.error(f"❌ Error loading Core Engines: {e}")
        logger.error(f"Core Engines UI error: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
