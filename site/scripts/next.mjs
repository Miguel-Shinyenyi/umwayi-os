// Runs the Next.js command line with its telemetry switched off (12.R17.2: NEXT_TELEMETRY_DISABLED=1), the same on every system.
// node scripts/next.mjs build | start | dev. The owner runs it; umwayi never runs npm, node or this site.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const bin = require.resolve('next/dist/bin/next');
const child = spawn(process.execPath, [bin, ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' },
});
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
