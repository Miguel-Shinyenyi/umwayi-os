// Entry point of the owner's live view, the one file page. It has no High (12.R18.2). Opened from disk it makes no request: the
// page client (api/client.js) works only on http://127.0.0.1:PORT, where `umwayi serve` serves this page (W6.9).
// The scene code is in the same file, so loading it is already done. The public site (site/) does not use initBackend and never
// gets the client: it does not import this file.
import { boot } from './boot.js';
import { createApp } from './app.js';
import { initBackend } from './ui/backend.js';

boot(window, { maxTier: 2, local: true }, () => Promise.resolve(createApp));
initBackend(window.document, window);
