/* MIS Portal — Bookmarks (added Nov 20, 2026, at Steven's direction)
   The bookmarks idea, borrowed from his AntiGravity page: star any link on
   the portal and it is saved to a "My bookmarks" shelf. Bookmarks live only
   in this browser (localStorage), the same rule as the notebook links and
   study notes already on this page. Nothing is uploaded anywhere. */
(function () {
  "use strict";
  var KEY = "misPortalBookmarks";

  function load() {
    try {
      var raw = JSON.parse(localStorage.getItem(KEY) || "[]");
      return Array.isArray(raw) ? raw.filter(function (b) { return b && b.url; }) : [];
    } catch (e) { return []; }
  }
  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
  }
  function titleFor(a) {
    var strong = a.querySelector("strong");
    var t = (strong ? strong.textContent : a.textContent) || a.href;
    t = t.replace(/\s+/g, " ").replace(/↗/g, "").trim();
    return t.length > 70 ? t.slice(0, 67) + "…" : t;
  }
  function isBookmarkable(a) {
    var href = a.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#") return false;
    if (/^(javascript:|mailto:)/i.test(href)) return false;
    return true;
  }

  var style = document.createElement("style");
  style.textContent =
    ".bm-toggle{margin-left:.35em;border:1px solid currentColor;background:transparent;color:inherit;" +
    "border-radius:999px;font-size:.85em;line-height:1;padding:.15em .45em;cursor:pointer;vertical-align:middle}" +
    ".bm-toggle[aria-pressed=\"true\"]{background:#f5b301;color:#1a1a1a;border-color:#f5b301}" +
    ".bm-remove{margin-left:.35em;border:none;background:transparent;color:inherit;cursor:pointer;font-size:1em}";
  document.head.appendChild(style);

  var bookmarks = load();
  var urls = {};
  bookmarks.forEach(function (b) { urls[b.url] = true; });

  var listEl = document.getElementById("bookmark-list");
  var emptyEl = document.getElementById("bookmark-empty");

  function renderShelf() {
    if (!listEl) return;
    listEl.innerHTML = "";
    bookmarks.forEach(function (b) {
      var a = document.createElement("a");
      a.className = "button notebook-button";
      a.href = b.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = b.title + " ↗";
      var x = document.createElement("button");
      x.type = "button";
      x.className = "bm-remove";
      x.title = "Remove bookmark";
      x.setAttribute("aria-label", "Remove bookmark: " + b.title);
      x.textContent = "×";
      x.addEventListener("click", function (ev) {
        ev.preventDefault(); ev.stopPropagation();
        toggle(b.url, b.title);
      });
      var wrap = document.createElement("span");
      wrap.appendChild(a); wrap.appendChild(x);
      listEl.appendChild(wrap);
    });
    if (emptyEl) emptyEl.style.display = bookmarks.length ? "none" : "";
  }

  var toggles = [];
  function paint() {
    toggles.forEach(function (t) {
      var on = !!urls[t.url];
      t.btn.textContent = on ? "★" : "☆";
      t.btn.setAttribute("aria-pressed", on ? "true" : "false");
      t.btn.title = on ? "Remove bookmark" : "Bookmark this link";
    });
    renderShelf();
  }

  function toggle(url, title) {
    if (urls[url]) {
      delete urls[url];
      bookmarks = bookmarks.filter(function (b) { return b.url !== url; });
    } else {
      urls[url] = true;
      bookmarks.push({ url: url, title: title });
    }
    save(bookmarks);
    paint();
  }

  document.querySelectorAll("main a[href]").forEach(function (a) {
    if (!isBookmarkable(a)) return;
    if (a.closest("#bookmarks")) return;
    var url = a.href;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "bm-toggle";
    btn.setAttribute("aria-label", "Bookmark this link");
    btn.addEventListener("click", function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      toggle(url, titleFor(a));
    });
    toggles.push({ url: url, btn: btn });
    a.insertAdjacentElement("afterend", btn);
  });

  paint();
})();
