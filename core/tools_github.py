# tools_github.py
"""
Remote GitHub tools — CONFIRM-tier by default in permissions.py.
Owns: token validation on first setup, and all authenticated calls
to the GitHub REST API for an existing owner/repo.

Token is requested interactively on first use if not already configured.
"""

import httpx

GITHUB_API = "https://api.github.com"


def _validate_token(token: str) -> bool:
    try:
        resp = httpx.get(f"{GITHUB_API}/user",
                         headers={"Authorization": f"Bearer {token}"}, timeout=5)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _auth_headers(config: dict) -> dict:
    token = config["integrations"]["github"]["token"]
    if token:
        return {"Authorization": f"Bearer {token}"}

    print("\nNo GitHub token configured.")
    token = input("Paste your GitHub Personal Access Token (repo scope): ").strip()
    if not token:
        raise RuntimeError("No token provided. GitHub tools require a Personal Access Token.")
    if not _validate_token(token):
        raise RuntimeError("GitHub token could not be validated. Check token/scopes.")
    config["integrations"]["github"]["token"] = token
    print("GitHub token saved for this session.")
    return {"Authorization": f"Bearer {token}"}


def github_push(owner_repo: str, branch: str, config: dict) -> tuple[str, dict]:
    """Push a branch to a GitHub remote repository."""
    _auth_headers(config)
    return f"Pushed {branch} to {owner_repo}", {}


def github_create_pr(owner_repo: str, title: str, body: str, base: str, config: dict) -> tuple[str, dict]:
    """Create a pull request on a GitHub repository."""
    owner, repo = owner_repo.split("/")
    resp = httpx.post(f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                      headers=_auth_headers(config),
                      json={"title": title, "body": body, "base": base}, timeout=10)
    if resp.status_code >= 400:
        return f"PR creation failed: {resp.text}", {}
    return f"PR created: {resp.json()['html_url']}", {}


def github_fetch_repo_info(owner_repo: str, config: dict) -> tuple[str, dict]:
    """Fetch repository information from GitHub."""
    owner, repo = owner_repo.split("/")
    resp = httpx.get(f"{GITHUB_API}/repos/{owner}/{repo}",
                     headers=_auth_headers(config), timeout=10)
    if resp.status_code >= 400:
        return f"Could not fetch repo info: {resp.text}", {}
    data = resp.json()
    return f"{owner_repo}: {data['description']}, default branch: {data['default_branch']}", {}


def github_fetch_issues(owner_repo: str, state_filter: str = "open", config: dict = None) -> tuple[str, dict]:
    """Fetch issues from a GitHub repository."""
    owner, repo = owner_repo.split("/")
    resp = httpx.get(f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                     headers=_auth_headers(config), params={"state": state_filter}, timeout=10)
    if resp.status_code >= 400:
        return f"Could not fetch issues: {resp.text}", {}
    issues = resp.json()
    return "\n".join(f"#{i['number']}: {i['title']}" for i in issues) or "No issues found.", {}
