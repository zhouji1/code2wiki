/* code2wiki viewer.
 *
 * Two modes, auto-detected:
 *  - Embedded (static build): window.WIKI_DATA (manifest) and window.WIKI_CONTENT
 *    (map of file path -> raw markdown) are present. Everything renders offline.
 *  - Served (live preview): no embedded data; fetch wiki.json and page markdown
 *    from the server, and poll /__mtime to auto-reload when files change.
 */
(function () {
  "use strict";

  var EMBEDDED = typeof window.WIKI_DATA !== "undefined";
  var manifest = EMBEDDED ? window.WIKI_DATA : null;
  var contentCache = {}; // file -> markdown string
  if (EMBEDDED && window.WIKI_CONTENT) contentCache = window.WIKI_CONTENT;

  var pageEl = document.getElementById("page");
  var navTree = document.getElementById("nav-tree");
  var searchEl = document.getElementById("search");
  var footerEl = document.getElementById("sidebar-footer");
  var sidebar = document.getElementById("sidebar");

  // ---- markdown / diagram setup -------------------------------------------
  if (window.marked) {
    marked.setOptions({
      gfm: true,
      breaks: false,
      highlight: function (code, lang) {
        if (window.hljs) {
          try {
            return lang && hljs.getLanguage(lang)
              ? hljs.highlight(code, { language: lang }).value
              : hljs.highlightAuto(code).value;
          } catch (e) { /* fall through */ }
        }
        return code;
      },
    });
  }
  if (window.mermaid) {
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default", securityLevel: "loose" });
  }

  // ---- helpers ------------------------------------------------------------
  function flatPages() {
    var out = [];
    (manifest.sections || []).forEach(function (s) {
      (s.pages || []).forEach(function (p) { out.push({ section: s, page: p }); });
    });
    return out;
  }

  function parseFrontMatter(md) {
    var meta = {};
    var body = md;
    var m = /^---\s*\n([\s\S]*?)\n---\s*\n?/.exec(md);
    if (m) {
      body = md.slice(m[0].length);
      m[1].split("\n").forEach(function (line) {
        var idx = line.indexOf(":");
        if (idx === -1) return;
        var key = line.slice(0, idx).trim();
        var val = line.slice(idx + 1).trim();
        if (/^\[.*\]$/.test(val)) {
          val = val.slice(1, -1).split(",").map(function (s) { return s.trim(); }).filter(Boolean);
        }
        meta[key] = val;
      });
    }
    return { meta: meta, body: body };
  }

  function getContent(file) {
    if (contentCache[file] !== undefined) return Promise.resolve(contentCache[file]);
    // served mode: fetch from disk
    return fetch(file, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (t) { contentCache[file] = t; return t; })
      .catch(function () { return "# Not found\n\nCould not load `" + file + "`."; });
  }

  // ---- navigation ---------------------------------------------------------
  function buildNav() {
    navTree.innerHTML = "";
    (manifest.sections || []).forEach(function (s) {
      var sec = document.createElement("div");
      sec.className = "nav-section";
      sec.dataset.section = s.id;

      var title = document.createElement("div");
      title.className = "nav-section-title";
      title.textContent = s.title;
      sec.appendChild(title);

      (s.pages || []).forEach(function (p) {
        var a = document.createElement("a");
        a.className = "nav-page";
        a.textContent = p.title;
        a.href = "#" + s.id + "/" + p.id;
        a.dataset.key = s.id + "/" + p.id;
        a.dataset.search = (p.title + " " + s.title).toLowerCase();
        sec.appendChild(a);
      });
      navTree.appendChild(sec);
    });
  }

  function highlightNav(key) {
    var links = navTree.querySelectorAll(".nav-page");
    for (var i = 0; i < links.length; i++) {
      links[i].classList.toggle("active", links[i].dataset.key === key);
    }
  }

  // ---- rendering ----------------------------------------------------------
  function renderMeta(meta) {
    if (!meta || !Object.keys(meta).length) return "";
    var bits = [];
    if (meta.source_files) {
      var sf = Array.isArray(meta.source_files) ? meta.source_files : [meta.source_files];
      if (sf.length) bits.push("Sources: " + sf.map(function (f) { return "<code>" + escapeHtml(f) + "</code>"; }).join(", "));
    }
    if (meta.generated_at) bits.push("Generated " + escapeHtml(meta.generated_at));
    if (String(meta.locked) === "true") bits.push("🔒 locked");
    if (!bits.length) return "";
    return '<div class="page-meta">' + bits.join(" &nbsp;·&nbsp; ") + "</div>";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function renderPage(key) {
    var entry = flatPages().filter(function (e) { return e.section.id + "/" + e.page.id === key; })[0];
    if (!entry) {
      pageEl.innerHTML = "<h1>Page not found</h1><p>No page <code>" + escapeHtml(key) + "</code>.</p>";
      return;
    }
    highlightNav(key);
    document.title = entry.page.title + " · " + (manifest.title || "Wiki");

    getContent(entry.page.file).then(function (md) {
      var parsed = parseFrontMatter(md);
      var html = window.marked ? marked.parse(parsed.body) : "<pre>" + escapeHtml(parsed.body) + "</pre>";
      pageEl.innerHTML = renderMeta(parsed.meta) + html;
      runMermaid();
      window.scrollTo(0, 0);
    });
  }

  function runMermaid() {
    if (!window.mermaid) return;
    var blocks = pageEl.querySelectorAll("code.language-mermaid, pre code.language-mermaid");
    var nodes = [];
    blocks.forEach(function (b) {
      var pre = b.closest("pre") || b;
      var div = document.createElement("div");
      div.className = "mermaid";
      div.textContent = b.textContent;
      pre.replaceWith(div);
      nodes.push(div);
    });
    if (nodes.length) {
      try { mermaid.run({ nodes: nodes }); }
      catch (e) { try { mermaid.init(undefined, nodes); } catch (e2) {} }
    }
  }

  // ---- routing ------------------------------------------------------------
  function currentKey() {
    var h = location.hash.replace(/^#/, "");
    if (h) return h;
    var first = flatPages()[0];
    return first ? first.section.id + "/" + first.page.id : "";
  }
  function route() { var k = currentKey(); if (k) renderPage(k); }

  // ---- search -------------------------------------------------------------
  function applySearch(q) {
    q = q.trim().toLowerCase();
    var sections = navTree.querySelectorAll(".nav-section");
    sections.forEach(function (sec) {
      var anyVisible = false;
      sec.querySelectorAll(".nav-page").forEach(function (a) {
        var match = !q || a.dataset.search.indexOf(q) !== -1;
        a.classList.toggle("hidden", !match);
        if (match) anyVisible = true;
      });
      sec.classList.toggle("hidden", !anyVisible);
    });
  }

  // ---- live reload (serve mode only) --------------------------------------
  function startLiveReload() {
    if (EMBEDDED) return;
    var last = null;
    setInterval(function () {
      fetch("/__mtime", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          var sig = data.mtime + ":" + data.count;
          if (last !== null && sig !== last) {
            // refresh manifest + current page content without losing scroll position much
            contentCache = {};
            loadManifest().then(function () { buildNav(); route(); toast("Wiki updated"); });
          }
          last = sig;
        })
        .catch(function () {});
    }, 1500);
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("show"); });
    setTimeout(function () { t.classList.remove("show"); setTimeout(function () { t.remove(); }, 400); }, 2200);
  }

  // ---- bootstrap ----------------------------------------------------------
  function loadManifest() {
    if (EMBEDDED) return Promise.resolve();
    return fetch("wiki.json", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) { manifest = data; });
  }

  function setFooter() {
    var parts = [];
    if (manifest.generated_at) parts.push("Generated " + manifest.generated_at);
    if (!EMBEDDED) parts.push("live preview");
    footerEl.textContent = parts.join(" · ");
    var titleEls = document.querySelectorAll("#wiki-title, title");
    titleEls.forEach(function (el) { if (manifest.title) el.textContent = manifest.title; });
  }

  loadManifest().then(function () {
    buildNav();
    setFooter();
    route();
    startLiveReload();
  });

  window.addEventListener("hashchange", route);
  if (searchEl) searchEl.addEventListener("input", function () { applySearch(searchEl.value); });

  var toggle = document.getElementById("menu-toggle");
  if (toggle) toggle.addEventListener("click", function () { sidebar.classList.toggle("open"); });
  navTree.addEventListener("click", function (e) {
    if (e.target.classList.contains("nav-page")) sidebar.classList.remove("open");
  });
  var titleEl = document.getElementById("wiki-title");
  if (titleEl) titleEl.addEventListener("click", function () {
    var first = flatPages()[0];
    if (first) location.hash = first.section.id + "/" + first.page.id;
  });
})();
