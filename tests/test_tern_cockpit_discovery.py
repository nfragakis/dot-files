from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "tern/plugins/agent-cockpit/discovery.luau"


@unittest.skipUnless(shutil.which("lua"), "Lua is required for the pure cockpit model")
class CockpitDiscoveryTest(unittest.TestCase):
    def run_lua(self, body: str) -> None:
        result = subprocess.run(
            ["lua", "-", str(MODEL)],
            input='local discovery = dofile(arg[1])\n' + body,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_command_identity_does_not_classify_mentions_or_service_helpers(self) -> None:
        self.run_lua(r'''
assert(discovery.provider('claude --resume') == 'claude')
assert(discovery.provider('env TOKEN=unused command "/opt/my apps/codex" --resume') == 'codex')
assert(discovery.provider('exec /home/me/bin/omp') == 'omp')
assert(discovery.provider('echo claude') == nil)
assert(discovery.provider('cat codex.log') == nil)
assert(discovery.provider('codex app-server') == nil)
assert(discovery.provider('claude --version') == nil)
assert(discovery.provider('echo ok && codex') == nil)
''')

    def test_uninstrumented_claude_and_codex_are_not_falsely_idle_or_working(self) -> None:
        self.run_lua(r'''
local panes = {
    {pane=11, kind='agent', title='Reviewing an API', cwd='/work/api', busy=true},
    {pane=12, kind='terminal', title='Fix tests', cwd='/work/api', busy=true, running={line='codex --resume'}},
}
local agents = {{pane=11, command='claude', cwd='/work/api', state='idle'}}
local rows = discovery.collect(panes, agents, {}, {}, {}, {})
assert(#rows == 2)
for _, row in ipairs(rows) do
    assert(row.status == 'unknown')
    assert(row.activity == nil, 'A session title is not observed activity')
end
''')

    def test_omp_lifecycle_and_turn_failure_are_distinct_from_tool_output(self) -> None:
        self.run_lua(r'''
local panes = {{pane=7, kind='agent', cwd='/work/api', title='Agent'}}
local agent = {pane=7, cwd='/work/api', state='waiting_input', last_message='Need a decision'}
local rows = discovery.collect(panes, {agent}, {}, {}, {}, {})
assert(rows[1].provider == 'omp' and rows[1].status == 'waiting_input')
assert(rows[1].activity == 'Need a decision')
agent.state = 'idle'
rows = discovery.collect(panes, {agent}, {}, {}, {}, {[7]='failed'})
assert(rows[1].status == 'failed')
agent.state = 'working'
rows = discovery.collect(panes, {agent}, {}, {}, {}, {[7]='failed'})
assert(rows[1].status == 'working')
''')

    def test_session_titles_distinguish_agents_in_the_same_workspace(self) -> None:
        self.run_lua(r'''
local rows = discovery.collect({
    {pane=1,kind='agent',title='Fix authentication',cwd='/work/api'},
    {pane=2,kind='agent',title='Review schema',cwd='/work/api'},
    {pane=3,kind='terminal',title='/usr/bin/claude',cwd='/work/api',program='claude'},
}, {
    {pane=1,cwd='/work/api',state='idle'},
    {pane=2,cwd='/work/api',state='working'},
}, {}, {}, {}, {})
local titles = {}
for _, row in ipairs(rows) do titles[row.key] = row.title end
assert(titles['pane-1'] == 'Fix authentication')
assert(titles['pane-2'] == 'Review schema')
assert(titles['pane-3'] == 'api')
''')

    def test_host_membership_keeps_targets_exact_and_disconnect_invalidates_live_phase(self) -> None:
        self.run_lua(r'''
local remote = 17592186044423
local panes = {
    {pane=7, kind='agent', tab=1, cwd='/work/api', title='Local'},
    {pane=remote, kind='agent', tab=2, cwd='/work/api', title='Remote'},
}
local agents = {
    {pane=7, state='working', cwd='/work/api'},
    {pane=remote, state='working', cwd='/work/api'},
}
local hosts = {
    {id=1, name='laptop', kind='local', state='connected', panes={7}},
    {id=2, name='fw-dev', kind='remote', state='stalled', panes={remote}},
}
local sessions = {{id=1,name='Local',host=1},{id=2,name='Project',host=2}}
local tabs = {{id=1,session=1},{id=2,session=2}}
local rows, targets = discovery.collect(panes, agents, hosts, sessions, tabs, {})
assert(#rows == 2)
for _, row in ipairs(rows) do
    if row.host == 'fw-dev' then
        assert(row.status == 'unknown' and row.session == 'Project')
        assert(targets[row.key].pane == remote and targets[row.key].session == 2)
    else
        assert(row.status == 'working' and targets[row.key].pane == 7)
    end
end
''')

    def test_exited_and_parked_agents_remain_inspectable_without_invented_session(self) -> None:
        self.run_lua(r'''
local rows, targets = discovery.collect(
    {{pane=9,kind='agent',parked=true,title='Codex',cwd='/repo',exited=2}},
    {{pane=9,command='codex',cwd='/repo',state='idle'}}, {}, {}, {}, {})
assert(rows[1].status == 'failed' and rows[1].parked)
assert(rows[1].session == 'Parked' and targets[rows[1].key].session == nil)
assert(discovery.clean('hello\27\nworld', 20) == 'hello world')
assert(discovery.clean('αβγδε', 3) == 'αβγ…')
''')


if __name__ == "__main__":
    unittest.main()
