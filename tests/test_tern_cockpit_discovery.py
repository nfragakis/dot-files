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

    def test_local_lifecycle_transitions_keep_remote_unknown_and_invalidate_provider_changes(self) -> None:
        self.run_lua(r'''
local directory = arg[1]:gsub("discovery%.luau$", "")
local remote, clock, serial, focused = 17592186044423, 0, 0, 7
local values, timers, events, snapshots = {}, {}, {}, {}
local open, cx
local panes = {
    {pane=7,kind="agent",program="claude",title="Same project",cwd="/same",tab=1},
    {pane=remote,kind="agent",program="claude",title="Same project",cwd="/same",tab=2},
}
local agents = {{pane=7,command="claude",state="idle"},{pane=remote,command="claude",state="idle"}}
local metadata = {
    session_id="exact-local-session",model="recorded-model",request="Exact local request",
    lifecycle={status="working",activity="Running Read",event="PreToolUse",observed_at="2020-01-01T00:00:00.000000Z"},
}
local function encode(value)
    serial=serial+1
    local key="json"..serial
    values[key]=value
    return key
end
local function decode(value) return assert(values[value]) end
local function clone(value)
    if type(value)~="table" then return value end
    local result={}
    for key,child in pairs(value) do result[key]=clone(child) end
    return result
end
local function pane(id)
    for _, item in ipairs(panes) do if item.pane==id then return item end end
end
local function row(id)
    for _, item in ipairs(assert(snapshots[#snapshots]).rows) do
        if item.key=="pane-"..string.format("%.0f",id) then return item end
    end
    error("missing exact pane")
end
local function event(name, value)
    for _, callback in ipairs(events[name] or {}) do callback(value,cx) end
end
local function advance(milliseconds)
    clock=clock+milliseconds
    for _=1,100 do
        local found
        for index,item in ipairs(timers) do if item.due<=clock then found=index break end end
        if not found then return end
        table.remove(timers,found).callback(cx)
    end
    error("unbounded timers")
end
cx={
    session={
        panes=function() return panes end,pane=function(_,id) return pane(id) end,
        tabs=function() return {{id=1,session=1},{id=2,session=2}} end,focused=function() return focused end,
        event=function(_,_,value)
            if value.act=="cockpit_snapshot" then snapshots[#snapshots+1]=decode(value.value) end
        end,
    },
    agents={list=function() return agents end},
    hosts={list=function() return {
        {id=1,name="local",kind="local",state="connected",panes={7,100}},
        {id=2,name="remote",kind="remote",state="connected",panes={remote}},
    } end},
    sessions={
        list=function() return {{id=1,name="Local",host=1},{id=2,name="Remote",host=2}} end,
        current=function() return {id=1} end,
    },
    layout={focus=function(_,id) focused=id end,float=function() return true end},
    new_block=function() panes[#panes+1]={pane=100,kind="block",title="Cockpit"} return 100 end,
}
local fixture={
    plugin={dir=directory},now=function() return clock end,
    timer=function(delay,callback) timers[#timers+1]={due=clock+delay,callback=callback} end,
    json={encode=encode,decode=decode,array=function(value) return value or {} end},
    on=function(name,callback) events[name]=events[name] or {} table.insert(events[name],callback) end,
    command=function(command) open=command.run end,route={link=function() end},
    process={run=function(_,options)
        local request=decode(options.stdin)
        local rows={}
        for _,item in ipairs(request.panes) do
            assert(item.pane=="7","window attempted remote metadata I/O")
            if item.provider=="claude" then rows[item.key]=clone(metadata) end
        end
        return {next=function(_,callback)
            timers[#timers+1]={due=clock+1,callback=function()
                callback({status=0,stdout=encode({rows=rows})},nil,cx)
            end}
        end}
    end},
}
local environment=setmetatable({tern=fixture,require=function() return discovery end},{__index=_G})
assert(loadfile(directory.."window.luau","t",environment))()
open(cx)
advance(1)
assert(row(7).status=="working" and row(7).activity=="Running Read")
assert(row(7).session_id=="exact-local-session" and row(7).model=="recorded-model")
assert(row(remote).status=="unknown" and row(remote).session_id==nil,"cross-pane metadata")
metadata.lifecycle={status="waiting_input",activity="Permission required",event="PermissionRequest",observed_at="2020-01-01T00:00:01.000000Z"}
advance(6000) advance(1)
assert(row(7).status=="waiting_input")
metadata.lifecycle={status="idle",activity="Ready",event="Stop",observed_at="2020-01-01T00:00:02.000000Z"}
advance(6000) advance(1)
assert(row(7).status=="idle")
assert(row(remote).status=="unknown" and row(remote).model==nil)
pane(7).exited=2
event("title",{pane=7}) advance(0)
assert(row(7).status=="failed","terminal exit must win over cached hook idle")
pane(7).exited=nil
agents[1].command="codex"
event("command_started",{pane=7,line="codex"}) advance(0)
assert(row(7).provider=="codex" and row(7).status=="unknown")
assert(row(7).model==nil and row(7).request==nil,"provider change retained stale metadata")
agents[1].command=nil
pane(7).program="omp"
cx.agents.transcript=function(_,id,options)
    assert(id==7 and options.last==30)
    return {
        {role="assistant",text="Old response"},
        {role="user",text=string.rep("request ",100)},
        {role="assistant",text="Latest "..string.rep("x",500)},
        {role="assistant",text=""},
    }
end
event("command_started",{pane=7,line="omp"}) advance(0)
assert(row(7).last_response==discovery.clean("Latest "..string.rep("x",500),300))
assert(row(7).request==discovery.clean(string.rep("request ",100),300))
''')


if __name__ == "__main__":
    unittest.main()
