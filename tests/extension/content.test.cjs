// Hermetic tests for extension/content.js. No browser, no deps.
// Run: node --test tests/extension/content.test.cjs (from repo root).
const test = require("node:test");
const assert = require("node:assert/strict");
const bridge = require("../../extension/content.js");
const { makeRoot, el } = require("./fake_dom.cjs");

function assistantTurn(text) {
  return el("article", { "data-testid": "conversation-turn-3" }, text);
}

function depsFor(tree, hooks = {}) {
  const calls = { fetch: [] };
  const root = makeRoot(tree);
  const fetch = async (url, opts) => {
    calls.fetch.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
    const respond = hooks.respond || (() => ({}));
    return { ok: true, json: async () => respond(url, opts) };
  };
  return {
    deps: {
      root,
      fetch,
      documentExecCommand: (cmd, ui, text) => root.execCommand(cmd, ui, text),
      pollUntil: async (fn) => {
        for (let i = 0; i < 3; i++) { try { if (fn()) return true; } catch { /* retry */ } }
        return false;
      },
    },
    calls,
    root,
  };
}

function stableFeed(tree, times = 3) {
  // run observeTicks until finished (mirrors poll cadence)
  return async (rt) => {
    let last = null;
    for (let i = 0; i < times; i++) last = await rt.observeTick();
    return last;
  };
}

test("envelope assembly posts generating/finished/texts", async () => {
  const { deps, calls } = depsFor(el("main", {}, "", [assistantTurn("hi")]));
  const rt = bridge.createRuntime(deps, null);
  await stableFeed()(rt);
  const posts = calls.fetch.filter((c) => c.url.includes("/observe"));
  assert.ok(posts.length >= 1);
  const env = posts[posts.length - 1].body;
  assert.deepEqual(Object.keys(env).sort(), ["finished", "generating", "texts"]);
  assert.equal(env.finished, true);
  assert.deepEqual(env.texts, ["hi"]);
});

test("identical observations are not re-posted", async () => {
  const { deps, calls } = depsFor(el("main", {}, "", [assistantTurn("same")]));
  const rt = bridge.createRuntime(deps, null);
  for (let i = 0; i < 5; i++) await rt.observeTick();
  const posts = calls.fetch.filter((c) => c.url.includes("/observe"));
  // t0/t1 identical (unfinished) -> 1 post; t2 finished -> 1 post;
  // t3/t4 repeat t2 exactly -> skipped.
  assert.equal(posts.length, 2);
});

test("invalid payload rejected without executing", async () => {
  const tree = el("main", {}, "", []);
  const { deps, calls, root } = depsFor(tree, {
    respond: () => ({ item: { id: "c1", payload: 12345 } }),
  });
  const rt = bridge.createRuntime(deps, null);
  await rt.receiveTick();
  const confirms = calls.fetch.filter((c) => c.url.includes("/slot/confirm"));
  assert.equal(confirms.length, 1);
  assert.equal(confirms[0].body.ok, false);
  assert.equal(root.__inserted, undefined);
});

test("unicode, markdown and special chars inserted verbatim", async () => {
  const payload = "**bold** `code` ✓→日本語\nline2; $(x) \"q\"";
  const main = el("main", {}, "", [assistantTurn("x")]);
  const composer = el("div", { id: "prompt-textarea", contenteditable: "true" }, "");
  main.children.push(composer);
  const btn = el("button", { "data-testid": "send-button" }, "Send");
  btn.onClick = () => {
    main.children.push(el("article", { "data-message-author-role": "user" }, payload));
  };
  main.children.push(btn);
  const { deps, calls, root } = depsFor(main, {
    respond: (url) => (url.includes("/slot/take") ? { item: { id: "c9", payload } } : {}),
  });
  const rt = bridge.createRuntime(deps, null);
  await rt.receiveTick();
  assert.equal(root.__inserted, payload);
  const confirms = calls.fetch.filter((c) => c.url.includes("/slot/confirm"));
  assert.equal(confirms[0].body.ok, true);
});

test("proof success and failure", async () => {
  // success: tested above (ok:true). failure: no user node ever appears.
  const main = el("main", {}, "", [assistantTurn("x")]);
  main.children.push(el("div", { id: "prompt-textarea", contenteditable: "true" }, ""));
  main.children.push(el("button", { "data-testid": "send-button" }, "Send"));
  const { deps, calls } = depsFor(main, {
    respond: (url) => (url.includes("/slot/take") ? { item: { id: "c2", payload: "hello" } } : {}),
  });
  const rt = bridge.createRuntime(deps, null);
  await rt.receiveTick();
  const confirms = calls.fetch.filter((c) => c.url.includes("/slot/confirm"));
  assert.equal(confirms[0].body.ok, false);
  assert.equal(confirms[0].body.detail, "unproven");
});

test("missing composer fails closed", async () => {
  const { deps, calls } = depsFor(el("main", {}, "", [assistantTurn("x")]), {
    respond: (url) => (url.includes("/slot/take") ? { item: { id: "c3", payload: "hi" } } : {}),
  });
  const rt = bridge.createRuntime(deps, null);
  await rt.receiveTick();
  const confirms = calls.fetch.filter((c) => c.url.includes("/slot/confirm"));
  assert.equal(confirms[0].body.ok, false);
  assert.equal(confirms[0].body.detail, "no-composer");
});

test("missing send button fails closed", async () => {
  const main = el("main", {}, "", [
    assistantTurn("x"),
    el("div", { id: "prompt-textarea", contenteditable: "true" }, ""),
  ]);
  const { deps, calls } = depsFor(main, {
    respond: (url) => (url.includes("/slot/take") ? { item: { id: "c4", payload: "hi" } } : {}),
  });
  const rt = bridge.createRuntime(deps, null);
  await rt.receiveTick();
  const confirms = calls.fetch.filter((c) => c.url.includes("/slot/confirm"));
  assert.equal(confirms[0].body.ok, false);
  assert.equal(confirms[0].body.detail, "no-send");
});

test("alternate selector config", async () => {
  const tree = el("div", {}, "", [el("div", { "data-turn": "1" }, "custom")]);
  const { deps, calls } = depsFor(tree);
  const rt = bridge.createRuntime(deps, {
    turnStrategies: [{ name: "custom", sel: "[data-turn]" }],
    stopSelectors: [],
    stablePolls: 1,
  });
  await rt.observeTick();
  await rt.observeTick();
  // finished on second identical poll with stablePolls=1
  const env = calls.fetch.filter((c) => c.url.includes("/observe")).pop().body;
  assert.equal(env.finished, true);
  assert.deepEqual(env.texts, ["custom"]);
});
