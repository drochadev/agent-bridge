// Hermetic tests for adapters/chatgpt/observer.js. No browser, no deps.
// Run: node --test tests/chatgpt/observer.test.mjs (from repo root).
import test from "node:test";
import assert from "node:assert/strict";
import { createObserver } from "../../adapters/chatgpt/observer.js";
import { el, makeRoot } from "./fake_dom.mjs";

function article(text, extra = {}) {
  return el("article", { "data-testid": "conversation-turn-1", ...extra }, text);
}

test("simple assistant text, stable then finished", () => {
  const obs = createObserver();
  const root = () => makeRoot(el("main", {}, "", [article("hello")]));
  let r = obs.observe(root());
  assert.equal(r.generating, false);
  assert.equal(r.finished, false); // first sight: not stable yet
  r = obs.observe(root());
  assert.equal(r.finished, false); // stableCount=1 < 2
  r = obs.observe(root());
  assert.equal(r.finished, true);
  assert.deepEqual(r.texts, ["hello"]);
});

test("stop button means generating", () => {
  const obs = createObserver();
  const btn = el("button", { "data-testid": "stop-button" }, "Stop");
  const root = makeRoot(el("main", {}, "", [article("partial"), btn]));
  const r = obs.observe(root);
  assert.equal(r.generating, true);
  assert.equal(r.finished, false);
});

test("markdown, code, unicode, empty", () => {
  const obs = createObserver();
  const body = "# Title\n\n`code()` **bold** ✓→日本語";
  const root = () => makeRoot(el("main", {}, "", [article(body), article("")]));
  obs.observe(root());
  obs.observe(root());
  const r = obs.observe(root());
  assert.equal(r.finished, true);
  assert.ok(r.texts[0].includes("✓→日本語"));
  assert.ok(r.texts.includes(""));
});

test("multiple turns, user excluded, outside ignored", () => {
  const obs = createObserver();
  const tree = el("div", {}, "", [
    el("main", {}, "", [
      article("first answer"),
      el("article", { "data-testid": "conversation-turn-2", "data-message-author-role": "user" }, "user prompt"),
      article("second answer"),
    ]),
    el("footer", {}, "outside noise"),
  ]);
  const root = () => makeRoot(tree);
  obs.observe(root());
  obs.observe(root());
  const r = obs.observe(root());
  assert.deepEqual(r.texts, ["first answer", "second answer"]);
});

test("strategy fallback reported", () => {
  const obs = createObserver();
  const tree = el("div", {}, "", [
    el("section", { "data-message-author-role": "assistant" }, "hi"),
  ]);
  const root = () => makeRoot(tree);
  obs.observe(root());
  obs.observe(root());
  const r = obs.observe(root());
  assert.equal(r.strategy, "msg-author-role");
  assert.deepEqual(r.texts, ["hi"]);
});

test("content changing resets stability", () => {
  const obs = createObserver();
  let text = "a";
  const root = () => makeRoot(el("main", {}, "", [article(text)]));
  obs.observe(root());
  obs.observe(root());
  text = "ab";
  let r = obs.observe(root());
  assert.equal(r.finished, false);
  r = obs.observe(root());
  assert.equal(r.finished, false);
  r = obs.observe(root());
  assert.equal(r.finished, true);
});

test("envelope shape fits ObservationFeed contract", () => {
  const obs = createObserver();
  const root = makeRoot(el("main", {}, "", [article("x")]));
  const r = obs.observe(root);
  assert.deepEqual(Object.keys(r).sort(), ["finished", "generating", "strategy", "texts"]);
  assert.equal(typeof r.generating, "boolean");
  assert.equal(typeof r.finished, "boolean");
  assert.ok(Array.isArray(r.texts));
});

test("configurable selectors without touching the mechanism", () => {
  const obs = createObserver({
    turnStrategies: [{ name: "custom", sel: "[data-turn]" }],
    stopSelectors: ["[data-busy]"],
    roleAttribute: "data-role",
    excludedRoles: ["human"],
    stablePolls: 1,
  });
  const tree = el("div", {}, "", [
    el("div", { "data-turn": "1" }, "custom text"),
  ]);
  const root = () => makeRoot(tree);
  obs.observe(root());
  const r = obs.observe(root());
  assert.equal(r.strategy, "custom");
  assert.equal(r.finished, true);
  assert.deepEqual(r.texts, ["custom text"]);
});
