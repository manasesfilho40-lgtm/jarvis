import json
import re
import sys
import threading
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable

from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision
from core.utils import BASE_DIR, API_CONFIG_PATH, get_api_key as _get_api_key


class ToolExecutionError(Exception):
    pass


TOOL_DISPATCH = {}


def _register(tool_name):
    def wrapper(fn):
        TOOL_DISPATCH[tool_name] = fn
        return fn
    return wrapper


@_register("open_app")
def _open_app(parameters, speak=None):
    from actions.open_app import open_app
    return open_app(parameters=parameters, player=None) or "Done."


@_register("web_search")
def _web_search(parameters, speak=None):
    from actions.web_search import web_search
    return web_search(parameters=parameters, player=None) or "Done."


@_register("game_updater")
def _game_updater(parameters, speak=None):
    from actions.game_updater import game_updater
    return game_updater(parameters=parameters, player=None, speak=speak) or "Done."


@_register("browser_control")
def _browser_control(parameters, speak=None):
    from actions.browser_control import browser_control
    return browser_control(parameters=parameters, player=None) or "Done."


@_register("file_controller")
def _file_controller(parameters, speak=None):
    from actions.file_controller import file_controller
    return file_controller(parameters=parameters, player=None) or "Done."


@_register("code_helper")
def _code_helper(parameters, speak=None):
    from actions.code_helper import code_helper
    return code_helper(parameters=parameters, player=None, speak=speak) or "Done."


@_register("dev_agent")
def _dev_agent(parameters, speak=None):
    from actions.dev_agent import dev_agent
    return dev_agent(parameters=parameters, player=None, speak=speak) or "Done."


@_register("screen_process")
def _screen_process(parameters, speak=None):
    from actions.screen_processor import screen_process
    screen_process(parameters=parameters, player=None)
    return "Screen captured and analyzed."


@_register("send_message")
def _send_message(parameters, speak=None):
    from actions.send_message import send_message
    return send_message(parameters=parameters, player=None) or "Done."


@_register("reminder")
def _reminder(parameters, speak=None):
    from actions.reminder import reminder
    return reminder(parameters=parameters, player=None) or "Done."


@_register("youtube_video")
def _youtube_video(parameters, speak=None):
    from actions.youtube_video import youtube_video
    return youtube_video(parameters=parameters, player=None) or "Done."


@_register("weather_report")
def _weather_report(parameters, speak=None):
    from actions.weather_report import weather_action
    return weather_action(parameters=parameters, player=None) or "Done."


@_register("computer_settings")
def _computer_settings(parameters, speak=None):
    from actions.computer_settings import computer_settings
    return computer_settings(parameters=parameters, player=None) or "Done."


@_register("desktop_control")
def _desktop_control(parameters, speak=None):
    from actions.desktop import desktop_control
    return desktop_control(parameters=parameters, player=None) or "Done."


@_register("computer_control")
def _computer_control(parameters, speak=None):
    from actions.computer_control import computer_control
    return computer_control(parameters=parameters, player=None) or "Done."


@_register("generated_code")
def _generated_code(parameters, speak=None):
    description = parameters.get("description", "")
    if not description:
        raise ValueError("generated_code requires a 'description' parameter.")
    return _run_generated_code(description, speak=speak)


@_register("flight_finder")
def _flight_finder(parameters, speak=None):
    from actions.flight_finder import flight_finder
    return flight_finder(parameters=parameters, player=None, speak=speak) or "Done."


@_register("notifier")
def _notifier(parameters, speak=None):
    from actions.notifier import send_notification
    title = parameters.get("title", "Alert")
    message = parameters.get("message", "")
    send_notification(title, message)
    return "Notification sent."


@_register("whatsapp_web")
def _whatsapp_web(parameters, speak=None):
    from actions.whatsapp_web import whatsapp_web_action
    return whatsapp_web_action(parameters=parameters, player=None) or "Done."


@_register("apify_leads")
def _apify_leads(parameters, speak=None):
    from actions.apify_leads import apify_leads
    return apify_leads(parameters=parameters) or "Done."


@_register("negotiation_script")
def _negotiation_script(parameters, speak=None):
    from actions.negotiation_script import negotiation_script_action
    return negotiation_script_action(parameters=parameters) or "Done."


@_register("manage_memory")
def _manage_memory(parameters, speak=None):
    from memory.memory_manager import manage_memory
    return manage_memory(parameters) or "Done."


@_register("self_repair")
def _self_repair(parameters, speak=None):
    from actions.self_repair import run_diagnostics_and_repair
    return run_diagnostics_and_repair(parameters=parameters, player=None, speak=speak) or "Done."


@_register("manage_crm")
def _manage_crm(parameters, speak=None):
    from actions.leads_manager import manage_crm
    return manage_crm(parameters=parameters) or "Done."


@_register("refresh_geopolitics")
def _refresh_geopolitics(parameters, speak=None):
    from actions.geopolitics_monitor import fetch_geopolitics_news
    return fetch_geopolitics_news()


@_register("conversation")
def _conversation(parameters, speak=None):
    user_message = parameters.get("user_message", "")
    if not user_message:
        return "OK"
    import agent.local_genai as genai
    genai.configure(api_key=_get_api_key())

    from agent.local_genai import get_routing_mode, get_ollama_model
    is_local = get_routing_mode() == "llama"

    if is_local:
        prompt = (
            f"Você é JARVIS, assistente pessoal de Tony Stark. "
            f"Responda em português brasileiro, tratando o usuário como 'senhor'. "
            f"Seja direto, inteligente e natural. Máximo 3 frases.\n\n"
            f"Usuário: {user_message}\nJARVIS:"
        )
        model = genai.GenerativeModel(
            model_name="",
            system_instruction=""
        )
    else:
        prompt = user_message
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=(
                "Você é JARVIS, assistente pessoal de Tony Stark. "
                "Responda em português brasileiro tratando o usuário como 'senhor'. "
                "Seja direto, eficiente, profissional. Máximo 3 frases. "
                "Se não souber algo, ofereça pesquisar."
            )
        )

    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()
        if speak:
            speak(reply)
        return reply
    except Exception as e:
        print(f"[Executor] [Conversation] Error: {e}")
        fallbacks = [
            "Sim, senhor. Estou operacional e à sua disposição.",
            "Compreendo, senhor. Como deseja proceder?",
            "Entendido, senhor. Algo mais em que possa ajudar?",
            "Prossiga, senhor. Estou ouvindo.",
        ]
        import random
        reply = random.choice(fallbacks)
        if speak:
            speak(reply)
        return reply


def _call_tool(tool: str, parameters: dict, speak: Callable | None) -> str:
    if tool == "unknown_tool":
        msg = parameters.get("description", "Não entendi qual ferramenta usar para esta tarefa, senhor.")
        raise ToolExecutionError(msg)

    fn = TOOL_DISPATCH.get(tool)
    if fn:
        return fn(parameters, speak=speak) or "Done."
    print(f"[Executor] [WARNING] Unknown tool '{tool}'")
    raise ToolExecutionError(f"Ferramenta '{tool}' não está disponível, senhor.")


def _run_generated_code(description: str, speak: Callable | None = None) -> str:
    import agent.local_genai as genai

    if speak:
        speak("Escrevendo um código personalizado para esta tarefa, senhor.")

    home      = Path.home()
    desktop   = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    if not desktop.exists():
        try:
            import winreg
            key     = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            pass

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=(
            "You are an expert Python developer. "
            "Write clean, complete, working Python code. "
            "Use standard library + common packages. "
            "Install missing packages with subprocess + pip if needed. "
            "Return ONLY the Python code. No explanation, no markdown, no backticks.\n\n"
            f"SYSTEM PATHS:\n"
            f"  Desktop   = r'{desktop}'\n"
            f"  Downloads = r'{downloads}'\n"
            f"  Documents = r'{documents}'\n"
            f"  Home      = r'{home}'\n"
        )
    )

    try:
        response = model.generate_content(
            f"Write Python code to accomplish this task:\n\n{description}"
        )
        code = response.text.strip()
        code = re.sub(r"```(?:python)?", "", code).strip().rstrip("`").strip()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        print(f"[Executor] 🐍 Running generated code: {tmp_path}")

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=120, cwd=str(Path.home())
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        output = result.stdout.strip()
        error  = result.stderr.strip()

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            return "Task completed successfully."
        elif error:
            raise RuntimeError(f"Code error: {error[:400]}")
        return "Completed."

    except subprocess.TimeoutExpired:
        raise RuntimeError("Generated code timed out after 120 seconds.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Generated code failed: {e}")


def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print(f"[Executor] 💉 Injected + translated content")

    return params


def _detect_language(text: str) -> str:
    import agent.local_genai as genai
    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash-lite")
    try:
        response = model.generate_content(
            f"What language is this text written in? "
            f"Reply with ONLY the language name in English (e.g. Turkish, English, French).\n\n"
            f"Text: {text[:200]}"
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        import agent.local_genai as genai
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel("gemini-2.5-flash")

        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        response = model.generate_content(prompt)
        translated = response.text.strip()
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content


class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[Executor] [GOAL] Goal: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {}
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "Não foi possível elaborar um protocolo para esta tarefa, senhor."
                if speak: speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak: speak("Protocolo cancelado, senhor.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})

                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] [STEP] Step {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        print(f"[Executor] [SUCCESS] Step {step_num} done: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] [FAILURE] Step {step_num} attempt {attempt} failed: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] [SKIP] Skipping step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Protocolo abortado, senhor. Motivo: {recovery.get('reason', '')}"
                            if speak: speak(msg)
                            return msg

                        else:
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak: speak("Tentando uma abordagem alternativa, senhor.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] [WARNING] Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False

                if not success:
                    break

            if success:
                return self._summarize(goal, completed_steps, speak, step_results)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"O protocolo falhou após {replan_attempts} tentativas de replanejamento, senhor."
                if speak: speak(msg)
                return msg

            if speak: speak("Ajustando minha abordagem, senhor.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(self, goal: str, completed_steps: list, speak: Callable | None, step_results: dict | None = None) -> str:
        if not completed_steps:
            msg = f"Não foi possível executar nenhuma etapa para: {goal[:60]}, senhor."
            if speak: speak(msg)
            return msg

        # If all steps were conversation, it already spoke — don't repeat
        all_conversation = all(s.get("tool") == "conversation" for s in completed_steps)
        if all_conversation:
            result = (step_results or {}).get(completed_steps[0].get("step", "?"), "")
            return str(result) or "OK"

        # For web_search steps, use LLM to synthesize a proper explanation
        has_web_search = any(s.get("tool") == "web_search" for s in completed_steps)
        if has_web_search:
            try:
                import agent.local_genai as genai
                genai.configure(api_key=_get_api_key())
                model     = genai.GenerativeModel(model_name="gemini-2.5-flash-lite")
                steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
                results_str = ""
                if step_results:
                    for step in completed_steps:
                        sn = step.get("step", "?")
                        r = str((step_results or {}).get(sn, ""))
                        if r and r != "Done.":
                            results_str += f"\nResultado do passo {sn}: {r[:300]}"

                prompt = (
                    f'O usuário perguntou: "{goal}"\n'
                    f"Passos executados:\n{steps_str}\n"
                    f"Resultados obtidos:{results_str}\n\n"
                    "Com base APENAS nos resultados reais acima, escreva uma resposta natural em português brasileiro "
                    "respondendo à pergunta do usuário. Seja direto, informativo e preciso. "
                    "Não invente informações que não estão nos resultados. Máximo 4 frases."
                )
                response = model.generate_content(prompt)
                summary = response.text.strip()
                if speak: speak(summary)
                return summary
            except Exception:
                pass  # fall through to default summarizer

        success_lines = []
        for step in completed_steps:
            tool = step.get("tool", "?")
            desc = step.get("description", "")
            step_num = step.get("step", "?")
            result = (step_results or {}).get(step_num, "")
            result_str = str(result)[:120].strip()
            if result_str and result_str != "Done.":
                success_lines.append(f"{desc}: {result_str}")
            else:
                success_lines.append(desc)

        if len(success_lines) == 1:
            msg = success_lines[0]
            if not msg.endswith((".", "!", "?")):
                msg += ", senhor."
            elif not msg.lower().endswith("senhor"):
                msg = msg.rstrip(".!?") + ", senhor."
        else:
            msg = "Protocolo concluído, senhor. " + "; ".join(success_lines) + "."

        if speak: speak(msg)
        return msg
