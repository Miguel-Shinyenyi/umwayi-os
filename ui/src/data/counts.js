// The line of counts shown in a station's panel and in the list view. Pure: a snapshot (or the sample) in, text out.
// A part that is null or missing is "unknown", never zero. Stations the snapshot has no counts for say so.
const unknown = 'unknown';
const n = (v) => (Number.isFinite(v) ? String(v) : unknown);

export function describe(id, c) {
  if (!c) return null;
  switch (id) {
    case 'queue':
      return c.queue ? `${n(c.queue.open)} open, ${n(c.queue.answered)} answered` : unknown;
    case 'rules':
      return c.rules ? `${n(c.rules.yes)} Yes, ${n(c.rules.no)} No, ${n(c.rules.ask)} Ask me first` : `${unknown}, drawn as Ask me first`;
    case 'logbook':
      return c.logbook ? `${n(c.logbook.entries)} entries, ${n(c.logbook.chain_length)} in the chain` : unknown;
    case 'killswitch':
      return c.kill_switch === 'off' ? 'off' : c.kill_switch === 'on' ? 'on' : `${unknown}, drawn as on`;
    case 'automation':
      return c.schedule ? `${n(c.schedule.entries)} schedules, ${n(c.schedule.installed)} installed, ${n(c.schedule.enabled)} enabled` : unknown;
    case 'budget':
      return c.budget && Array.isArray(c.budget.days) ? `Used in the last 7 days (UU): ${c.budget.days.map((d) => n(d.used_uu)).join(', ')}` : unknown;
    default:
      return null; // memory, archive, helpers, workflows, adapters: the snapshot has no count for them
  }
}

export const NO_COUNT = 'No count is shown for this station.';
