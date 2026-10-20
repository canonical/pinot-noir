// Notes and markdown export for the bug triage page.
//
// Ported from startriage's html report (startriage/data/report.html): notes
// are kept in localStorage per report for 31 days. The export is the full
// markdown of 'startriage triage --markdown FILE [--ai]' (headings, every item,
// the appended AI report), with each note below its item's block. Noted items
// missing from the markdown are listed after the triage part.
//
// Markup: a container with data-report-id, the markdown template in a
// json_script element with id "triage-markdown", items with data-url and
// data-label, a textarea.js-triage-note and an optional .js-triage-note-flag
// inside each item, and #triage-md-copy / #triage-md-save buttons with
// data-filename on the save button.
(function () {
  "use strict";

  var PREFIX = "pinot-noir-triage:";
  var MAX_AGE = 31 * 24 * 3600 * 1000;

  function load(key) {
    try {
      for (var i = localStorage.length - 1; i >= 0; i--) {
        var k = localStorage.key(i);
        if (k.indexOf(PREFIX) !== 0 || k === key) continue;
        var entry = JSON.parse(localStorage.getItem(k) || "{}");
        if (!entry.time || Date.now() - entry.time > MAX_AGE) localStorage.removeItem(k);
      }
      return JSON.parse(localStorage.getItem(key) || "{}");
    } catch (e) {
      return {};
    }
  }

  function save(key, notes) {
    try {
      localStorage.setItem(key, JSON.stringify({ time: Date.now(), notes: notes }));
    } catch (e) {
      // storage unavailable
    }
  }

  // The whole markdown, with each note at the end of its item's block.
  function markdown(template, items, notes) {
    var pending = {}; // url link -> note
    var labels = {};
    items.forEach(function (item) {
      var note = (notes[item.id] || "").trim();
      if (!note) return;
      var link = "](" + item.dataset.url + ")";
      pending[link] = note;
      labels[link] = item.dataset.label;
    });

    // blocks: a heading line and the lines up to the next heading
    var blocks = [];
    template.split("\n").forEach(function (line) {
      if (/^#+ /.test(line) || !blocks.length) blocks.push([]);
      blocks[blocks.length - 1].push(line);
    });

    var out = [];
    var aiStart = -1; // where startriage's "---" separator before the AI report is
    blocks.forEach(function (lines) {
      var rule = aiStart < 0 ? lines.indexOf("---") : -1;
      if (rule >= 0) aiStart = out.length + rule;
      var link = Object.keys(pending).find(function (l) {
        return lines[0].includes(l);
      });
      if (link === undefined) {
        out = out.concat(lines);
        return;
      }
      out = out.concat(lines.join("\n").trimEnd().split("\n"), "", pending[link], "");
      delete pending[link];
    });

    // items with notes the markdown doesn't have, before the AI report
    var extra = [];
    Object.keys(pending).forEach(function (link) {
      extra.push("", "#### [" + labels[link] + link, "", pending[link], "");
    });
    if (extra.length) {
      var at = aiStart < 0 ? out.length : aiStart;
      out = out.slice(0, at).concat(extra, [""], out.slice(at));
    }
    return out.join("\n").replace(/\n{3,}/g, "\n\n").trim() + "\n";
  }

  // Briefly show *text* as the button's label, keeping its icon.
  function flash(button, text) {
    var label = button.querySelector("span") || button;
    var old = label.textContent;
    label.textContent = text;
    setTimeout(function () {
      label.textContent = old;
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var container = document.querySelector("[data-report-id]");
    var templateElement = document.getElementById("triage-markdown");
    if (!container || !templateElement) return;

    var key = PREFIX + container.dataset.reportId;
    var template = JSON.parse(templateElement.textContent) || "";
    var notes = load(key).notes || {};
    var items = Array.prototype.slice.call(container.querySelectorAll("[data-url]"));

    items.forEach(function (item) {
      var textarea = item.querySelector("textarea.js-triage-note");
      var flag = item.querySelector(".js-triage-note-flag");
      if (!textarea) return;

      function update() {
        if (flag) flag.classList.toggle("u-hide", !textarea.value.trim());
      }

      textarea.value = notes[item.id] || "";
      update();
      textarea.addEventListener("input", function () {
        if (textarea.value) notes[item.id] = textarea.value;
        else delete notes[item.id];
        update();
        save(key, notes);
      });
    });

    var copyButton = document.getElementById("triage-md-copy");
    var saveButton = document.getElementById("triage-md-save");

    if (copyButton) {
      copyButton.addEventListener("click", function () {
        navigator.clipboard.writeText(markdown(template, items, notes)).then(
          function () {
            flash(copyButton, "Copied");
          },
          function () {
            flash(copyButton, "Copy failed");
          },
        );
      });
    }

    if (saveButton) {
      saveButton.addEventListener("click", function () {
        var link = document.createElement("a");
        link.href = URL.createObjectURL(
          new Blob([markdown(template, items, notes)], { type: "text/markdown" }),
        );
        link.download = saveButton.dataset.filename || "triage.md";
        link.click();
        URL.revokeObjectURL(link.href);
      });
    }
  });
})();
