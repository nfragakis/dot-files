import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "nfragakis.workspaces"

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }

    return null
  }

  function workspaceIds() {
    var highestVisibleId = root.defaultWorkspaceCount
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id <= 0) continue

      // Keep any existing workspace reachable, and reveal one additional
      // destination after the highest occupied workspace.
      highestVisibleId = Math.max(highestVisibleId, id)
      if (values[i].toplevels.values.length > 0)
        highestVisibleId = Math.max(highestVisibleId, id + 1)
    }

    var ids = []
    for (var workspaceId = 1; workspaceId <= highestVisibleId; workspaceId++)
      ids.push(workspaceId)

    return ids
  }

  function displayNumber(id) {
    return id === 10 ? "0" : String(id)
  }

  // Ghostty exposes tmux status in titles as:
  //   hostname ❐ SESSION_NAME ● N window_name
  // Read it directly from Quickshell's live Hyprland model so labels update
  // immediately without a polling process renaming the workspace itself.
  function tmuxSession(workspace) {
    if (workspace === null) return ""

    var toplevels = workspace.toplevels.values
    for (var i = 0; i < toplevels.length; i++) {
      var title = String(toplevels[i].title || "")
      var match = title.match(/❐\s+([^●]+?)\s+●/)
      if (match === null) continue

      return match[1]
        .replace(/^\s+|\s+$/g, "")
        .replace(/-[0-9]+$/, "")
    }

    return ""
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  readonly property int defaultWorkspaceCount: 5
  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)
  readonly property var hostWindow: root.QsWindow.window
  readonly property real screenWidth: hostWindow && hostWindow.screen ? hostWindow.screen.width : 0
  // QScreen dimensions are logical pixels, so this responds to both monitor
  // size and display scaling. A 5K Studio Display at 2x reports 2560px and
  // gets room for roughly six characters; a typical laptop stays compact.
  readonly property int sessionSlotUnits: screenWidth >= 2300
    ? 88
    : (screenWidth >= 1800 ? 74 : (screenWidth >= 1600 ? 64 : 56))
  readonly property int compactSlotUnits: screenWidth >= 2300 ? 38 : 34
  readonly property real workspaceSlotWidth: Style.space(sessionSlotUnits)
  readonly property real compactWorkspaceSlotWidth: Style.space(compactSlotUnits)
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
        readonly property int windowCount: workspace !== null ? workspace.toplevels.values.length : 0
        readonly property bool occupied: windowCount > 0
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData
        readonly property bool urgent: workspace !== null && workspace.urgent
        readonly property string numberText: root.displayNumber(modelData)
        readonly property string sessionName: root.tmuxSession(workspace)

        bar: root.bar
        text: ""
        labelVisible: false
        keepSpace: true
        hasVisualContent: true
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical
          ? root.barSize
          : (sessionName !== "" ? root.workspaceSlotWidth : root.compactWorkspaceSlotWidth)
        fixedHeight: root.barSize
        tooltipText: sessionName !== ""
          ? "Workspace " + numberText + " — tmux: " + sessionName
          : (occupied ? "Workspace " + numberText + " — " + windowCount + " window" + (windowCount === 1 ? "" : "s") : "Workspace " + numberText + " — empty")

        Rectangle {
          id: workspaceSurface
          anchors.fill: parent
          anchors.margins: Style.space(2)
          z: -1
          radius: Style.space(3)
          color: workspaceButton.focused
            ? Util.alpha(Color.accent, 0.11)
            : Util.alpha(workspaceButton.foreground, workspaceButton.occupied ? 0.16 : 0.01)
          border.width: Style.space(1)
          border.color: workspaceButton.focused
            ? Util.alpha(Color.accent, 0.85)
            : Util.alpha(workspaceButton.foreground, workspaceButton.occupied ? 0.46 : 0.13)

          Behavior on color {
            ColorAnimation { duration: 160 }
          }
        }

        Item {
          id: numberSlot
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          x: workspaceButton.sessionName !== "" && !root.vertical
            ? Style.space(5)
            : Math.round((parent.width - width) / 2)
          width: Style.space(10)

          Text {
            anchors.fill: parent
            text: workspaceButton.numberText
            color: workspaceButton.focused
              ? Util.alpha(Color.accent, 0.78)
              : Util.alpha(workspaceButton.foreground, workspaceButton.occupied ? 0.68 : 0.36)
            font.family: workspaceButton.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.bold: workspaceButton.focused
            renderType: Text.NativeRendering
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
          }
        }

        Rectangle {
          id: sessionDivider
          visible: workspaceButton.sessionName !== "" && !root.vertical
          anchors.left: numberSlot.right
          anchors.leftMargin: Style.space(2)
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(1)
          height: Style.font.body
          color: workspaceButton.focused
            ? Util.alpha(Color.accent, 0.48)
            : Util.alpha(workspaceButton.foreground, 0.28)
        }

        Item {
          visible: workspaceButton.sessionName !== "" && !root.vertical
          anchors.left: sessionDivider.right
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          anchors.leftMargin: Style.space(2)
          anchors.rightMargin: Style.space(4)
          clip: true

          Text {
            anchors.fill: parent
            text: workspaceButton.sessionName
            color: workspaceButton.focused ? Color.accent : workspaceButton.foreground
            font.family: workspaceButton.fontFamily
            font.pixelSize: Style.font.body
            font.bold: workspaceButton.focused
            renderType: Text.NativeRendering
            elide: Text.ElideRight
            maximumLineCount: 1
            wrapMode: Text.NoWrap
            horizontalAlignment: Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
          }
        }

        Rectangle {
          visible: workspaceButton.focused
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          anchors.leftMargin: Style.space(8)
          anchors.rightMargin: Style.space(8)
          anchors.bottomMargin: Style.space(3)
          height: Style.space(2)
          radius: height / 2
          color: Color.accent
        }

        Rectangle {
          visible: workspaceButton.urgent
          anchors.top: parent.top
          anchors.right: parent.right
          anchors.topMargin: Style.space(5)
          anchors.rightMargin: Style.space(5)
          width: Style.space(4)
          height: width
          radius: width / 2
          color: Color.urgent
        }

        onPressed: function() { root.focusWorkspace(modelData) }
      }
    }
  }
}
