// The page shell: the html element is List (tier 1) in what the server sends, so with no script the page is List (12.R16.1).
// data-js is not here: only the script sets it, so the Copy buttons and the switch show only where they work.
import { createElement as h } from 'react';

export function Document({ children }) {
  return h('html', { lang: 'en', 'data-tier': 'list' }, h('body', null, children));
}
