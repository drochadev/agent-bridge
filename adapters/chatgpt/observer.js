// Generic chat-observation mechanism. No product details here: every DOM
// assumption arrives via config (see selectors.js). Works against any root
// exposing querySelectorAll(sel) -> iterable of nodes with getAttribute()
// and innerText. Never clicks, focuses, writes, or sends anything.
import { DEFAULT_CONFIG } from "./selectors.js";

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

export function createObserver(config = {}) {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  let lastHash = "";
  let stableCount = 0;

  function collectTurns(root) {
    let nodes = [];
    let strategy = "none";
    for (const st of cfg.turnStrategies) {
      let list = [];
      try {
        list = toArray(root.querySelectorAll(st.sel));
      } catch {
        continue; // invalid selector for this root: try next strategy
      }
      if (list.length > 0 && nodes.length === 0) {
        nodes = list;
        strategy = st.name;
      }
    }
    return { nodes, strategy };
  }

  function isAssistant(node) {
    let role = "";
    try {
      role = node.getAttribute(cfg.roleAttribute) || "";
    } catch {
      role = "";
    }
    return !cfg.excludedRoles.includes(role);
  }

  function nodeText(node) {
    try {
      return (node.innerText || "").replace(/\s+$/g, "");
    } catch {
      return "";
    }
  }

  function generating(root) {
    for (const sel of cfg.stopSelectors) {
      try {
        if (toArray(root.querySelectorAll(sel)).length > 0) return true;
      } catch {
        /* invalid selector: ignore */
      }
    }
    return false;
  }

  function observe(root) {
    const { nodes, strategy } = collectTurns(root);
    const texts = nodes.filter(isAssistant).map(nodeText);
    const gen = generating(root);
    const h = texts.length ? hashText(texts.join("\n")) : "";
    if (h === lastHash && h !== "") stableCount++;
    else {
      stableCount = 0;
      lastHash = h;
    }
    const finished = !gen && h !== "" && stableCount >= cfg.stablePolls;
    return { generating: gen, finished, texts, strategy };
  }

  return { observe };
}
