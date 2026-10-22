"use strict";
const $ = (id) => document.getElementById(id);
let apiKey = "",
  selectedDomain = "",
  activeSource = null,
  latestQuery = "",
  latestStats = null;
const names = {
  search: "Search index",
  crawl: "Crawl websites",
  api: "API & agents",
};
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = `notice${error ? " error" : ""}`;
  $("notice").hidden = !message;
}
function view(name) {
  document
    .querySelectorAll(".view")
    .forEach((n) => (n.hidden = n.id !== `view-${name}`));
  document
    .querySelectorAll(".nav")
    .forEach((n) => n.classList.toggle("active", n.dataset.view === name));
  $("view-title").textContent = names[name];
  notice("");
  if (name === "crawl") refreshJobs();
}
document
  .querySelectorAll("[data-view]")
  .forEach((n) => n.addEventListener("click", () => view(n.dataset.view)));
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "x-api-key": apiKey },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !$("connection").open)
      $("connection").showModal();
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  }
  return data;
}
async function refreshStats() {
  try {
    latestStats = await api("/stats");
    $("page-count").textContent = `${latestStats.documents} pages`;
    $("connection-status").textContent = "Connected to local index";
    $("index-badge").textContent = latestStats.neuralEnabled
      ? "NEURAL + KEYWORD"
      : "KEYWORD INDEX";
    $("domains").replaceChildren();
    latestStats.domains.forEach((d) => {
      const button = el("button", "domain");
      button.append(el("span", "", d.domain), el("span", "", String(d.pages)));
      button.classList.toggle("active", selectedDomain === d.domain);
      button.addEventListener("click", () => setDomain(d.domain));
      $("domains").append(button);
    });
    if (latestStats.documents && !latestQuery)
      empty(
        "Your index is ready.",
        `Search across ${latestStats.documents} pages from ${latestStats.domains.length} sources.`,
        false,
      );
  } catch (error) {
    $("connection-status").textContent = "Connection needed";
    notice(error.message, true);
  }
}
function setDomain(domain) {
  selectedDomain = domain;
  $("scope").textContent = domain || "All sources";
  $("all-domains").classList.toggle("active", !domain);
  refreshStats();
  view("search");
  if ($("query").value.trim()) $("search-form").requestSubmit();
  else $("query").focus();
}
$("all-domains").addEventListener("click", () => setDomain(""));
function empty(title, message, action = false) {
  const box = el("div", "empty"),
    orbit = el("div", "orbit");
  orbit.setAttribute("aria-hidden", "true");
  orbit.append(el("span", "", "↗"));
  box.append(orbit, el("h2", "", title), el("p", "", message));
  if (action) {
    const b = el("button", "primary", "Crawl a website ↗");
    b.addEventListener("click", () => view("crawl"));
    box.append(b);
  }
  $("results").replaceChildren(box);
}
function renderResults(data, elapsed) {
  $("result-summary").textContent =
    `${data.results.length} results${elapsed !== undefined ? ` · ${elapsed} ms` : ""}`;
  $("retrieval-label").textContent = `${data.searchType} retrieval`;
  $("results").replaceChildren();
  if (!data.results.length) {
    empty(
      "No matching pages yet.",
      "Try a broader query, select all sources, or crawl more pages.",
      true,
    );
    return;
  }
  data.results.forEach((r, i) => {
    const article = el("article", "result"),
      meta = el("div", "result-meta"),
      host = new URL(r.url).hostname;
    meta.append(
      el("span", "source-icon", host.replace(/^www\./, "")[0].toUpperCase()),
      el("span", "", host),
      el("span", "", `· ${String(i + 1).padStart(2, "0")}`),
    );
    const heading = el("h2"),
      link = el("a", "", r.title);
    link.href = r.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    heading.append(link);
    const actions = el("div", "result-actions"),
      read = el("button", "", "Read page ↗"),
      similar = el("button", "", "Find similar");
    read.addEventListener("click", () => inspect(r));
    similar.addEventListener("click", () => findSimilar(r));
    actions.append(
      read,
      similar,
      el("span", "score", `RRF ${r.score.toFixed(4)}`),
    );
    article.append(
      meta,
      heading,
      el("p", "", (r.highlights?.join(" ") || r.text || "").slice(0, 430)),
      actions,
    );
    $("results").append(article);
  });
  if (data.warnings?.length) notice(data.warnings.join(" "));
}
$("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  latestQuery = $("query").value.trim();
  if (!latestQuery) return;
  notice("");
  const button = $("search-button");
  button.disabled = true;
  button.textContent = "Searching…";
  const start = performance.now();
  try {
    const data = await api("/search", {
      query: latestQuery,
      type: $("mode").value,
      numResults: Number($("count").value),
      includeDomains: selectedDomain ? [selectedDomain] : [],
    });
    renderResults(data, Math.round(performance.now() - start));
  } catch (error) {
    notice(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Search ↗";
  }
});
async function inspect(result) {
  try {
    const data = await api("/contents", {
      urls: [result.url],
      maxCharacters: 100000,
    });
    const full = data.results[0];
    if (!full) throw new Error("This page is no longer in the index.");
    activeSource = full;
    $("source-title").textContent = full.title;
    $("source-url").textContent = full.url;
    $("source-url").href = full.url;
    $("source-meta").textContent =
      `Crawled ${new Date(full.crawledAt).toLocaleString()}`;
    $("source-text").textContent = full.text;
    $("copy-source").textContent = "Copy text";
    $("inspector").showModal();
  } catch (error) {
    notice(error.message, true);
  }
}
async function findSimilar(source) {
  if ($("inspector").open) $("inspector").close();
  view("search");
  notice(`Finding pages related to “${source.title}”…`);
  try {
    const data = await api("/findSimilar", {
      url: source.url,
      numResults: Number($("count").value),
      includeDomains: selectedDomain ? [selectedDomain] : [],
    });
    notice("");
    renderResults(data);
    $("result-summary").textContent =
      `${data.results.length} pages related to “${source.title}”`;
  } catch (error) {
    notice(error.message, true);
  }
}
$("similar-button").addEventListener("click", () => findSimilar(activeSource));
$("close-inspector").addEventListener("click", () => $("inspector").close());
$("copy-source").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(
      `${activeSource.title}\n${activeSource.url}\n\n${activeSource.text}`,
    );
    $("copy-source").textContent = "Copied";
  } catch {
    $("copy-source").textContent = "Select text to copy";
  }
});
$("crawl-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  notice("");
  $("crawl-button").disabled = true;
  try {
    await api("/crawl", {
      urls: $("seed-urls")
        .value.split(/\n/)
        .map((s) => s.trim())
        .filter(Boolean),
      maxPages: Number($("max-pages").value),
      maxDepth: Number($("depth").value),
    });
    notice("Crawl started. Progress will update below.");
    await refreshJobs();
  } catch (error) {
    notice(error.message, true);
  } finally {
    $("crawl-button").disabled = false;
  }
});
async function refreshJobs() {
  try {
    const data = await api("/crawl");
    $("jobs").replaceChildren();
    if (!data.jobs.length) {
      $("jobs").append(
        el("p", "hint", "No crawls yet. Add a seed URL to begin."),
      );
      return;
    }
    data.jobs.forEach((job) => {
      const block = el("article", "job"),
        header = el("div", "job-header"),
        intro = el("div");
      intro.append(
        el("h3", "", job.urls.join(", ")),
        el(
          "div",
          "hint",
          `${job.indexed} indexed · ${job.attempted} attempted · ${new Date(job.createdAt).toLocaleString()}`,
        ),
      );
      header.append(intro, el("span", `job-status ${job.status}`, job.status));
      block.append(header);
      if (job.currentUrl) block.append(el("p", "hint", job.currentUrl));
      if (job.errors.length) {
        const details = el("details"),
          list = el("ul");
        details.append(
          el("summary", "", `${job.errors.length} skipped or failed pages`),
        );
        job.errors.forEach((e) =>
          list.append(el("li", "", `${e.url}: ${e.error}`)),
        );
        details.append(list);
        block.append(details);
      }
      $("jobs").append(block);
    });
  } catch (error) {
    notice(error.message, true);
  }
}
$("refresh-jobs").addEventListener("click", refreshJobs);
$("connection-button").addEventListener("click", () =>
  $("connection").showModal(),
);
$("close-connection").addEventListener("click", () => $("connection").close());
$("connection-form").addEventListener("submit", (event) => {
  event.preventDefault();
  apiKey = $("api-key").value;
  $("connection").close();
  notice("");
  refreshStats();
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) &&
    !document.querySelector("dialog[open]")
  ) {
    event.preventDefault();
    view("search");
    $("query").focus();
  }
});
$("api-example").textContent =
  `curl ${location.origin}/search \\\n  -H "Content-Type: application/json" \\\n  -H "x-api-key: YOUR_KEY_IF_CONFIGURED" \\\n  -d '{"query":"your next discovery","type":"auto","numResults":5}'`;
refreshStats();
setInterval(() => {
  if (!document.hidden) {
    refreshStats();
    if (!$("view-crawl").hidden) refreshJobs();
  }
}, 5000);
