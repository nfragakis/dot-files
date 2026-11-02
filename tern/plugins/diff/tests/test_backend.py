"""Consumer-level regression tests for backend.py using real temporary Git repositories.

Run from the project root: python3 -m unittest discover -s tests
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend.py"
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402

FAKE_GH = r'''
import base64, json, os, re, subprocess, sys

REPO = os.environ["FAKE_GH_REPO"]
with open(os.environ["FAKE_GH_STATE"]) as fh:
    STATE = json.load(fh)
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, check=True).stdout


def try_git(*args):
    res = subprocess.run(["git", "-C", REPO, *args], capture_output=True)
    return res.stdout if res.returncode == 0 else None


def fail(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def out(obj):
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


if STATE.get("fail_auth"):
    fail("To get started with GitHub CLI, please run:  gh auth login", 4)

args = sys.argv[1:]
if args[:2] == ["pr", "list"]:
    limit = int(args[args.index("--limit") + 1])
    out([{"number": n, "title": f"PR {n}", "url": f"https://github.com/o/r/pull/{n}"} for n in range(1, 61)][:limit])
if not args or args[0] != "api":
    fail("fake gh: unsupported command " + " ".join(args))

endpoint = None
paginate = slurp = False
body = None
i = 1
while i < len(args):
    a = args[i]
    if a in ("-X", "--method", "-f", "-F", "--field", "--raw-field"):
        fail("fake gh: write-capable flag used: " + a)
    if a in ("--hostname", "-H", "--header", "--input", "--jq", "-q"):
        if a == "--input":
            body = sys.stdin.read() if args[i + 1] == "-" else open(args[i + 1]).read()
        i += 2
        continue
    if a == "--paginate":
        paginate = True
    elif a == "--slurp":
        slurp = True
    else:
        endpoint = a
    i += 1
endpoint = endpoint.replace("{owner}/{repo}", "o/r")
base = git("rev-parse", STATE["base"]).decode().strip()
head = git("rev-parse", STATE["head"]).decode().strip()
merge_base = git("merge-base", base, head).decode().strip()
number = STATE["number"]


def files():
    raw = git("diff", "--no-color", "--no-ext-diff", "-M", "--raw", "-z", "--no-abbrev", merge_base, head)
    toks = raw.split(b"\0")
    result = []
    j = 0
    while j < len(toks) - 1:
        meta = toks[j][1:].split(b" ")
        letter = meta[4].decode()[0]
        if letter == "R":
            old, new = toks[j + 1].decode(), toks[j + 2].decode()
            j += 3
        else:
            old = new = toks[j + 1].decode()
            j += 2
        numstat = git("diff", "--numstat", "-M", merge_base, head, "--", old, new).decode().split("\t")
        patch = git("diff", "--no-color", "--no-ext-diff", "-M", merge_base, head, "--", old, new).decode("utf-8", "replace")
        entry = {
            "filename": new,
            "status": {"A": "added", "D": "removed", "M": "modified", "R": "renamed", "T": "changed"}[letter],
            "additions": 0 if numstat[0] == "-" else int(numstat[0]),
            "deletions": 0 if numstat[1] == "-" else int(numstat[1]),
            "sha": (meta[2] if letter == "D" else meta[3]).decode(),
        }
        if old != new:
            entry["previous_filename"] = old
        if "\n@@" in patch:
            entry["patch"] = patch[patch.index("\n@@") + 1 :]
        result.append(entry)
    return result


def pr_json():
    return {
        "number": number,
        "title": STATE["title"],
        "state": "open",
        "html_url": f"https://github.com/o/r/pull/{number}",
        "base": {"sha": base, "ref": STATE["base"], "repo": {"full_name": "o/r"}},
        "head": {"sha": head, "ref": STATE["head"], "repo": {"full_name": "fork/r"}},
        "changed_files": STATE.get("changed_files") or len(files()),
    }


if re.fullmatch(r"repos/o/r/pulls/\d+", endpoint):
    out(pr_json())
if re.fullmatch(r"repos/o/r/pulls/\d+/files\?per_page=100", endpoint):
    if not (paginate and slurp):
        fail("fake gh: files endpoint must be requested with --paginate --slurp")
    fs = files()
    size = STATE.get("page_size", 100)
    out([fs[k : k + size] for k in range(0, len(fs), size)] or [[]])
m = re.fullmatch(r"repos/o/r/compare/([0-9a-f]+)\.\.\.([0-9a-f]+)\?per_page=1", endpoint)
if m:
    out({"merge_base_commit": {"sha": git("merge-base", m.group(1), m.group(2)).decode().strip()}})
m = re.fullmatch(r"repos/o/r/git/blobs/([0-9a-f]+)", endpoint)
if m:
    data = git("cat-file", "blob", m.group(1))
    if STATE.get("corrupt_blob"):
        data += b"tampered"
    out({"sha": m.group(1), "size": len(data), "encoding": "base64", "content": base64.encodebytes(data).decode()})
if endpoint == "graphql":
    request = json.loads(body)
    variables = request["variables"]
    if variables["owner"] != "o" or variables["name"] != "r":
        fail("fake gh: wrong repository")
    repository = {}
    for alias, var in re.findall(r"(e\d+): object\(expression: \$(v\d+)\)", request["query"]):
        expr = variables[var]
        listing = try_git("ls-tree", "-z", "-l", expr if ":" in expr else expr + "^{tree}")
        if listing is None:
            repository[alias] = None
            continue
        entries = []
        for rec in listing.split(b"\0"):
            if not rec:
                continue
            meta, name = rec.split(b"\t", 1)
            mode, kind, oid, size = meta.split()
            entries.append({
                "name": name.decode(),
                "mode": int(mode, 8),
                "oid": oid.decode(),
                "type": kind.decode(),
                "size": None if size == b"-" else int(size),
            })
        repository[alias] = {"entries": entries} if ":" in expr else {"tree": {"entries": entries}}
    out({"data": {"repository": repository}})
fail(f"gh: Not Found (HTTP 404) {endpoint}")
'''


def snapshot(root: Path) -> dict:
    """Every path under root (including .git) with mode, size, mtime and content hash."""
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            rel = os.path.relpath(path, root)
            if stat.S_ISLNK(st.st_mode):
                snap[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(st.st_mode):
                snap[rel] = ("dir", st.st_mode, st.st_mtime_ns)
            else:
                with open(path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                snap[rel] = ("file", st.st_mode, st.st_size, st.st_mtime_ns, digest)
    return snap


class BackendTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tern-diff-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        home = self.tmp / "home"
        home.mkdir()
        config = self.tmp / "gitconfig"
        config.write_text(
            "[user]\n\tname = Test\n\temail = test@example.com\n"
            "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            HOME=str(home),
            XDG_CONFIG_HOME=str(home / ".config"),
            GIT_CONFIG_GLOBAL=str(config),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=str(self.tmp.parent),
            GIT_AUTHOR_DATE="2024-01-01T00:00:00Z",
            GIT_COMMITTER_DATE="2024-01-01T00:00:00Z",
        )
        self.env = env

    # -- helpers ---------------------------------------------------------------------------

    def git(self, repo: Path, *args, stdin: bytes | None = None) -> str:
        res = subprocess.run(["git", *args], cwd=repo, env=self.env, input=stdin, capture_output=True)
        if res.returncode != 0:
            self.fail(f"git {args} failed: {res.stderr.decode()}")
        return res.stdout.decode("utf-8", "replace")

    def make_repo(self, name: str = "repo") -> Path:
        repo = self.tmp / name
        repo.mkdir()
        self.git(repo, "init", "-q")
        return repo

    def write(self, repo: Path, rel, content, mode: int | None = None) -> None:
        path = os.path.join(os.fsencode(repo), os.fsencode(rel))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content.encode() if isinstance(content, str) else content)
        if mode is not None:
            os.chmod(path, mode)

    def commit(self, repo: Path, message: str) -> str:
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "--allow-empty", "-m", message)
        return self.git(repo, "rev-parse", "HEAD").strip()

    def call(self, op: str, request, *, expect_error: bool = False) -> dict:
        res = subprocess.run(
            [sys.executable, str(BACKEND), op],
            input=json.dumps(request).encode(),
            env=self.env,
            capture_output=True,
            timeout=120,
        )
        try:
            data = json.loads(res.stdout)
        except ValueError:
            self.fail(f"non-JSON output: {res.stdout!r} stderr={res.stderr!r}")
        if expect_error:
            self.assertNotEqual(res.returncode, 0, data)
            self.assertIsInstance(data.get("error"), str, data)
        else:
            self.assertEqual(res.returncode, 0, data)
            self.assertNotIn("error", data)
        return data

    def listing(self, repo: Path, kind: str = "worktree", **source) -> dict:
        return self.call("list", {"cwd": str(repo), "source": {"kind": kind, **source}})

    def detail(self, comparison: dict, file: dict) -> dict:
        return self.call("detail", {"comparison": comparison, "file": file})

    @staticmethod
    def by_path(comparison: dict) -> dict:
        return {f["path"]: f for f in comparison["files"]}

    def empty_tree(self, repo: Path) -> str:
        return self.git(repo, "hash-object", "-t", "tree", "--stdin", stdin=b"").strip()


class LocalComparisonTests(BackendTestCase):
    def test_worktree_staged_unstaged_and_untracked(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "one\n")
        self.write(repo, "b.txt", "keep\n")
        head = self.commit(repo, "init")
        self.write(repo, "a.txt", "one\ntwo\n")
        self.write(repo, "c.txt", "new\n")
        self.git(repo, "add", "c.txt")
        self.write(repo, "d.txt", "untracked\n")

        worktree = self.listing(repo)
        self.assertEqual(worktree["root"], str(repo))
        self.assertEqual(worktree["base"], head)
        self.assertEqual(worktree["head"], "worktree")
        files = self.by_path(worktree)
        self.assertEqual(set(files), {"a.txt", "c.txt", "d.txt"})
        self.assertEqual((files["a.txt"]["status"], files["a.txt"]["additions"], files["a.txt"]["deletions"]), ("modified", 1, 0))
        self.assertEqual(files["c.txt"]["status"], "added")
        self.assertEqual(files["d.txt"]["status"], "untracked")

        default = self.call("list", {"cwd": str(repo / ".")})
        self.assertEqual(default["id"], worktree["id"])
        self.assertEqual(set(self.by_path(default)), set(files))

        staged = self.listing(repo, "staged")
        self.assertEqual(staged["head"], "index")
        self.assertEqual({f["path"]: f["status"] for f in staged["files"]}, {"c.txt": "added"})

        unstaged = self.listing(repo, "unstaged")
        self.assertEqual({f["path"]: f["status"] for f in unstaged["files"]}, {"a.txt": "modified", "d.txt": "untracked"})

        patch = self.detail(worktree, files["d.txt"])["patch"]
        self.assertIn("new file mode 100644", patch)
        self.assertIn("+untracked", patch)
        self.assertIn("+new", self.detail(staged, staged["files"][0])["patch"])
        unstaged_a = self.detail(unstaged, self.by_path(unstaged)["a.txt"])
        self.assertIn("+two", unstaged_a["patch"])
        self.assertTrue(unstaged_a["patch"].startswith("diff --git a/a.txt b/a.txt\n"))

    def test_renames_and_deletions_are_listed(self) -> None:
        repo = self.make_repo()
        body = "".join(f"line {n}\n" for n in range(30))
        self.write(repo, "long.txt", body)
        self.write(repo, "moved.txt", body.replace("line", "row"))
        self.write(repo, "gone.txt", "bye\n")
        self.commit(repo, "init")
        (repo / "dir").mkdir()
        self.git(repo, "mv", "moved.txt", "dir/moved2.txt")
        self.git(repo, "rm", "-q", "gone.txt")
        os.remove(repo / "long.txt")
        self.write(repo, "long-renamed.txt", body + "extra\n")

        files = self.by_path(self.listing(repo))
        self.assertEqual(files["dir/moved2.txt"]["status"], "renamed")
        self.assertEqual(files["dir/moved2.txt"]["old_path"], "moved.txt")
        self.assertEqual(files["long-renamed.txt"]["status"], "renamed")
        self.assertEqual(files["long-renamed.txt"]["old_path"], "long.txt")
        self.assertTrue(files["long-renamed.txt"]["untracked"])
        self.assertEqual(files["gone.txt"]["status"], "deleted")
        self.assertNotIn("long.txt", files)

        worktree = self.listing(repo)
        patch = self.detail(worktree, self.by_path(worktree)["long-renamed.txt"])["patch"]
        self.assertIn("rename from long.txt", patch)
        self.assertIn("rename to long-renamed.txt", patch)
        self.assertIn("+extra", patch)
        self.assertIn("deleted file mode", self.detail(worktree, self.by_path(worktree)["gone.txt"])["patch"])

        staged = self.by_path(self.listing(repo, "staged"))
        self.assertEqual(set(staged), {"dir/moved2.txt", "gone.txt"})
        self.assertEqual(staged["dir/moved2.txt"]["status"], "renamed")

    def test_unborn_head(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "staged\n")
        self.git(repo, "add", "a.txt")
        self.write(repo, "u.txt", "loose\n")
        worktree = self.listing(repo)
        self.assertEqual(worktree["base"], self.empty_tree(repo))
        files = self.by_path(worktree)
        self.assertEqual({p: f["status"] for p, f in files.items()}, {"a.txt": "added", "u.txt": "untracked"})
        self.assertIn("+staged", self.detail(worktree, files["a.txt"])["patch"])
        staged = self.listing(repo, "staged")
        self.assertEqual([f["path"] for f in staged["files"]], ["a.txt"])
        refs = self.call("refs", {"cwd": str(repo)})
        self.assertEqual(refs["commits"], [])
        self.assertEqual(refs["branches"], [])

    def test_root_commit_and_commit_comparisons(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "first\n")
        first = self.commit(repo, "first subject")
        self.write(repo, "a.txt", "first\nsecond\n")
        self.write(repo, "b.txt", "bee\n")
        second = self.commit(repo, "second subject")

        root = self.listing(repo, "commit", head=first)
        self.assertEqual(root["base"], self.empty_tree(repo))
        self.assertEqual(root["head"], first)
        self.assertIn("root commit", root["label"])
        self.assertEqual({f["path"]: f["status"] for f in root["files"]}, {"a.txt": "added"})
        self.assertIn("new file mode", self.detail(root, root["files"][0])["patch"])

        latest = self.listing(repo, "commit", head="HEAD")
        self.assertEqual((latest["base"], latest["head"]), (first, second))
        self.assertIn("second subject", latest["label"])
        self.assertEqual({f["path"]: f["status"] for f in latest["files"]}, {"a.txt": "modified", "b.txt": "added"})

    def test_branch_comparison_is_pinned_to_resolved_revisions(self) -> None:
        repo = self.make_repo()
        self.write(repo, "base.txt", "base\n")
        fork = self.commit(repo, "base")
        self.git(repo, "branch", "feature")
        self.write(repo, "m.txt", "main only\n")
        main = self.commit(repo, "main work")
        self.git(repo, "checkout", "-q", "feature")
        self.write(repo, "f.txt", "feature\n")
        feature = self.commit(repo, "feature work")
        self.git(repo, "checkout", "-q", "main")

        cmp = self.listing(repo, "branch", base="main", head="feature")
        self.assertEqual((cmp["base"], cmp["head"]), (fork, feature))
        self.assertEqual(cmp["source"]["base_tip"], main)
        self.assertEqual([f["path"] for f in cmp["files"]], ["f.txt"])
        listed = cmp["files"][0]

        defaulted = self.listing(repo, "branch", head="feature")
        self.assertEqual(defaulted["source"]["base"], "main")
        self.assertEqual([f["path"] for f in defaulted["files"]], ["f.txt"])

        self.git(repo, "checkout", "-q", "feature")
        self.write(repo, "f.txt", "feature rewritten\n")
        self.commit(repo, "move feature")
        self.git(repo, "checkout", "-q", "main")
        detail = self.detail(cmp, listed)
        self.assertIn("+feature\n", detail["patch"])
        self.assertNotIn("rewritten", detail["patch"])
        self.assertEqual(detail["fingerprint"], listed["fingerprint"])

    def test_revision_names_cannot_inject_options(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "a\n")
        self.commit(repo, "init")
        target = self.tmp / "pwned"
        for source in (
            {"kind": "branch", "base": "main", "head": f"--output={target}"},
            {"kind": "branch", "base": "-n", "head": "main"},
            {"kind": "commit", "head": "--help"},
            {"kind": "commit", "head": "no-such-ref"},
        ):
            self.call("list", {"cwd": str(repo), "source": source}, expect_error=True)
        self.assertFalse(target.exists())
        cmp = self.listing(repo, "commit", head="HEAD")
        bad = dict(cmp, base="--output=" + str(target))
        self.call("detail", {"comparison": bad, "file": cmp["files"][0]}, expect_error=True)
        self.assertFalse(target.exists())

    def test_unusual_paths(self) -> None:
        repo = self.make_repo()
        names = [
            "with space.txt",
            "tab\there.txt",
            "new\nline.txt",
            "-dash.txt",
            "ünïcode.txt",
            "[ab].txt",
            "a.txt",
            "*",
            ":(glob)x",
            'quote"s.txt',
        ]
        for name in names:
            self.write(repo, name, "v1\n")
        self.commit(repo, "init")
        for name in names:
            self.write(repo, name, f"v1\nv2 {json.dumps(name)}\n")
        raw_name = b"raw-\xff.txt"
        self.write(repo, raw_name, "raw bytes\n")

        cmp = self.listing(repo)
        files = self.by_path(cmp)
        self.assertEqual(set(names) | {raw_name.decode("utf-8", "replace")}, set(files))
        for name in names:
            patch = self.detail(cmp, files[name])["patch"]
            self.assertEqual(patch.count("diff --git"), 1, name)
            self.assertIn(f"+v2 {json.dumps(name)}\n", patch)
        raw_entry = files[raw_name.decode("utf-8", "replace")]
        self.assertEqual(base64.b64decode(raw_entry["path_raw"]), raw_name)
        self.assertEqual(raw_entry["status"], "untracked")
        raw_detail = self.detail(cmp, raw_entry)
        self.assertIn("+raw bytes", raw_detail["patch"])
        self.assertEqual(raw_detail["fingerprint"], raw_entry["fingerprint"])

    def test_racily_clean_same_size_rewrite_is_detected(self) -> None:
        # Simulates a rewrite within the same filesystem timestamp tick as the index write:
        # same size, same inode, same mtime. Git compares content only because the entry is
        # not older than the index file; the backend's private index copy must keep that.
        repo = self.make_repo()
        self.git(repo, "config", "core.trustctime", "false")
        self.write(repo, "f.dat", b"\x00aaaa\n")
        self.commit(repo, "init")
        path = repo / "f.dat"
        original = os.stat(path)
        self.write(repo, "f.dat", b"\x00bbbb\n")
        self.assertEqual(os.stat(path).st_ino, original.st_ino)
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        os.utime(repo / ".git" / "index", ns=(original.st_mtime_ns, original.st_mtime_ns))
        for kind in ("worktree", "unstaged"):
            cmp = self.listing(repo, kind)
            entry = self.by_path(cmp)["f.dat"]
            detail = self.detail(cmp, entry)
            self.assertEqual(detail["fingerprint"], entry["fingerprint"], kind)
            self.assertTrue(detail["binary"], kind)
            self.assertNotIn("notice", detail, kind)

    def test_fingerprints_track_content_mode_binary_and_rename(self) -> None:
        repo = self.make_repo()
        self.write(repo, "t.txt", "a\n")
        self.write(repo, "bin.dat", bytes(range(256)) * 4)
        self.write(repo, "s.sh", "echo hi\n", 0o644)
        self.write(repo, "r.txt", "".join(f"r{n}\n" for n in range(20)))
        self.commit(repo, "init")

        def fp(kind: str, path: str) -> tuple[str, dict, dict]:
            cmp = self.listing(repo, kind)
            entry = self.by_path(cmp)[path]
            detail = self.detail(cmp, entry)
            self.assertEqual(detail["fingerprint"], entry["fingerprint"], path)
            return entry["fingerprint"], entry, detail

        self.write(repo, "t.txt", "a\nb\n")
        first, _, _ = fp("worktree", "t.txt")
        os.utime(repo / "t.txt", (1_000_000, 1_000_000))
        self.assertEqual(fp("worktree", "t.txt")[0], first, "metadata-only touch must keep the fingerprint")
        self.write(repo, "t.txt", "a\nc\n")
        self.assertNotEqual(fp("worktree", "t.txt")[0], first, "same-size content change must reset")

        self.write(repo, "bin.dat", bytes(reversed(range(256))) * 4)
        bin_one, entry, detail = fp("worktree", "bin.dat")
        self.assertTrue(entry["binary"])
        self.assertTrue(detail["binary"])
        self.assertIn("Binary files", detail["patch"])
        self.write(repo, "bin.dat", bytes(range(1, 256)) * 4 + b"\x00" * 4)
        self.assertNotEqual(fp("worktree", "bin.dat")[0], bin_one)

        os.chmod(repo / "s.sh", 0o755)
        mode_fp, entry, detail = fp("worktree", "s.sh")
        self.assertEqual(entry["status"], "modified")
        self.assertIn("old mode 100644", detail["patch"])
        self.assertIn("new mode 100755", detail["patch"])
        self.write(repo, "s.sh", "echo hi\n", 0o644)
        self.write(repo, "s.sh", "echo ho\n", 0o755)
        self.assertNotEqual(fp("worktree", "s.sh")[0], mode_fp)

        self.git(repo, "mv", "r.txt", "renamed.txt")
        rename_fp, entry, detail = fp("staged", "renamed.txt")
        self.assertEqual(entry["old_path"], "r.txt")
        self.assertIn("rename from r.txt", detail["patch"])
        self.write(repo, "renamed.txt", "".join(f"r{n}\n" for n in range(20)) + "tail\n")
        self.git(repo, "add", "renamed.txt")
        self.assertNotEqual(fp("staged", "renamed.txt")[0], rename_fp)

        self.commit(repo, "everything")
        cmp = self.listing(repo, "commit", head="HEAD")
        for entry in cmp["files"]:
            self.assertEqual(self.detail(cmp, entry)["fingerprint"], entry["fingerprint"])

    def test_untracked_symlinks_are_not_followed(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "a\n")
        self.commit(repo, "init")
        outside = self.tmp / "outside-secret.txt"
        outside.write_text("SECRET\n")
        outdir = self.tmp / "outside-dir"
        outdir.mkdir()
        (outdir / "inner.txt").write_text("INNER SECRET\n")
        os.symlink(outside, repo / "link")
        os.symlink(outdir, repo / "linkdir")

        cmp = self.listing(repo)
        files = self.by_path(cmp)
        self.assertEqual(set(files), {"link", "linkdir"})
        detail = self.detail(cmp, files["link"])
        self.assertIn("new file mode 120000", detail["patch"])
        self.assertIn(str(outside), detail["patch"])
        self.assertNotIn("SECRET", detail["patch"])
        self.assertNotIn("INNER", self.detail(cmp, files["linkdir"])["patch"])
        outside.write_text("CHANGED SECRET\n")
        self.assertEqual(self.by_path(self.listing(repo))["link"]["fingerprint"], files["link"]["fingerprint"])

    def test_repository_is_not_modified_and_repo_programs_do_not_run(self) -> None:
        repo = self.make_repo()
        self.write(repo, "a.txt", "a\n")
        self.write(repo, "b.txt", "b\n")
        self.write(repo, "old-name.txt", "".join(f"o{n}\n" for n in range(20)))
        self.commit(repo, "init")
        self.git(repo, "branch", "feature")
        self.write(repo, "c.txt", "c\n")
        self.commit(repo, "second")
        self.write(repo, "staged.txt", "staged\n")
        self.git(repo, "add", "staged.txt")

        markers = self.tmp / "markers"
        markers.mkdir()
        script = self.tmp / "mark.sh"
        script.write_text(f'#!/bin/sh\ntouch "{markers}/$(basename "$0")-$$"\ncat\n')
        script.chmod(0o755)
        for name in ("clean", "smudge", "process", "textconv", "external", "fsmonitor", "hook"):
            os.symlink(script, self.tmp / name)
        for key, value in (
            ("filter.evil.clean", self.tmp / "clean"),
            ("filter.evil.smudge", self.tmp / "smudge"),
            ("filter.evil.process", self.tmp / "process"),
            ("filter.evil.required", "true"),
            ("diff.evil.textconv", self.tmp / "textconv"),
            ("diff.external", self.tmp / "external"),
            ("core.fsmonitor", self.tmp / "fsmonitor"),
        ):
            self.git(repo, "config", key, str(value))
        (repo / ".git" / "info" / "attributes").write_text("*.txt filter=evil diff=evil\n")
        for hook in ("post-index-change", "reference-transaction", "post-checkout"):
            os.symlink(self.tmp / "hook", repo / ".git" / "hooks" / hook)
        self.write(repo, "a.txt", "a changed\n")
        os.rename(repo / "old-name.txt", repo / "new-name.txt")
        self.write(repo, "untracked.txt", "u\n")

        before = snapshot(repo)
        comparisons = [
            self.listing(repo),
            self.listing(repo, "staged"),
            self.listing(repo, "unstaged"),
            self.listing(repo, "branch", base="feature", head="HEAD"),
            self.listing(repo, "commit", head="HEAD"),
        ]
        for cmp in comparisons:
            self.assertTrue(cmp["files"], cmp["source"])
            for entry in cmp["files"]:
                self.detail(cmp, entry)
        self.call("refs", {"cwd": str(repo)})
        self.assertEqual(snapshot(repo), before)
        self.assertEqual(sorted(os.listdir(markers)), [])
        renamed = self.by_path(comparisons[0])["new-name.txt"]
        self.assertEqual((renamed["status"], renamed["old_path"]), ("renamed", "old-name.txt"))

    def test_huge_patch_is_reported_not_loaded(self) -> None:
        repo = self.make_repo()
        self.write(repo, "big.txt", "small\n")
        self.commit(repo, "init")
        self.write(repo, "big.txt", ("x" * 99 + "\n") * 55_000)
        cmp = self.listing(repo)
        entry = cmp["files"][0]
        self.assertEqual(entry["additions"], 55_000)
        detail = self.detail(cmp, entry)
        self.assertTrue(detail["truncated"])
        self.assertEqual(detail["patch"], "")
        self.assertIn("MiB", detail["notice"])
        self.assertEqual(detail["fingerprint"], entry["fingerprint"])
        self.assertEqual(cmp["limits"]["patch_bytes"], backend.PATCH_LIMIT)

    def test_refs_lists_branches_and_commits(self) -> None:
        repo = self.make_repo()
        for n in range(3):
            self.write(repo, "a.txt", f"{n}\n")
            self.commit(repo, f"subject {n}")
        self.git(repo, "branch", "feature")
        refs = self.call("refs", {"cwd": str(repo)})
        self.assertEqual(set(refs["branches"]), {"main", "feature"})
        self.assertEqual([c["subject"] for c in refs["commits"]], ["subject 2", "subject 1", "subject 0"])
        self.assertEqual(refs["commits"][0]["sha"], self.git(repo, "rev-parse", "HEAD").strip())
        self.assertFalse(refs["commits_truncated"])
        self.assertEqual(refs["commits_limit"], backend.COMMIT_LIMIT)

    def test_errors_are_reported_as_json(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        err = self.call("list", {"cwd": str(plain)}, expect_error=True)
        self.assertIn("not a git repository", err["error"])
        self.call("list", {"cwd": str(self.tmp / "missing")}, expect_error=True)
        self.call("list", {"cwd": str(plain), "source": {"kind": "bogus"}}, expect_error=True)
        res = subprocess.run([sys.executable, str(BACKEND), "list"], input=b"{nope", env=self.env, capture_output=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not valid JSON", json.loads(res.stdout)["error"])
        res = subprocess.run([sys.executable, str(BACKEND), "explode"], input=b"{}", env=self.env, capture_output=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("usage", json.loads(res.stdout)["error"])


class GitHubTransformTests(unittest.TestCase):
    def test_parse_pr_spec(self) -> None:
        P = backend.PrSpec
        self.assertEqual(backend.parse_pr_spec("12"), P(12))
        self.assertEqual(backend.parse_pr_spec("#12"), P(12))
        self.assertEqual(backend.parse_pr_spec("octo/repo.js#5"), P(5, None, "octo", "repo.js"))
        self.assertEqual(backend.parse_pr_spec("https://github.com/o/r/pull/7/files"), P(7, "github.com", "o", "r"))
        self.assertEqual(backend.parse_pr_spec("https://www.github.com/o/r/pull/7"), P(7, "github.com", "o", "r"))
        self.assertEqual(backend.parse_pr_spec("https://ghe.example.com/o/r/pull/9#x"), P(9, "ghe.example.com", "o", "r"))
        for bad in ("https://github.com/o/r/issues/3", "feature", "-x/r#1", "https://github.com/o/r/pull/abc"):
            with self.assertRaises(backend.BackendError):
                backend.parse_pr_spec(bad)

    def test_pr_files_transform_and_fingerprints(self) -> None:
        merge_base = "1" * 40
        pages = [
            [
                {"filename": "a.txt", "status": "modified", "additions": 1, "deletions": 2, "sha": "a" * 40, "patch": "@@ -1 +1 @@\n-a\n+b"},
                {"filename": "new.txt", "previous_filename": "old.txt", "status": "renamed", "additions": 0, "deletions": 0, "sha": "b" * 40},
            ],
            [
                {"filename": "gone.txt", "status": "removed", "additions": 0, "deletions": 3, "sha": "c" * 40, "patch": "@@ -1,3 +0,0 @@\n-x\n-y\n-z"},
                {"filename": "img.png", "status": "added", "additions": 0, "deletions": 0, "sha": "d" * 40},
                {"filename": "run.sh", "status": "changed", "additions": 0, "deletions": 0, "sha": "e" * 40},
            ],
        ]
        files = backend.pr_files_to_list(pages, merge_base)
        self.assertEqual(
            [(f["path"], f.get("old_path"), f["status"]) for f in files],
            [
                ("a.txt", None, "modified"),
                ("new.txt", "old.txt", "renamed"),
                ("gone.txt", None, "deleted"),
                ("img.png", None, "added"),
                ("run.sh", None, "modified"),
            ],
        )
        self.assertEqual((files[0]["additions"], files[0]["deletions"]), (1, 2))
        for f in files:
            self.assertEqual(f["fingerprint"], backend.pr_fingerprint(f, merge_base))

        edited = json.loads(json.dumps(pages))
        edited[0][0]["patch"] = "@@ -1 +1 @@\n-z\n+b"
        self.assertNotEqual(backend.pr_files_to_list(edited, merge_base)[0]["fingerprint"], files[0]["fingerprint"])
        moved = backend.pr_files_to_list(pages, "2" * 40)
        self.assertEqual(moved[0]["fingerprint"], files[0]["fingerprint"], "patch text pins content")
        self.assertNotEqual(moved[3]["fingerprint"], files[3]["fingerprint"], "patchless file falls back to merge base")
        self.assertEqual(len({f["fingerprint"] for f in files}), len(files))

    def test_graphql_modes(self) -> None:
        self.assertEqual(backend.gql_mode(33188), "100644")
        self.assertEqual(backend.gql_mode(33261), "100755")
        self.assertEqual(backend.gql_mode(40960), "120000")
        self.assertEqual(backend.gql_mode(57344), "160000")
        self.assertEqual(backend.gql_mode(100644), "100644")
        self.assertEqual(backend.gql_mode("100755"), "100755")
        with self.assertRaises(backend.BackendError):
            backend.gql_mode(12345)


class GitHubAdapterTests(BackendTestCase):
    """Drives the real gh code path against a fake `gh` that answers from a real repository."""

    def setUp(self) -> None:
        super().setUp()
        repo = self.make_repo("upstream")
        body = "".join(f"line {n}\n" for n in range(30))
        self.write(repo, "keep.txt", "keep\n")
        self.write(repo, "rename-me.txt", body)
        self.write(repo, "delete-me.txt", "doomed\n")
        self.write(repo, "mode.sh", "echo hi\n", 0o644)
        self.write(repo, "image.bin", bytes(range(256)) * 8)
        self.write(repo, "dir/nested.txt", "nested\n")
        self.commit(repo, "base")
        self.git(repo, "checkout", "-q", "-b", "feature")
        self.git(repo, "mv", "rename-me.txt", "renamed.txt")
        self.write(repo, "renamed.txt", body.replace("line 5\n", "line five\n"))
        self.git(repo, "rm", "-q", "delete-me.txt")
        os.chmod(repo / "mode.sh", 0o755)
        self.write(repo, "image.bin", bytes(reversed(range(256))) * 8)
        self.write(repo, "added.txt", "brand new\n")
        self.write(repo, "dir/nested.txt", "nested\nmore\n")
        self.commit(repo, "feature")
        self.git(repo, "checkout", "-q", "main")
        self.write(repo, "other.txt", "main moved on\n")
        self.commit(repo, "main advance")
        self.repo = repo

        bindir = self.tmp / "bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.state_path = self.tmp / "gh-state.json"
        self.log_path = self.tmp / "gh-log.jsonl"
        self.set_state()
        self.env.update(
            PATH=str(bindir) + os.pathsep + self.env.get("PATH", ""),
            FAKE_GH_REPO=str(repo),
            FAKE_GH_STATE=str(self.state_path),
            FAKE_GH_LOG=str(self.log_path),
        )
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()

    def set_state(self, **extra) -> None:
        state = {"number": 7, "title": "Add things", "base": "main", "head": "feature", "page_size": 2, **extra}
        self.state_path.write_text(json.dumps(state))

    def gh_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def test_pr_url_listing_and_patches_match_local_git(self) -> None:
        cmp = self.call("list", {"cwd": str(self.elsewhere), "source": {"kind": "pr", "pr": "https://github.com/o/r/pull/7"}})
        main = self.git(self.repo, "rev-parse", "main").strip()
        feature = self.git(self.repo, "rev-parse", "feature").strip()
        merge_base = self.git(self.repo, "merge-base", "main", "feature").strip()
        self.assertNotEqual(main, merge_base)
        self.assertEqual(cmp["root"], str(self.elsewhere))
        self.assertEqual(cmp["id"], "pr:github.com/o/r#7")
        self.assertEqual((cmp["base"], cmp["head"]), (merge_base, feature))
        self.assertEqual(cmp["pr"]["base_sha"], main)
        self.assertFalse(cmp["truncated"])
        self.assertEqual(cmp["limits"]["github_pr_files"], 3000)
        files = self.by_path(cmp)
        self.assertEqual(
            {p: (f["status"], f.get("old_path")) for p, f in files.items()},
            {
                "added.txt": ("added", None),
                "delete-me.txt": ("deleted", None),
                "dir/nested.txt": ("modified", None),
                "image.bin": ("modified", None),
                "mode.sh": ("modified", None),
                "renamed.txt": ("renamed", "rename-me.txt"),
            },
        )
        for path, entry in files.items():
            detail = self.detail(cmp, entry)
            paths = [entry.get("old_path") or path, path]
            expected = self.git(
                self.repo,
                "-c", "core.quotePath=false",
                "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--find-renames",
                "--src-prefix=a/", "--dst-prefix=b/", merge_base, feature, "--", *dict.fromkeys(paths),
            )
            self.assertEqual(detail["patch"], expected, path)
            self.assertEqual(detail["fingerprint"], entry["fingerprint"], path)
            self.assertEqual(detail["binary"], path == "image.bin", path)
        for call in self.gh_calls():
            self.assertNotIn("checkout", call)
            self.assertNotIn("fetch", call)

    def test_pr_number_resolves_against_cwd_repository(self) -> None:
        cmp = self.call("list", {"cwd": str(self.repo), "source": {"kind": "pr", "pr": "#7"}})
        self.assertEqual(cmp["root"], str(self.repo))
        self.assertEqual(cmp["pr"]["owner"], "o")
        self.assertEqual(len(cmp["files"]), 6)
        self.assertTrue(any("repos/{owner}/{repo}/pulls/7" in call for call in self.gh_calls()))

    def test_pr_file_cap_is_reported(self) -> None:
        self.set_state(changed_files=5000)
        cmp = self.call("list", {"cwd": str(self.elsewhere), "source": {"kind": "pr", "pr": "o/r#7"}})
        self.assertTrue(cmp["truncated"])
        self.assertIn("3000", cmp["notice"])
        self.assertIn("6 of 5000", cmp["notice"])

    def test_pr_blob_mismatch_is_an_error(self) -> None:
        cmp = self.call("list", {"cwd": str(self.elsewhere), "source": {"kind": "pr", "pr": "o/r#7"}})
        self.set_state(corrupt_blob=True)
        err = self.call("detail", {"comparison": cmp, "file": self.by_path(cmp)["added.txt"]}, expect_error=True)
        self.assertIn("does not match", err["error"])

    def test_gh_auth_errors_are_passed_through(self) -> None:
        self.set_state(fail_auth=True)
        err = self.call("list", {"cwd": str(self.elsewhere), "source": {"kind": "pr", "pr": "o/r#7"}}, expect_error=True)
        self.assertIn("gh auth login", err["error"])
        err = self.call("pulls", {"cwd": str(self.repo)}, expect_error=True)
        self.assertIn("gh auth login", err["error"])

    def test_pulls_are_bounded(self) -> None:
        res = self.call("pulls", {"cwd": str(self.repo)})
        self.assertEqual(res["limit"], backend.PULL_LIMIT)
        self.assertEqual(len(res["pulls"]), backend.PULL_LIMIT)
        self.assertTrue(res["truncated"])
        self.assertEqual(res["pulls"][0], {"number": 1, "title": "PR 1", "url": "https://github.com/o/r/pull/1"})


if __name__ == "__main__":
    unittest.main()
