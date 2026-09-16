"""ChatGPT-side adapters: observe a chat UI and emit source envelopes.

The DOM of ChatGPT Web is NOT a stable API: every selector below was
observed against the live product and may require updates when the product
changes. All fragile knowledge lives in selectors.js (explicit config);
observer.js holds only the generic mechanism and never hardcodes product
details. This package does NOT insert, send, click, or focus anything.
"""
