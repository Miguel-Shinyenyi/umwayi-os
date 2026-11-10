// The eleven stations: the words (meta.js) joined with the models (one module each). The ring order is the order here.
import * as THREE from 'three';
import { STATIONS } from './meta.js';
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

export function stationDefs() {
  return STATIONS.map((meta) => {
    const mod = MODULES[meta.id];
    return { ...meta, poses: meta.poses.map((p, i) => ({ ...p, params: mod.poses[i] })), build: mod.build };
  });
}

export const ANCHOR_HEIGHT = 2.5; // where the label's line ends, above the station

export function buildStation(def, kit) {
  const model = def.build(kit);
  const group = new THREE.Group();
  group.name = def.id;
  group.add(kit.platform());
  model.group.position.y = kit.PLATFORM_TOP;
  group.add(model.group);
  kit.shadow(group);
  const hit = new THREE.Mesh(new THREE.CylinderGeometry(2.7, 2.7, 3.4, 16), new THREE.MeshBasicMaterial());
  hit.position.y = 1.7;
  hit.visible = false;
  hit.userData.station = def.id;
  group.add(hit);
  return {
    id: def.id, def, group, hit, poses: def.poses, restIndex: def.restIndex,
    apply: model.apply, setCounts: model.setCounts, rest: model.rest,
  };
}
