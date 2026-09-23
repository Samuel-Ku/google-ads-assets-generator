/* Shared edits across the responsive formats of one composition. */
(function (global) {
  'use strict';
  const copy = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const cleanLayer = layer => layer.type === 'image' && ['product', 'background'].includes(layer.role);
  const pmaxComposed = state => state && state.pmax_mode === 'composed';
  const cleanForProfile = (profile, state) => {
    if (profile === 'rda') return true;
    if (profile === 'pmax') return !pmaxComposed(state);
    return false;
  };

  function patchScene(target, before, after, adaptScene) {
    const next = copy(target), old = new Map(before.layers.map(l => [l.id, l]));
    const fresh = new Map(after.layers.map(l => [l.id, l]));
    next.layers = next.layers.filter(layer => !old.has(layer.id) || fresh.has(layer.id));
    for (const layer of next.layers) {
      const previous = old.get(layer.id), edited = fresh.get(layer.id);
      if (!previous || !edited) continue;
      const geometry = {x:layer.x, y:layer.y, w:layer.w, h:layer.h};
      const changedGeometry = new Set();
      for (const key of new Set([...Object.keys(previous), ...Object.keys(edited)])) {
        if (key === 'id' || equal(previous[key], edited[key])) continue;
        if (['x', 'y', 'w', 'h'].includes(key)) changedGeometry.add(key);
        if (!(key in edited)) { delete layer[key]; continue; }
        const value = edited[key];
        if (['x', 'y'].includes(key) && numeric(previous[key]) && numeric(value)) {
          layer[key] = Number(geometry[key] || 0) + value - previous[key];
        } else if (['w', 'h', 'fontSize'].includes(key) && numeric(previous[key]) && previous[key] > 0 && numeric(value)) {
          layer[key] = Number(layer[key] ?? previous[key]) * value / previous[key];
        } else if (key === 'borderWidth' && numeric(value)) {
          layer[key] = value * next.height / after.height;
        } else {
          layer[key] = copy(value);
        }
      }
      // The same relative movement can reach an edge sooner in another aspect
      // ratio. Bound only the affected axes, preserving unrelated local edits.
      if (changedGeometry.has('w') && numeric(layer.w)) layer.w = Math.max(.005, Math.min(1, layer.w));
      if (changedGeometry.has('h') && numeric(layer.h)) layer.h = Math.max(.005, Math.min(1, layer.h));
      if ((changedGeometry.has('x') || changedGeometry.has('w')) && numeric(layer.x)) {
        layer.x = Math.max(0, Math.min(Math.max(0, 1 - Number(layer.w || 0)), layer.x));
      }
      if ((changedGeometry.has('y') || changedGeometry.has('h')) && numeric(layer.y)) {
        layer.y = Math.max(0, Math.min(Math.max(0, 1 - Number(layer.h || 0)), layer.y));
      }
    }
    const added = after.layers.filter(layer => !old.has(layer.id));
    if (added.length) {
      const adapted = adaptScene(after, next.width, next.height, {clean:Boolean(next.clean)});
      for (const layer of added) {
        if (next.clean && !cleanLayer(layer)) continue;
        const candidate = adapted.layers.find(item => item.id === layer.id) || layer;
        next.layers.push(copy(candidate));
      }
    }
    // Preserve local order unless this edit actually changed relative ordering.
    const shared = new Set(before.layers.filter(l => fresh.has(l.id)).map(l => l.id));
    const oldOrder = before.layers.filter(l => shared.has(l.id)).map(l => l.id);
    const newOrder = after.layers.filter(l => shared.has(l.id)).map(l => l.id);
    if (!equal(oldOrder, newOrder)) {
      const positions = new Map(after.layers.map((l, i) => [l.id, i]));
      const movable = next.layers.filter(l => positions.has(l.id)).sort((a,b) => positions.get(a.id)-positions.get(b.id));
      let cursor = 0;
      next.layers = next.layers.map(l => positions.has(l.id) ? movable[cursor++] : l);
    }
    if (!equal(before.background, after.background)) next.background = after.background;
    next.content = next.content || {};
    for (const layer of after.layers) {
      if (layer.type === 'text' && !equal(old.get(layer.id)?.text, layer.text)) next.content[layer.role] = layer.text;
    }
    for (const layer of before.layers) {
      if (layer.type === 'text' && !fresh.has(layer.id)) next.content[layer.role] = '';
    }
    if (next.clean) next.layers = next.layers.filter(cleanLayer);
    return next;
  }

  function applyEdit(state, {template, formatId='master', before, after, masterScene, formats=[], adaptScene}) {
    state.template_scenes = state.template_scenes || {};
    state.scenes = state.scenes || {};
    const saveSource = () => {
      if (formatId === 'master') {
        state.template_scenes[template] = copy(after);
        if (!state.template || state.template === template) state.scene = copy(after);
      } else state.scenes[template + ':' + formatId] = copy(after);
    };
    if (!before || equal(before, after)) { saveSource(); return; }

    const master = copy(masterScene || state.template_scenes[template] || state.scene || adaptScene(before,1200,900));
    const targets = new Map();
    for (const f of formats) {
      if (f.profile === 'logos' || f.id.startsWith('logo_')) continue;
      targets.set(f.id, {width:f.width,height:f.height,clean:cleanForProfile(f.profile, state)});
    }
    for (const [key, scene] of Object.entries(state.scenes)) {
      if (key.startsWith(template + ':') && !key.slice(template.length + 1).startsWith('logo_') && !targets.has(key.slice(template.length + 1))) {
        targets.set(key.slice(template.length + 1),{width:scene.width,height:scene.height,clean:Boolean(scene.clean)});
      }
    }
    if (state.sync_formats === false) {
      // Unsaved formats normally derive lazily from the master. Freeze their
      // prior appearance before an isolated master edit changes that source.
      if (formatId === 'master') {
        for (const [id, dimensions] of targets) {
          const key = template + ':' + id;
          if (!state.scenes[key]) state.scenes[key] = adaptScene(master,dimensions.width,dimensions.height,{clean:dimensions.clean});
        }
      }
      saveSource();
      return;
    }
    for (const [id, dimensions] of targets) {
      if (id === formatId) continue;
      const key = template + ':' + id;
      const target = state.scenes[key] || adaptScene(master,dimensions.width,dimensions.height,{clean:dimensions.clean});
      state.scenes[key] = patchScene(target,before,after,adaptScene);
    }
    if (formatId !== 'master') {
      state.template_scenes[template] = patchScene(master,before,after,adaptScene);
      if (!state.template || state.template === template) state.scene = copy(state.template_scenes[template]);
    }
    const old = new Map(before.layers.map(layer => [layer.id,layer]));
    const textFields = {headline:'headlines',description:'descriptions',cta:'ctas'};
    for (const layer of after.layers) {
      const field = textFields[layer.role];
      if (layer.type === 'text' && field && !equal(old.get(layer.id)?.text,layer.text)) {
        state[field] = Array.isArray(state[field]) ? state[field].slice() : [];
        state[field][0] = layer.text || '';
      }
    }
    saveSource();
  }
  global.StudioSync = Object.freeze({applyEdit});
})(window);
