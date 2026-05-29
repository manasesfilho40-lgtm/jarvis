import asyncio
import json
import logging
import os
import re
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    trafilatura = None

from core.event_bus import EventType, emit
from providers.provider_manager import get_manager

logger = logging.getLogger("deep_research")

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = BASE_DIR / "research_outputs"
RESEARCH_DIR.mkdir(exist_ok=True)


def _get_provider():
    return get_manager()


def _web_search_sync(query: str, mode: str = "search") -> str:
    try:
        from actions.web_search import web_search
        return web_search(parameters={"query": query, "mode": mode}, player=None)
    except Exception as e:
        return f"Search error: {e}"


def _fetch_url_text(url: str, timeout: int = 15) -> Optional[str]:
    if not HAS_TRAFILATURA:
        return None
    try:
        downloaded = trafilatura.fetch_url(url, timeout=timeout)
        if downloaded:
            return trafilatura.extract(downloaded)
        return None
    except Exception:
        return None


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r'https?://[^\s<>"\')\]]+', text)
    return [u for u in urls if not any(x in u for x in ['google.com/search', 'youtube.com', 'facebook.com', 'x.com'])]


class ResearchProgress:
    def __init__(self, total_steps: int = 1, on_progress: Optional[Callable] = None):
        self.total = total_steps
        self.current = 0
        self.step_name = ""
        self.status = "pending"
        self.result = None
        self.error = None
        self._on_progress = on_progress
        self._lock = threading.Lock()

    def advance(self, step_name: str = ""):
        with self._lock:
            self.current += 1
            if step_name:
                self.step_name = step_name
            self._notify()

    def set_status(self, status: str):
        with self._lock:
            self.status = status
            self._notify()

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total": self.total,
                "current": self.current,
                "step_name": self.step_name,
                "status": self.status,
                "pct": round((self.current / self.total * 100) if self.total else 0),
            }

    def _notify(self):
        if self._on_progress:
            try:
                self._on_progress(self.to_dict())
            except Exception:
                pass


class DeepResearch:
    def __init__(self):
        self._provider = _get_provider()
        self._active_researches: dict[str, ResearchProgress] = {}
        self._monitors: dict[str, tuple] = {}
        self._monitor_threads: dict[str, threading.Thread] = {}

    async def _llm_generate(self, prompt: str, temperature: float = 0.3) -> str:
        try:
            response = await self._provider.generate_async(prompt, temperature=temperature)
            return response.text
        except Exception:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, lambda: self._provider.generate(prompt, temperature=temperature))
                return response.text
            except Exception as e:
                raise RuntimeError(f"LLM generation failed: {e}")

    def _build_report_md(self, query: str, summary: str, sources: list[dict],
                         sub_answers: list[dict] = None, depth: int = 1) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# Relatório de Pesquisa Profunda",
            f"",
            f"**Pergunta:** {query}",
            f"**Data:** {timestamp}",
            f"**Profundidade:** {depth} rodada(s)",
            f"",
            f"---",
            f"",
            f"## Resumo",
            f"",
            summary,
            f"",
        ]

        if sub_answers:
            lines.append("## Sub-Tópicos Investigados")
            lines.append("")
            for sa in sub_answers:
                q = sa.get("sub_question", "")
                a = sa.get("answer", "")
                lines.append(f"### {q}")
                lines.append(f"")
                lines.append(a)
                lines.append(f"")

        if sources:
            lines.append("## Fontes")
            lines.append("")
            for i, src in enumerate(sources, 1):
                url = src.get("url", "")
                title = src.get("title", url)
                lines.append(f"{i}. [{title}]({url})")
            lines.append(f"")

        lines.append("---")
        lines.append(f"*Relatório gerado automaticamente por MARK XXXIX Deep Research*")
        return "\n".join(lines)

    def _save_report(self, query: str, content: str, fmt: str = "md") -> str:
        safe_name = re.sub(r'[^\w\s-]', '', query).strip()[:60]
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"deep_research_{safe_name}_{timestamp}.{fmt}"
        filepath = RESEARCH_DIR / filename
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    async def _decompose_question(self, query: str, max_sub: int = 4) -> list[str]:
        prompt = f"""Decompose this research question into {max_sub} specific sub-questions that should be answered to build a complete understanding.

Question: {query}

Return ONLY a JSON array of strings, each being a specific sub-question.
Example: ["What are the key technologies involved?", "Who are the main companies?", "What is the current market size?"]
Max {max_sub} sub-questions. They should be independent so they can be searched in parallel."""
        try:
            text = await self._llm_generate(prompt)
            text = text.replace("```json", "").replace("```", "").strip()
            questions = json.loads(text)
            return questions[:max_sub] if isinstance(questions, list) else [query]
        except Exception:
            return [query]

    async def _synthesize_summary(self, query: str, findings: list[dict]) -> str:
        findings_text = "\n\n".join(
            f"## Sub-Questão: {f.get('sub_question', 'Principal')}\n"
            f"Resultados: {f.get('search_results', '')[:2000]}\n"
            f"Extração: {f.get('extracted_text', '')[:3000]}"
            for f in findings
        )
        prompt = f"""You are a deep research analyst. Synthesize all findings below into a comprehensive answer.

Original question: {query}

Findings from multiple sources:
{findings_text}

Write a detailed, well-structured summary in Brazilian Portuguese covering:
1. Main answer to the original question
2. Key data points and evidence found
3. Different perspectives if any
4. Confidence level in the findings

Format in clear paragraphs with Markdown headers."""
        return await self._llm_generate(prompt)

    async def _identify_gaps(self, query: str, summary: str, sources: list[dict]) -> list[str]:
        sources_text = "\n".join(f"- {s.get('url', '')}" for s in sources[:10])
        prompt = f"""You are a research gap analyzer. Based on what was found, identify what important aspects are STILL MISSING or need more investigation.

Original question: {query}

Summary so far: {summary[:2000]}

Sources consulted: {sources_text}

Return ONLY a JSON array of 1-3 follow-up questions that would fill the most important knowledge gaps.
Example: ["What are the specific technical specifications?", "What is the adoption rate among enterprises?"]"""
        try:
            text = await self._llm_generate(prompt)
            text = text.replace("```json", "").replace("```", "").strip()
            gaps = json.loads(text)
            return gaps[:3] if isinstance(gaps, list) else []
        except Exception:
            return []

    def _extract_page_links(self, url: str, max_links: int = 5) -> list[str]:
        if not HAS_TRAFILATURA:
            return []
        try:
            downloaded = trafilatura.fetch_url(url, timeout=10)
            if not downloaded:
                return []
            text = trafilatura.extract(downloaded)
            if not text:
                return []
            urls = _extract_urls(text)
            same_domain = [u for u in urls if url.split('/')[2] in u][:max_links]
            return same_domain
        except Exception:
            return []

    def _extract_from_pdf(self, pdf_path: str) -> Optional[str]:
        try:
            import PyPDF2
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return text[:10000]
            return None
        except ImportError:
            logger.warning("PyPDF2 not installed. Install with: pip install PyPDF2")
        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
        try:
            import pdfminer.high_level
            text = pdfminer.high_level.extract_text(pdf_path)
            if text.strip():
                return text[:10000]
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"PDFMiner extraction error: {e}")
        return None

    def _extract_from_docx(self, docx_path: str) -> Optional[str]:
        try:
            import docx
            doc = docx.Document(docx_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text[:10000] if text.strip() else None
        except ImportError:
            logger.warning("python-docx not installed. Install with: pip install python-docx")
        except Exception as e:
            logger.warning(f"DOCX extraction error: {e}")
        return None

    def _extract_from_file(self, file_path: str) -> Optional[str]:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return self._extract_from_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return self._extract_from_docx(file_path)
        elif ext in (".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css"):
            try:
                text = Path(file_path).read_text(encoding="utf-8")
                return text[:10000] if text.strip() else None
            except Exception:
                return None
        return None

    async def deep_research(
        self,
        query: str,
        depth: int = 2,
        max_sources: int = 10,
        save: bool = False,
        format: str = "md",
        on_progress: Optional[Callable] = None,
        background: bool = False,
        file_paths: Optional[list[str]] = None,
    ) -> dict:
        research_id = f"dr_{int(time.time())}_{hash(query) % 10000}"
        steps = 2 + (depth * 2) + (1 if save else 0)
        progress = ResearchProgress(total_steps=steps, on_progress=on_progress)
        self._active_researches[research_id] = progress

        if background:
            emit(EventType.UI_NOTIFICATION, {
                "title": "Pesquisa Profunda Iniciada",
                "message": f"Investigando: {query[:60]}... ({depth} rodada(s))"
            }, source="deep_research")
            thread = threading.Thread(
                target=self._run_background,
                args=(research_id, query, depth, max_sources, save, format, file_paths),
                daemon=True
            )
            thread.start()
            return {
                "research_id": research_id,
                "status": "background",
                "message": f"Pesquisa em andamento (ID: {research_id}). Use get_research_status('{research_id}') para acompanhar.",
            }

        return await self._execute_research(research_id, progress, query, depth, max_sources, save, format, file_paths)

    def _run_background(self, research_id: str, query: str, depth: int,
                        max_sources: int, save: bool, format: str, file_paths: Optional[list[str]]):
        try:
            progress = self._active_researches.get(research_id)
            if not progress:
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self._execute_research(research_id, progress, query, depth, max_sources, save, format, file_paths)
            )
            loop.close()
            progress.result = result
            progress.set_status("completed")
            emit(EventType.UI_NOTIFICATION, {
                "title": "Pesquisa Profunda Concluída",
                "message": f"Relatório sobre '{query[:50]}' está pronto!"
            }, source="deep_research")
        except Exception as e:
            progress = self._active_researches.get(research_id)
            if progress:
                progress.error = str(e)
                progress.set_status("failed")

    async def _execute_research(
        self, research_id: str, progress: ResearchProgress,
        query: str, depth: int, max_sources: int, save: bool, format: str,
        file_paths: Optional[list[str]]
    ) -> dict:
        all_findings = []
        all_sources = []
        current_query = query
        sub_answers = []

        progress.set_status("decomposing")
        progress.advance("Decompondo a pergunta em sub-tópicos")
        sub_questions = await self._decompose_question(query)

        for round_num in range(depth):
            progress.advance(f"Rodada {round_num + 1}/{depth}: pesquisando sub-tópicos")
            round_questions = sub_questions if round_num == 0 else await self._decompose_question(current_query, max_sub=3)
            round_findings = []

            for sq in round_questions:
                progress.set_status(f"Buscando: {sq[:60]}...")
                search_text = await asyncio.get_event_loop().run_in_executor(
                    None, _web_search_sync, sq, "search"
                )

                urls = _extract_urls(search_text)[:3]
                extracted = ""

                for url in urls:
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, _fetch_url_text, url, 10
                    )
                    if text and len(text) > 100:
                        extracted += f"\n\n--- Conteúdo de {url} ---\n{text[:2000]}"
                        all_sources.append({"url": url, "title": url.split('/')[-1] or url})
                    await asyncio.sleep(0.3)

                finding = {
                    "sub_question": sq,
                    "search_results": search_text[:2000],
                    "extracted_text": extracted[:3000],
                }
                round_findings.append(finding)
                sub_answers.append({"sub_question": sq, "answer": extracted[:1500] or search_text[:1500]})
                all_findings.append(finding)

            progress.advance(f"Rodada {round_num + 1}/{depth}: sintetizando descobertas")
            summary = await self._synthesize_summary(
                current_query if round_num > 0 else query,
                round_findings
            )
            all_sources = all_sources[:max_sources]

            if round_num < depth - 1:
                progress.advance(f"Rodada {round_num + 1}/{depth}: identificando lacunas")
                gaps = await self._identify_gaps(current_query, summary, all_sources)
                if gaps:
                    current_query = f"{query}. Aspectos adicionais: " + "; ".join(gaps)
                    progress.set_status(f"Lacunas identificadas: {len(gaps)} nova(s) pergunta(s)")
                    sub_questions = gaps
                else:
                    break

            if round_num == depth - 1:
                final_summary = summary

        progress.advance("Gerando relatório final")
        final_summary = await self._synthesize_summary(query, all_findings)

        if file_paths:
            progress.set_status("Analisando documentos fornecidos")
            for fp in file_paths:
                doc_text = await asyncio.get_event_loop().run_in_executor(
                    None, self._extract_from_file, fp
                )
                if doc_text:
                    prompt = f"""Document content from {Path(fp).name}:
{doc_text[:5000]}

Integrate the key information from this document into the research about: {query}

Extract the most relevant data points that complement or enhance the findings."""
                    doc_analysis = await self._llm_generate(prompt)
                    all_findings.append({
                        "sub_question": f"Documento: {Path(fp).name}",
                        "search_results": "",
                        "extracted_text": doc_analysis,
                    })

        report_md = self._build_report_md(
            query, final_summary, all_sources, sub_answers, depth
        )

        saved_path = None
        if save:
            progress.set_status("Salvando relatório")
            if format == "md":
                saved_path = self._save_report(query, report_md, "md")
            else:
                saved_path = self._save_report(query, report_md, "md")

        progress.advance("Pesquisa concluída")
        progress.set_status("completed")

        result = {
            "query": query,
            "summary": final_summary,
            "sources_count": len(all_sources),
            "sources": all_sources[:max_sources],
            "sub_questions_explored": len(sub_answers),
            "depth_achieved": depth,
            "report_md": report_md,
            "saved_path": saved_path,
            "research_id": research_id,
        }
        progress.result = result
        self._active_researches[research_id] = progress
        return result

    async def comparative_research(self, query: str, items: list[str],
                                    aspect: str = "geral", save: bool = False) -> dict:
        progress = ResearchProgress(total_steps=3)
        progress.set_status("Pesquisa comparativa")

        progress.advance("Buscando informações de cada item")
        item_data = {}
        for item in items:
            item_query = f"{item} {aspect}" if aspect != "geral" else item
            search_text = await asyncio.get_event_loop().run_in_executor(
                None, _web_search_sync, f"{query} {item_query}", "search"
            )
            urls = _extract_urls(search_text)[:3]
            extracted = ""
            for url in urls:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_url_text, url, 10
                )
                if text:
                    extracted += f"\n{text[:1500]}"
                await asyncio.sleep(0.3)
            item_data[item] = {
                "search": search_text[:2000],
                "extracted": extracted[:3000],
            }

        progress.advance("Sintetizando comparação")
        items_text = "\n\n".join(
            f"=== {item} ===\nBusca: {data['search']}\nExtraído: {data['extracted']}"
            for item, data in item_data.items()
        )
        prompt = f"""Realize uma comparação detalhada em português brasileiro.

Pergunta original: {query}
Aspecto: {aspect}

Dados coletados:
{items_text}

Produza uma comparação estruturada com tabela comparativa, destacando:
- Principais diferenças
- Melhor custo-benefício
- Recomendação final baseada nos dados"""
        comparison = await self._llm_generate(prompt)

        result = {
            "query": query,
            "items": items,
            "aspect": aspect,
            "comparison": comparison,
        }

        if save:
            progress.set_status("Salvando comparação")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comparative_{'_'.join(items[:3])}_{timestamp}.md"
            safe_filename = re.sub(r'[^\w_.-]', '', filename)
            filepath = RESEARCH_DIR / safe_filename
            md = f"# Comparação: {query}\n\n**Itens:** {', '.join(items)}\n**Aspecto:** {aspect}\n\n{comparison}"
            filepath.write_text(md, encoding="utf-8")
            result["saved_path"] = str(filepath)

        progress.advance("Concluído")
        return result

    async def crawl_research(self, query: str, crawl_depth: int = 2,
                              max_pages: int = 15, save: bool = False) -> dict:
        progress = ResearchProgress(total_steps=3 + crawl_depth)
        progress.set_status("Iniciando pesquisa com crawl")

        progress.advance("Buscando páginas iniciais")
        search_text = await asyncio.get_event_loop().run_in_executor(
            None, _web_search_sync, query, "search"
        )
        seed_urls = _extract_urls(search_text)[:3]
        visited = set()
        all_content = []
        page_queue = [(url, 0) for url in seed_urls]

        while page_queue and len(visited) < max_pages:
            url, current_depth = page_queue.pop(0)
            if url in visited or current_depth > crawl_depth:
                continue
            visited.add(url)

            progress.set_status(f"Crawling ({len(visited)}/{max_pages}): {url[:60]}...")
            text = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_url_text, url, 10
            )
            if text and len(text) > 200:
                all_content.append({"url": url, "depth": current_depth, "content": text[:3000]})

            if current_depth < crawl_depth:
                links = await asyncio.get_event_loop().run_in_executor(
                    None, self._extract_page_links, url, 3
                )
                for link in links:
                    if link not in visited:
                        page_queue.append((link, current_depth + 1))

            await asyncio.sleep(0.3)
            progress.advance(f"Crawling profundidade {current_depth}")

        progress.set_status("Sintetizando material crawlado")
        content_text = "\n\n".join(
            f"--- {c['url']} (profundidade {c['depth']}) ---\n{c['content'][:2000]}"
            for c in all_content[:10]
        )
        prompt = f"""Sintetize o material coletado via crawling sobre: {query}

Páginas analisadas ({len(all_content)}):
{content_text}

Produza um relatório estruturado em português brasileiro com:
1. Visão geral do tema
2. Principais achados organizados por tópico
3. Conexões entre as diferentes fontes"""
        summary = await self._llm_generate(prompt)

        result = {
            "query": query,
            "pages_crawled": len(all_content),
            "summary": summary,
            "crawled_sources": [{"url": c["url"], "depth": c["depth"]} for c in all_content],
            "report_md": f"# Crawl Research: {query}\n\n{summary}",
        }

        if save:
            progress.set_status("Salvando relatório")
            result["saved_path"] = self._save_report(f"crawl_{query}", result["report_md"])

        return result

    def get_status(self, research_id: str) -> Optional[dict]:
        progress = self._active_researches.get(research_id)
        if not progress:
            return None
        d = progress.to_dict()
        if progress.result:
            d["result"] = progress.result
        if progress.error:
            d["error"] = progress.error
        return d

    def list_active(self) -> list[dict]:
        return [
            {"research_id": rid, **p.to_dict()}
            for rid, p in self._active_researches.items()
        ]

    def _monitor_loop(self, topic: str, monitor_id: str, interval_hours: int,
                       on_progress: Optional[Callable] = None):
        while True:
            monitor = self._monitors.get(monitor_id)
            if not monitor or monitor.get("active") is False:
                break
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    self.deep_research(
                        query=f"Atualização sobre {topic} (notícias recentes)",
                        depth=1,
                        max_sources=5,
                        save=True,
                        on_progress=on_progress,
                    )
                )
                loop.close()
                emit(EventType.UI_NOTIFICATION, {
                    "title": f"Monitor: {topic[:40]}",
                    "message": f"Nova atualização disponível! Fontes: {result.get('sources_count', 0)}",
                }, source="deep_research")
            except Exception as e:
                logger.error(f"Monitor {monitor_id} error: {e}")
            for _ in range(interval_hours * 3600):
                monitor = self._monitors.get(monitor_id)
                if not monitor or monitor.get("active") is False:
                    return
                time.sleep(1)

    def start_monitor(self, topic: str, interval_hours: int = 6,
                       on_progress: Optional[Callable] = None) -> str:
        monitor_id = f"mon_{int(time.time())}_{hash(topic) % 10000}"
        self._monitors[monitor_id] = {
            "topic": topic,
            "interval_hours": interval_hours,
            "active": True,
            "started_at": time.time(),
        }
        thread = threading.Thread(
            target=self._monitor_loop,
            args=(topic, monitor_id, interval_hours, on_progress),
            daemon=True,
        )
        self._monitor_threads[monitor_id] = thread
        thread.start()
        return monitor_id

    def stop_monitor(self, monitor_id: str) -> bool:
        if monitor_id in self._monitors:
            self._monitors[monitor_id]["active"] = False
            return True
        return False

    def list_monitors(self) -> list[dict]:
        return [
            {
                "id": mid,
                "topic": m["topic"],
                "interval_hours": m["interval_hours"],
                "active": m["active"],
                "started_at": datetime.fromtimestamp(m["started_at"]).isoformat(),
            }
            for mid, m in self._monitors.items()
        ]


_research_instance = None


def get_deep_research() -> DeepResearch:
    global _research_instance
    if _research_instance is None:
        _research_instance = DeepResearch()
    return _research_instance


def deep_research_action(parameters: dict, player=None) -> str:
    dr = get_deep_research()
    query = parameters.get("query", "").strip()
    action = parameters.get("action", "research")
    depth = int(parameters.get("depth", 2))
    max_sources = int(parameters.get("max_sources", 10))
    save = bool(parameters.get("save", False))
    background = bool(parameters.get("background", False))
    monitor_interval = int(parameters.get("monitor_interval", 0))
    crawl_depth = int(parameters.get("crawl_depth", 1))
    file_paths = parameters.get("file_paths")
    items = parameters.get("items", [])
    aspect = parameters.get("aspect", "geral")
    monitor_id = parameters.get("monitor_id", "")
    topic = parameters.get("topic", "")
    format = parameters.get("format", "md")

    def _on_progress(pdata: dict):
        if player:
            pct = pdata.get("pct", 0)
            step = pdata.get("step_name", "")
            player.write_log(f"[DeepResearch] {pct}% - {step}")

    try:
        if action == "status":
            rid = parameters.get("research_id", "")
            if rid:
                status = dr.get_status(rid)
                return json.dumps(status, ensure_ascii=False, indent=2) if status else f"Pesquisa '{rid}' não encontrada."
            active = dr.list_active()
            return json.dumps(active, ensure_ascii=False, indent=2) if active else "Nenhuma pesquisa ativa."

        elif action == "monitor_status":
            monitors = dr.list_monitors()
            return json.dumps(monitors, ensure_ascii=False, indent=2) if monitors else "Nenhum monitor ativo."

        elif action == "start_monitor":
            if not topic:
                return "Parâmetro 'topic' obrigatório para monitor."
            mid = dr.start_monitor(topic, interval_hours=monitor_interval or 6, on_progress=_on_progress)
            msg = f"Monitor iniciado para '{topic}' a cada {monitor_interval or 6}h (ID: {mid})."
            if player:
                player.write_log(msg)
            return msg

        elif action == "stop_monitor":
            if not monitor_id:
                return "Parâmetro 'monitor_id' obrigatório."
            if dr.stop_monitor(monitor_id):
                return f"Monitor '{monitor_id}' parado."
            return f"Monitor '{monitor_id}' não encontrado."

        elif action == "compare":
            if not items:
                return "Lista de 'items' obrigatória para comparação."
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(dr.comparative_research(query, items, aspect, save))
            finally:
                loop.close()
            lines = [f"## Comparação: {query}", f"**Itens:** {', '.join(items)}", "", result.get("comparison", "")]
            if result.get("saved_path"):
                lines.append(f"\n*Salvo em: {result['saved_path']}*")
            return "\n".join(lines)

        elif action == "crawl":
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    dr.crawl_research(query, crawl_depth=crawl_depth, max_pages=max_sources, save=save)
                )
            finally:
                loop.close()
            lines = [
                f"## Crawl Research: {query}",
                f"**Páginas analisadas:** {result['pages_crawled']}",
                "",
                result.get("summary", ""),
            ]
            if result.get("saved_path"):
                lines.append(f"\n*Salvo em: {result['saved_path']}*")
            return "\n".join(lines)

        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    dr.deep_research(
                        query=query,
                        depth=depth,
                        max_sources=max_sources,
                        save=save,
                        format=format,
                        on_progress=_on_progress,
                        background=background,
                        file_paths=file_paths,
                    )
                )
            finally:
                loop.close()

            if result.get("status") == "background":
                return result["message"]

            lines = [
                f"## Pesquisa Profunda: {query}",
                f"**Profundidade:** {result.get('depth_achieved', depth)} rodada(s)",
                f"**Fontes consultadas:** {result.get('sources_count', 0)}",
                f"**Sub-tópicos explorados:** {result.get('sub_questions_explored', 0)}",
                "",
                result.get("summary", ""),
            ]
            if result.get("saved_path"):
                lines.append(f"\n*Relatório salvo em: {result['saved_path']}*")
            if player:
                player.write_log(f"[DeepResearch] Concluído: {query[:60]}... ({result.get('sources_count', 0)} fontes)")
            return "\n".join(lines)

    except Exception as e:
        logger.error(f"Deep research action error: {e}")
        traceback.print_exc()
        return f"Erro na pesquisa profunda: {e}"
