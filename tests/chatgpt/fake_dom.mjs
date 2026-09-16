// Hermetic fake DOM for observer tests: object trees + a small matcher for
// exactly the selector shapes used in selectors.js. No browser, no deps.
function parsePart(part) {
  const m = part.match(/^([a-zA-Z][a-zA-Z0-9]*)?((?:\[[^\]]+\])*)$/);
  const out = { tag: (m[1] || "").toLowerCase(), attrs: [] };
  const attrRe = /\[([a-zA-Z0-9_-]+)(\^=|\*=|=)?(?:"([^"]*)")?\]/g;
  let a;
  while ((a = attrRe.exec(m[2]))) {
    out.attrs.push({ name: a[1], op: a[2] || null, value: a[3] || "" });
  }
  return out;
}

function matchPart(node, part) {
  const p = parsePart(part);
  if (p.tag && (node.tag || "").toLowerCase() !== p.tag) return false;
  for (const a of p.attrs) {
    const v = node.attrs ? node.attrs[a.name] : undefined;
    if (v === undefined) return false;
    const s = String(v);
    if (a.op === null) continue;
    if (a.op === "=" && s !== a.value) return false;
    if (a.op === "^=" && !s.startsWith(a.value)) return false;
    if (a.op === "*=" && !s.includes(a.value)) return false;
  }
  return true;
}

function matchSelector(node, ancestors, selector) {
  const parts = selector.trim().split(/\s+/);
  const last = parts[parts.length - 1];
  if (!matchPart(node, last)) return false;
  let ai = ancestors.length - 1;
  for (let i = parts.length - 2; i >= 0; i--) {
    let found = false;
    while (ai >= 0) {
      if (matchPart(ancestors[ai], parts[i])) {
        found = true;
        ai--;
        break;
      }
      ai--;
    }
    if (!found) return false;
  }
  return true;
}

export function makeRoot(tree) {
  function walk(node, ancestors, out) {
    out.push({ node, ancestors: [...ancestors] });
    for (const child of node.children || []) walk(child, [...ancestors, node], out);
  }
  return {
    querySelectorAll(sel) {
      const all = [];
      walk(tree, [], all);
      const out = [];
      for (const { node, ancestors } of all) {
        const sels = sel.split(",").map((s) => s.trim()).filter(Boolean);
        if (sels.some((s) => { try { return matchSelector(node, ancestors, s); } catch { return false; } })) {
          out.push(wrap(node));
        }
      }
      return out;
    },
    querySelector(sel) {
      const list = this.querySelectorAll(sel);
      return list.length ? list[0] : null;
    },
  };
}

function wrap(node) {
  return {
    getAttribute: (name) => (node.attrs && name in node.attrs ? String(node.attrs[name]) : null),
    get innerText() {
      return node.text || "";
    },
  };
}

export function el(tag, attrs = {}, text = "", children = []) {
  return { tag, attrs, text, children };
}
