// Compact hermetic fake DOM for extension tests (CJS). Supports the
// selector shapes used in content.js CONFIG. No browser, no deps.
function matchPart(node, part) {
  const m = part.match(/^([a-zA-Z][a-zA-Z0-9]*)?((?:\[[^\]]+\])*)$/);
  const tag = (m[1] || "").toLowerCase();
  if (tag && (node.tag || "").toLowerCase() !== tag) return false;
  const attrRe = /\[([a-zA-Z0-9_-]+)(\^=|\*=|=)?(?:"([^"]*)")?\]/g;
  let a;
  while ((a = attrRe.exec(m[2]))) {
    const v = node.attrs ? node.attrs[a[1]] : undefined;
    if (v === undefined) return false;
    const s = String(v);
    if (a[2] === "=" && s !== a[3]) return false;
    if (a[2] === "^=" && !s.startsWith(a[3])) return false;
    if (a[2] === "*=" && !s.includes(a[3])) return false;
  }
  return true;
}

function matchSel(node, ancestors, sel) {
  const parts = sel.trim().split(/\s+/);
  if (!matchPart(node, parts[parts.length - 1])) return false;
  let ai = ancestors.length - 1;
  for (let i = parts.length - 2; i >= 0; i--) {
    let found = false;
    while (ai >= 0) {
      if (matchPart(ancestors[ai], parts[i])) { found = true; ai--; break; }
      ai--;
    }
    if (!found) return false;
  }
  return true;
}

function collect(tree) {
  const out = [];
  (function walk(node, ancestors) {
    out.push({ node, ancestors: [...ancestors] });
    for (const c of node.children || []) walk(c, [...ancestors, node]);
  })(tree, []);
  return out;
}

function wrap(node) {
  return {
    __node: node,
    getAttribute: (n) => (node.attrs && n in node.attrs ? String(node.attrs[n]) : null),
    get innerText() { return node.text || ""; },
    focus() { node.focused = true; },
    click() { node.clicked = true; (node.onClick || (() => {}))(); },
    get parentElement() { return node.__parent ? wrap(node.__parent) : null; },
  };
}

function linkParents(node, parent) {
  node.__parent = parent || null;
  for (const c of node.children || []) linkParents(c, node);
}

function makeRoot(tree) {
  linkParents(tree, null);
  return {
    querySelectorAll(sel) {
      const out = [];
      for (const { node, ancestors } of collect(tree)) {
        const sels = sel.split(",").map((s) => s.trim()).filter(Boolean);
        try {
          if (sels.some((s) => matchSel(node, ancestors, s))) out.push(wrap(node));
        } catch { /* ignore */ }
      }
      return out;
    },
    querySelector(sel) {
      const l = this.querySelectorAll(sel);
      return l.length ? l[0] : null;
    },
    execCommand(cmd, ui, text) {
      if (cmd === "insertText") {
        this.__inserted = (this.__inserted || "") + text;
        return true;
      }
      return false;
    },
  };
}

function el(tag, attrs, text, children) {
  return { tag, attrs: attrs || {}, text: text || "", children: children || [] };
}

module.exports = { makeRoot, el };
