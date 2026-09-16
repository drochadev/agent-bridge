// Selectors observed against ChatGPT Web (behavioral reference only).
// FRAGILE: the product DOM is not a stable API. When the product changes,
// update these lists — never the mechanism in observer.js. Strategies are
// tried in order; the first one matching any node wins (reported back).

export const TURN_STRATEGIES = [
  { name: "article-testid", sel: 'article[data-testid^="conversation-turn"]' },
  { name: "msg-author-role", sel: "[data-message-author-role]" },
  { name: "article-plain", sel: "main article" },
];

// Any match means "assistant is generating".
export const STOP_SELECTORS = [
  'button[data-testid="stop-button"]',
  'button[data-testid="stop-generating-button"]',
  'button[aria-label="Stop generating"]',
  'button[aria-label="Parar de gerar"]',
  'button[aria-label*="Stop"]',
];

export const ROLE_ATTRIBUTE = "data-message-author-role";

// Turns explicitly marked with these roles are never treated as assistant.
export const EXCLUDED_ROLES = ["user", "system"];

export const DEFAULT_CONFIG = {
  turnStrategies: TURN_STRATEGIES,
  stopSelectors: STOP_SELECTORS,
  roleAttribute: ROLE_ATTRIBUTE,
  excludedRoles: EXCLUDED_ROLES,
  stablePolls: 2, // unchanged content over N polls => finished
};
