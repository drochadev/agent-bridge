/* Agent Bridge companion — classic script (no modules, no deps).
 *
 * Two independent halves sharing nothing but timers:
 *  OBSERVE: DOM -> envelope -> POST /observe (dedupe by envelope signature).
 *  RECEIVE: poll GET /slot/take -> composer insert -> send click ->
 *           DOM proof -> POST /slot/confirm.
 *
 * Observation logic mirrors adapters/chatgpt/observer.js (same section
 * names, same stability rule); keep them in sync by hand — no bundler by
 * design. Payloads are TEXT ONLY: inserted via execCommand, never executed,
 * never set as HTML. Failures post ok:false or nothing at all; delivery
 * confirmation is never invented.
 */
(function (root, factory) {
  const api = factory();
  root.AgentBridgeChat = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const CONFIG = {
    turnStrategies: [
      { name: "article-testid", sel: 'article[data-testid^="conversation-turn"]' },
      { name: "msg-author-role", sel: "[data-message-author-role]" },
      { name: "article-plain", sel: "main article" },
    ],
    stopSelectors: [
      'button[data-testid="stop-button"]',
      'button[data-testid="stop-generating-button"]',
      'button[aria-label="Stop generating"]',
      'button[aria-label="Parar de gerar"]',
      'button[aria-label*="Stop"]',
    ],
    composerSelectors: [
      "div#prompt-textarea",
      'div[contenteditable="true"]',
      'textarea[data-testid="chat-input"]',
      "textarea",
    ],
    sendSelectors: [
      'button[data-testid="send-button"]',
      'button[aria-label="Send message"]',
      'button[aria-label="Enviar mensagem"]',
    ],
    roleAttribute: "data-message-author-role",
    excludedRoles: ["user", "system"],
    stablePolls: 2,
    observeMs: 1000,
    receiveMs: 1000,
    observeUrl: "http://127.0.0.1:18766/observe",
    outboxUrl: "http://127.0.0.1:18765/slot/take",
    confirmUrl: "http://127.0.0.1:18765/slot/confirm",
  };

  function hashText(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h.toString(16);
  }

  function toArray(list) {
    try {
      return Array.from(list || []);
    } catch {
      return [];
    }
  }

  function firstMatch(root, selectors) {
    for (const sel of selectors) {
      try {
        const list = toArray(root.querySelectorAll(sel));
        if (list.length > 0) return { sel, list };
      } catch {
        /* invalid selector for this root */
      }
    }
    return { sel: null, list: [] };
  }

  // ---- OBSERVE ----
  function collectTurns(root, cfg) {
    let nodes = [];
    let strategy = "none";
    for (const st of cfg.turnStrategies) {
      const found = firstMatch(root, [st.sel]);
      if (found.list.length > 0 && nodes.length === 0) {
        nodes = found.list;
        strategy = st.name;
      }
    }
    return { nodes, strategy };
  }

  function observeState() {
    return { lastHash: "", stableCount: 0 };
  }

  function observe(root, cfg, mem) {
    const { nodes } = collectTurns(root, cfg);
    const texts = [];
    for (const node of nodes) {
      let role = "";
      try {
        role = node.getAttribute(cfg.roleAttribute) || "";
      } catch {
        role = "";
      }
      if (cfg.excludedRoles.indexOf(role) >= 0) continue;
      try {
        texts.push((node.innerText || "").replace(/\s+$/g, ""));
      } catch {
        texts.push("");
      }
    }
    let generating = false;
    for (const sel of cfg.stopSelectors) {
      try {
        if (toArray(root.querySelectorAll(sel)).length > 0) {
          generating = true;
          break;
        }
      } catch {
        /* ignore */
      }
    }
    const h = texts.length ? hashText(texts.join("\n")) : "";
    if (h === mem.lastHash && h !== "") mem.stableCount++;
    else {
      mem.stableCount = 0;
      mem.lastHash = h;
    }
    const finished = !generating && h !== "" && mem.stableCount >= cfg.stablePolls;
    return { generating, finished, texts };
  }

  // ---- SEND (observation -> mediator) ----
  function envelopeSignature(env) {
    return [env.generating, env.finished, (env.texts || []).join("\n")].join("|");
  }

  async function sendObservation(deps, cfg, mem, env) {
    const sig = envelopeSignature(env);
    if (sig === mem.lastSentSig) return "duplicate-skipped";
    mem.lastSentSig = sig;
    try {
      const res = await deps.fetch(cfg.observeUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(env),
      });
      if (!res.ok) {
        mem.lastSentSig = null; // allow retry: not confirmed received
        return "http-error";
      }
      return "sent";
    } catch {
      mem.lastSentSig = null; // transport failed: retry later, invent nothing
      return "transport-failed";
    }
  }

  // ---- COMPOSER (isolated DOM writing) ----
  function findComposer(root, cfg) {
    const found = firstMatch(root, cfg.composerSelectors);
    return found.list.length ? found.list[0] : null;
  }

  function findSendButton(root, cfg, composer) {
    const scope = (composer && composer.parentElement) || root;
    const btns = firstMatch(scope, cfg.sendSelectors);
    if (btns.list.length) return btns.list[0];
    return firstMatch(root, cfg.sendSelectors).list[0] || null;
  }

  function norm(s) {
    return (s || "").replace(/[`*_#~]/g, "").replace(/\s+/g, " ").trim();
  }

  function snapshotUserKeys(root) {
    const keys = new Set();
    try {
      for (const n of toArray(root.querySelectorAll("[data-message-author-role='user']"))) {
        try {
          keys.add(n.innerText || "");
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* no snapshot: proof fails closed */
    }
    return keys;
  }

  function proveUserMessage(root, payload, before) {
    // A NEW user node whose normalized text contains the normalized payload.
    try {
      for (const n of toArray(root.querySelectorAll("[data-message-author-role='user']"))) {
        let text = "";
        try {
          text = n.innerText || "";
        } catch {
          continue;
        }
        if (before.has(text)) continue;
        if (text.indexOf(payload) >= 0 || norm(text).indexOf(norm(payload)) >= 0) return true;
      }
    } catch {
      /* retry next poll */
    }
    return false;
  }

  async function receiveOne(deps, cfg, mem, item) {
    // Returns "delivered" | "no-composer" | "no-send" | "unproven".
    // Caller posts the confirmation; this function never confirms itself.
    const root = deps.root;
    const composer = findComposer(root, cfg);
    if (!composer) return "no-composer";
    const before = snapshotUserKeys(root);
    let inserted = false;
    try {
      if (typeof composer.focus === "function") composer.focus();
      inserted = root.execCommand
        ? root.execCommand("insertText", false, item.payload)
        : deps.documentExecCommand
          ? deps.documentExecCommand("insertText", false, item.payload)
          : false;
    } catch {
      inserted = false;
    }
    if (!inserted) return "no-composer";
    const btn = findSendButton(root, cfg, composer);
    if (!btn) return "no-send";
    try {
      if (typeof btn.click === "function") btn.click();
      else return "no-send";
    } catch {
      return "no-send";
    }
    const proven = await deps.pollUntil(() => proveUserMessage(root, item.payload, before), 5, 400);
    return proven ? "delivered" : "unproven";
  }

  async function postConfirm(deps, cfg, id, ok, detail) {
    try {
      await deps.fetch(cfg.confirmUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ok, detail: String(detail).slice(0, 300) }),
      });
    } catch {
      /* confirm failed: mediator keeps no slot (take-once already consumed) */
    }
  }

  async function pollOutbox(deps, cfg, mem) {
    if (mem.receiving) return;
    mem.receiving = true;
    try {
      const res = await deps.fetch(cfg.outboxUrl);
      if (!res.ok) return;
      const data = await res.json();
      const item = data && data.item;
      if (!item || !item.id || mem.claimed.has(item.id)) return;
      mem.claimed.add(item.id);
      if (typeof item.payload !== "string") {
        await postConfirm(deps, cfg, item.id, false, "invalid-payload");
        return;
      }
      const outcome = await receiveOne(deps, cfg, mem, item);
      if (outcome === "delivered") {
        await postConfirm(deps, cfg, item.id, true, "dom-proof");
      } else {
        // Honest negative confirmations ("no-composer"/"no-send"/"unproven")
        // report ok:false so the mediator audits instead of re-offering.
        await postConfirm(deps, cfg, item.id, false, outcome);
      }
    } catch {
      /* poll failed: try again next interval */
    } finally {
      mem.receiving = false;
    }
  }

  function createRuntime(deps, cfg) {
    const full = { ...CONFIG, ...(cfg || {}) };
    const obsMem = { ...observeState(), lastSentSig: null };
    const mem = { receiving: false, claimed: new Set() };
    return {
      config: full,
      async observeTick() {
        const env = observe(deps.root, full, obsMem);
        return sendObservation(deps, full, obsMem, env);
      },
      async receiveTick() {
        return pollOutbox(deps, full, mem);
      },
    };
  }

  function boot(deps) {
    const rt = createRuntime(deps, null);
    const timers = deps.timers || { setInterval };
    timers.setInterval(() => void rt.observeTick(), rt.config.observeMs);
    timers.setInterval(() => void rt.receiveTick(), rt.config.receiveMs);
    return rt;
  }

  // Browser entry: only when a real document exists (never under node tests,
  // which import the factory above through the module wrapper below).
  if (typeof document !== "undefined" && typeof fetch !== "undefined") {
    boot({
      root: document,
      fetch: fetch.bind(window),
      documentExecCommand: (cmd, ui, text) => {
        try {
          return document.execCommand(cmd, ui, text);
        } catch {
          return false;
        }
      },
      pollUntil: async (fn, tries, ms) => {
        for (let i = 0; i < tries; i++) {
          try {
            if (fn()) return true;
          } catch {
            /* retry */
          }
          await new Promise((r) => setTimeout(r, ms));
        }
        return false;
      },
    });
  }

  return { CONFIG, createRuntime, observe, observeState, collectTurns, envelopeSignature, findComposer, proveUserMessage, norm };
});
