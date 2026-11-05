from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tern/plugins/omarchy/window.luau"
HARNESS = r'''
local state = {
    host = 1, session = 10, focused = 2,
    panes = {
        [1] = {pane=1, tab=12},
        [2] = {pane=2, tab=12},
        [3] = {pane=3, tab=12},
        [77] = {pane=77, tab=99},
    },
    layouts = {[12] = {root={split='right',ratio=0.5,[1]={pane=1},[2]={pane=2}}}},
    next = {left={[2]=1,[3]=2}, right={[1]=2}, up={}, down={}},
    actions = {}, commands = {}, effects = {}, timers = {}, dispatches = {}, toasts = {}, logs = {}, moves = {},
    session_rows = {{current=true,tabs={12}}},
    processes = {}, environment = {XDG_RUNTIME_DIR='/run/test'},
}
local cx
cx = {
    hosts = {
        current=function() return {id=state.host} end,
        list=function() return {{kind='local',panes={77}}} end,
    },
    sessions = {current=function() return {id=state.session} end},
    session = {
        focused=function() return state.focused end,
        pane=function(_, spec)
            if spec == '@focused' then return state.panes[state.focused] end
            if state.remote_ids then assert(spec == 77, 'Numeric remote pane lookup is not round-trip safe') end
            return state.panes[spec]
        end,
        layout=function(_, tab) return state.layouts[tab] end,
        sessions=function() return state.session_rows end,
        panes=function()
            local rows = {}
            for _, pane in pairs(state.panes) do rows[#rows+1]=pane end
            return rows
        end,
    },
    layout = {
        move=function(_, from, target, direction)
            assert(direction=='swap', 'Reparenting is not a swap')
            state.moves[#state.moves+1]={from=from,target=target,direction=direction}
            if state.swap_result==false then return false end
            local function swap_leaves(node)
                if node.pane==from then node.pane=target
                elseif node.pane==target then node.pane=from
                elseif node[1] then swap_leaves(node[1]); swap_leaves(node[2]) end
            end
            swap_leaves(state.layouts[12].root)
            return true
        end,
    },
    canvas = {list=function() return {} end},
    action=function(_, action)
        state.actions[#state.actions+1] = action
        local resize=action:match('^resize_split:(%w+)$')
        if resize and state.layouts[12] then
            local horizontal=resize=='left' or resize=='right'
            local function nearest(node, divider)
                if node.pane then return node.pane==state.focused, divider end
                if not node[1] then return false end
                local current=node.split==(horizontal and 'right' or 'down') and node or divider
                local found, split=nearest(node[1],current)
                if found then return true,split end
                return nearest(node[2],current)
            end
            local _,split=nearest(state.layouts[12].root)
            if split then
                local delta=(resize=='right' or resize=='down') and 0.05 or -0.05
                split.ratio=split.ratio+delta
            end
        end
        local dir=action:match('^focus_pane:(%w+)$')
        if dir then
            state.effects[#state.effects+1]=function()
                state.focused=state.next[dir][state.focused] or state.focused
            end
        end
    end,
    command=function(_, command) state.commands[#state.commands+1]=command end,
    toast=function(_, ...) state.toasts[#state.toasts+1]={...} end,
}
local modules = {
    ['./lib/agents']={start=function() end},
    ['./lib/heartbeat']={start=function() end},
    ['./lib/geometry']={
        rects=function(tree)
            if tree.rects then return tree.rects end
            local rects={}
            local function walk(node,x,y,w,h)
                if node.pane then rects[node.pane]={x=x,y=y,w=w,h=h};return end
                local r=node.ratio or 0.5
                if node.split=='down' then
                    walk(node[1],x,y,w,h*r);walk(node[2],x,y+h*r,w,h*(1-r))
                else
                    walk(node[1],x,y,w*r,h);walk(node[2],x+w*r,y,w*(1-r),h)
                end
            end
            walk(tree,0,0,1,1)
            return rects
        end,
        neighbor=function(rects, pane, dir)
            local c=rects[pane]
            if c.neighbors then return c.neighbors[dir] end
            for id,r in pairs(rects) do
                if id~=pane then
                    local horizontal=math.min(c.y+c.h,r.y+r.h)>math.max(c.y,r.y)
                    local vertical=math.min(c.x+c.w,r.x+r.w)>math.max(c.x,r.x)
                    if (dir=='l' and horizontal and r.x+r.w<=c.x+1e-6)
                        or (dir=='r' and horizontal and r.x>=c.x+c.w-1e-6)
                        or (dir=='u' and vertical and r.y+r.h<=c.y+1e-6)
                        or (dir=='d' and vertical and r.y>=c.y+c.h-1e-6) then return id end
                end
            end
        end,
    },
    ['./lib/hypr']={
        TERN_CLASS='so.stencil.tern',
        dispatch=function(expr) state.dispatches[#state.dispatches+1]=expr end,
        active=function(callback) state.active=callback end,
        press=function() end,
    },
}
require=function(name) return assert(modules[name], name) end
local binds={}
tern={
    bind=function(chord, fn) binds[chord]=fn end,
    timer=function(_, callback) state.timers[#state.timers+1]=callback end,
    log={warn=function(...) state.logs[#state.logs+1]={...} end},
    getenv=function(key) return state.environment[key] end,
    json={decode=function(out) assert(out=='native-tree'); return state.tree end},
    process={run=function(argv, options, callback)
        if state.spawn_error then error(state.spawn_error) end
        state.processes[#state.processes+1]={argv=argv,options=options,callback=callback}
    end},
}
local function flush()
    local count=0
    while #state.effects>0 or #state.timers>0 do
        count=count+1
        assert(count<100, 'Callbacks did not finish')
        local effects=state.effects
        state.effects={}
        for _, effect in ipairs(effects) do effect() end
        if #state.timers>0 then table.remove(state.timers,1)(cx) end
    end
end
local function press(chord) assert(type(binds[chord])=='function'); binds[chord](cx) end
local function complete(tree, result)
    state.tree=tree
    local process=table.remove(state.processes,1)
    assert(process,'No native geometry query is pending')
    process.callback(result or {status=0,stdout='native-tree'},cx)
end
dofile(arg[1])
'''


@unittest.skipUnless(shutil.which("lua"), "Lua is required for the Omarchy action regression seam")
class TernOmarchyActionsTest(unittest.TestCase):
    def run_lua(self, body: str) -> None:
        result = subprocess.run(
            ["lua", "-", str(ENTRY)], input=HARNESS + body,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_focus_checks_fresh_context_before_bubbling_at_edge(self) -> None:
        self.run_lua(r'''
press('cmd+left')
assert(state.focused==2 and #state.dispatches==0)
flush()
assert(state.focused==1 and #state.dispatches==0)
press('cmd+left')
flush()
assert(#state.dispatches==1 and state.dispatches[1]:find('direction = "l"',1,true))
''')

    def test_focus_bubble_does_not_cross_an_async_host_or_session_switch(self) -> None:
        self.run_lua(r'''
press('cmd+right')
state.host=0
flush()
assert(#state.dispatches==0)
state.host=1
press('cmd+right')
state.session=11
flush()
assert(#state.dispatches==0)
''')

    def test_vertical_focus_and_host_edge_use_the_same_native_path(self) -> None:
        self.run_lua(r'''
state.next.up={[2]=1}
state.next.down={[1]=2}
press('cmd+up')
flush()
assert(state.focused==1 and #state.dispatches==0)
press('cmd+down')
flush()
assert(state.focused==2 and #state.dispatches==0)
press('cmd+down')
flush()
assert(#state.dispatches==1 and state.dispatches[1]:find('direction = "d"',1,true))
''')

    def test_entry_walks_natively_to_opposite_edge(self) -> None:
        self.run_lua(r'''
state.focused=3
press('cmd+ctrl+shift+right')
flush()
assert(state.focused==1 and #state.dispatches==0)
assert(#state.actions==3)
''')

    def test_swap_preserves_nested_split_topology_and_ratios(self) -> None:
        self.run_lua(r'''
local root={split='right',ratio=0.6,[1]={pane=1},[2]={split='down',ratio=0.3,[1]={pane=2},[2]={pane=3}}}
state.layouts[12].root=root
state.focused=1
press('cmd+ctrl+shift+d')
assert(#state.actions==0 and #state.moves==1 and #state.dispatches==0)
assert(root.split=='right' and root.ratio==0.6 and root[1].pane==2)
assert(root[2].split=='down' and root[2].ratio==0.3 and root[2][1].pane==1 and root[2][2].pane==3)
press('cmd+ctrl+shift+s')
assert(#state.moves==2 and root[2][1].pane==3 and root[2][2].pane==1)
press('cmd+ctrl+shift+d')
assert(#state.moves==2 and #state.dispatches==1)
''')

    def test_rejected_local_swap_reports_failure_without_host_fallback(self) -> None:
        self.run_lua(r'''
state.swap_result=false
press('cmd+ctrl+shift+a')
assert(#state.moves==1 and #state.toasts==1 and #state.logs==1)
assert(#state.actions==0 and #state.dispatches==0)
''')

    def test_unresolvable_swap_uses_native_move_without_window_fallback(self) -> None:
        self.run_lua(r'''
state.panes[1]=nil
press('cmd+ctrl+shift+a')
assert(#state.moves==0 and state.actions[1]=='move_pane:left')
assert(#state.toasts==0 and #state.logs==0 and #state.dispatches==0)
''')

    def test_resize_grows_and_shrinks_both_sides_of_each_axis(self) -> None:
        self.run_lua(r'''
for _,axis in ipairs({'right','down'}) do
    local grow=axis=='right' and 'o' or 'u'
    local shrink=axis=='right' and 'y' or 'i'
    for _,focused in ipairs({1,2}) do
        local root={split=axis,ratio=0.5,[1]={pane=1},[2]={pane=2}}
        state.layouts[12].root=root
        state.focused=focused
        press('cmd+ctrl+shift+'..grow)
        assert(math.abs(root.ratio-(focused==1 and 0.55 or 0.45))<1e-6)
        press('cmd+ctrl+shift+'..shrink)
        assert(math.abs(root.ratio-0.5)<1e-6)
    end
end
assert(#state.dispatches==0 and #state.toasts==0)
''')

    def test_interior_resize_uses_nearest_native_split_not_outer_edge(self) -> None:
        self.run_lua(r'''
local inner={split='right',ratio=0.5,[1]={pane=2},[2]={pane=3}}
state.layouts[12].root={split='right',ratio=0.5,[1]={pane=1},[2]=inner}
press('cmd+ctrl+shift+o')
assert(state.actions[1]=='resize_split:right' and math.abs(inner.ratio-0.55)<1e-6)
state.layouts[12].root={split='right',ratio=0.5,[1]={split='right',ratio=0.5,[1]={pane=1},[2]={pane=2}},[2]={pane=3}}
press('cmd+ctrl+shift+o')
assert(state.actions[2]=='resize_split:left')
assert(math.abs(state.layouts[12].root[1].ratio-0.45)<1e-6)
''')

    def test_resize_bubbles_only_when_requested_axis_has_no_divider(self) -> None:
        self.run_lua(r'''
press('cmd+ctrl+shift+l')
assert(#state.actions==4 and state.actions[4]=='resize_split:left')
press('cmd+ctrl+shift+j')
assert(#state.dispatches==1 and state.dispatches[1]:find('window.resize',1,true))
''')

    def test_missing_native_topology_queries_exact_window_then_uses_native_move(self) -> None:
        self.run_lua(r'''
state.layouts={}
state.remote_ids=true
press('cmd+ctrl+shift+a')
assert(#state.actions==0 and #state.dispatches==0)
local query=state.processes[1]
assert(table.concat(query.argv,' ')=='tern ctl tree .tn-pane')
assert(query.options.env.TERN_PANE=='2')
assert(query.options.env.TERN_PANE_SOCKET=='/run/test/tern/daemon.sock')
complete({ok=true,nodes={
    {class='tn-pane multi dim',rect={3,37,1300,1366}},
    {class='tn-pane multi on',rect={1303,37,1252,1366}},
    {class='tn-pane pip on',rect={1,1,100,100}},
    {class='tn-pane dim',rect={0,0,0,0}},
}})
assert(state.actions[1]=='move_pane:left')
assert(#state.moves==0 and #state.toasts==0 and #state.dispatches==0)
''')

    def test_focused_pane_anchors_geometry_when_local_ids_do_not_round_trip(self) -> None:
        self.run_lua(r'''
state.layouts={}
state.panes[77]=nil
press('cmd+enter')
state.active({class='so.stencil.tern',size={1600,900}},cx)
assert(#state.processes==1, 'focused pane should anchor the owning window control query')
local query=state.processes[1]
assert(query.options.env.TERN_PANE=='2')
complete({ok=true,nodes={
    {class='tn-pane multi dim',rect={0,0,800,900}},
    {class='tn-pane multi on',rect={800,0,800,900}},
}})
assert(state.commands[1]=='split_down' and #state.toasts==0)
''')

    def test_remote_resize_preserves_grow_semantics_on_boundary_panes(self) -> None:
        self.run_lua(r'''
state.layouts={}
state.remote_ids=true
for _,case in ipairs({
    {rect={0,0,800,900},other={800,0,800,900},grow='o',shrink='y',direction='right',opposite='left'},
    {rect={800,0,800,900},other={0,0,800,900},grow='o',shrink='y',direction='left',opposite='right'},
    {rect={0,0,1600,450},other={0,450,1600,450},grow='u',shrink='i',direction='down',opposite='up'},
    {rect={0,450,1600,450},other={0,0,1600,450},grow='u',shrink='i',direction='up',opposite='down'},
}) do
    local tree={ok=true,nodes={{class='tn-pane on',rect=case.rect},{class='tn-pane dim',rect=case.other}}}
    press('cmd+ctrl+shift+'..case.grow)
    complete(tree)
    assert(state.actions[#state.actions]=='resize_split:'..case.direction)
    press('cmd+ctrl+shift+'..case.shrink)
    complete(tree)
    assert(state.actions[#state.actions]=='resize_split:'..case.opposite)
end
assert(#state.toasts==0 and #state.dispatches==0 and #state.moves==0)
''')

    def test_remote_interior_resize_refuses_to_guess_split_ancestry(self) -> None:
        self.run_lua(r'''
state.layouts={}
state.remote_ids=true
press('cmd+ctrl+shift+o')
complete({ok=true,nodes={
    {class='tn-pane dim',rect={0,0,400,900}},
    {class='tn-pane on',rect={400,0,400,900}},
    {class='tn-pane dim',rect={800,0,800,900}},
}})
assert(#state.toasts==1 and #state.logs==1 and #state.actions==0 and #state.dispatches==0)
assert(state.toasts[1][3]:find('nearest divider',1,true))
''')

    def test_unavailable_control_geometry_is_reported_without_host_fallback(self) -> None:
        self.run_lua(r'''
state.layouts={}
press('cmd+ctrl+shift+a')
complete(nil,{status=1,stderr='no owning endpoint'})
assert(#state.toasts==1 and #state.logs==1)
assert(#state.actions==0 and #state.dispatches==0)
state.panes[77]=nil
press('cmd+ctrl+shift+l')
complete(nil,{status=1,stderr='no owning endpoint'})
assert(#state.processes==0 and #state.toasts==2)
''')

    def test_high_tab_resize_and_split_use_physical_native_rectangles(self) -> None:
        self.run_lua(r'''
state.layouts={}
local tree={ok=true,nodes={
    {class='tn-pane multi dim',rect={0,0,800,900}},
    {class='tn-pane multi on',rect={800,0,800,900}},
}}
press('cmd+ctrl+shift+l')
complete(tree)
assert(#state.actions==4 and state.actions[4]=='resize_split:left')
press('cmd+ctrl+shift+j')
complete(tree)
assert(#state.dispatches==1 and state.dispatches[1]:find('window.resize',1,true))
press('cmd+enter')
state.active({class='so.stencil.tern',size={1600,900}},cx)
assert(#state.commands==0)
complete(tree)
assert(state.commands[1]=='split_down' and #state.toasts==0)
''')

    def test_native_geometry_result_is_discarded_after_context_changes(self) -> None:
        self.run_lua(r'''
state.layouts={}
press('cmd+ctrl+shift+l')
state.host=0
complete({ok=true,nodes={}})
assert(#state.actions==0 and #state.dispatches==0 and #state.toasts==0)
state.host=1
press('cmd+ctrl+shift+a')
state.focused=1
complete({ok=true,nodes={}})
assert(#state.actions==0 and #state.dispatches==0 and #state.toasts==0)
state.focused=2
press('cmd+ctrl+shift+a')
state.session=11
complete({ok=true,nodes={}})
assert(#state.actions==0 and #state.dispatches==0 and #state.toasts==0)
''')

    def test_invalid_native_geometry_is_never_treated_as_a_host_edge(self) -> None:
        self.run_lua(r'''
state.layouts={}
press('cmd+ctrl+shift+a')
complete({ok=true,nodes={{class='tn-pane pip on',rect={0,0,800,900}}}})
assert(#state.toasts==1 and #state.actions==0 and #state.dispatches==0)
press('cmd+ctrl+shift+a')
complete({ok=true,nodes={
    {class='tn-pane on',rect={0,0,800,900}},
    {class='tn-pane on',rect={800,0,800,900}},
}})
assert(#state.toasts==2 and #state.actions==0 and #state.dispatches==0)
''')

    def test_query_start_and_decode_errors_are_reported(self) -> None:
        self.run_lua(r'''
state.layouts={}
state.spawn_error='tern executable missing'
press('cmd+ctrl+shift+a')
assert(#state.processes==0 and #state.toasts==1)
state.spawn_error=nil
press('cmd+ctrl+shift+a')
complete(nil,{status=0,stdout='malformed-json'})
assert(#state.toasts==2 and #state.actions==0 and #state.dispatches==0)
''')

    def test_split_uses_native_fresh_context_and_current_host(self) -> None:
        self.run_lua(r'''
press('cmd+enter')
assert(#state.commands==0)
state.active({class='so.stencil.tern',size={1600,900}},cx)
assert(state.commands[1]=='split_down')
press('cmd+enter')
state.host=0
state.active({class='so.stencil.tern',size={1600,900}},cx)
assert(#state.commands==1)
''')

    def test_split_ignores_stale_focus_and_reports_missing_geometry(self) -> None:
        self.run_lua(r'''
press('cmd+enter')
state.focused=1
state.active({class='so.stencil.tern',size={1600,900}},cx)
assert(#state.commands==0)
press('cmd+enter')
state.active(nil,cx)
assert(#state.commands==0 and #state.toasts==1 and #state.logs==1)
''')

    def test_close_counts_only_current_session(self) -> None:
        self.run_lua(r'''
state.panes[3]={pane=3,tab=99}
press('cmd+w')
assert(state.commands[1]=='close_pane' and #state.dispatches==0)
state.panes[1]=nil
press('cmd+w')
assert(#state.dispatches==1 and state.dispatches[1]:find('window.close',1,true))
''')


if __name__ == "__main__":
    unittest.main()
