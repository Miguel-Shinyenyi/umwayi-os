section: Provenance record (W49), found while building the record
title: the record exists but nothing signs or verifies it, and it is off unless the owner turns it on
number: 335

These are facts of the code of this change. The record is made by the supervisor and read by nothing yet.

- `umwayi.json` must say `"provenance": {"record": true}`. Off, no task has a record and nothing changes. The design note makes it always on; this is the deviation, so no existing root breaks for lack of a hash chain.
- A record needs the hash chain (`umwayi logbook seal --chain`). With the setting on and no chain, the task goes to `needs owner` (config, cause `provenance_not_recorded`) and no record is written.
- The record is not signed. `umwayi provenance sign` and `umwayi verify` are not built: they need the owner's key, and their tests need keys. A record on its own does not show that a file came out of a umwayi task. Anyone who can write the root can write a record and its entry.
- `provenance.compare` says whether bytes match a record. It is a comparison, not a proof, and no command calls it yet.
- The records are on this machine in `.umwayi/provenance/`. A clone has none. `.gitignore` ignores the folder.
- The structure hash of a `.py` file is compared only under the same Python minor version. A docstring change counts as a structure change.
- The record holds paths, hashes and sizes of the files a task changed. It holds no content. The entry holds the hash of the record and counts, no path.
