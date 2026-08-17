const test = require("node:test")
const assert = require("node:assert/strict")
const Model = require("../Model.js")

test("month grid includes event dots", () => {
  const index = {
    "2026-08-17": [
      { color: "#ff0000" },
      { color: "#00ff00" },
      { color: "#ff0000" }
    ]
  }
  const weeks = Model.monthGrid(2026, 7, 1, "2026-08-17", index)
  const days = weeks.flatMap(week => week.days)
  const target = days.find(day => day.key === "2026-08-17")
  assert.equal(target.hasEvent, true)
  assert.deepEqual(target.dots, ["#ff0000", "#00ff00"])
})

test("event indexing returns selected date rows", () => {
  const rows = [{ dateKey: "2026-08-17", title: "One" }, { dateKey: "2026-08-18", title: "Two" }]
  const index = Model.indexEventsByDate(rows)
  assert.equal(Model.eventsForDateKey(index, "2026-08-17")[0].title, "One")
})

test("future day shows only tasks due on that day", () => {
  const tasks = [
    { id: "overdue", due: "2026-08-16", content: "Past" },
    { id: "today", due: "2026-08-17T09:00:00-05:00", content: "Now" },
    { id: "tomorrow", due: "2026-08-18", content: "Next" },
    { id: "later", due: "2026-08-19", content: "Later" }
  ]

  const visible = Model.tasksForDateKey(tasks, "2026-08-18", "2026-08-17")

  assert.deepEqual(visible.map(task => task.id), ["tomorrow"])
})

test("today includes overdue and today tasks but not future tasks", () => {
  const tasks = [
    { id: "overdue", due: "2026-08-16", content: "Past" },
    { id: "today", due: "2026-08-17T09:00:00-05:00", content: "Now" },
    { id: "tomorrow", due: "2026-08-18", content: "Next" }
  ]

  const visible = Model.tasksForDateKey(tasks, "2026-08-17", "2026-08-17")

  assert.deepEqual(visible.map(task => task.id), ["overdue", "today"])
})

test("open URL policy accepts trusted schemes only", () => {
  assert.equal(Model.safeOpenUrl("https://meet.google.com/abc"), "https://meet.google.com/abc")
  assert.equal(Model.safeOpenUrl("calendar:///?source-uid=a&comp-uid=b"), "calendar:///?source-uid=a&comp-uid=b")
  assert.equal(Model.safeOpenUrl("javascript:alert(1)"), "")
})
