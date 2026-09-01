import QtQuick 2.15
import QtTest 1.3
import "../.." as Omamail

Item {
  width: 400
  height: 300

  QtObject {
    id: shellStore

    property string updatedId: ""
    property var updatedEntry: null

    function updateEntryInline(id, entry) {
      updatedId = String(id)
      updatedEntry = entry
    }
  }

  Omamail.Service {
    id: mailService
    shell: shellStore
    manifest: ({ id: "omamail", __sourceDir: "/tmp/omamail-test" })
  }

  TestCase {
    name: "ServiceSettings"

    function test_unified_calendar_setting_defaults_on_and_persists_changes() {
      mailService.applySettings({})
      compare(mailService.unifiedCalendarView, true)

      mailService.setUnifiedCalendarView(false)
      compare(mailService.unifiedCalendarView, false)
      compare(shellStore.updatedId, "omamail")
      verify(shellStore.updatedEntry !== null)
      compare(shellStore.updatedEntry.unifiedCalendarView, false)
    }
  }
}
