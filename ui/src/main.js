// Entry point of the owner's live view, the one file page. It has no High (12.R18.2) and ignores the network: it is a file on disk.
// The scene code is in the same file, so loading it is already done.
import { boot } from './boot.js';
import { createApp } from './app.js';

boot(window, { maxTier: 2, local: true }, () => Promise.resolve(createApp));
