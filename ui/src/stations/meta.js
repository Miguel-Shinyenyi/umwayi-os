// The words of the eleven stations, as plain data: no three.js here. The page, the list view and the build read this.
// Order is the order on the ring (UI-Q8): neighbours that depend on each other sit next to each other.
// Words are the product's own: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first.
// state is "built" or "planned". Every station is built today, because every layer in it is built.
// deps are the stations this one leans on; the arcs in the sky are drawn from the selected station to these.
export const STATIONS = [
  {
    id: 'memory', name: 'Memory', layer: '1', state: 'built',
    lines: ['Plain files hold what your AI helpers need to know.', 'Private paths are left out of every context bundle.'],
    command: 'umwayi memory bundle', deps: ['logbook'],
    poses: [
      { id: 'graze', caption: 'Sheep graze in the pasture.' },
      { id: 'pebbles', caption: 'Pebbles in the walled plot stand for private paths.' },
      { id: 'closed', caption: 'The lid is closed. Private paths stay out.' },
    ],
  },
  {
    id: 'rules', name: 'Rules', layer: '2', state: 'built',
    lines: ['Every action gets Yes, No or Ask me first from your rules.', 'If anything is unclear, the answer is Ask me first.'],
    note: 'When a state is unknown, the gate is drawn as Ask me first.',
    command: 'umwayi check', deps: ['queue', 'logbook'],
    poses: [
      { id: 'yes', caption: 'Yes: the gate opens and the sheep passes.' },
      { id: 'no', caption: 'No: the gate stays shut and the sheep turns back.' },
      { id: 'ask', caption: 'Ask me first: the gate is half open and the sheep waits.' },
    ],
  },
  {
    id: 'queue', name: 'Queue', layer: '3', state: 'built',
    lines: ['Tasks and decisions wait here for you.', 'Ask me first puts a decision in the queue.'],
    command: 'umwayi queue list', deps: ['logbook'],
    poses: [
      { id: 'line', caption: 'Sheep wait in single file.' },
      { id: 'door', caption: 'The front sheep reaches the door.' },
      { id: 'moved', caption: 'The door closes and the line moves up.' },
    ],
  },
  {
    id: 'archive', name: 'Archive', layer: '4', state: 'built',
    lines: ['Text you move out leaves a pointer and a fingerprint.', 'The fingerprint shows if the text changes later.'],
    command: 'umwayi archive verify', deps: ['logbook'],
    poses: [
      { id: 'slab', caption: 'The text sits at the slab.' },
      { id: 'lifted', caption: 'It is lifted toward the cairn.' },
      { id: 'sealed', caption: 'A stone with a seal joins the cairn. A flag stays at the slab.' },
    ],
  },
  {
    id: 'logbook', name: 'Logbook', layer: '5', state: 'built', restIndex: 0,
    lines: ['Every change is one entry, and entries are only added.', 'Each entry is linked to the one before it, so an edit shows.'],
    command: 'umwayi logbook verify', deps: [],
    poses: [
      { id: 'intact', caption: 'Each entry is linked to the one before.' },
      { id: 'added', caption: 'A new entry joins the end of the chain.' },
      { id: 'altered', caption: 'One entry is altered. Every link after it goes dark.' },
    ],
  },
  {
    id: 'automation', name: 'Automation', layer: '6 and 11', state: 'built',
    lines: ['Jobs run on a schedule you set, through systemd timers.', 'Each run still passes the kill switch, the rules and the logbook.'],
    command: 'umwayi schedule check', deps: ['rules', 'killswitch', 'logbook'],
    poses: [
      { id: 'morning', caption: 'Morning. The shadow falls long.' },
      { id: 'noon', caption: 'Noon. The shadow is short.' },
      { id: 'evening', caption: 'Evening. The shadow has turned.' },
    ],
  },
  {
    id: 'helpers', name: 'AI helpers', layer: '7', state: 'built',
    lines: ['AI helpers draft. They never publish.', 'You read the draft and you post it.'],
    command: 'umwayi steward', deps: ['rules', 'queue', 'logbook'],
    poses: [
      { id: 'draft', caption: 'The helper carries the draft.' },
      { id: 'line', caption: 'The helper stops at the white line.' },
      { id: 'stool', caption: 'The draft waits on the stool for you to publish.' },
    ],
  },
  {
    id: 'workflows', name: 'Workflows', layer: '8', state: 'built',
    lines: ['Steps run in a fixed order: collect, brief, draft, approve.', 'The approve step waits for you.'],
    command: 'umwayi workflow run', deps: ['rules', 'killswitch', 'queue', 'logbook'],
    poses: [
      { id: 'start', caption: 'The first step is done.' },
      { id: 'middle', caption: 'The steps go on in order.' },
      { id: 'approve', caption: 'At the last step a token waits for your approval.' },
    ],
  },
  {
    id: 'adapters', name: 'Adapters', layer: '9 and 10', state: 'built', restIndex: 0,
    lines: ['Hooks and the front door put your rules before Claude Code and Kiro.', 'Every tool call is checked before it runs.'],
    command: 'umwayi agent check', deps: ['rules', 'logbook'],
    poses: [
      { id: 'fences', caption: 'Three kinds of fence, one latch.' },
      { id: 'claude', caption: 'Claude Code reaches the latch.' },
      { id: 'kiro', caption: 'Kiro reaches it too.' },
      { id: 'stdio', caption: 'So does any stdin and stdout tool.' },
    ],
  },
  {
    id: 'killswitch', name: 'Kill switch', layer: '8', state: 'built', restIndex: 0,
    lines: ['One flag stops every AI helper, job and workflow.', 'If umwayi cannot tell, it stops.'],
    command: 'umwayi kill status', deps: ['logbook'],
    poses: [
      { id: 'open', caption: 'The lane is open.' },
      { id: 'passes', caption: 'A sheep passes.' },
      { id: 'on', caption: 'The switch is on. The hurdle is up and the next sheep halts.' },
    ],
  },
  {
    id: 'budget', name: 'Budget', layer: 'budget governor', state: 'built', restIndex: 0,
    lines: ['A budget per run and per day, in units of one US cent.', 'A run that would pass its limit does not start.'],
    note: 'B.10, the capture of one real export, is not done.',
    command: 'umwayi budget status', deps: ['logbook', 'rules'],
    poses: [
      { id: 'low', caption: 'The trough is low. There is room.' },
      { id: 'mark', caption: 'Today\u2019s use reaches the mark.' },
      { id: 'limit', caption: 'At the limit. A run that would pass it does not start.' },
    ],
  },
];

export const BY_ID = Object.fromEntries(STATIONS.map((s) => [s.id, s]));
export const IDS = STATIONS.map((s) => s.id);
