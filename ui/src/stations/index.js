// The eleven stations: the words (meta.js) joined with the models (one module each), and where each stands (world/layout.js).
import * as THREE from 'three';
import { STATIONS } from './meta.js';
import { TABLE } from '../world/layout.js';
import * as memory from './memory.js';
import * as rules from './rules.js';
import * as queue from './queue.js';
import * as archive from './archive.js';
import * as logbook from './logbook.js';
import * as automation from './automation.js';
import * as helpers from './helpers.js';
import * as workflows from './workflows.js';
import * as adapters from './adapters.js';
import * as killswitch from './killswitch.js';
import * as budget from './budget.js';

const MODULES = { memory, rules, queue, archive, logbook, automation, helpers, workflows, adapters, killswitch, budget };
export const ANCHOR_HEIGHT = 2.8; // where the name, the trails and the buttons hang, above the ground

export function stationDefs() {
  return STATIONS.map((meta) => {
    const mod = MODULES[meta.id];
    return { ...meta, poses: meta.poses.map((p, i) => ({ ...p, params: mod.poses[i] })), build: mod.build };
  });
}

export function buildStation(def, kit) {
  const row = TABLE.find((r) => r.id === def.id);
  const model = def.build(kit);
  const group = new THREE.Group();
  group.name = def.id;
  group.add(model.group);
  kit.shadow(group);
  const hit = new THREE.Mesh(new THREE.CylinderGeometry(row.footprint + 0.3, row.footprint + 0.3, 4.4, 14), new THREE.MeshBasicMaterial());
  hit.position.y = 2.0;
  hit.visible = false;
  hit.userData.station = def.id;
  group.add(hit);
  return {
    id: def.id, def, group, hit, row, river: !!row.river, footprint: row.footprint,
    pos: { x: 0, z: 0, y: 0 }, facing: { x: 0, z: 1 }, anchor: new THREE.Vector3(),
    poses: def.poses, restIndex: def.restIndex,
    apply: model.apply, setCounts: model.setCounts, rest: model.rest,
  };
}
