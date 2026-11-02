#!/usr/bin/env python3
"""Read-only Git/GitHub diff backend for the Tern diff viewer.

Usage: backend.py <list|detail|refs|pulls>  with one JSON request object on stdin.

Writes exactly one JSON object to stdout. Failures write {"error": "..."} and exit 1.

Safety rules this file enforces:
- Never writes to the repository, its index, its object database or its worktree. Index-backed
  diffs run against a private copy of the index and a private object directory (real objects are
  reachable read-only as an alternate), so neither `git add --intent-to-add` for untracked files
  nor porcelain index refreshes touch the real repository.
- Never runs repository-configured programs: --no-ext-diff, --no-textconv, fsmonitor disabled,
  every configured filter driver blanked, submodule diffs in short form, lazy fetches disabled.
- Every revision passed to git is either a validated hex object id or resolved with
  `rev-parse --verify --end-of-options`; names starting with "-" are rejected. Paths go after
  "--" with --literal-pathspecs and NUL-separated parsing.
- GitHub access is read-only through `gh api` / `gh pr list`; no checkout or fetch happens.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator
from urllib.parse import urlparse

# ---------------------------------------------------------------------------------------------
# Limits (reported to the client in `limits` so truncation is never silent)
# ---------------------------------------------------------------------------------------------

FILE_LIMIT = 10_000  # files per comparison listing
PATCH_LIMIT = 4 * 1024 * 1024  # bytes of patch text per file
BLOB_LIMIT = 32 * 1024 * 1024  # bytes per GitHub blob download
CONTENT_HASH_LIMIT = 8 * 1024 * 1024  # larger worktree files fingerprint by stat metadata
OUTPUT_LIMIT = 64 * 1024 * 1024  # raw git listing output
BRANCH_LIMIT = 200
COMMIT_LIMIT = 100
PULL_LIMIT = 50
GITHUB_PR_FILES_MAX = 3000  # GitHub's own cap for the pull request files API
GITHUB_FILES_PER_PAGE = 100
GIT_TIMEOUT = 120
GH_TIMEOUT = 60

LIMITS = {
    "files": FILE_LIMIT,
    "patch_bytes": PATCH_LIMIT,
    "github_blob_bytes": BLOB_LIMIT,
    "github_pr_files": GITHUB_PR_FILES_MAX,
    "github_files_per_page": GITHUB_FILES_PER_PAGE,
    "worktree_content_hash_bytes": CONTENT_HASH_LIMIT,
}

SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
GH_NAME_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*$")
GH_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(?::\d+)?$")
SOURCE_KINDS = ("worktree", "unstaged", "staged", "branch", "commit", "pr")
STATUS_NAMES = {
    "A": "added",
    "D": "deleted",
    "M": "modified",
    "R": "renamed",
    "C": "copied",
    "T": "typechange",
    "U": "unmerged",
    "X": "unknown",
}
GITHUB_STATUS = {
    "added": "added",
    "removed": "deleted",
    "modified": "modified",
    "renamed": "renamed",
    "copied": "copied",
    "changed": "modified",
    "unchanged": "modified",
}
KEEP_GIT_ENV = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_CEILING_DIRECTORIES"}
SAFE_CONFIG = [
    "core.fsmonitor=false",
    "core.untrackedCache=false",
    "core.splitIndex=false",
    "core.quotePath=false",
    "core.pager=cat",
    "core.hooksPath=/dev/null",
    "color.ui=never",
    "color.diff=never",
    "diff.noprefix=false",
    "diff.mnemonicPrefix=false",
    "diff.relative=false",
    "diff.submodule=short",
    "diff.suppressBlankEmpty=false",
    "log.showSignature=false",
    "submodule.recurse=false",
    "gc.auto=0",
    "maintenance.auto=false",
]
DIFF_FLAGS = [
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--find-renames",
    "--submodule=short",
    "--ignore-submodules=dirty",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "--no-relative",
]
RENAME_LIMIT_NOTICE = (
    "Git skipped inexact rename detection because too many files changed; "
    "some renames are listed as a deletion plus an addition."
)
NON_UTF8_NOTICE = "The patch contains bytes that are not valid UTF-8; they are shown as U+FFFD."


class BackendError(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Subprocesses
# ---------------------------------------------------------------------------------------------


@dataclass
class Result:
    code: int
    out: bytes
    err: str
    truncated: bool


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in KEEP_GIT_ENV}
    for key in ("GH_DEBUG", "DEBUG", "PAGER", "GH_PAGER"):
        env.pop(key, None)
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_LAZY_FETCH="1",
        GIT_PAGER="cat",
        LC_ALL="C",
        GH_PROMPT_DISABLED="1",
        GH_NO_UPDATE_NOTIFIER="1",
        GH_PAGER="cat",
        NO_COLOR="1",
        CLICOLOR="0",
    )
    if extra:
        env.update(extra)
    return env


def run_process(
    argv: list,
    *,
    cwd: str,
    env: dict[str, str],
    stdin: bytes | None = None,
    cap: int | None = None,
    timeout: float,
) -> Result:
    """Runs argv without a shell; stdout is read up to `cap` bytes, then the process is killed."""
    name = os.fsdecode(argv[0])
    with tempfile.TemporaryFile() as errf:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=errf,
            )
        except FileNotFoundError:
            if not os.path.isdir(cwd):
                raise BackendError(f"directory does not exist: {cwd}")
            if name == "gh":
                raise BackendError("GitHub CLI (gh) is not installed or not on PATH")
            raise BackendError(f"{name} is not installed or not on PATH")
        except OSError as exc:
            raise BackendError(f"cannot run {name}: {exc.strerror or exc}")
        timed_out = threading.Event()

        def on_timeout() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, on_timeout)
        timer.daemon = True
        timer.start()
        writer = None
        if stdin is not None:
            payload = stdin

            def feed() -> None:
                try:
                    proc.stdin.write(payload)
                except OSError:
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass

            writer = threading.Thread(target=feed, daemon=True)
            writer.start()
        chunks: list[bytes] = []
        size = 0
        truncated = False
        try:
            while True:
                block = proc.stdout.read1(1 << 16)
                if not block:
                    break
                if cap is not None and size + len(block) > cap:
                    chunks.append(block[: cap - size])
                    size = cap
                    truncated = True
                    proc.kill()
                    break
                chunks.append(block)
                size += len(block)
        finally:
            proc.stdout.close()
            code = proc.wait()
            timer.cancel()
            if writer is not None:
                writer.join()
        if timed_out.is_set():
            raise BackendError(f"{name} timed out after {int(timeout)} seconds")
        errf.seek(0)
        err = errf.read(64 * 1024).decode("utf-8", "replace")
    return Result(code, b"".join(chunks), err, truncated)


def describe_failure(what: str, result: Result) -> str:
    message = result.err.strip()
    if len(message) > 2000:
        message = message[:2000] + " …"
    return f"{what} failed: {message}" if message else f"{what} failed with exit code {result.code}"


class Git:
    """git invocations with hardened configuration for one working directory or git dir."""

    def __init__(self, cwd: str, git_dir: str | None = None):
        self.cwd = cwd
        self.git_dir = git_dir
        self._filter_overrides: list[str] | None = None

    def _argv(self, args: list) -> list:
        argv: list = ["git", "--no-pager", "--literal-pathspecs"]
        if self.git_dir:
            argv.append("--git-dir=" + self.git_dir)
        for item in SAFE_CONFIG + self.filter_overrides():
            argv += ["-c", item]
        return argv + list(args)

    def filter_overrides(self) -> list[str]:
        """Blanks every configured filter driver so no clean/smudge/process program runs."""
        if self._filter_overrides is None:
            self._filter_overrides = []
            res = run_process(
                self._argv(["config", "-z", "--get-regexp", r"^filter\."]),
                cwd=self.cwd,
                env=child_env(),
                timeout=GIT_TIMEOUT,
                cap=OUTPUT_LIMIT,
            )
            names: set[str] = set()
            if res.code == 0:
                for record in res.out.split(b"\0"):
                    key = os.fsdecode(record.split(b"\n", 1)[0])
                    if key.startswith("filter.") and key.count(".") >= 2:
                        names.add(key[len("filter.") : key.rindex(".")])
            overrides: list[str] = []
            for name in sorted(names):
                overrides += [
                    f"filter.{name}.clean=",
                    f"filter.{name}.smudge=",
                    f"filter.{name}.process=",
                    f"filter.{name}.required=false",
                ]
            self._filter_overrides = overrides
        return self._filter_overrides

    def run(
        self,
        args: list,
        *,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
        cap: int = OUTPUT_LIMIT,
        ok: tuple[int, ...] = (0,),
        allow_truncate: bool = False,
    ) -> Result:
        res = run_process(
            self._argv(args), cwd=self.cwd, env=child_env(env), stdin=stdin, cap=cap, timeout=GIT_TIMEOUT
        )
        if res.truncated:
            if not allow_truncate:
                raise BackendError(f"git {args[0]} output exceeded {cap} bytes")
            return res
        if res.code not in ok:
            raise BackendError(describe_failure(f"git {args[0]}", res))
        return res


def strip_newline(data: bytes) -> bytes:
    return data[:-1] if data.endswith(b"\n") else data


# ---------------------------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------------------------


def require_dict(value, what: str) -> dict:
    if not isinstance(value, dict):
        raise BackendError(f"{what} must be an object")
    return value


def optional_str(obj: dict, key: str) -> str | None:
    value = obj.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise BackendError(f"{key} must be a string")
    return value


def require_cwd(req: dict) -> str:
    cwd = optional_str(req, "cwd")
    if cwd is None:
        raise BackendError("cwd is required")
    cwd = os.path.abspath(os.path.expanduser(cwd))
    if not os.path.isdir(cwd):
        raise BackendError(f"directory does not exist: {cwd}")
    return cwd


def require_sha(value, what: str) -> str:
    if not isinstance(value, str) or not SHA_RE.match(value):
        raise BackendError(f"{what} must be a full hexadecimal object id")
    return value


def check_revision_name(name: str) -> str:
    if not name or name.startswith("-") or any(c in name for c in "\0\n\r"):
        raise BackendError(f"invalid revision name: {name!r}")
    return name


def path_fields(key: str, raw: bytes) -> dict:
    """JSON fields for a git path; non-UTF-8 paths also carry exact bytes as base64 in <key>_raw."""
    try:
        return {key: raw.decode("utf-8")}
    except UnicodeDecodeError:
        return {key: raw.decode("utf-8", "replace"), key + "_raw": base64.b64encode(raw).decode("ascii")}


def file_path(file: dict, key: str) -> bytes | None:
    raw = file.get(key + "_raw")
    if raw is not None:
        if not isinstance(raw, str):
            raise BackendError(f"{key}_raw must be a base64 string")
        try:
            data = base64.b64decode(raw, validate=True)
        except ValueError:
            raise BackendError(f"{key}_raw is not valid base64")
    else:
        value = file.get(key)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise BackendError(f"{key} must be a string")
        data = value.encode("utf-8")
    parts = data.split(b"/")
    if not data or b"\0" in data or data.startswith(b"/") or any(p in (b"", b".", b"..") for p in parts):
        raise BackendError(f"invalid repository path in {key}")
    return data


# ---------------------------------------------------------------------------------------------
# Local repositories
# ---------------------------------------------------------------------------------------------


@dataclass
class RawEntry:
    status: str
    old: bytes
    new: bytes
    old_mode: bytes
    new_mode: bytes
    old_oid: bytes
    new_oid: bytes


def parse_raw(out: bytes) -> list[RawEntry]:
    toks = out.split(b"\0")
    entries: list[RawEntry] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        if not tok:
            i += 1
            continue
        meta = tok[1:].split(b" ") if tok.startswith(b":") else []
        if len(meta) != 5:
            raise BackendError("unexpected git diff --raw output")
        status = meta[4].decode("ascii", "replace")
        if status[:1] in ("R", "C"):
            if i + 2 >= len(toks):
                raise BackendError("truncated git diff --raw output")
            old, new = toks[i + 1], toks[i + 2]
            i += 3
        else:
            if i + 1 >= len(toks):
                raise BackendError("truncated git diff --raw output")
            old = new = toks[i + 1]
            i += 2
        entries.append(RawEntry(status, old, new, meta[0], meta[1], meta[2], meta[3]))
    return entries


def parse_numstat(out: bytes) -> dict[tuple[bytes, bytes], tuple[int, int, bool]]:
    toks = out.split(b"\0")
    stats: dict[tuple[bytes, bytes], tuple[int, int, bool]] = {}
    i = 0
    while i < len(toks):
        tok = toks[i]
        if not tok:
            i += 1
            continue
        fields = tok.split(b"\t", 2)
        if len(fields) != 3:
            raise BackendError("unexpected git diff --numstat output")
        added, deleted, rest = fields
        if rest == b"":
            if i + 2 >= len(toks):
                raise BackendError("truncated git diff --numstat output")
            old, new = toks[i + 1], toks[i + 2]
            i += 3
        else:
            old = new = rest
            i += 1
        binary = added == b"-" or deleted == b"-"
        stats[(old, new)] = (0 if binary else int(added), 0 if binary else int(deleted), binary)
    return stats


def is_null_oid(oid: bytes) -> bool:
    return not oid.strip(b"0")


def worktree_digest(root: str, rel: bytes) -> bytes:
    """Content identity of a worktree path without following any symlink (leaf or parent)."""
    parts = rel.split(b"/")
    try:
        dfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise BackendError(f"cannot open repository root: {exc.strerror}")
    try:
        for comp in parts[:-1]:
            try:
                nfd = os.open(comp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
            except OSError:
                return b"absent"
            os.close(dfd)
            dfd = nfd
        name = parts[-1]
        try:
            st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except OSError:
            return b"absent"
        if stat.S_ISLNK(st.st_mode):
            return b"link:" + os.readlink(name, dir_fd=dfd)
        if stat.S_ISDIR(st.st_mode):
            return b"dir:" + gitlink_head(os.path.join(os.fsencode(root), rel))
        if not stat.S_ISREG(st.st_mode):
            return b"special:%o" % st.st_mode
        exec_bit = b"x" if st.st_mode & 0o111 else b"-"
        if st.st_size > CONTENT_HASH_LIMIT:
            return b"meta:%s:%d:%d:%d:%d" % (exec_bit, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        except OSError:
            return b"absent"
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return b"special"
            digest = hashlib.sha256()
            while True:
                block = os.read(fd, 1 << 20)
                if not block:
                    break
                digest.update(block)
        finally:
            os.close(fd)
        return b"file:" + exec_bit + b":" + digest.hexdigest().encode()
    finally:
        os.close(dfd)


def gitlink_head(path: bytes) -> bytes:
    if not os.path.exists(os.path.join(path, b".git")):
        return b""
    res = Git(os.fsdecode(path)).run(["rev-parse", "--verify", "-q", "HEAD"], ok=(0, 1, 128))
    return res.out.strip() if res.code == 0 else b""


def local_fingerprint(entries: list[RawEntry], worktree_root: str | None) -> str:
    """Identity of the diff for one file: statuses, paths, modes, old/new content.

    Object ids identify committed/indexed content; worktree-side content (worktree_root given)
    is hashed from disk. Similarity scores are excluded so equal content gives equal identity.
    """
    digest = hashlib.sha256(b"tern-diff-local-v1\0")
    for e in entries:
        new_identity = e.new_oid
        if worktree_root is not None and e.status[:1] != "D":
            if e.new_mode == b"160000" and not is_null_oid(e.new_oid):
                new_identity = b"gitlink:" + e.new_oid
            else:
                new_identity = worktree_digest(worktree_root, e.new)
        for field in (e.status[:1].encode(), e.old, e.new, e.old_mode, e.new_mode, e.old_oid, new_identity):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return digest.hexdigest()


def split_patch_sections(patch: bytes) -> list[bytes] | None:
    starts = [m.start() for m in re.finditer(rb"(?m)^diff --git ", patch)]
    if not starts or starts[0] != 0:
        return None
    ends = starts[1:] + [len(patch)]
    return [patch[s:e] for s, e in zip(starts, ends)]


def patch_is_binary(patch: bytes) -> bool:
    for line in patch.split(b"\n"):
        if line.startswith(b"@@"):
            return False
        if line.startswith(b"Binary files ") and line.endswith(b" differ"):
            return True
        if line == b"GIT binary patch":
            return True
    return False


def decode_patch(patch: bytes) -> tuple[str, str | None]:
    try:
        return patch.decode("utf-8"), None
    except UnicodeDecodeError:
        return patch.decode("utf-8", "replace"), NON_UTF8_NOTICE


def too_large_notice(size: int | None, limit: int = PATCH_LIMIT) -> str:
    mib = limit / (1024 * 1024)
    if size is None:
        return f"Patch is larger than the {mib:g} MiB display limit and was not loaded."
    return f"Patch is {size / (1024 * 1024):.1f} MiB, larger than the {mib:g} MiB display limit, and was not loaded."


class Repo:
    def __init__(self, root: str):
        self.root = root
        self.git = Git(root)
        self._empty_tree: str | None = None

    @classmethod
    def discover(cls, cwd: str) -> "Repo":
        res = Git(cwd).run(["rev-parse", "--show-toplevel"])
        return cls(os.fsdecode(strip_newline(res.out)))

    def head(self) -> str | None:
        res = self.git.run(["rev-parse", "--verify", "-q", "HEAD^{commit}"], ok=(0, 1, 128))
        return res.out.strip().decode("ascii") if res.code == 0 else None

    def empty_tree(self) -> str:
        if self._empty_tree is None:
            res = self.git.run(["hash-object", "-t", "tree", "--stdin"], stdin=b"")
            self._empty_tree = res.out.strip().decode("ascii")
        return self._empty_tree

    def try_resolve(self, name: str) -> str | None:
        check_revision_name(name)
        res = self.git.run(
            ["rev-parse", "--verify", "-q", "--end-of-options", name + "^{commit}"], ok=(0, 1, 128)
        )
        return res.out.strip().decode("ascii") if res.code == 0 else None

    def resolve(self, name: str) -> str:
        sha = self.try_resolve(name)
        if sha is None:
            raise BackendError(f"unknown revision or not a commit: {name}")
        return sha

    def git_path(self, name: str) -> str:
        res = self.git.run(["rev-parse", "--git-path", name])
        return os.path.join(self.root, os.fsdecode(strip_newline(res.out)))

    def subject(self, sha: str) -> str:
        res = self.git.run(["log", "-n", "1", "--no-show-signature", "--format=%s", sha, "--"])
        return strip_newline(res.out).decode("utf-8", "replace")

    def untracked(self, paths: list[bytes] | None = None) -> tuple[list[bytes], bool]:
        args: list = ["ls-files", "-z", "--others", "--exclude-standard"]
        if paths:
            args += ["--", *paths]
        res = self.git.run(args, allow_truncate=True)
        items = res.out.split(b"\0")
        if res.truncated:
            items = items[:-1]  # last record may be cut
        return [p for p in items if p and not p.endswith(b"/")], res.truncated

    @contextmanager
    def scratch(self, untracked: list[bytes]) -> Iterator[dict[str, str]]:
        """Private index copy + private object dir; untracked paths added intent-to-add there."""
        tmp = tempfile.mkdtemp(prefix="tern-diff-")
        try:
            index_src = self.git_path("index")
            index = os.path.join(tmp, "index")
            if os.path.exists(index_src):
                # copy2 keeps the index mtime: git treats entries whose mtime is not older than
                # the index file as "racily clean" and compares content. A fresh mtime on the copy
                # would make same-size rewrites in the same timestamp tick look unchanged.
                shutil.copy2(index_src, index)
            objects = os.path.join(tmp, "objects")
            os.mkdir(objects)
            real_objects = os.path.abspath(self.git_path("objects"))
            env = {"GIT_INDEX_FILE": index, "GIT_OBJECT_DIRECTORY": objects}
            # intent-to-add records the empty blob; keep it (and its freshening) in the private odb.
            self.git.run(["hash-object", "-w", "--stdin"], env=env, stdin=b"")
            env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = real_objects
            if untracked:
                self.git.run(
                    ["add", "--intent-to-add", "--pathspec-from-file=-", "--pathspec-file-nul"],
                    env=env,
                    stdin=b"".join(p + b"\0" for p in untracked),
                )
            yield env
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def diff_raw(self, args: list, env: dict[str, str], paths: list[bytes] | None = None) -> tuple[list[RawEntry], str | None]:
        argv = ["diff", *DIFF_FLAGS, "--raw", "-z", "--no-abbrev", *args]
        if paths is not None:
            argv += ["--", *paths]
        res = self.git.run(argv, env=env)
        notice = RENAME_LIMIT_NOTICE if "rename detection was skipped" in res.err else None
        return parse_raw(res.out), notice

    def diff_numstat(self, args: list, env: dict[str, str]) -> dict[tuple[bytes, bytes], tuple[int, int, bool]]:
        res = self.git.run(["diff", *DIFF_FLAGS, "--numstat", "-z", *args], env=env)
        return parse_numstat(res.out)

    def diff_patch(self, args: list, env: dict[str, str], paths: list[bytes]) -> Result:
        return self.git.run(
            ["diff", *DIFF_FLAGS, "--patch", *args, "--", *paths], env=env, cap=PATCH_LIMIT * 2, allow_truncate=True
        )


def local_diff_args(kind: str, base: str | None, head: str | None) -> list:
    if kind == "worktree":
        return [base]
    if kind == "staged":
        return ["--cached", base]
    if kind == "unstaged":
        return []
    return [base, head]


def group_entries(entries: list[RawEntry]) -> list[list[int]]:
    """Indices of raw entries grouped by displayed path (unmerged paths can appear twice)."""
    order: list[bytes] = []
    groups: dict[bytes, list[int]] = {}
    for idx, e in enumerate(entries):
        if e.new not in groups:
            groups[e.new] = []
            order.append(e.new)
        groups[e.new].append(idx)
    return [groups[p] for p in order]


def build_local_files(
    entries: list[RawEntry],
    numstat: dict[tuple[bytes, bytes], tuple[int, int, bool]],
    untracked: set[bytes],
    worktree_root: str | None,
) -> list[dict]:
    files = []
    for indices in group_entries(entries):
        group = [entries[i] for i in indices]
        primary = next((e for e in group if e.status[:1] != "U"), group[0])
        letter = primary.status[:1]
        status = "unmerged" if any(e.status[:1] == "U" for e in group) else STATUS_NAMES.get(letter, "unknown")
        is_untracked = primary.new in untracked and letter in ("A", "R", "C")
        if is_untracked and status == "added":
            status = "untracked"
        entry: dict = {}
        entry.update(path_fields("path", primary.new))
        if letter in ("R", "C"):
            entry.update(path_fields("old_path", primary.old))
        added, deleted, binary = numstat.get((primary.old, primary.new), (0, 0, False))
        entry.update(status=status, additions=added, deletions=deleted)
        if binary:
            entry["binary"] = True
        if is_untracked:
            entry["untracked"] = True
        entry["fingerprint"] = local_fingerprint(group, worktree_root)
        files.append(entry)
    return files


def default_branch_base(repo: Repo, head_name: str, head_sha: str) -> tuple[str, str]:
    candidates: list[str] = []
    for remote in ("upstream", "origin"):
        res = repo.git.run(["symbolic-ref", "-q", f"refs/remotes/{remote}/HEAD"], ok=(0, 1, 128))
        target = strip_newline(res.out).decode("utf-8", "replace")
        if res.code == 0 and target.startswith("refs/remotes/"):
            candidates.append(target[len("refs/remotes/") :])
    candidates += ["main", "master", "origin/main", "origin/master", "upstream/main", "upstream/master", "trunk"]
    res = repo.git.run(
        # head_name was validated by check_revision_name (resolved above); rev-parse without
        # --verify would echo --end-of-options back, so it is not used here.
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", head_name + "@{upstream}"],
        ok=(0, 1, 128),
    )
    if res.code == 0 and res.out.strip():
        candidates.append(strip_newline(res.out).decode("utf-8", "replace"))
    fallback: tuple[str, str] | None = None
    seen: set[str] = set()
    for name in candidates:
        if name in seen or name == head_name:
            continue
        seen.add(name)
        sha = repo.try_resolve(name)
        if sha is None:
            continue
        if sha != head_sha:
            return name, sha
        fallback = fallback or (name, sha)
    if fallback:
        return fallback
    raise BackendError("could not determine a base branch (no upstream, main or master); choose a base explicitly")


def list_local(cwd: str, source: dict) -> dict:
    kind = source["kind"]
    repo = Repo.discover(cwd)
    root = repo.root
    notices: list[str] = []
    truncated = False
    untracked: list[bytes] = []
    worktree_root = root if kind in ("worktree", "unstaged") else None
    out_source: dict = {"kind": kind}

    if kind in ("worktree", "staged", "unstaged"):
        head = repo.head()
        short = head[:12] if head else "unborn HEAD"
        if kind == "worktree":
            base, head_label = head or repo.empty_tree(), "worktree"
            label = f"Working tree vs HEAD ({short})"
        elif kind == "staged":
            base, head_label = head or repo.empty_tree(), "index"
            label = f"Staged vs HEAD ({short})"
        else:
            base, head_label = "index", "worktree"
            label = "Unstaged (working tree vs index)"
        ident = f"{kind}:{root}"
        if kind != "staged":
            untracked, cut = repo.untracked()
            if len(untracked) > FILE_LIMIT or cut:
                truncated = True
                notices.append(
                    f"More than {FILE_LIMIT} untracked files; only the first {FILE_LIMIT} are included."
                )
                untracked = untracked[:FILE_LIMIT]
        args = local_diff_args(kind, base if kind != "unstaged" else None, None)
    elif kind == "branch":
        head_name = optional_str(source, "head") or "HEAD"
        head = repo.resolve(head_name)
        base_name = optional_str(source, "base")
        if base_name:
            base_tip = repo.resolve(base_name)
        else:
            base_name, base_tip = default_branch_base(repo, head_name, head)
        mb = repo.git.run(["merge-base", base_tip, head], ok=(0, 1))
        if mb.code != 0:
            raise BackendError(f"{base_name} and {head_name} have no common ancestor")
        base = mb.out.strip().decode("ascii")
        head_label = head
        label = f"{base_name}...{head_name}"
        ident = f"branch:{root}:{base_name}...{head_name}"
        out_source.update(base=base_name, head=head_name, base_tip=base_tip)
        args = [base, head]
    elif kind == "commit":
        name = optional_str(source, "head") or optional_str(source, "base") or "HEAD"
        head = repo.resolve(name)
        parent = repo.try_resolve(head + "^1")
        base = parent or repo.empty_tree()
        head_label = head
        label = f"{head[:12]} {repo.subject(head)}"
        if parent is None:
            label += " (root commit)"
        ident = f"commit:{root}:{head}"
        out_source.update(head=name)
        args = [base, head]
    else:
        raise BackendError(f"unsupported source kind: {kind}")

    with repo.scratch(untracked) as env:
        entries, rename_notice = repo.diff_raw(args, env)
        numstat = repo.diff_numstat(args, env)
    if rename_notice:
        notices.append(rename_notice)
    files = build_local_files(entries, numstat, set(untracked), worktree_root)
    if len(files) > FILE_LIMIT:
        truncated = True
        notices.append(f"{len(files)} files changed; only the first {FILE_LIMIT} are listed.")
        files = files[:FILE_LIMIT]
    result = {
        "root": root,
        "id": ident,
        "label": label,
        "base": base,
        "head": head_label,
        "source": out_source,
        "files": files,
        "truncated": truncated,
        "limits": LIMITS,
    }
    if notices:
        result["notice"] = " ".join(notices)
    return result


def detail_local(comparison: dict, file: dict) -> dict:
    source = require_dict(comparison.get("source"), "comparison.source")
    kind = source.get("kind")
    root = optional_str(comparison, "root")
    if root is None or not os.path.isdir(root):
        raise BackendError("comparison.root is missing or not a directory")
    base = comparison.get("base")
    head = comparison.get("head")
    if kind in ("worktree", "staged", "branch", "commit"):
        require_sha(base, "comparison.base")
    if kind in ("branch", "commit"):
        require_sha(head, "comparison.head")
    new = file_path(file, "path")
    if new is None:
        raise BackendError("file.path is required")
    old = file_path(file, "old_path") or new
    paths = [old] if old == new else [old, new]
    repo = Repo(root)
    worktree = kind in ("worktree", "unstaged")
    args = local_diff_args(kind, base, head)
    untracked = repo.untracked(paths)[0] if worktree else []

    def read_entries(env: dict[str, str]) -> tuple[list[RawEntry], list[int], str]:
        entries, _ = repo.diff_raw(args, env, paths)
        picked = [i for i, e in enumerate(entries) if e.new == new]
        return entries, picked, local_fingerprint([entries[i] for i in picked], repo.root if worktree else None)

    with repo.scratch(untracked) as env:
        for _attempt in range(3):
            entries, picked, fingerprint = read_entries(env)
            patch_res = repo.diff_patch(args, env, paths)
            if not worktree or read_entries(env)[2] == fingerprint:
                break
        else:
            raise BackendError("the file kept changing while it was being read; try again")

    result: dict = {}
    result.update(path_fields("path", new))
    result["fingerprint"] = fingerprint
    notices: list[str] = []
    if patch_res.truncated:
        result.update(patch="", binary=False, truncated=True)
        notices.append(too_large_notice(None))
    else:
        if patch_res.code != 0:
            raise BackendError(describe_failure("git diff", patch_res))
        patch = patch_res.out
        sections = split_patch_sections(patch)
        if sections is not None and len(sections) == len(entries):
            patch = b"".join(sections[i] for i in picked)
        if len(patch) > PATCH_LIMIT:
            result.update(patch="", binary=patch_is_binary(patch), truncated=True)
            notices.append(too_large_notice(len(patch)))
        else:
            text, notice = decode_patch(patch)
            result.update(patch=text, binary=patch_is_binary(patch), truncated=False)
            if notice:
                notices.append(notice)
            if not picked:
                notices.append("This file no longer differs; refresh the file list.")
    if notices:
        result["notice"] = " ".join(notices)
    return result


def refs(req: dict) -> dict:
    repo = Repo.discover(require_cwd(req))
    res = repo.git.run(
        [
            "for-each-ref",
            "--sort=-committerdate",
            f"--count={BRANCH_LIMIT + 1}",
            "--format=%(refname)%00%(symref)",
            "refs/heads",
            "refs/remotes",
        ]
    )
    branches = []
    for line in res.out.split(b"\n"):
        if not line:
            continue
        refname, _, symref = line.partition(b"\0")
        if symref:
            continue
        name = refname.decode("utf-8", "replace")
        for prefix in ("refs/heads/", "refs/remotes/"):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        branches.append(name)
    commits = []
    head = repo.head()
    if head:
        log = repo.git.run(
            ["log", "--no-show-signature", f"-n{COMMIT_LIMIT + 1}", "--format=tformat:%H%x00%s", head, "--"]
        )
        for line in log.out.split(b"\n"):
            if not line:
                continue
            sha, _, subject = line.partition(b"\0")
            commits.append({"sha": sha.decode("ascii"), "subject": subject.decode("utf-8", "replace")})
    return {
        "branches": branches[:BRANCH_LIMIT],
        "commits": commits[:COMMIT_LIMIT],
        "branches_limit": BRANCH_LIMIT,
        "commits_limit": COMMIT_LIMIT,
        "branches_truncated": len(branches) > BRANCH_LIMIT,
        "commits_truncated": len(commits) > COMMIT_LIMIT,
    }


# ---------------------------------------------------------------------------------------------
# GitHub pull requests (read-only through gh)
# ---------------------------------------------------------------------------------------------


@dataclass
class PrSpec:
    number: int
    host: str | None = None
    owner: str | None = None
    repo: str | None = None


def parse_pr_spec(spec: str) -> PrSpec:
    """Accepts 123, #123, owner/repo#123 or https://host/owner/repo/pull/123[/...]."""
    spec = spec.strip()
    m = re.fullmatch(r"#?(\d+)", spec)
    if m:
        return PrSpec(int(m.group(1)))
    m = re.fullmatch(r"([^/\s#]+)/([^/\s#]+)#(\d+)", spec)
    if m and GH_NAME_RE.match(m.group(1)) and GH_NAME_RE.match(m.group(2)):
        return PrSpec(int(m.group(3)), None, m.group(1), m.group(2))
    url = urlparse(spec)
    if url.scheme in ("http", "https") and url.netloc:
        parts = [p for p in url.path.split("/") if p]
        host = url.netloc.lower()
        if host == "www.github.com":
            host = "github.com"
        if (
            len(parts) >= 4
            and parts[2] in ("pull", "pulls")
            and parts[3].isdigit()
            and GH_NAME_RE.match(parts[0])
            and GH_NAME_RE.match(parts[1])
            and GH_HOST_RE.match(host)
        ):
            repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
            return PrSpec(int(parts[3]), host, parts[0], repo)
    raise BackendError(
        f"unrecognized pull request {spec!r}; use a number, owner/repo#number or a pull request URL"
    )


def gh_run(args: list[str], cwd: str, *, stdin: bytes | None = None, cap: int = OUTPUT_LIMIT) -> bytes:
    res = run_process(["gh", *args], cwd=cwd, env=child_env(), stdin=stdin, cap=cap, timeout=GH_TIMEOUT)
    if res.truncated:
        raise BackendError(f"GitHub response exceeded {cap} bytes")
    if res.code != 0:
        raise BackendError(describe_failure("GitHub request (gh " + " ".join(a for a in args[:1]) + ")", res))
    return res.out


def gh_json(args: list[str], cwd: str, *, stdin: bytes | None = None, cap: int = OUTPUT_LIMIT):
    out = gh_run(args, cwd, stdin=stdin, cap=cap)
    try:
        return json.loads(out)
    except ValueError:
        raise BackendError("unexpected non-JSON response from GitHub")


def gh_api(endpoint: str, host: str | None, cwd: str, *, paginate: bool = False, cap: int = OUTPUT_LIMIT):
    args = ["api"]
    if host:
        args += ["--hostname", host]
    args += ["-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28"]
    if paginate:
        args += ["--paginate", "--slurp"]
    return gh_json(args + [endpoint], cwd, cap=cap)


def flatten_pages(pages) -> list:
    if not isinstance(pages, list):
        raise BackendError("unexpected GitHub pagination response")
    if pages and all(isinstance(p, list) for p in pages):
        return [item for page in pages for item in page]
    return pages


def pr_fingerprint(file: dict, merge_base: str) -> str:
    """Identity from immutable API data: new blob id plus GitHub's diff text hash.

    The patch text with the new content determines the old content; when GitHub omits the
    patch (binary, mode-only or very large files) the pinned merge base stands in for it.
    """
    fields = [
        "tern-diff-gh-v1",
        str(file.get("status") or ""),
        str(file.get("old_path") or ""),
        str(file.get("path") or ""),
        str(file.get("blob_sha") or ""),
        str(file.get("additions") or 0),
        str(file.get("deletions") or 0),
        str(file.get("patch_sha256") or "base:" + merge_base),
    ]
    digest = hashlib.sha256()
    for field in fields:
        data = field.encode("utf-8")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def pr_files_to_list(pages, merge_base: str) -> list[dict]:
    files = []
    for item in flatten_pages(pages):
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            raise BackendError("unexpected GitHub pull request file entry")
        status = GITHUB_STATUS.get(str(item.get("status")), "modified")
        entry: dict = {"path": item["filename"]}
        previous = item.get("previous_filename")
        if isinstance(previous, str) and previous and previous != item["filename"]:
            entry["old_path"] = previous
            if status != "copied":
                status = "renamed"
        entry.update(
            status=status,
            additions=int(item.get("additions") or 0),
            deletions=int(item.get("deletions") or 0),
        )
        if isinstance(item.get("sha"), str):
            entry["blob_sha"] = item["sha"]
        patch = item.get("patch")
        if isinstance(patch, str):
            entry["patch_sha256"] = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        entry["fingerprint"] = pr_fingerprint(entry, merge_base)
        files.append(entry)
    return files


def fetch_pr(spec: PrSpec, cwd: str) -> tuple[dict, str, str, str]:
    if spec.owner:
        pr = gh_api(f"repos/{spec.owner}/{spec.repo}/pulls/{spec.number}", spec.host, cwd)
    else:
        pr = gh_api(f"repos/{{owner}}/{{repo}}/pulls/{spec.number}", None, cwd)
    try:
        full_name = pr["base"]["repo"]["full_name"]
        owner, name = full_name.split("/", 1)
        host = spec.host or (urlparse(pr["html_url"]).hostname or "github.com").lower()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise BackendError("unexpected GitHub pull request response")
    if not (GH_NAME_RE.match(owner) and GH_NAME_RE.match(name) and GH_HOST_RE.match(host)):
        raise BackendError(f"unexpected repository name from GitHub: {full_name}")
    return pr, host, owner, name


def pr_shas(pr: dict) -> tuple[str, str]:
    try:
        return require_sha(pr["base"]["sha"], "pull request base sha"), require_sha(pr["head"]["sha"], "pull request head sha")
    except (KeyError, TypeError):
        raise BackendError("unexpected GitHub pull request response")


def list_pr(cwd: str, source: dict) -> dict:
    spec_text = optional_str(source, "pr")
    if spec_text is None:
        raise BackendError("source.pr is required for pull requests")
    spec = parse_pr_spec(spec_text)
    try:
        root = Repo.discover(cwd).root
    except BackendError:
        if spec.owner is None:
            raise
        root = cwd
    pr, host, owner, name = fetch_pr(spec, cwd)
    number = spec.number
    for _attempt in range(3):
        base_sha, head_sha = pr_shas(pr)
        pages = gh_api(
            f"repos/{owner}/{name}/pulls/{number}/files?per_page={GITHUB_FILES_PER_PAGE}", host, cwd, paginate=True
        )
        latest = gh_api(f"repos/{owner}/{name}/pulls/{number}", host, cwd)
        if pr_shas(latest) == (base_sha, head_sha):
            pr = latest
            break
        pr = latest
    else:
        raise BackendError("the pull request kept changing while it was being loaded; try again")
    compare = gh_api(f"repos/{owner}/{name}/compare/{base_sha}...{head_sha}?per_page=1", host, cwd)
    try:
        merge_base = require_sha(compare["merge_base_commit"]["sha"], "merge base")
    except (KeyError, TypeError):
        raise BackendError("unexpected GitHub compare response")
    files = pr_files_to_list(pages, merge_base)
    changed = int(pr.get("changed_files") or len(files))
    truncated = changed > len(files)
    result = {
        "root": root,
        "id": f"pr:{host}/{owner}/{name}#{number}",
        "label": f"#{number} {pr.get('title') or ''}".rstrip(),
        "base": merge_base,
        "head": head_sha,
        "source": {"kind": "pr", "pr": spec_text},
        "files": files,
        "truncated": truncated,
        "limits": LIMITS,
        "pr": {
            "host": host,
            "owner": owner,
            "repo": name,
            "number": number,
            "url": pr.get("html_url"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "base_ref": (pr.get("base") or {}).get("ref"),
            "head_ref": (pr.get("head") or {}).get("ref"),
            "base_sha": base_sha,
            "head_sha": head_sha,
            "merge_base": merge_base,
            "changed_files": changed,
        },
    }
    if truncated:
        result["notice"] = (
            f"GitHub lists at most {GITHUB_PR_FILES_MAX} files for a pull request; "
            f"showing {len(files)} of {changed} changed files."
        )
    return result


GQL_ENTRY = "name mode oid type size"
KNOWN_MODES = {"100644", "100755", "120000", "160000", "040000"}


def gql_mode(mode) -> str:
    """GitHub reports TreeEntry.mode as an integer (33188 == 0o100644); accept octal-looking too."""
    if isinstance(mode, int):
        candidates = [format(mode, "o"), str(mode)]
    elif isinstance(mode, str):
        candidates = [mode]
    else:
        candidates = []
    for c in candidates:
        c = c.zfill(6)
        if c in KNOWN_MODES:
            return c
    raise BackendError(f"unexpected file mode from GitHub: {mode!r}")


def gh_tree_entries(host: str, owner: str, name: str, cwd: str, lookups: list[tuple[str, str]]) -> list[dict | None]:
    decls = ["$owner: String!", "$name: String!"]
    fields = []
    variables: dict[str, str] = {"owner": owner, "name": name}
    for i, (sha, path) in enumerate(lookups):
        directory = path.rpartition("/")[0]
        variables[f"v{i}"] = f"{sha}:{directory}" if directory else sha
        decls.append(f"$v{i}: String!")
        fields.append(
            f"e{i}: object(expression: $v{i}) {{ ... on Tree {{ entries {{ {GQL_ENTRY} }} }} "
            f"... on Commit {{ tree {{ entries {{ {GQL_ENTRY} }} }} }} }}"
        )
    query = f"query({', '.join(decls)}) {{ repository(owner: $owner, name: $name) {{ {' '.join(fields)} }} }}"
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    data = gh_json(["api", "--hostname", host, "graphql", "--input", "-"], cwd, stdin=body)
    if not isinstance(data, dict):
        raise BackendError("unexpected GitHub GraphQL response")
    errors = data.get("errors")
    if errors:
        messages = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
        raise BackendError(f"GitHub GraphQL error: {messages}")
    repository = (data.get("data") or {}).get("repository")
    if repository is None:
        raise BackendError(f"repository {owner}/{name} not found on {host}")
    found: list[dict | None] = []
    for i, (_sha, path) in enumerate(lookups):
        obj = repository.get(f"e{i}") or {}
        entries = obj.get("entries")
        if entries is None:
            entries = (obj.get("tree") or {}).get("entries") or []
        leaf = path.rpartition("/")[2]
        found.append(next((e for e in entries if isinstance(e, dict) and e.get("name") == leaf), None))
    return found


def gh_blob(host: str, owner: str, name: str, oid: str, cwd: str) -> bytes:
    data = gh_api(f"repos/{owner}/{name}/git/blobs/{oid}", host, cwd, cap=BLOB_LIMIT * 4 // 3 + (1 << 20))
    if not isinstance(data, dict) or data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise BackendError(f"unexpected GitHub blob response for {oid}")
    try:
        return base64.b64decode(data["content"])
    except ValueError:
        raise BackendError(f"GitHub blob {oid} is not valid base64")


@dataclass
class TreeItem:
    path: str
    mode: str
    oid: str
    data: bytes | None  # None for gitlinks


def build_tree_patch(old: list[TreeItem], new: list[TreeItem], *, copies: bool = False) -> Result:
    """Exact git patch between two synthetic trees, built in a private temporary repository.

    Blob contents are hashed into the scratch repository and must reproduce the advertised
    object ids, so the patch is verified to describe exactly the pinned revisions.
    """
    object_format = "sha256" if any(len(i.oid) == 64 for i in old + new) else "sha1"
    with tempfile.TemporaryDirectory(prefix="tern-diff-pr-") as tmp:
        git_dir = os.path.join(tmp, "repo.git")
        Git(tmp).run(["init", "-q", "--bare", "--template=", f"--object-format={object_format}", git_dir])
        git = Git(tmp, git_dir)
        written: set[str] = set()
        for item in old + new:
            if item.data is None or item.oid in written:
                continue
            res = git.run(["hash-object", "-w", "--stdin", "-t", "blob"], stdin=item.data)
            if res.out.strip().decode("ascii") != item.oid:
                raise BackendError(f"content downloaded for {item.path} does not match GitHub object {item.oid}")
            written.add(item.oid)
        trees = []
        for side, items in (("old", old), ("new", new)):
            env = {"GIT_INDEX_FILE": os.path.join(tmp, f"{side}.index")}
            if items:
                info = b"".join(f"{i.mode} {i.oid}\t".encode() + i.path.encode("utf-8") + b"\0" for i in items)
                git.run(["update-index", "-z", "--index-info"], env=env, stdin=info)
            res = git.run(["write-tree", "--missing-ok"], env=env)
            trees.append(res.out.strip().decode("ascii"))
        flags = ["-C", "--find-copies-harder"] if copies else []
        return git.run(
            ["diff-tree", "-r", "--patch", *DIFF_FLAGS, *flags, trees[0], trees[1]],
            cap=PATCH_LIMIT + 1,
            allow_truncate=True,
        )


def detail_pr(comparison: dict, file: dict) -> dict:
    meta = require_dict(comparison.get("pr"), "comparison.pr")
    host = optional_str(meta, "host") or ""
    owner = optional_str(meta, "owner") or ""
    name = optional_str(meta, "repo") or ""
    if not (GH_HOST_RE.match(host) and GH_NAME_RE.match(owner) and GH_NAME_RE.match(name)):
        raise BackendError("comparison.pr does not identify a GitHub repository")
    merge_base = require_sha(meta.get("merge_base"), "comparison.pr.merge_base")
    head = require_sha(meta.get("head_sha"), "comparison.pr.head_sha")
    new_bytes = file_path(file, "path")
    if new_bytes is None:
        raise BackendError("file.path is required")
    new = new_bytes.decode("utf-8", "replace")
    old_bytes = file_path(file, "old_path")
    old = old_bytes.decode("utf-8", "replace") if old_bytes else new
    status = file.get("status")
    cwd = optional_str(comparison, "root") or os.getcwd()
    if not os.path.isdir(cwd):
        cwd = os.getcwd()

    lookups: list[tuple[str, str, str]] = []  # (side, sha, path)
    if status != "added":
        lookups.append(("old", merge_base, old))
    if status != "deleted":
        lookups.append(("new", head, new))
    if status == "copied":
        lookups.append(("new", head, old))
    entries = gh_tree_entries(host, owner, name, cwd, [(sha, path) for _side, sha, path in lookups])
    if not any(entries):
        raise BackendError(f"{new} was not found at the pinned pull request revisions on GitHub")

    result: dict = {"path": file.get("path"), "fingerprint": pr_fingerprint(file, merge_base)}
    sides: dict[str, list[TreeItem]] = {"old": [], "new": []}
    for (side, _sha, path), entry in zip(lookups, entries):
        if entry is None:
            continue
        mode = gql_mode(entry.get("mode"))
        oid = require_sha(entry.get("oid"), "GitHub object id")
        kind = entry.get("type")
        if kind == "tree":
            raise BackendError(f"{path} is a directory at {_sha[:12]}")
        data = None
        if kind == "blob":
            size = entry.get("size")
            if isinstance(size, int) and size > BLOB_LIMIT:
                result.update(patch="", binary=False, truncated=True)
                result["notice"] = (
                    f"{path} is {size / (1024 * 1024):.1f} MiB at {_sha[:12]}, larger than the "
                    f"{BLOB_LIMIT // (1024 * 1024)} MiB GitHub download limit; the patch was not loaded."
                )
                return result
            data = gh_blob(host, owner, name, oid, cwd)
        sides[side].append(TreeItem(path, mode, oid, data))
    res = build_tree_patch(sides["old"], sides["new"], copies=status == "copied")
    if res.truncated or len(res.out) > PATCH_LIMIT:
        result.update(patch="", binary=False, truncated=True, notice=too_large_notice(None))
        return result
    text, notice = decode_patch(res.out)
    result.update(patch=text, binary=patch_is_binary(res.out), truncated=False)
    if notice:
        result["notice"] = notice
    return result


def pulls(req: dict) -> dict:
    cwd = require_cwd(req)
    data = gh_json(
        ["pr", "list", "--state", "open", "--limit", str(PULL_LIMIT + 1), "--json", "number,title,url"], cwd
    )
    if not isinstance(data, list):
        raise BackendError("unexpected response from gh pr list")
    items = [
        {"number": int(p["number"]), "title": str(p.get("title") or ""), "url": str(p.get("url") or "")}
        for p in data
        if isinstance(p, dict) and "number" in p
    ]
    return {"pulls": items[:PULL_LIMIT], "limit": PULL_LIMIT, "truncated": len(items) > PULL_LIMIT}


# ---------------------------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------------------------


def op_list(req: dict) -> dict:
    cwd = require_cwd(req)
    source = req.get("source")
    source = {"kind": "worktree"} if source is None else require_dict(source, "source")
    kind = source.get("kind") or "worktree"
    if kind not in SOURCE_KINDS:
        raise BackendError(f"unknown source kind: {kind!r}")
    source = {**source, "kind": kind}
    if kind == "pr":
        return list_pr(cwd, source)
    return list_local(cwd, source)


def op_detail(req: dict) -> dict:
    comparison = require_dict(req.get("comparison"), "comparison")
    file = require_dict(req.get("file"), "file")
    source = require_dict(comparison.get("source"), "comparison.source")
    kind = source.get("kind")
    if kind == "pr":
        return detail_pr(comparison, file)
    if kind not in SOURCE_KINDS:
        raise BackendError(f"unknown source kind: {kind!r}")
    return detail_local(comparison, file)


OPERATIONS: dict[str, Callable[[dict], dict]] = {
    "list": op_list,
    "detail": op_detail,
    "refs": refs,
    "pulls": pulls,
}


def emit(obj: dict) -> None:
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8", "replace"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in OPERATIONS:
        emit({"error": f"usage: backend.py <{'|'.join(OPERATIONS)}> < request.json"})
        return 1
    try:
        try:
            req = json.loads(sys.stdin.buffer.read() or b"{}")
        except ValueError as exc:
            raise BackendError(f"request is not valid JSON: {exc}")
        result = OPERATIONS[argv[1]](require_dict(req, "request"))
    except BackendError as exc:
        emit({"error": str(exc)})
        return 1
    except Exception as exc:  # report, never crash with a traceback on stdout
        emit({"error": f"internal error: {type(exc).__name__}: {exc}"})
        return 1
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
