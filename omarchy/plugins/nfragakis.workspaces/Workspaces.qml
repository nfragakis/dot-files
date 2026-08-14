import QtQuick
import QtQuick.Layouts
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }

    return null
  }

  function workspaceIds() {
    var ids = [1, 2, 3, 4, 5]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && id <= 10 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function workspaceLabel(id, workspace) {
    var fallback = id === 10 ? "0" : String(id)
    if (root.vertical || workspace === null) return fallback

    var name = String(workspace.name || "")
    return name.length > 0 ? name : fallback
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)
  readonly property real workspaceSlotWidth: Style.space(64)
  readonly property real workspaceGap: Style.space(5)

  implicitWidth: grid.implicitWidth + trailingGap
  implicitHeight: grid.implicitHeight

  GridLayout {
    id: grid
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    columns: root.vertical ? 1 : root.workspaceIds().length
    columnSpacing: root.vertical ? 0 : root.workspaceGap
    rowSpacing: root.vertical ? Style.space(2) : 0

    Repeater {
      model: root.workspaceIds()

      WidgetButton {
        id: workspaceButton

        required property int modelData

        readonly property var workspace: root.workspaceById(modelData)
        readonly property bool occupied: workspace !== null && workspace.toplevels.values.length > 0
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData
        readonly property string workspaceLabel: root.workspaceLabel(modelData, workspace)

        bar: root.bar
        text: workspaceLabel
        fontSize: Style.font.subtitle
        active: focused
        useActiveColor: true
        opacity: focused ? 1 : (occupied ? 0.95 : 0.45)
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical ? root.barSize : root.workspaceSlotWidth
        fixedHeight: root.barSize
        tooltipText: workspace !== null ? String(workspace.name || "") : ""

        Rectangle {
          anchors.fill: parent
          anchors.margins: Style.space(2)
          z: -1
          radius: Style.space(3)
          color: workspaceButton.focused
            ? Util.alpha(workspaceButton.activeColor, 0.16)
            : Util.alpha(workspaceButton.foreground, workspaceButton.occupied ? 0.18 : 0.02)
          border.width: workspaceButton.focused ? Style.space(2) : Style.space(1)
          border.color: workspaceButton.focused
            ? workspaceButton.activeColor
            : Util.alpha(workspaceButton.foreground, workspaceButton.occupied ? 0.55 : 0.16)

          Behavior on color {
            ColorAnimation { duration: 160 }
          }
        }

        onPressed: function() { root.focusWorkspace(modelData) }
      }
    }
  }
}
