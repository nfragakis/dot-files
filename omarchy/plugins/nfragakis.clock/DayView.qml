import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui

Item {
  id: root

  property date selectedDate: new Date()
  property var events: []
  property var tasks: []
  property bool selectedDayIsToday: false
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property string statusText: ""

  signal backRequested()
  signal openUrlRequested(string url)

  readonly property real sectionWidth: Style.space(420)
  readonly property real listCap: Style.space(184)

  implicitWidth: sectionWidth
  implicitHeight: content.implicitHeight

  function eventTarget(event) {
    return String(event.eventUrl || event.meetingUrl || "")
  }

  Column {
    id: content
    width: root.sectionWidth
    spacing: Style.space(8)

    Item {
      width: parent.width
      height: Math.max(backButton.implicitHeight, dateLabel.implicitHeight) + Style.space(4)

      PanelActionButton {
        id: backButton
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        iconText: "󰅁"
        tooltipText: "Back to month"
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.backRequested()
      }

      Text {
        id: dateLabel
        anchors.centerIn: parent
        text: Qt.formatDate(root.selectedDate, "dddd d MMMM").toUpperCase()
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        font.letterSpacing: 1
      }
    }

    Text {
      width: parent.width
      text: qsTr("EVENTS · %1").arg(root.events.length)
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
      font.letterSpacing: 1
    }

    ListView {
      id: eventList
      width: parent.width
      height: Math.min(Math.max(contentHeight, Style.space(48)), root.listCap)
      model: root.events
      spacing: Style.space(3)
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      interactive: contentHeight > height
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      delegate: Rectangle {
        id: eventRow
        required property var modelData

        width: ListView.view.width
        height: Style.space(45)
        radius: Style.cornerRadius
        color: eventMouse.containsMouse
          ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
          : "transparent"

        readonly property string targetUrl: root.eventTarget(modelData)
        readonly property bool openable: targetUrl !== ""
        readonly property bool joinable: String(modelData.meetingUrl || "") !== ""

        Rectangle {
          id: joinButton
          visible: eventRow.joinable
          anchors.right: parent.right
          anchors.rightMargin: Style.space(2)
          anchors.verticalCenter: parent.verticalCenter
          width: joinText.implicitWidth + Style.space(12)
          height: joinText.implicitHeight + Style.space(6)
          radius: height / 2
          color: joinMouse.containsMouse
            ? Style.selectedStateColor(root.foreground, Color.accent)
            : "transparent"
          border.width: Style.spacing.hairline
          border.color: joinMouse.containsMouse ? "transparent" : Qt.darker(root.foreground, 1.8)

          Text {
            id: joinText
            anchors.centerIn: parent
            text: qsTr("Join")
            color: joinMouse.containsMouse ? Color.background : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          MouseArea {
            id: joinMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.openUrlRequested(String(eventRow.modelData.meetingUrl))
          }
        }

        MouseArea {
          id: eventMouse
          anchors.left: parent.left
          anchors.right: eventRow.joinable ? joinButton.left : parent.right
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          anchors.rightMargin: eventRow.joinable ? Style.space(4) : 0
          hoverEnabled: true
          enabled: eventRow.openable
          cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
          onClicked: root.openUrlRequested(eventRow.targetUrl)

          Row {
            anchors.fill: parent
            spacing: Style.space(5)

            Rectangle {
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(3)
              height: Style.space(28)
              radius: width / 2
              color: eventRow.modelData.color || Color.accent
            }

            Text {
              width: Style.space(52)
              anchors.verticalCenter: parent.verticalCenter
              text: eventRow.modelData.allDay
                ? qsTr("All day")
                : Qt.formatDateTime(new Date(eventRow.modelData.start), "HH:mm")
              color: Qt.darker(root.foreground, 1.45)
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }

            Column {
              width: eventMouse.width - Style.space(65)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(1)

              Text {
                width: parent.width
                text: eventRow.modelData.title
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
              }

              Text {
                width: parent.width
                text: eventRow.modelData.location || eventRow.modelData.calendarName || ""
                visible: text !== ""
                color: Qt.darker(root.foreground, 1.8)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
          }
        }
      }

      Text {
        anchors.centerIn: parent
        visible: root.events.length === 0
        text: qsTr("Nothing scheduled")
        color: Qt.darker(root.foreground, 1.8)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    Text {
      width: parent.width
      text: qsTr("TODOIST · %1").arg(root.tasks.length)
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
      font.letterSpacing: 1
    }

    ListView {
      id: taskList
      width: parent.width
      height: Math.min(Math.max(contentHeight, Style.space(48)), root.listCap)
      model: root.tasks
      spacing: Style.space(3)
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      interactive: contentHeight > height
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      delegate: Rectangle {
        id: taskRow
        required property var modelData

        width: ListView.view.width
        height: Style.space(38)
        radius: Style.cornerRadius
        color: taskMouse.containsMouse
          ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
          : "transparent"

        MouseArea {
          id: taskMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.openUrlRequested(String(taskRow.modelData.url || ""))
        }

        Row {
          anchors.fill: parent
          spacing: Style.space(6)

          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(12)
            height: width
            radius: width / 2
            color: "transparent"
            border.width: Style.spacing.hairline
            border.color: taskRow.modelData.priority >= 4
              ? "#e5484d"
              : taskRow.modelData.priority === 3
                ? "#f5a623"
                : Qt.darker(root.foreground, 1.7)
          }

          Column {
            width: taskRow.width - Style.space(24)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(1)

            Text {
              width: parent.width
              text: taskRow.modelData.content
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }

            Text {
              width: parent.width
              visible: text !== ""
              text: taskRow.modelData.due || ""
              color: Qt.darker(root.foreground, 1.8)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }
        }
      }

      Text {
        anchors.centerIn: parent
        visible: root.tasks.length === 0
        text: root.selectedDayIsToday
          ? qsTr("No tasks due today or overdue")
          : qsTr("No tasks due on or before this day")
        color: Qt.darker(root.foreground, 1.8)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    Text {
      width: parent.width
      visible: root.statusText !== ""
      text: root.statusText
      color: Qt.darker(root.foreground, 1.9)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      horizontalAlignment: Text.AlignRight
      elide: Text.ElideLeft
    }
  }
}
