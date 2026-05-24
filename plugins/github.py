import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("plugin_github")

try:
    from github import Github, GithubIntegration
    HAS_PYGITHUB = True
except ImportError:
    HAS_PYGITHUB = False


class GitHubPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="github",
                version="1.0.0",
                description="GitHub integration - repos, issues, PRs, commits",
            )
        super().__init__(manifest)
        self._client: Optional[Github] = None
        self._token: str = ""
        self._project_root = Path(__file__).resolve().parent.parent

    async def on_load(self):
        self._token = self.config.get("github_token", "")
        if self._token and HAS_PYGITHUB:
            try:
                self._client = Github(self._token)
                user = self._client.get_user()
                logger.info(f"GitHub plugin loaded - authenticated as {user.login}")
            except Exception as e:
                logger.warning(f"GitHub auth failed: {e}")
        elif HAS_PYGITHUB:
            logger.info("GitHub plugin loaded (no token - read-only public)")

    async def on_unload(self):
        if self._client:
            self._client.close()
        logger.info("GitHub plugin unloaded")

    def get_repo(self, repo_name: str):
        if self._client:
            try:
                return self._client.get_repo(repo_name)
            except Exception as e:
                logger.error(f"Failed to get repo {repo_name}: {e}")
        return None

    async def create_issue(self, repo_name: str, title: str, body: str = "", labels: list[str] = None) -> Optional[dict]:
        repo = self.get_repo(repo_name)
        if not repo:
            return None
        try:
            issue = repo.create_issue(title=title, body=body, labels=labels or [])
            return {"number": issue.number, "title": issue.title, "url": issue.html_url}
        except Exception as e:
            logger.error(f"Failed to create issue: {e}")
            return None

    async def list_open_issues(self, repo_name: str, state: str = "open", limit: int = 10) -> list[dict]:
        repo = self.get_repo(repo_name)
        if not repo:
            return []
        try:
            issues = repo.get_issues(state=state)[:limit]
            return [{"number": i.number, "title": i.title, "state": i.state, "url": i.html_url} for i in issues]
        except Exception as e:
            logger.error(f"Failed to list issues: {e}")
            return []

    async def list_pull_requests(self, repo_name: str, state: str = "open", limit: int = 10) -> list[dict]:
        repo = self.get_repo(repo_name)
        if not repo:
            return []
        try:
            prs = repo.get_pulls(state=state)[:limit]
            return [{"number": pr.number, "title": pr.title, "state": pr.state, "user": pr.user.login if pr.user else "unknown"} for pr in prs]
        except Exception as e:
            logger.error(f"Failed to list PRs: {e}")
            return []

    async def get_repo_info(self, repo_name: str) -> Optional[dict]:
        repo = self.get_repo(repo_name)
        if not repo:
            return None
        try:
            return {
                "name": repo.full_name,
                "description": repo.description,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "open_issues": repo.open_issues_count,
                "language": repo.language,
                "default_branch": repo.default_branch,
            }
        except Exception as e:
            logger.error(f"Failed to get repo info: {e}")
            return None

    async def get_commit_history(self, repo_name: str, branch: str = "main", limit: int = 10) -> list[dict]:
        repo = self.get_repo(repo_name)
        if not repo:
            return []
        try:
            commits = repo.get_commits(branch)[:limit]
            return [{"sha": c.sha[:8], "message": c.commit.message.split("\n")[0], "author": c.commit.author.name if c.commit.author else "unknown"} for c in commits]
        except Exception as e:
            logger.error(f"Failed to get commits: {e}")
            return []

    async def get_local_git_status(self) -> dict:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self._project_root),
            )
            changes = result.stdout.strip().split("\n") if result.stdout.strip() else []
            return {
                "has_changes": len(changes) > 0,
                "changes_count": len(changes),
                "branch": self._get_git_branch(),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_git_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._project_root),
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"


manifest = PluginManifest(
    name="github",
    version="1.0.0",
    description="GitHub integration - repos, issues, PRs, commits",
)
