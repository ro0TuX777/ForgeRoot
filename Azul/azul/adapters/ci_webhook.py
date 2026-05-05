"""
adapters/ci_webhook.py — CI pipeline webhook adapter
======================================================
Parses an inbound CI webhook payload and runs Azul verification.

Expected webhook payload (any CI system — GitHub Actions, GitLab CI, etc.):
{
    "repository":    str,           # "org/repo" or full URL
    "commit_sha":    str,           # triggering commit
    "branch":        str,
    "changed_files": list[str],     # files modified in this push/PR
    "pr_number":     int | None,
    "author":        str,
    "event_type":    "push" | "pull_request" | "merge_queue",
    "ci_context":    dict           # arbitrary CI metadata (optional)
}

Returns a structured verdict dict:
{
    "verdict":     "pass" | "reject",   # boolean result for CI gate
    "severity":    "ok" | "warn" | "critical",
    "ticket_id":   str,
    "alerts":      list[str],
    "xp_awarded":  int,
}
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from ..ticket import create_ticket, TicketType, TicketPriority
from ..ticket_store import AzulTicketStore
from ..xp_ledger import XPLedger
from ..verification_engine import verify
from ..config import AZUL_CI_STATUS_FAIL_CLOSED, AZUL_CI_STATUS_POST_ENABLED

logger = logging.getLogger(__name__)

# ── Validation ─────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"repository", "commit_sha", "changed_files"}


def _validate(payload: Dict[str, Any]) -> Optional[str]:
    missing = REQUIRED_FIELDS - set(payload.keys())
    if missing:
        return f"Missing required webhook fields: {sorted(missing)}"
    if not isinstance(payload.get("changed_files"), list):
        return "changed_files must be a list"
    return None


def _derive_priority(payload: Dict[str, Any]) -> TicketPriority:
    """Elevate priority for main/master branch pushes or merge-queue events."""
    branch = payload.get("branch", "")
    event  = payload.get("event_type", "push")
    if branch in ("main", "master") or event == "merge_queue":
        return TicketPriority.HIGH
    return TicketPriority.NORMAL


def _build_change_summary(payload: Dict[str, Any]) -> str:
    repo   = payload.get("repository", "unknown")
    sha    = payload.get("commit_sha", "unknown")[:8]
    branch = payload.get("branch", "")
    files  = payload.get("changed_files", [])
    return f"CI gate — {repo}@{sha} ({branch}): {len(files)} file(s) changed"


def _status_context() -> str:
    return os.environ.get("AZUL_CI_STATUS_CONTEXT", "azul/verification")


def _detect_provider(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("provider", "")).strip().lower()
    if explicit in {"github", "gitlab"}:
        return explicit
    ci_ctx = payload.get("ci_context") if isinstance(payload.get("ci_context"), dict) else {}
    hinted = str(ci_ctx.get("provider", "")).strip().lower()
    if hinted in {"github", "gitlab"}:
        return hinted
    repo = str(payload.get("repository", "")).lower()
    if "gitlab" in repo:
        return "gitlab"
    return "github"


def _github_repo_slug(repository: str) -> str:
    text = repository.strip()
    if "://" in text:
        parsed = parse.urlparse(text)
        return parsed.path.strip("/").removesuffix(".git")
    return text.removesuffix(".git").strip("/")


def _post_github_status(
    *,
    repository: str,
    commit_sha: str,
    state: str,
    description: str,
    context: str,
    target_url: str,
) -> Dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return {"status": "error", "provider": "github", "reason": "missing GITHUB_TOKEN"}
    repo_slug = _github_repo_slug(repository)
    if not repo_slug or "/" not in repo_slug:
        return {"status": "error", "provider": "github", "reason": f"invalid repository slug: {repository}"}
    api_base = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
    url = f"{api_base}/repos/{repo_slug}/statuses/{commit_sha}"
    body = {
        "state": state,
        "context": context,
        "description": description[:140],
    }
    if target_url:
        body["target_url"] = target_url
    req = request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "azul-ci-webhook",
        },
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            if code >= 300:
                return {"status": "error", "provider": "github", "reason": f"http {code}"}
    except error.HTTPError as exc:
        return {"status": "error", "provider": "github", "reason": f"http {exc.code}: {exc.reason}"}
    except OSError as exc:
        return {"status": "error", "provider": "github", "reason": str(exc)}
    return {"status": "posted", "provider": "github", "state": state}


def _post_gitlab_status(
    *,
    repository: str,
    commit_sha: str,
    state: str,
    description: str,
    context: str,
    target_url: str,
) -> Dict[str, Any]:
    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        return {"status": "error", "provider": "gitlab", "reason": "missing GITLAB_TOKEN"}

    project = repository.strip()
    if "://" in project:
        parsed = parse.urlparse(project)
        project = parsed.path.strip("/").removesuffix(".git")
    if not project:
        return {"status": "error", "provider": "gitlab", "reason": f"invalid repository: {repository}"}

    gitlab_state = "success" if state == "success" else "failed"
    api_base = os.environ.get("GITLAB_API_BASE", "https://gitlab.com/api/v4").rstrip("/")
    encoded_project = parse.quote_plus(project)
    params = {
        "state": gitlab_state,
        "name": context,
        "description": description[:255],
    }
    if target_url:
        params["target_url"] = target_url
    url = f"{api_base}/projects/{encoded_project}/statuses/{commit_sha}?{parse.urlencode(params)}"
    req = request.Request(
        url=url,
        method="POST",
        headers={
            "PRIVATE-TOKEN": token,
            "User-Agent": "azul-ci-webhook",
        },
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            if code >= 300:
                return {"status": "error", "provider": "gitlab", "reason": f"http {code}"}
    except error.HTTPError as exc:
        return {"status": "error", "provider": "gitlab", "reason": f"http {exc.code}: {exc.reason}"}
    except OSError as exc:
        return {"status": "error", "provider": "gitlab", "reason": str(exc)}
    return {"status": "posted", "provider": "gitlab", "state": gitlab_state}


def _post_commit_status(
    *,
    payload: Dict[str, Any],
    ci_verdict: str,
    severity: str,
    alerts: List[str],
) -> Dict[str, Any]:
    if not AZUL_CI_STATUS_POST_ENABLED:
        return {"status": "skipped", "reason": "AZUL_CI_STATUS_POST_ENABLED=false"}

    provider = _detect_provider(payload)
    commit_sha = str(payload.get("commit_sha", "")).strip()
    repository = str(payload.get("repository", "")).strip()
    if not commit_sha or not repository:
        return {"status": "error", "provider": provider, "reason": "missing commit_sha or repository"}

    state = "success" if ci_verdict == "pass" else "failure"
    description = f"Azul {ci_verdict.upper()} [{severity}]"
    if alerts:
        description = f"{description}: {alerts[0]}"
    target_url = ""
    ci_context = payload.get("ci_context")
    if isinstance(ci_context, dict):
        target_url = str(ci_context.get("run_url", "") or ci_context.get("url", ""))

    if provider == "gitlab":
        return _post_gitlab_status(
            repository=repository,
            commit_sha=commit_sha,
            state=state,
            description=description,
            context=_status_context(),
            target_url=target_url,
        )
    return _post_github_status(
        repository=repository,
        commit_sha=commit_sha,
        state=state,
        description=description,
        context=_status_context(),
        target_url=target_url,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def handle_webhook(
    payload:  Dict[str, Any],
    domain:   str = "ci_change_control",
    mode:     str = "shadow",
    store:    Optional[AzulTicketStore] = None,
    ledger:   Optional[XPLedger]        = None,
) -> Dict[str, Any]:
    """
    Parse a CI webhook payload and run Azul verification.

    Returns a verdict dict with "verdict": "pass" | "reject" for the CI gate.
    On validation failure returns {"verdict": "error", "reason": str}.
    Never raises.
    """
    err = _validate(payload)
    if err:
        logger.warning(f"[ci_webhook] Invalid payload: {err}")
        return {"verdict": "error", "reason": err, "ticket_id": None}

    ticket = create_ticket(
        ticket_type    = TicketType.CI_GATE,
        domain         = domain,
        mode           = mode,
        change_summary = _build_change_summary(payload),
        change_payload = payload,
        source         = {
            "adapter":    "ci_webhook",
            "repository": payload.get("repository"),
            "commit_sha": payload.get("commit_sha"),
            "pr_number":  payload.get("pr_number"),
            "event_type": payload.get("event_type", "push"),
        },
        target_files   = payload.get("changed_files", []),
        priority       = _derive_priority(payload),
        metadata       = {"ci_context": payload.get("ci_context", {})},
    )

    logger.info(
        f"[ci_webhook] Submitting ticket {ticket.ticket_id} "
        f"({payload.get('repository')}@{payload.get('commit_sha','')}[:8])"
    )

    result = verify(ticket, store=store, ledger=ledger)

    # Normalise to CI-friendly "pass" / "reject" gate signal
    ci_verdict = "pass" if result.get("verdict") == "pass" else "reject"
    severity = str(result.get("severity") or "critical")
    alerts = list(result.get("alerts", []))
    status_post = _post_commit_status(
        payload=payload,
        ci_verdict=ci_verdict,
        severity=severity,
        alerts=alerts,
    )

    if status_post.get("status") == "error" and AZUL_CI_STATUS_FAIL_CLOSED:
        ci_verdict = "reject"
        severity = "critical"
        alerts = alerts + [f"CI_STATUS_POST_FAILED: {status_post.get('reason', '')}"]

    return {
        "verdict":   ci_verdict,
        "severity":  severity,
        "ticket_id": result.get("ticket_id"),
        "alerts":    alerts,
        "xp_awarded": result.get("xp_awarded", 0),
        "status_post": status_post,
    }
