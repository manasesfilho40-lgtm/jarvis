"""
JARVIS MARK XXXIX - Evolution Bootstrap
Initializes the new infrastructure (Event Bus, Providers, Vector Memory, Agents,
Context Engine, Reasoning Engine, Skills, Embeddings)
without modifying existing code.
"""
import asyncio
import logging
import sys
import threading

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("bootstrap")


def bootstrap(ui=None, headless: bool = False):
    logger.info("=" * 50)
    logger.info("J.A.R.V.I.S MARK XXXIX - Full System Bootstrap v2")
    logger.info("=" * 50)

    # 1. Initialize Event Bus
    from core.event_bus import get_bus, EventType, emit
    bus = get_bus()
    logger.info(f"[1/10] EventBus initialized: {bus}")

    # 2. Initialize Runtime
    from core.runtime import get_runtime
    runtime = get_runtime()
    logger.info(f"[2/10] Runtime initialized: {runtime}")

    # 3. Initialize System Bridge (wires UI events)
    from core.system_bridge import get_bridge
    bridge = get_bridge()
    bridge.initialize(ui=ui)
    logger.info(f"[3/10] SystemBridge initialized: {bridge}")

    # 4. Initialize Vector Memory
    from memory.vector_memory import get_vector_memory
    vm = get_vector_memory()
    stores = vm.count()
    logger.info(f"[4/10] VectorMemory initialized: {stores} stores")

    # 5. Initialize Embedding Service
    try:
        from core.embedding_service import get_embedding_service
        emb = get_embedding_service()
        logger.info(f"  -> EmbeddingService initialized: {emb}")
    except Exception as e:
        logger.warning(f"  -> EmbeddingService not initialized: {e}")

    # 6. Initialize Context Engine
    try:
        from memory.context_engine import get_context_engine
        ctx = get_context_engine()
        ctx.start()
        logger.info("  -> ContextEngine started")
    except Exception as e:
        logger.warning(f"  -> ContextEngine not initialized: {e}")

    # 7. Initialize Provider Manager
    from providers.provider_manager import get_manager
    pm = get_manager()
    logger.info(f"[5/10] ProviderManager initialized: {pm}")

    # Register default providers (Gemini)
    try:
        from core.utils import get_api_key_safe
        api_key = get_api_key_safe()
        if api_key:
            from providers.gemini_provider import create_gemini_provider
            gemini = create_gemini_provider(api_key=api_key)
            pm.register("gemini", gemini)
            pm.set_default("gemini")
            logger.info("  -> Gemini provider registered")
    except Exception as e:
        logger.warning(f"  -> Gemini provider not registered: {e}")

    # Register Ollama provider
    try:
        from agent.local_genai import get_ollama_model
        model = get_ollama_model()
        from providers.ollama_provider import create_ollama_provider
        ollama = create_ollama_provider(model=model)
        pm.register("ollama", ollama)
        pm.add_fallback("ollama")
        logger.info(f"  -> Ollama provider registered (model: {model})")
    except Exception as e:
        logger.warning(f"  -> Ollama provider not registered: {e}")

    # Register OpenAI provider if key available
    try:
        api_keys = getattr(pm, '_config', None) or {}
        openai_key = getattr(pm, '_openai_key', None) or ""
        if openai_key:
            from providers.openai_provider import create_openai_provider
            openai_prov = create_openai_provider(api_key=openai_key)
            pm.register("openai", openai_prov)
            logger.info("  -> OpenAI provider registered")
    except Exception as e:
        logger.debug(f"  -> OpenAI provider not registered: {e}")

    # 8. Load Plugins
    from plugins.plugin_manager import get_plugin_manager
    plugin_mgr = get_plugin_manager()
    plugin_count = 0
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        plugin_count = loop.run_until_complete(plugin_mgr.discover_and_load(["plugins"]))
        loop.close()
    except Exception as e:
        logger.warning(f"Plugin loading failed: {e}")
    logger.info(f"[6/10] PluginManager: {plugin_count} plugins loaded")

    # 9. Initialize Skill Manager
    try:
        from skills.skill_manager import get_skill_manager
        skill_mgr = get_skill_manager()
        asyncio.run(skill_mgr.discover(["skills"]))
        skills_loaded = len(skill_mgr.list_skills())
        logger.info(f"[7/10] SkillManager: {skills_loaded} skills loaded")
    except Exception as e:
        logger.warning(f"  -> SkillManager not initialized: {e}")

    # 10. Register Built-in Workflows
    try:
        from core.builtin_workflows import register_builtin_workflows
        register_builtin_workflows()
        from core.workflow_engine import get_workflow_engine
        wf_engine = get_workflow_engine()
        wf_count = len(wf_engine.get_recent_workflows())
        logger.info(f"[8/10] WorkflowEngine: {wf_count} workflows registered")
    except Exception as e:
        logger.warning(f"Workflow registration failed: {e}")

    # 11. Initialize Reasoning Engine
    try:
        from core.reasoning_engine import get_reasoning_engine
        re = get_reasoning_engine()
        logger.info(f"[9/10] ReasoningEngine initialized")
    except Exception as e:
        logger.warning(f"  -> ReasoningEngine not initialized: {e}")

    # 12. Initialize HUD Overlay (if not headless)
    hud = None
    if ui and not headless:
        try:
            from jui.hud_integration import integrate_hud, hud_status_updater
            hud = integrate_hud(ui)
            if hud:
                hud_status_updater(interval=1.0)
                logger.info("[10/10] HUD Overlay active")
            else:
                logger.info("[10/10] HUD Overlay skipped (PyQt6 needed)")
        except Exception as e:
            logger.warning(f"HUD initialization skipped: {e}")
    else:
        logger.info("[10/10] HUD Overlay skipped (headless mode)")

    # Emit startup event
    emit(EventType.SYSTEM_STARTUP, {
        "status": "bootstrap_complete",
        "version": "2.0",
        "providers": pm.list_providers(),
        "vector_stores": stores,
        "plugins": plugin_count,
        "workflows": wf_count if 'wf_count' in dir() else 0,
        "skills": skills_loaded if 'skills_loaded' in dir() else 0,
    }, source="bootstrap")

    logger.info("=" * 50)
    logger.info("Full bootstrap v2 complete. J.A.R.V.I.S evolution active.")
    logger.info("=" * 50)

    return bridge


if __name__ == "__main__":
    bootstrap()
    print("\nSystem ready. Press Ctrl+C to exit.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
