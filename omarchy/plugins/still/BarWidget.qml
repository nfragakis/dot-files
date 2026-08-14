import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
    id: root

    readonly property bool remindersEnabled: setting("reminders", false) === true
    readonly property string reminderTimes: String(setting("reminderTimes", "10:00,15:00"))
    property string lastReminderKey: ""
    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

    function injectPanel() {
        var target = panelLoader.item;
        if (!target)
            return ;

        target.bar = root.bar;
        target.settings = root.settings;
        target.anchorItem = button;
        target.hostWidget = root;
    }

    function open() {
        if (panelLoader.item)
            panelLoader.item.open();

    }

    function close() {
        if (panelLoader.item)
            panelLoader.item.close();

    }

    function togglePanel() {
        if (panelLoader.item)
            panelLoader.item.toggle();

    }

    function closeForPopoutSwitch() {
        if (panelLoader.item)
            panelLoader.item.closeForPopoutSwitch();

    }

    function checkReminders() {
        if (!remindersEnabled || !root.bar)
            return ;

        var now = new Date();
        var hh = String(now.getHours()).padStart(2, "0");
        var mm = String(now.getMinutes()).padStart(2, "0");
        var time = hh + ":" + mm;
        var key = Qt.formatDate(now, "yyyy-MM-dd") + "T" + time;
        var configured = reminderTimes.split(",");
        for (var i = 0; i < configured.length; i++) {
            if (configured[i].trim() === time && lastReminderKey !== key) {
                lastReminderKey = key;
                root.bar.run("notify-send -a Still 'Take a breath' 'Open Still when you have a moment.'");
                return ;
            }
        }
    }

    moduleName: "still"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()

    Timer {
        interval: 30000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.checkReminders()
    }

    Loader {
        id: panelLoader

        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel();
            Qt.callLater(root.injectPanel);
        }
    }

    BarIconButton {
        id: button

        anchors.fill: parent
        bar: root.bar
        text: "○"
        tooltipText: "Still"
        active: root.opened
        onPressed: function(mouseButton) {
            root.togglePanel();
        }
    }

}
