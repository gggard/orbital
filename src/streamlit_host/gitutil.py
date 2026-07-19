import subprocess


class GitError(Exception):
    pass


def resolve_branch_head(repo_url: str, branch: str, timeout: int = 30) -> str:
    """Return the commit sha of the branch head using git ls-remote."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        raise GitError(f"git ls-remote failed: {e.stderr.strip()}") from e
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git ls-remote timed out for {repo_url}") from e
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}":
            return sha.strip()
    raise GitError(f"branch {branch!r} not found in {repo_url}")
