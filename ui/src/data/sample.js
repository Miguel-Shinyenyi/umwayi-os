// Sample counts, in the shape of the snapshot of requirement 12.R4. They are made up. The page says "sample"
// while it shows them. The real counts come from `umwayi view snapshot` (UI.2) and are read in UI.3.
export const SAMPLE = {
  schema: 1,
  date: '2026-11-10',
  queue: { open: 6, answered: 5 },
  rules: { yes: 7, no: 6, ask: 2 },
  logbook: { entries: 312, chain_length: 20 },
  budget: {
    days: [4, 12, 7, 20, 15, 31, 18].map((used_uu, i) => ({ date: `2026-11-0${i + 4}`, used_uu })),
  },
  kill_switch: 'off',
  schedule: { entries: 3, installed: 2, enabled: 1 },
};
