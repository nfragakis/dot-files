"""Read-only local Git snapshots and exact-head GitHub metadata via authenticated gh."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
from urllib.parse import urlsplit

from metadata_common import clean

OUTPUT_LIMIT = 256 * 1024
CACHE_SECONDS = 60
CACHE_LIMIT = 8192
GIT_SECONDS = 0.5
NETWORK_SECONDS = 1.5
_HEX = re.compile(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\Z")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+\Z")
_NETWORK_FIELDS = {"pr_status", "pr_url", "ci_status"}
# Query refs, not a title search: a fork's ref can have a PR in its parent repository.
# Both connections expose truncation; a bounded partial response never means green CI.
_QUERY = """query($owner:String!,$name:String!,$ref:String!){
  repository(owner:$owner,name:$name){nameWithOwner url ref(qualifiedName:$ref){
    target{oid ...Checks} associatedPullRequests(first:20,states:OPEN){
      totalCount pageInfo{hasNextPage} nodes{
        number state isDraft headRefName headRefOid reviewDecision
        headRepository{nameWithOwner url} baseRepository{nameWithOwner url}
        commits(last:1){nodes{commit{...Checks}}}
      }
    }
  }}
}
fragment Checks on Commit{oid statusCheckRollup{state
  contexts(first:100){totalCount pageInfo{hasNextPage} nodes{
    __typename ... on CheckRun{status conclusion} ... on StatusContext{state}
  }}
}}"""


def _environment() -> dict[str, str]:
    # Do not inherit a different pane's repository/index or gh's implicit repository.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    for name in ("GH_REPO", "GH_DEBUG", "GH_FORCE_TTY", "GH_PAGER"):
        env.pop(name, None)
    env.update({
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
        "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1",
        "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1", "NO_COLOR": "1", "LC_ALL": "C",
    })
    return env


def _run(argv: list[str], cwd: Path, deadline: float, seconds: float,
         limit: int = OUTPUT_LIMIT) -> tuple[str, bytes]:
    end = min(deadline, time.monotonic() + seconds)
    if end <= time.monotonic():
        return "deadline", b""
    process = None
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=_environment(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        chunks = []
        size = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    return "timeout", b""
                chunk = os.read(process.stdout.fileno(), min(8192, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    return "output limit", b""
        process.wait(timeout=max(0.001, end - time.monotonic()))
        return ("ok", b"".join(chunks)) if process.returncode == 0 else ("failed", b"")
    except FileNotFoundError:
        return "not installed or directory missing", b""
    except subprocess.TimeoutExpired:
        return "timeout", b""
    except (OSError, ValueError, subprocess.SubprocessError):
        return "unavailable", b""
    finally:
        if process is not None:
            # Also terminate children holding stdout open after their parent exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _git(cwd: Path, deadline: float, *args: str) -> tuple[str, bytes]:
    return _run([
        "git", "--no-pager", "--no-optional-locks", "--literal-pathspecs",
        "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
        "-c", "core.untrackedCache=false", "-c", "maintenance.auto=false",
        "-c", "gc.auto=0", *args,
    ], cwd, deadline, GIT_SECONDS)


def _snapshot(raw: bytes) -> tuple[dict[str, str], str, str] | None:
    headers = {}
    tracked = untracked = 0
    records = iter(raw.split(b"\0"))
    for item in records:
        if item.startswith(b"# "):
            key, _, value = item[2:].partition(b" ")
            headers[key] = value.decode("utf-8", "replace")
        elif item.startswith((b"1 ", b"u ")):
            tracked += 1
        elif item.startswith(b"2 "):
            tracked += 1
            if next(records, None) is None:
                return None
        elif item.startswith(b"? "):
            untracked += 1
        elif item:
            return None
    branch, commit = headers.get(b"branch.head"), headers.get(b"branch.oid")
    if not branch or not commit or (commit != "(initial)" and not _HEX.fullmatch(commit)):
        return None
    detached = branch == "(detached)"
    fields = {
        "workspace_branch": "Detached HEAD · " + commit[:12] if detached else branch,
        "git_status": "Clean" if not (tracked or untracked) else f"Dirty · {tracked} tracked · {untracked} untracked",
    }
    upstream = headers.get(b"branch.upstream")
    divergence = headers.get(b"branch.ab", "")
    match = re.fullmatch(r"\+(\d+) -(\d+)", divergence)
    if upstream and match:
        fields["git_divergence"] = f"↑{match[1]} ↓{match[2]} · {upstream} (local tracking ref)"
    elif upstream:
        fields["git_divergence"] = f"Upstream unavailable · {upstream}"
    else:
        fields["git_divergence"] = "No upstream"
    return fields, "" if detached else branch, "" if commit == "(initial)" else commit


def _identity(raw: str) -> str:
    """Normalize owner/repo and host, never retaining URL credentials or parameters."""
    try:
        if "://" in raw:
            url = urlsplit(raw)
            if url.scheme not in ("https", "http", "ssh", "git"):
                return ""
            host, path = url.hostname or "", url.path
            if url.scheme in ("http", "https") and url.port not in (None, 80, 443):
                return ""
        else:
            match = re.fullmatch(r"(?:[^/@:]+@)?([A-Za-z0-9.-]+):(.+)", raw)
            if match is None:
                return ""
            host, path = match.groups()
        host = host.lower()
        path = path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or not _REPO.fullmatch(path):
            return ""
        if path.split("/")[1] in (".", ".."):
            return ""
        return host + "/" + path.lower()
    except ValueError:
        return ""


def _remote_name(raw: bytes, branch: str) -> str:
    config: dict[str, list[str]] = {}
    for record in raw.split(b"\0"):
        key, separator, value = record.partition(b"\n")
        if separator:
            config.setdefault(key.decode("utf-8", "replace"), []).append(value.decode("utf-8", "replace"))
    selected = next((config[key][-1] for key in (
        f"branch.{branch}.pushremote", "remote.pushdefault", f"branch.{branch}.remote",
    ) if config.get(key)), "")
    remotes = {key[7:-4] for key in config if key.startswith("remote.") and key.endswith(".url")}
    if not selected:
        selected = "origin" if "origin" in remotes else next(iter(remotes)) if len(remotes) == 1 else ""
    # A configured push destination takes precedence; do not substitute another repo.
    return selected


def _remote_identity(raw: bytes) -> str:
    identities = {_identity(value) for value in raw.decode("utf-8", "replace").splitlines()}
    if len(identities) != 1:
        return ""
    identity = identities.pop()
    host = identity.partition("/")[0]
    enterprise = os.environ.get("GH_HOST", "").lower()
    return identity if identity and host in ("github.com", enterprise) else ""


def _ci(pr: dict) -> str:
    commits = pr.get("commits")
    nodes = commits.get("nodes") if isinstance(commits, dict) else None
    commit = nodes[0].get("commit") if isinstance(nodes, list) and len(nodes) == 1 and isinstance(nodes[0], dict) else None
    if not isinstance(commit, dict) or commit.get("oid") != pr.get("headRefOid"):
        return "Unavailable · PR commit not reported"
    if "statusCheckRollup" not in commit:
        return "Unavailable · check data missing"
    rollup = commit.get("statusCheckRollup")
    if rollup is None:
        return "No checks reported"
    contexts = rollup.get("contexts") if isinstance(rollup, dict) else None
    if not isinstance(contexts, dict) or not isinstance(contexts.get("nodes"), list):
        return "Unavailable · check data missing"
    checks, total = contexts["nodes"], contexts.get("totalCount")
    page = contexts.get("pageInfo")
    if type(total) is not int or total < 0 or not isinstance(page, dict) or type(page.get("hasNextPage")) is not bool:
        return "Unavailable · check coverage unknown"
    if page["hasNextPage"] or total != len(checks):
        state = {"SUCCESS": "success", "FAILURE": "failure", "PENDING": "pending"}.get(rollup.get("state"), "unknown")
        return f"Incomplete · {len(checks)}/{total} checks · rollup {state}"
    if not checks:
        return "No checks reported"
    counts = {"passed": 0, "pending": 0, "unsuccessful": 0, "skipped": 0, "unknown": 0}
    for check in checks:
        category = "unknown"
        if isinstance(check, dict) and check.get("__typename") == "StatusContext":
            category = {"SUCCESS": "passed", "PENDING": "pending", "EXPECTED": "pending",
                        "FAILURE": "unsuccessful", "ERROR": "unsuccessful"}.get(check.get("state"), "unknown")
        elif isinstance(check, dict) and check.get("__typename") == "CheckRun":
            if check.get("status") == "COMPLETED":
                category = {"SUCCESS": "passed", "NEUTRAL": "skipped", "SKIPPED": "skipped",
                            "FAILURE": "unsuccessful", "TIMED_OUT": "unsuccessful", "CANCELLED": "unsuccessful",
                            "ACTION_REQUIRED": "unsuccessful", "STARTUP_FAILURE": "unsuccessful",
                            "STALE": "unsuccessful"}.get(check.get("conclusion"), "unknown")
            elif check.get("status") in ("QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "PENDING", "EXPECTED"):
                category = "pending"
        counts[category] += 1
    label = ("Failing" if counts["unsuccessful"] else "Pending" if counts["pending"] else
             "Incomplete" if counts["unknown"] else "Passing" if counts["passed"] else "Skipped")
    detail = ", ".join(f"{number} {kind}" for kind, number in counts.items() if number)
    if label in ("Passing", "Skipped") and rollup.get("state") != "SUCCESS":
        label = "Incomplete"
        detail += " · rollup " + {"FAILURE": "failure", "PENDING": "pending"}.get(rollup.get("state"), "unknown")
    return f"{label} · {detail} / {total} checks"


def _pr_result(value: dict, identity: str, branch: str, commit: str) -> tuple[dict[str, str], str] | None:
    data = value.get("data")
    repo = data.get("repository") if isinstance(data, dict) else None
    host, name = identity.split("/", 1)
    if value.get("errors") or not isinstance(repo, dict) or _identity(repo.get("url", "")) != identity or str(repo.get("nameWithOwner", "")).lower() != name:
        return None
    ref = repo.get("ref")
    if ref is None:
        return {"pr_status": "Unavailable · branch not pushed", "ci_status": "Unavailable · branch not pushed"}, "branch not pushed"
    target = ref.get("target") if isinstance(ref, dict) else None
    remote_head = target.get("oid") if isinstance(target, dict) else None
    prs = ref.get("associatedPullRequests") if isinstance(ref, dict) else None
    if not isinstance(remote_head, str) or not _HEX.fullmatch(remote_head) or not isinstance(prs, dict):
        return None
    branch_ci = _ci({"headRefOid": remote_head, "commits": {"nodes": [{"commit": target}]}})
    branch_ci = ("Branch HEAD · " if remote_head == commit else "Remote HEAD · ") + branch_ci
    note = "pushed HEAD " + remote_head[:12]
    if remote_head != commit:
        note += " (local HEAD differs)"
    nodes, page, total = prs.get("nodes"), prs.get("pageInfo"), prs.get("totalCount")
    if not isinstance(nodes, list) or not isinstance(page, dict) or page.get("hasNextPage") is not False or type(total) is not int or total != len(nodes):
        return {"pr_status": "Unavailable · incomplete PR coverage", "ci_status": branch_ci}, "incomplete PR coverage; " + note
    matches = []
    for pr in nodes:
        if not isinstance(pr, dict) or pr.get("state") != "OPEN" or pr.get("headRefName") != branch:
            continue
        head = pr.get("headRepository")
        if not isinstance(head, dict) or _identity(head.get("url", "")) != identity or str(head.get("nameWithOwner", "")).lower() != name:
            continue
        if pr.get("headRefOid") != remote_head:
            return None
        matches.append(pr)
    if not matches:
        return {"pr_status": "No open PR", "ci_status": branch_ci}, note
    if len(matches) != 1:
        return {"pr_status": "Unavailable · multiple open PRs", "ci_status": branch_ci}, "ambiguous PR target; " + note
    pr = matches[0]
    number, base = pr.get("number"), pr.get("baseRepository")
    if type(number) is not int or number <= 0 or not isinstance(base, dict):
        return None
    base_identity = _identity(base.get("url", ""))
    if not base_identity.startswith(host + "/") or str(base.get("nameWithOwner", "")).lower() != base_identity.partition("/")[2]:
        return None
    decision = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes requested",
                "REVIEW_REQUIRED": "review required", "": "review undecided", None: "review unavailable"}.get(pr.get("reviewDecision"), "review unavailable")
    fields = {"pr_status": f"#{number} · {'Draft' if pr.get('isDraft') is True else 'Open'} · {decision}", "ci_status": _ci(pr)}
    url = "https://" + base_identity + "/pull/" + str(number)
    if len(url) <= 300:
        fields["pr_url"] = url
    if remote_head != commit:
        fields["pr_status"] += " · local HEAD differs"
        fields["ci_status"] = "Remote HEAD · " + fields["ci_status"]
    return fields, note


def _cache_directory() -> int:
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        info = os.fstat(current)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("unsafe state directory")
        for name in ("tern", "agent-cockpit", "workspaces"):
            try:
                os.mkdir(name, mode=0o700, dir_fd=current)
            except FileExistsError:
                pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            try:
                if os.fstat(child).st_uid != os.getuid():
                    raise ValueError("unsafe cache directory")
                os.fchmod(child, 0o700)
            except BaseException:
                os.close(child)
                raise
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _cached(key: str) -> dict:
    directory = None
    try:
        directory = _cache_directory()
        fd = os.open(key + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return {}
            raw = stream.read(CACHE_LIMIT + 1)
        value = json.loads(raw) if len(raw) <= CACHE_LIMIT else None
        if not isinstance(value, dict) or value.get("identity") != key:
            return {}
        for stamp in ("attempted", "observed"):
            if type(value.get(stamp)) not in (int, float) or not 0 <= value[stamp] <= time.time():
                return {}
        fields = value.get("fields")
        if not isinstance(fields, dict) or any(name not in _NETWORK_FIELDS or not isinstance(text, str) or len(text) > 300 for name, text in fields.items()):
            return {}
        if not isinstance(value.get("note"), str) or not isinstance(value.get("error"), str):
            return {}
        return value
    except (OSError, ValueError, UnicodeError):
        return {}
    finally:
        if directory is not None:
            os.close(directory)


def _store(key: str, value: dict) -> None:
    directory = None
    temporary = "." + key + "." + os.urandom(8).hex()
    created = False
    try:
        directory = _cache_directory()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"))
        os.replace(temporary, key + ".json", src_dir_fd=directory, dst_dir_fd=directory)
    except (OSError, ValueError):
        pass
    finally:
        if directory is not None:
            if created:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.close(directory)


def _github(cwd: Path, gitdir: str, identity: str, branch: str, commit: str,
            deadline: float) -> tuple[dict[str, str], str]:
    key = hashlib.sha256(json.dumps([gitdir, commit, branch, identity]).encode()).hexdigest()
    cached = _cached(key)
    if not cached or time.time() - cached["attempted"] >= CACHE_SECONDS:
        host, owner, name = identity.split("/", 2)
        status, raw = _run([
            "gh", "api", "graphql", "--hostname", host,
            "--raw-field", "query=" + _QUERY, "--raw-field", "owner=" + owner,
            "--raw-field", "name=" + name, "--raw-field", "ref=refs/heads/" + branch,
        ], cwd, deadline, NETWORK_SECONDS)
        result = None
        if status == "ok":
            try:
                value = json.loads(raw)
                result = _pr_result(value, identity, branch, commit) if isinstance(value, dict) else None
            except (ValueError, TypeError, AttributeError):
                pass
        stamp = time.time()
        if result is not None:
            fields, note = result
            cached = {"identity": key, "attempted": stamp, "observed": stamp,
                      "fields": fields, "note": note, "error": ""}
        else:
            error = "authentication/network unavailable" if status == "failed" else "response unavailable" if status == "ok" else status
            cached = {"identity": key, "attempted": stamp, "observed": cached.get("observed", 0),
                      "fields": cached.get("fields", {}), "note": cached.get("note", ""), "error": error}
        if status != "deadline":
            _store(key, cached)
    age = int(max(0, time.time() - cached["observed"]))
    fields = dict(cached["fields"])
    if cached["error"]:
        if fields:
            for name in ("pr_status", "ci_status"):
                if name in fields:
                    fields[name] = "Stale · " + fields[name]
            return fields, f"GitHub · {identity} · stale {age}s · {cached['error']} · {cached['note']}"
        return {"pr_status": "Unavailable", "ci_status": "Unavailable"}, f"GitHub · {identity} · unavailable · {cached['error']}"
    return fields, f"GitHub · {identity} · cached {age}s · {cached['note']}"


def collect(cwd: Path, *, deadline: float | None = None) -> dict:
    """Collect only an already-attributed local cwd; never fetch or modify Git/PRs."""
    deadline = time.monotonic() + 3.0 if deadline is None else deadline
    # Leave the owner time to revalidate PID/start/cwd and serialize the Git snapshot.
    deadline -= 0.1
    status, raw = _git(cwd, deadline, "rev-parse", "--absolute-git-dir")
    if status != "ok":
        reason = "not a worktree or unreadable" if status == "failed" else status
        return {"workspace_source": "Git unavailable · " + reason}
    gitdir = raw.removesuffix(b"\n").decode("utf-8", "replace")
    status, raw = _git(cwd, deadline, "status", "--porcelain=v2", "--branch", "--ahead-behind", "-z", "--untracked-files=all", "--ignore-submodules=none")
    snapshot = _snapshot(raw) if status == "ok" else None
    if snapshot is None:
        return {"git_status": "Unavailable", "workspace_source": "Git status unavailable · " + (status if status != "ok" else "invalid snapshot")}
    fields, branch, commit = snapshot
    reason = "detached HEAD" if not branch else "unborn branch" if not commit else ""
    if not reason:
        status, raw = _git(cwd, deadline, "config", "--null", "--get-regexp", r"^(branch\..*\.(remote|pushremote)|remote\..*\.(url|pushurl)|remote\.pushdefault)$")
        selected = _remote_name(raw, branch) if status == "ok" else ""
        if selected:
            # Git applies insteadOf/pushInsteadOf here, unlike raw config values.
            status, raw = _git(cwd, deadline, "remote", "get-url", "--push", "--all", "--", selected)
        identity = _remote_identity(raw) if selected and status == "ok" else ""
        reason = "no GitHub remote" if status in ("ok", "failed") and not identity else status if not identity else ""
        if identity:
            network, source = _github(cwd, gitdir, identity, branch, commit, deadline)
            fields.update(network)
            fields["workspace_source"] = "Git · live working tree; " + source
    if reason:
        fields.update({"pr_status": "Unavailable · " + reason, "ci_status": "Unavailable · " + reason,
                       "workspace_source": "Git · live working tree; PR/CI unavailable · " + reason})
    return {key: clean(value) for key, value in fields.items() if clean(value)}
