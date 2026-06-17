/* Feedsmith embeddable live-feed widget (vanilla JS, no dependencies).
 *
 * Usage on a client site:
 *   <div data-feedsmith data-feed="books-demo" data-api="https://feed.example"
 *        data-fields="title,price" data-limit="10"></div>
 *   <script src="https://feed.example/widget.js"></script>
 *
 * Each [data-feedsmith] element is hydrated: an initial GET /feeds/{id}/data
 * renders a table, then an EventSource on /feeds/{id}/stream re-renders on each
 * live update and drives a "live / reconnecting" badge.
 */
(function () {
  "use strict";

  function esc(value) {
    var d = document.createElement("div");
    d.textContent = value == null ? "" : String(value);
    return d.innerHTML;
  }

  function FeedWidget(el) {
    this.el = el;
    this.api = (el.getAttribute("data-api") || "").replace(/\/$/, "");
    this.feed = el.getAttribute("data-feed");
    var f = el.getAttribute("data-fields");
    this.fields = f ? f.split(",").map(function (s) { return s.trim(); }) : null;
    this.limit = parseInt(el.getAttribute("data-limit") || "0", 10) || 0;
    // Poll fallback (ms): keeps data fresh even when a CDN/proxy buffers the SSE
    // stream. SSE (when it gets through) gives instant updates; this guarantees
    // freshness regardless. Override with data-poll; 0 disables polling.
    var pollAttr = el.getAttribute("data-poll");
    this.pollMs = pollAttr === null ? 15000 : (parseInt(pollAttr, 10) || 0);
    this.lastFetched = null;
    this.render({ count: 0, records: [], stale: true }, "connecting");
    this.load();
    this.subscribe();
    var self = this;
    setInterval(function () { self.tick(); }, 1000);
    if (this.pollMs > 0) {
      setInterval(function () { self.load(); }, this.pollMs);
    }
  }

  FeedWidget.prototype.url = function (suffix) {
    return this.api + "/feeds/" + encodeURIComponent(this.feed) + suffix;
  };

  FeedWidget.prototype.load = function () {
    var self = this;
    fetch(this.url("/data"))
      .then(function (r) { return r.json(); })
      .then(function (data) { self.render(data, "live"); })
      .catch(function () { self.setBadge("reconnecting"); });
  };

  FeedWidget.prototype.subscribe = function () {
    var self = this;
    if (typeof EventSource === "undefined") { return; }
    var es = new EventSource(this.url("/stream"));
    es.addEventListener("update", function (ev) {
      try { self.render(JSON.parse(ev.data), "live"); } catch (e) {}
    });
    es.onerror = function () { self.setBadge("reconnecting"); };
  };

  FeedWidget.prototype.render = function (data, state) {
    this.lastFetched = data.fetched_at ? Date.parse(data.fetched_at) : null;
    var records = data.records || [];
    if (this.limit > 0) { records = records.slice(0, this.limit); }
    var cols = this.fields;
    if (!cols && records.length) {
      cols = Object.keys(records[0]).filter(function (k) {
        return k !== "source" && k !== "fetched_at";
      });
    }
    cols = cols || [];
    var html = '<div class="fs-widget">';
    html += '<div class="fs-bar"><span class="fs-dot"></span>'
      + '<span class="fs-status"></span>'
      + '<span class="fs-count">' + records.length + " items</span></div>";
    html += "<table class=\"fs-table\"><thead><tr>";
    cols.forEach(function (c) { html += "<th>" + esc(c) + "</th>"; });
    html += "</tr></thead><tbody>";
    records.forEach(function (row) {
      html += "<tr>";
      cols.forEach(function (c) { html += "<td>" + esc(row[c]) + "</td>"; });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    this.el.innerHTML = html;
    this.setBadge(data.stale ? "stale" : state);
    this.tick();
  };

  FeedWidget.prototype.setBadge = function (state) {
    var dot = this.el.querySelector(".fs-dot");
    var status = this.el.querySelector(".fs-status");
    if (!dot || !status) { return; }
    if (state === "live") { dot.style.color = "#4ADE80"; }
    else if (state === "stale") { dot.style.color = "#FBBF24"; }
    else { dot.style.color = "#71717A"; }
    dot.textContent = "●";
    this._state = state;
  };

  FeedWidget.prototype.tick = function () {
    var status = this.el.querySelector(".fs-status");
    if (!status) { return; }
    var label = this._state === "reconnecting" ? "reconnecting…"
      : this._state === "stale" ? "stale" : "live";
    if (this.lastFetched) {
      var secs = Math.max(0, Math.round((Date.now() - this.lastFetched) / 1000));
      label += " · updated " + secs + "s ago";
    }
    status.textContent = label;
  };

  function init() {
    var nodes = document.querySelectorAll("[data-feedsmith]");
    Array.prototype.forEach.call(nodes, function (el) {
      if (!el.__fsInit) { el.__fsInit = true; new FeedWidget(el); }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
