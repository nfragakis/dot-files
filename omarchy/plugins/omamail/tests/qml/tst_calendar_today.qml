import QtQuick 2.15
import QtTest 1.3
import "../../components" as Omamail

Item {
  width: 900
  height: 600

  QtObject {
    id: calendarController

    property bool sourcesLoaded: false
    property bool loading: false
    property bool clockRunning: false
    property double nowMs: new Date(2026, 8, 1, 23, 59).getTime()
    property var events: []
    property string lastError: ""
    property string lastErrorKind: ""

    function refresh(_startMs, _endMs) {}
    function colorKeyFor(_sourceId) { return "accent" }
  }

  Omamail.CalendarView {
    id: calendarView
    anchors.fill: parent
    controller: calendarController
    textColor: Qt.rgba(1, 1, 1, 1)
    backgroundColor: Qt.rgba(0.06, 0.06, 0.06, 1)
    accentColor: Qt.rgba(1, 0.5, 0, 1)
    urgentColor: Qt.rgba(1, 0.2, 0.2, 1)
    dimColor: Qt.rgba(0.67, 0.67, 0.67, 1)
    calendarBorderColor: Qt.rgba(0.3, 0.3, 0.3, 1)
    calendarTodayBackgroundColor: Qt.rgba(1, 0.5, 0, 0.2)
    calendarBorderWidth: 1
    panelFontFamily: "monospace"
  }

  TestCase {
    name: "CalendarToday"
    when: windowShown

    function init() {
      calendarController.nowMs = new Date(2026, 8, 1, 23, 59).getTime()
      calendarView.viewMode = "week"
    }

    function test_today_follows_the_running_clock_across_midnight() {
      compare(calendarView.todayIso, "2026-09-01")

      calendarController.nowMs = new Date(2026, 8, 2, 0, 1).getTime()

      tryCompare(calendarView, "todayIso", "2026-09-02")
    }

    function test_the_clock_keeps_running_in_month_view() {
      calendarView.viewMode = "month"
      tryCompare(calendarController, "clockRunning", true)
    }

    function test_go_to_today_refreshes_the_clock_immediately() {
      calendarView.goToday()

      var now = new Date()
      var month = now.getMonth() + 1
      var day = now.getDate()
      var expected = now.getFullYear() + "-" + (month < 10 ? "0" : "") + month
        + "-" + (day < 10 ? "0" : "") + day
      compare(calendarView.todayIso, expected)
    }
  }
}
