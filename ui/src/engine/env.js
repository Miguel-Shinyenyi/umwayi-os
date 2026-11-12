// Reads the device hints for the tier choice (12.R16.5). This is the only file that reads them. What it reads stays in the
// page: it is never sent, stored or written to the address. The WebGL test uses a canvas of its own and lets it go.
export function readEnv(win) {
  const nav = win.navigator || {};
  let webgl = false, renderer = '';
  try {
    const gl = win.document.createElement('canvas').getContext('webgl2');
    if (gl) {
      webgl = true;
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      renderer = String(gl.getParameter(dbg ? dbg.UNMASKED_RENDERER_WEBGL : gl.RENDERER) || '');
      const lose = gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
    }
  } catch { webgl = false; }
  const c = nav.connection;
  const connection = c ? { effectiveType: c.effectiveType, downlink: c.downlink, saveData: c.saveData === true } : null;
  const s = win.screen || {};
  const reducedMotion = !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
  return { webgl, cores: nav.hardwareConcurrency, memory: nav.deviceMemory, connection, renderer, screen: { w: s.width, h: s.height }, reducedMotion };
}
