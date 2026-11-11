// The tier choice (12.R16.6). Pure: the device hints in, a tier out. Nothing here reads the browser, and nothing it is
// given is sent or stored anywhere: env.js reads the hints, this decides, and the result only picks which scene to draw.
export const TIERS = [
  { tier: 1, name: 'list', label: 'List' },
  { tier: 2, name: 'standard', label: 'Standard' },
  { tier: 3, name: 'high', label: 'High' },
];
const BY_NAME = Object.fromEntries(TIERS.map((t) => [t.name, t.tier]));
const nameOf = (tier) => TIERS[tier - 1].name;

const SOFTWARE = /swiftshader|llvmpipe|softpipe|software|basic render/i;
const num = (v) => typeof v === 'number' && Number.isFinite(v);
const validTier = (v) => v === 1 || v === 2 || v === 3;

// The automatic choice, before the switch.
function automatic(env, maxTier, local) {
  const c = !local && env.connection && typeof env.connection === 'object' ? env.connection : null;
  if (c && (c.saveData === true || c.effectiveType === 'slow-2g' || c.effectiveType === '2g')) return { tier: 1, reason: c.saveData === true ? 'save-data' : 'slow-network' };
  const s = env.screen || {};
  const high = maxTier >= 3 && !local && c
    && c.effectiveType === '4g' && num(c.downlink) && c.downlink >= 10
    && num(env.cores) && env.cores >= 8
    && (!num(env.memory) || env.memory >= 8)
    && typeof env.renderer === 'string' && env.renderer !== '' && !SOFTWARE.test(env.renderer)
    && num(s.w) && num(s.h) && Math.min(s.w, s.h) >= 720
    && env.reducedMotion !== true;
  return high ? { tier: 3, reason: 'capable' } : { tier: 2, reason: 'standard' };
}

// env: { webgl, cores, memory, connection: { effectiveType, downlink, saveData } | null, renderer, screen: { w, h }, reducedMotion }
// options: maxTier (3 on the public site, 2 in the owner's live view), local (true for a file on disk: the network is ignored),
// requested (1, 2 or 3 from the switch, or null)
export function chooseTier(env = {}, { maxTier = 3, local = false, requested = null } = {}) {
  const e = env && typeof env === 'object' ? env : {};
  if (e.webgl !== true) return { tier: 1, name: 'list', reason: 'no-webgl', warn: false };
  const auto = automatic(e, maxTier, local);
  if (validTier(requested)) {
    const tier = Math.min(requested, maxTier);
    return { tier, name: nameOf(tier), reason: 'requested', warn: tier > auto.tier };
  }
  return { tier: auto.tier, name: nameOf(auto.tier), reason: auto.reason, warn: false };
}

// The switch keeps its choice in the address fragment only (a browser never sends it to a server): "#tier=list".
const params = (hash) => String(hash || '').replace(/^#/, '').split('&').filter(Boolean);
export function parseTier(hash) {
  for (const p of params(hash)) {
    const [k, v] = p.split('=');
    if (k === 'tier' && Object.hasOwn(BY_NAME, v)) return BY_NAME[v];
  }
  return null;
}
export function tierHash(hash, tier) {
  const rest = params(hash).filter((p) => p.split('=')[0] !== 'tier');
  return '#' + [...rest, `tier=${nameOf(tier)}`].join('&');
}
