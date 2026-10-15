"""Real isolated Git worktrees; only GitHub's external transport is substituted."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "tern/plugins/agent-cockpit"
sys.path.insert(0, str(PLUGIN))
SPEC = importlib.util.spec_from_file_location("cockpit_workspace_metadata", PLUGIN / "metadata_workspace.py")
assert SPEC is not None and SPEC.loader is not None
WORKSPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKSPACE)
HEAD = "a" * 40
IDENTITY = "github.com/alice/project"


def pull_request(*, branch="main", commit=HEAD, number=17, checks=None):
    if checks is None:
        checks = [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]
    return {
        "number": number, "state": "OPEN", "isDraft": False,
        "headRefName": branch, "headRefOid": commit, "reviewDecision": "APPROVED",
        "headRepository": {"nameWithOwner": "alice/project", "url": "https://github.com/alice/project"},
        "baseRepository": {"nameWithOwner": "team/project", "url": "https://github.com/team/project"},
        "commits": {"nodes": [{"commit": {"oid": commit, "statusCheckRollup": {
            "state": "SUCCESS", "contexts": {
                "totalCount": len(checks), "pageInfo": {"hasNextPage": False}, "nodes": checks,
            },
        }}}]},
    }


def response(prs, *, commit=HEAD, checks=None):
    target = pull_request(commit=commit, checks=checks)["commits"]["nodes"][0]["commit"]
    return {"data": {"repository": {
        "nameWithOwner": "alice/project", "url": "https://github.com/alice/project",
        "ref": {"target": target, "associatedPullRequests": {
            "nodes": prs, "totalCount": len(prs), "pageInfo": {"hasNextPage": False},
        }},
    }}}


class WorkspaceGitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.root / "state"
        self.repo = self.root / "project"
        self.repo.mkdir()
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.state), "GH_CONFIG_DIR": str(self.home / ".config/gh"),
            "GH_HOST": "", "GIT_CONFIG_NOSYSTEM": "1",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.git("init", "-b", "main")
        (self.repo / "tracked.txt").write_text("initial\n")
        self.git("add", "tracked.txt")
        self.git("commit", "-m", "Initial")
        self.gh_calls = []
        self.gh_status = "ok"
        self.payload = response([pull_request(commit=self.head())], commit=self.head())
        original = WORKSPACE._run

        def transport(argv, cwd, deadline, seconds, limit=WORKSPACE.OUTPUT_LIMIT):
            if argv[0] != "gh":
                return original(argv, cwd, deadline, seconds, limit)
            self.gh_calls.append(argv)
            return self.gh_status, json.dumps(self.payload).encode()

        github = patch.object(WORKSPACE, "_run", side_effect=transport)
        github.start()
        self.addCleanup(github.stop)
        self.github_patch = github

    def git(self, *args, cwd=None):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
        return subprocess.run([
            "git", "-c", "user.name=Workspace Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", *args,
        ], cwd=cwd or self.repo, env=env, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE).stdout.decode().strip()

    def head(self):
        return self.git("rev-parse", "HEAD")

    def github_remote(self, value="https://github.com/alice/project.git"):
        self.git("remote", "add", "origin", value)

    def collect(self, cwd=None):
        return WORKSPACE.collect(cwd or self.repo)

    def cache(self):
        files = list((self.state / "tern/agent-cockpit/workspaces").glob("*.json"))
        self.assertEqual(len(files), 1)
        return files[0], json.loads(files[0].read_text())

    def expire_cache(self):
        path, record = self.cache()
        record["attempted"] -= WORKSPACE.CACHE_SECONDS + 1
        record["observed"] -= WORKSPACE.CACHE_SECONDS + 1
        path.write_text(json.dumps(record))

    def test_clean_dirty_and_untracked_are_live_without_network(self):
        first = self.collect()
        self.assertEqual(first["workspace_branch"], "main")
        self.assertEqual(first["git_status"], "Clean")
        self.assertEqual(first["git_divergence"], "No upstream")
        (self.repo / "tracked.txt").write_text("changed\n")
        (self.repo / "untracked\n# branch.head fake").write_text("new\n")
        second = self.collect()
        self.assertEqual(second["git_status"], "Dirty · 1 tracked · 1 untracked")
        self.assertEqual(self.gh_calls, [])
        self.assertNotIn("pr_url", second)

    def test_rename_original_path_does_not_become_an_extra_status_record(self):
        self.git("mv", "tracked.txt", "renamed.txt")
        (self.repo / "another.txt").write_text("new\n")
        self.assertEqual(self.collect()["git_status"], "Dirty · 1 tracked · 1 untracked")

    def test_detached_unborn_bare_and_nonrepo_have_no_pr_attribution(self):
        self.github_remote()
        self.git("checkout", "--detach")
        detached = self.collect()
        self.assertEqual(detached["workspace_branch"], "Detached HEAD · " + self.head()[:12])
        self.assertIn("detached HEAD", detached["pr_status"])
        unborn = self.root / "unborn"
        unborn.mkdir()
        self.git("init", "-b", "new", cwd=unborn)
        initial = self.collect(unborn)
        self.assertEqual(initial["workspace_branch"], "new")
        self.assertIn("unborn branch", initial["workspace_source"])
        bare = self.root / "bare.git"
        self.git("init", "--bare", str(bare))
        self.assertNotIn("workspace_branch", self.collect(bare))
        self.assertNotIn("workspace_branch", self.collect(self.home))
        self.assertEqual(self.gh_calls, [])

    def test_divergence_uses_local_upstream_without_fetch_or_index_changes(self):
        upstream = self.root / "upstream.git"
        self.git("init", "--bare", str(upstream))
        self.git("remote", "add", "origin", str(upstream))
        self.git("push", "-u", "origin", "main")
        self.assertEqual(self.collect()["git_divergence"], "↑0 ↓0 · origin/main (local tracking ref)")
        other = self.root / "other"
        self.git("clone", "--branch", "main", str(upstream), str(other))
        (self.repo / "local.txt").write_text("local\n")
        self.git("add", ".")
        self.git("commit", "-m", "Local")
        (other / "remote.txt").write_text("remote\n")
        self.git("add", ".", cwd=other)
        self.git("commit", "-m", "Remote", cwd=other)
        self.git("push", "origin", "main", cwd=other)
        # Collector must not fetch: its tracking ref is still the original commit.
        self.assertEqual(self.collect()["git_divergence"], "↑1 ↓0 · origin/main (local tracking ref)")
        self.git("fetch", "origin", "main")
        refs = self.git("show-ref")
        index = self.repo / ".git/index"
        before = index.read_bytes(), index.stat().st_mtime_ns
        snapshot = self.collect()
        self.assertEqual(snapshot["git_divergence"], "↑1 ↓1 · origin/main (local tracking ref)")
        self.assertEqual(self.git("show-ref"), refs)
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), before)
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertNotIn("↑0", self.collect()["git_divergence"])

    def test_repository_fsmonitor_hook_is_never_executed(self):
        sentinel = self.root / "hook-executed"
        script = self.root / "fsmonitor"
        script.write_text("#!/bin/sh\n touch '" + str(sentinel) + "'\n")
        script.chmod(0o700)
        self.git("config", "core.fsmonitor", str(script))
        self.assertEqual(self.collect()["git_status"], "Clean")
        self.assertFalse(sentinel.exists())

    def test_exact_fork_pr_review_ci_and_credential_free_identity(self):
        self.github_remote("https://credential:SECRET@github.com/alice/project.git?token=PRIVATE")
        result = self.collect()
        self.assertEqual(result["pr_status"], "#17 · Open · approved")
        self.assertEqual(result["pr_url"], "https://github.com/team/project/pull/17")
        self.assertEqual(result["ci_status"], "Passing · 1 passed / 1 checks")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("credential", json.dumps(self.gh_calls))
        self.assertIn("github.com/alice/project", result["workspace_source"])
        self.assertTrue(all(isinstance(text, str) and len(text) <= 300 for text in result.values()))

    def test_non_github_and_ambiguous_push_destinations_are_not_queried(self):
        self.github_remote("git@gitlab.com:alice/project.git")
        self.assertIn("no GitHub remote", self.collect()["workspace_source"])
        self.git("remote", "set-url", "origin", "git@github.com:alice/project.git")
        self.git("config", "--add", "remote.origin.pushurl", "git@github.com:alice/project.git")
        self.git("config", "--add", "remote.origin.pushurl", "git@github.com:other/project.git")
        self.assertIn("no GitHub remote", self.collect()["workspace_source"])
        self.assertEqual(self.gh_calls, [])

    def test_explicit_push_remote_selects_fork_not_tracking_base(self):
        self.github_remote()
        self.git("remote", "add", "upstream", "https://github.com/team/project.git")
        self.git("config", "branch.main.remote", "upstream")
        self.git("config", "branch.main.pushRemote", "origin")
        self.assertEqual(self.collect()["pr_url"], "https://github.com/team/project/pull/17")

    def test_git_push_url_rewriting_is_resolved_before_pr_attribution(self):
        self.github_remote("https://alias.invalid/alice/project.git")
        self.git("config", "url.https://github.com/.pushInsteadOf", "https://alias.invalid/")
        self.assertEqual(self.collect()["pr_url"], "https://github.com/team/project/pull/17")

    def test_network_cache_is_private_and_git_dirtiness_does_not_wait_for_ttl(self):
        self.github_remote()
        first = self.collect()
        path, record = self.cache()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for directory in (path.parent, path.parent.parent, path.parent.parent.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("token", json.dumps(record))
        self.payload = response([], commit=self.head())
        (self.repo / "tracked.txt").write_text("changed\n")
        second = self.collect()
        self.assertEqual(second["pr_status"], first["pr_status"])
        self.assertIn("Dirty", second["git_status"])
        self.assertEqual(len(self.gh_calls), 1)
        self.expire_cache()
        self.assertEqual(self.collect()["pr_status"], "No open PR")
        self.assertEqual(len(self.gh_calls), 2)

    def test_github_timeout_keeps_live_git_snapshot_and_marks_unavailable(self):
        self.github_remote()
        self.gh_status = "timeout"
        result = self.collect()
        self.assertEqual(result["workspace_branch"], "main")
        self.assertEqual(result["git_status"], "Clean")
        self.assertEqual(result["pr_status"], "Unavailable")
        self.assertIn("timeout", result["workspace_source"])
        self.assertNotIn("pr_url", result)

    def test_expired_success_is_explicitly_stale_after_failed_refresh(self):
        self.github_remote()
        self.collect()
        self.expire_cache()
        self.gh_status = "failed"
        self.payload = {"SECRET": "authentication token"}
        stale = self.collect()
        self.assertTrue(stale["pr_status"].startswith("Stale · #17"))
        self.assertTrue(stale["ci_status"].startswith("Stale · Passing"))
        self.assertIn("stale", stale["workspace_source"])
        self.assertIn("authentication/network unavailable", stale["workspace_source"])
        self.assertNotIn("SECRET", json.dumps(stale))
        self.collect()
        self.assertEqual(len(self.gh_calls), 2)

    def test_branch_head_repo_and_remote_switches_never_reuse_stale_pr(self):
        self.github_remote()
        self.collect()
        self.gh_status = "failed"
        self.git("checkout", "-b", "different")
        self.assertEqual(self.collect()["pr_status"], "Unavailable")
        self.git("checkout", "main")
        (self.repo / "new.txt").write_text("new\n")
        self.git("add", ".")
        self.git("commit", "-m", "New HEAD")
        self.assertEqual(self.collect()["pr_status"], "Unavailable")
        self.git("remote", "set-url", "origin", "https://github.com/bob/project.git")
        self.assertEqual(self.collect()["pr_status"], "Unavailable")
        other = self.root / "same-name"
        self.git("clone", "--branch", "main", str(self.repo), str(other))
        self.git("remote", "set-url", "origin", "https://github.com/alice/project.git", cwd=other)
        self.assertEqual(self.collect(other)["pr_status"], "Unavailable")
        self.assertEqual(len(self.gh_calls), 5)

    def test_missing_gh_preserves_git_and_does_not_release_errors(self):
        self.github_remote()
        self.github_patch.stop()
        binaries = self.root / "bin"
        binaries.mkdir()
        (binaries / "git").symlink_to(shutil.which("git"))
        with patch.dict(os.environ, {"PATH": str(binaries)}):
            result = self.collect()
        self.assertEqual(result["workspace_branch"], "main")
        self.assertEqual(result["git_status"], "Clean")
        self.assertEqual(result["pr_status"], "Unavailable")
        self.assertIn("not installed", result["workspace_source"])

    def test_symlink_cache_directory_cannot_write_outside_private_state(self):
        self.github_remote()
        outside = self.root / "outside"
        outside.mkdir()
        self.state.mkdir()
        (self.state / "tern").symlink_to(outside, target_is_directory=True)
        result = self.collect()
        self.assertEqual(result["pr_status"], "#17 · Open · approved")
        self.assertEqual(list(outside.iterdir()), [])


class GitHubSummaryTests(unittest.TestCase):
    def result(self, prs, *, commit=HEAD, payload=None):
        result = WORKSPACE._pr_result(payload or response(prs), IDENTITY, "main", commit)
        self.assertIsNotNone(result)
        return result[0]

    def test_wrong_branch_or_fork_owner_never_selects_first_title_match(self):
        wrong_branch = pull_request(branch="other")
        wrong_owner = pull_request()
        wrong_owner["headRepository"] = {"nameWithOwner": "someone/project", "url": "https://github.com/someone/project"}
        actual = pull_request(number=42)
        self.assertEqual(self.result([wrong_branch, wrong_owner, actual])["pr_url"], "https://github.com/team/project/pull/42")
        unmatched = self.result([wrong_branch, wrong_owner])
        self.assertEqual(unmatched["pr_status"], "No open PR")
        self.assertTrue(unmatched["ci_status"].startswith("Branch HEAD · Passing"))

    def test_multiple_prs_and_paginated_selection_are_unavailable_not_first(self):
        ambiguous = self.result([pull_request(), pull_request(number=42)])
        self.assertIn("multiple open PRs", ambiguous["pr_status"])
        self.assertNotIn("pr_url", ambiguous)
        self.assertTrue(ambiguous["ci_status"].startswith("Branch HEAD · Passing"))
        payload = response([pull_request()])
        connection = payload["data"]["repository"]["ref"]["associatedPullRequests"]
        connection["pageInfo"]["hasNextPage"] = True
        connection["totalCount"] = 21
        partial = self.result([], payload=payload)
        self.assertIn("incomplete PR coverage", partial["pr_status"])
        self.assertNotIn("pr_url", partial)
        self.assertTrue(partial["ci_status"].startswith("Branch HEAD · Passing"))

    def test_unpushed_branch_no_pr_and_unpushed_local_commit_are_distinct(self):
        payload = response([])
        payload["data"]["repository"]["ref"] = None
        self.assertIn("branch not pushed", self.result([], payload=payload)["pr_status"])
        self.assertEqual(self.result([])["pr_status"], "No open PR")
        result = self.result([pull_request()], commit="b" * 40)
        self.assertIn("local HEAD differs", result["pr_status"])
        self.assertTrue(result["ci_status"].startswith("Remote HEAD · "))
        branch_result = self.result([], commit="b" * 40)
        self.assertTrue(branch_result["ci_status"].startswith("Remote HEAD · "))

    def test_no_pr_branch_has_exact_head_passing_pending_and_failing_checks(self):
        cases = [
            ({"__typename": "StatusContext", "state": "SUCCESS"}, "Passing"),
            ({"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}, "Pending"),
            ({"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}, "Failing"),
        ]
        for check, expected in cases:
            with self.subTest(check=check):
                result = self.result([], payload=response([], checks=[check]))
                self.assertEqual(result["pr_status"], "No open PR")
                self.assertTrue(result["ci_status"].startswith("Branch HEAD · " + expected))
                self.assertNotIn("pr_url", result)

    def test_repository_host_head_commit_and_graphql_errors_are_not_attributed(self):
        valid = response([pull_request()])
        cases = []
        wrong_repo = copy.deepcopy(valid)
        wrong_repo["data"]["repository"]["url"] = "https://github.com/bob/project"
        cases.append(wrong_repo)
        wrong_host = copy.deepcopy(valid)
        wrong_host["data"]["repository"]["ref"]["associatedPullRequests"]["nodes"][0]["baseRepository"]["url"] = "https://attacker.invalid/team/project"
        cases.append(wrong_host)
        wrong_commit = response([pull_request(commit="b" * 40)])
        cases.append(wrong_commit)
        partial_error = copy.deepcopy(valid)
        partial_error["errors"] = [{"message": "secret error"}]
        cases.append(partial_error)
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(WORKSPACE._pr_result(payload, IDENTITY, "main", HEAD))

    def test_ci_states_zero_pending_failure_skipped_unknown_and_partial(self):
        success = {"__typename": "StatusContext", "state": "SUCCESS"}
        pending = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}
        failure = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
        skipped = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"}
        cases = [
            ([], "No checks reported"), ([success], "Passing"),
            ([success, pending], "Pending"), ([failure, pending], "Failing"),
            ([skipped], "Skipped"), ([{"__typename": "FutureCheck"}], "Incomplete"),
            ([{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": None}], "Incomplete"),
            ([{"__typename": "StatusContext", "state": "ERROR"}], "Failing"),
            ([{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "TIMED_OUT"}], "Failing"),
        ]
        for checks, label in cases:
            with self.subTest(checks=checks):
                self.assertTrue(self.result([pull_request(checks=checks)])["ci_status"].startswith(label))
        pr = pull_request()
        rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        rollup["contexts"]["totalCount"] = 101
        rollup["contexts"]["pageInfo"]["hasNextPage"] = True
        self.assertEqual(self.result([pr])["ci_status"], "Incomplete · 1/101 checks · rollup success")
        pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"] = None
        self.assertEqual(self.result([pr])["ci_status"], "No checks reported")
        pr["commits"]["nodes"] = []
        self.assertIn("Unavailable", self.result([pr])["ci_status"])

    def test_successful_visible_checks_cannot_override_non_success_rollup(self):
        pr = pull_request()
        pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["state"] = "FAILURE"
        summary = self.result([pr])["ci_status"]
        self.assertTrue(summary.startswith("Incomplete"))
        self.assertIn("rollup failure", summary)

    def test_review_and_draft_do_not_require_or_invent_approval(self):
        for decision, expected in [("REVIEW_REQUIRED", "review required"), ("CHANGES_REQUESTED", "changes requested"), ("", "review undecided"), (None, "review unavailable")]:
            with self.subTest(decision=decision):
                pr = pull_request()
                pr.update(isDraft=True, reviewDecision=decision)
                self.assertEqual(self.result([pr])["pr_status"], "#17 · Draft · " + expected)


class BoundedCommandTests(unittest.TestCase):
    def test_expired_deadline_never_starts_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "started"
            command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]
            status, raw = WORKSPACE._run(command, root, time.monotonic() - 1, 10)
            self.assertEqual((status, raw), ("deadline", b""))
            self.assertFalse(marker.exists())

    def test_process_runtime_and_output_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = time.monotonic()
            status, raw = WORKSPACE._run([sys.executable, "-c", "import time; time.sleep(5)"], root, start + 0.1, 10)
            self.assertEqual((status, raw), ("timeout", b""))
            self.assertLess(time.monotonic() - start, 1)
            status, raw = WORKSPACE._run([sys.executable, "-c", "print('x' * 1000000)"], root, time.monotonic() + 2, 1, limit=32)
            self.assertEqual((status, raw), ("output limit", b""))


if __name__ == "__main__":
    unittest.main()
