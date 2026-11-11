// Entry point of the owner's live view, the one file page. It has no High (12.R18.2) and ignores the network: it is a file on disk.
import { boot } from './boot.js';

boot(window, { maxTier: 2, local: true });
