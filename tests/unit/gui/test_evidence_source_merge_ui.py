"""验证采用补证原文时的草稿状态变化，使用项目已有 TypeScript 编译器。"""
import json
import subprocess
from pathlib import Path


def test_adopting_sources_keeps_prior_facts_and_replaces_only_explicit_single_field():
    root = Path(__file__).resolve().parents[3]
    source = root / 'ui/src/pages/evidence/source-merge.ts'
    assert source.exists(), '补证草稿的采用操作尚未实现'
    script = r'''
      const ts = require('typescript'), fs = require('fs');
      const code = ts.transpileModule(fs.readFileSync(process.argv[1], 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021}}).outputText;
      const module = {exports:{}}; new Function('exports','module',code)(module.exports,module);
      const {adoptSource} = module.exports;
      let d = {source_material_ids:['m1'],source_documents:[],artifacts:[{ref:'m1',label:'旧材料',type:'text_document'}],
               role_scope:'参与开发',time_range:'',context:'平台',actions:['保留原行动'],results:['保留原成果'],field_sources:[]};
      const ref = {material_id:'m2',document_id:'doc2',sha256:'hash2',label:'底稿'};
      d = adoptSource(d,'time_range','2022 – 至今',ref);
      d = adoptSource(d,'role_scope','Tech Lead',ref);
      d = adoptSource(d,'actions','建立 Feature 机制',ref);
      d = adoptSource(d,'actions','建立 Feature 机制',ref);
      d = adoptSource(d,'results','新增成果一\n新增成果二',ref);
      console.log(JSON.stringify(d));
    '''
    result = subprocess.run(['node','-e',script,str(source)],cwd=root/'ui',capture_output=True,text=True,check=True)
    draft = json.loads(result.stdout)
    assert draft['source_material_ids'] == ['m1','m2']
    assert len(draft['source_documents']) == 1 and len(draft['artifacts']) == 2
    assert draft['time_range'] == '2022 – 至今' and draft['role_scope'] == 'Tech Lead'
    assert draft['actions'] == ['保留原行动', '建立 Feature 机制', '建立 Feature 机制']
    assert draft['results'] == ['保留原成果', '新增成果一\n新增成果二']
    assert len(draft['field_sources']) == 5
    assert all(c['quote'] == c['value'] for c in draft['field_sources'])

_NODE_FIXTURE = r'''
const assert = require('node:assert/strict');
const fs = require('fs');
const ts = require('typescript');
function loadModule(path, dependencies = {}) {
  const code = ts.transpileModule(fs.readFileSync(path, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021, jsx: ts.JsxEmit.ReactJSX}
  }).outputText;
  const module = {exports: {}};
  new Function('module', 'exports', 'require', code)(module, module.exports, name => {
    if (name in dependencies) return dependencies[name];
    throw new Error('Unexpected dependency: ' + name);
  });
  return module.exports;
}
const merge = loadModule('src/pages/evidence/source-merge.ts');
const ref = {material_id: 'synthetic-a', document_id: 'doc-a', sha256: 'version-a', label: '合成记录 A'};
const otherRef = {material_id: 'synthetic-b', document_id: 'doc-b', sha256: 'version-b', label: '合成记录 B'};
const value = '吞吐提高 20%';
const forecast = '预测：吞吐提高 20%，\n仅用于容量规划。';
const measured = '测试环境实测：吞吐提高 20%，\n样本为 200 次请求；尚未验证生产环境。';
const nonquant = '完善故障排查文档，交由值班同事复核。';
const sourceText = '# 独立合成记录\n' + forecast + '\n\n' + measured + '\n\n' + nonquant + '\n\n复盘故障链路，并记录待验证项。\n';
function makeDraft() {
  return {
    title: '合成边界验证', context: '离线合成项目', role_scope: '参与验证',
    actions: ['复盘故障链路'], results: [value, '完善故障排查文档'],
    stack: [], tags: [], source_material_ids: [ref.material_id, otherRef.material_id],
    source_documents: [ref, otherRef],
    artifacts: [{type: 'text_document', ref: ref.material_id, label: ref.label}, {type: 'text_document', ref: otherRef.material_id, label: otherRef.label}],
    field_sources: [
      {field: 'results', value, quote: value, material_id: ref.material_id, document_id: ref.document_id},
      {field: 'results', value, quote: '评审草稿记下吞吐提高 20%', material_id: otherRef.material_id, document_id: otherRef.document_id},
      {field: 'results', value: '完善故障排查文档', quote: '完善故障排查文档', material_id: ref.material_id, document_id: ref.document_id},
      {field: 'actions', value: '复盘故障链路', quote: '复盘故障链路', material_id: ref.material_id, document_id: ref.document_id}
    ]
  };
}
const position = {field: 'results', index: 0, value};
function equal(actual, expected) { assert.equal(JSON.stringify(actual), JSON.stringify(expected)); }
'''


def _run_source_ui(script: str) -> None:
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ['node', '-e', _NODE_FIXTURE + script],
        cwd=root / 'ui', capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_adopt_source_normalizes_scalar_value_but_keeps_complete_quote_and_fact_bytes():
    _run_source_ui(r'''
const draft = makeDraft(), before = JSON.stringify(draft);
for (const field of ['actions', 'results']) {
  const quote = ' \n  测试环境：保留完整条件。\n尚未验证生产环境。 \n';
  const next = merge.adoptSource(draft, field, quote, ref);
  equal(next[field], [...draft[field], quote]);
  equal(next.field_sources.at(-1), {field, value: quote, quote, material_id: ref.material_id, document_id: ref.document_id});
  equal(next.field_sources.slice(0, -1), draft.field_sources);
}
for (const [field, value] of [['time_range', '2024-01 ~ 2024-06'], ['role_scope', '参与验证'], ['context', '测试环境\n仅覆盖合成请求']]) {
  const quote = ' \n  ' + value + ' \n';
  const next = merge.adoptSource(draft, field, quote, ref);
  assert.equal(next[field], value, 'scalar value must match the existing API normalization');
  equal(next.field_sources.at(-1), {field, value, quote, material_id: ref.material_id, document_id: ref.document_id});
  equal(next.actions, draft.actions);
  equal(next.results, draft.results);
}
assert.equal(JSON.stringify(draft), before);
''')


def test_extend_quote_keeps_exact_fact_other_sources_siblings_and_multiline_context():
    _run_source_ui(r'''
const draft = makeDraft(), before = JSON.stringify(draft);
for (const quote of [forecast, measured]) {
  const next = merge.extendSourceQuote(draft, position, draft.field_sources[0], {...ref, label: '只读显示名'}, sourceText, quote);
  const expected = JSON.parse(before);
  expected.field_sources[0].quote = quote;
  equal(next, expected);
  assert.equal(next.actions, draft.actions);
  assert.equal(next.results, draft.results);
  assert.equal(next.source_documents, draft.source_documents);
  assert.equal(next.field_sources[1], draft.field_sources[1]);
  assert.equal(next.field_sources[2], draft.field_sources[2]);
  assert.equal(next.field_sources[3], draft.field_sources[3]);
  assert.equal(JSON.stringify(draft), before);
}
for (const [index, pos, quote] of [
  [2, {field: 'results', index: 1, value: '完善故障排查文档'}, nonquant],
  [3, {field: 'actions', index: 0, value: '复盘故障链路'}, '复盘故障链路，并记录待验证项。']
]) {
  const next = merge.extendSourceQuote(draft, pos, draft.field_sources[index], ref, sourceText, quote);
  const expected = JSON.parse(before);
  expected.field_sources[index].quote = quote;
  equal(next, expected);
}
''')


def test_extend_quote_rejects_identity_version_replacement_and_ambiguous_locations():
    _run_source_ui(r'''
function reject(code, change) {
  const d = makeDraft();
  const args = [d, position, {...d.field_sources[0]}, ref, sourceText, measured];
  change(args, d);
  const before = JSON.stringify(d);
  assert.throws(() => merge.extendSourceQuote(...args), error => error.message === code);
  assert.equal(JSON.stringify(d), before);
}
for (const pos of [
  {field: 'results', index: 1, value},
  {field: 'results', index: 0, value: '20%'},
  {field: 'results', index: 0.5, value},
  {field: 'context', index: 0, value}
]) reject('fact_scope_invalid_position', args => args[1] = pos);
reject('fact_scope_invalid_position', (_, d) => d.results = ['完善故障排查文档', value]);
reject('fact_scope_invalid_position', (_, d) => d.results.push(value));
reject('field_source_not_traceable', args => args[2] = {...args[2], quote: '不同旧引文'});
reject('field_source_not_traceable', (_, d) => d.field_sources.push({...d.field_sources[0]}));
reject('field_source_not_traceable', args => args[2] = {...args[2], field: 'actions'});
for (const key of ['material_id', 'document_id', 'sha256']) {
  reject('material_document_changed_or_missing', args => args[3] = {...ref, [key]: 'changed'});
}
reject('material_document_changed_or_missing', (_, d) => d.source_documents = [otherRef]);
reject('field_source_not_traceable', args => args[5] = value);
reject('field_source_not_traceable', args => args[5] = '生产环境吞吐提高 20%');
reject('field_source_not_traceable', (args, d) => {
  d.field_sources[0].quote = measured;
  args[2] = {...d.field_sources[0]};
  args[5] = forecast;
});
reject('fact_scope_source_not_unique', args => args[4] = sourceText + measured);
reject('fact_scope_source_not_unique', args => args[5] = forecast + '\n\n' + measured);
''')


_COMPONENT = r'''
const Picker = function MaterialDocumentPicker() {};
function panel(initialDraft = makeDraft()) {
  const hooks = [];
  let cursor = 0, effects = [], dirty = false, tree, disposed = false;
  const changes = [];
  let props = {draft: initialDraft, materials: [
    {...ref, filename: 'synthetic-a.md', extension: '.md'},
    {...otherRef, filename: 'synthetic-b.md', extension: '.md'}
  ], disabled: false, onChange: next => changes.push(next)};
  const same = (a, b) => a && b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = {value: typeof initial === 'function' ? initial() : initial};
      return [hooks[index].value, next => {
        if (disposed) return;
        const value = typeof next === 'function' ? next(hooks[index].value) : next;
        if (!Object.is(value, hooks[index].value)) { hooks[index].value = value; dirty = true; }
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = {current: initial};
      return hooks[index];
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!hooks[index] || !same(hooks[index].deps, deps)) {
        const cleanup = hooks[index]?.cleanup;
        hooks[index] = {deps};
        effects.push(() => { cleanup?.(); hooks[index].cleanup = effect(); });
      }
    }
  };
  const jsx = (type, props, key) => ({type, props: props || {}, key});
  const {EvidenceSourceMerge} = loadModule('src/pages/evidence/source-merge-panel.tsx', {
    react, 'react/jsx-runtime': {jsx, jsxs: jsx},
    'react-i18next': {useTranslation: () => ({t: key => key})},
    './material-document-picker': {MaterialDocumentPicker: Picker},
    './source-merge': merge
  });
  function render(runEffects = true) {
    if (runEffects) {
      const pending = effects; effects = [];
      pending.forEach(effect => effect());
    }
    let count = 0;
    do {
      assert.ok(++count < 20, 'component did not settle');
      dirty = false; cursor = 0; effects = [];
      tree = EvidenceSourceMerge(props);
      if (!runEffects) break;
      const pending = effects; effects = [];
      pending.forEach(effect => effect());
    } while (dirty);
    return tree;
  }
  function nodes() {
    const result = [];
    function visit(node) {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) { node.forEach(visit); return; }
      result.push(node); visit(node.props?.children);
    }
    visit(tree);
    return result;
  }
  function text(node) {
    if (node === null || node === undefined || typeof node === 'boolean') return '';
    if (Array.isArray(node)) return node.map(text).join('');
    return typeof node === 'object' ? text(node.props?.children) : String(node);
  }
  function button(label, index = 0) {
    const found = nodes().filter(n => n.type === 'button' && text(n).includes(label))[index];
    assert.ok(found, 'missing button ' + label);
    return found;
  }
  function picker() { return nodes().find(n => n.type === Picker); }
  function quote(value) {
    nodes().find(n => n.type === 'textarea').props.onChange({target: {value}});
    render();
  }
  function confirm() {
    nodes().find(n => n.type === 'input' && n.props.type === 'checkbox').props.onChange({target: {checked: true}});
    render();
  }
  function read(document = ref, content = sourceText) {
    const old = picker();
    old.props.onSelect(null); render();
    old.props.onRead(content); old.props.onSelect(document); render();
  }
  function start(index = 0) { button('sourceMerge.extend', index).props.onClick(); render(); }
  function ready(quoteText = measured, index = 0) { start(index); read(); quote(quoteText); confirm(); }
  render();
  return {
    changes, nodes, button, picker, quote, confirm, read, start, ready, render,
    setProps(next, runEffects = true) { props = {...props, ...next}; render(runEffects); },
    alerts() { return nodes().filter(n => n.props.role === 'alert').map(text).join(' '); },
    unmount() { hooks.forEach(hook => hook?.cleanup?.()); disposed = true; }
  };
}
'''


def test_source_merge_component_expands_only_the_selected_binding_as_draft():
    _run_source_ui(_COMPONENT + r'''
const p = panel();
p.ready();
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, false);
p.button('sourceMerge.applyExtension').props.onClick();
p.render();
assert.equal(p.changes.length, 1);
const expected = makeDraft();
expected.field_sources[0].quote = measured;
equal(p.changes[0], expected);
assert.ok(p.nodes().some(node => node.props.children === 'sourceMerge.reviewExtension'));
''')


def test_source_merge_component_rejects_same_number_other_context_and_changed_document():
    _run_source_ui(_COMPONENT + r'''
const d = makeDraft();
d.field_sources[0].quote = measured;
const p = panel(d);
p.ready(forecast);
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, true);
p.button('sourceMerge.applyExtension').props.onClick();
assert.equal(p.changes.length, 0);
assert.ok(p.alerts().includes('sourceMerge.extensionInvalid'));
const q = panel();
q.start(); q.read({...ref, sha256: 'another-version'}); q.quote(measured); q.confirm();
assert.equal(q.button('sourceMerge.applyExtension').props.disabled, true);
q.button('sourceMerge.applyExtension').props.onClick();
assert.equal(q.changes.length, 0);
assert.ok(q.alerts().includes('sourceMerge.extensionSourceChanged'));
equal(d.source_documents, [ref, otherRef]);
''')


def test_source_merge_component_target_change_ignores_old_apply_and_reader_callbacks():
    _run_source_ui(_COMPONENT + r'''
const p = panel();
p.ready();
const oldApply = p.button('sourceMerge.applyExtension').props.onClick;
const oldReader = p.picker().props;
p.start(2);
oldReader.onRead(sourceText); oldReader.onSelect(ref); p.render();
oldApply();
assert.equal(p.changes.length, 0);
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, true);
p.read(); p.quote(nonquant); p.confirm();
oldApply();
assert.equal(p.changes.length, 0);
p.button('sourceMerge.applyExtension').props.onClick();
assert.equal(p.changes.length, 1);
const expected = makeDraft();
expected.field_sources[2].quote = nonquant;
equal(p.changes[0], expected);
''')


def test_source_merge_component_draft_busy_and_card_changes_invalidate_old_confirmation():
    _run_source_ui(_COMPONENT + r'''
for (const change of [
  p => p.setProps({draft: {...makeDraft(), results: ['完善故障排查文档', value]}}),
  p => { p.setProps({disabled: true}); p.setProps({disabled: false}); },
  p => p.unmount()
]) {
  const p = panel();
  p.ready();
  const oldApply = p.button('sourceMerge.applyExtension').props.onClick;
  const oldReader = p.picker().props;
  change(p);
  oldReader.onRead(sourceText); oldReader.onSelect(ref);
  oldApply();
  assert.equal(p.changes.length, 0);
}
const oldCard = panel();
oldCard.ready();
const stale = oldCard.button('sourceMerge.applyExtension').props.onClick;
oldCard.unmount();
const nextCard = panel();
stale();
assert.equal(oldCard.changes.length, 0);
assert.equal(nextCard.changes.length, 0);
''')


def test_source_merge_component_quote_or_source_change_requires_new_confirmation():
    _run_source_ui(_COMPONENT + r'''
const p = panel();
p.ready();
const oldApply = p.button('sourceMerge.applyExtension').props.onClick;
p.quote(forecast);
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, true);
oldApply();
assert.equal(p.changes.length, 0);
p.confirm();
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, false);
oldApply();
assert.equal(p.changes.length, 0);
const beforeRead = p.button('sourceMerge.applyExtension').props.onClick;
p.picker().props.onSelect(null); p.render();
beforeRead();
assert.equal(p.changes.length, 0);
assert.equal(p.button('sourceMerge.applyExtension').props.disabled, true);
''')


_ACTUAL_PICKER = r'''
function actualPicker(p) {
  let hooks = [], cursor = 0, effects = [], tree, key;
  const requests = [];
  const same = (a, b) => a && b && a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
  const react = {
    useState(value) {
      const slots = hooks, index = cursor++;
      if (!slots[index]) slots[index] = {value: typeof value === 'function' ? value() : value};
      return [slots[index].value, next => { slots[index].value = typeof next === 'function' ? next(slots[index].value) : next; }];
    },
    useRef(value) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = {current: value};
      return hooks[index];
    },
    useEffect(effect, deps) {
      const slots = hooks, index = cursor++;
      if (!slots[index] || !same(slots[index].deps, deps)) {
        const cleanup = slots[index]?.cleanup;
        slots[index] = {deps};
        effects.push(() => { cleanup?.(); slots[index].cleanup = effect(); });
      }
    }
  };
  const jsx = (type, props) => ({type, props: props || {}});
  const {MaterialDocumentPicker} = loadModule('src/pages/evidence/material-document-picker.tsx', {
    react, 'react/jsx-runtime': {jsx, jsxs: jsx},
    'react-i18next': {useTranslation: () => ({t: key => key})},
    '@/lib/errors': {getErrorMessage: String},
    '@/lib/sidecar/api': {
      listMaterialDocuments: async () => ({items: [{document_id: ref.document_id, label: ref.label, char_count: sourceText.length}], matched: 1, total: 1}),
      readMaterialDocument: (material, document) => new Promise(resolve => requests.push({material, document, resolve}))
    }
  });
  function nodes(node) {
    if (Array.isArray(node)) return node.flatMap(nodes);
    return node && typeof node === 'object' ? [node, ...nodes(node.props?.children)] : [];
  }
  async function settle() {
    for (let i = 0; i < 6; i++) {
      p.render();
      const marker = p.picker();
      if (marker.key !== key) {
        hooks.forEach(hook => hook?.cleanup?.()); hooks = []; key = marker.key;
      }
      cursor = 0; effects = [];
      tree = MaterialDocumentPicker(marker.props);
      effects.forEach(effect => effect());
      await Promise.resolve(); await Promise.resolve();
    }
    p.render();
  }
  return {
    settle, requests,
    select() { nodes(tree).find(node => node.props['data-testid'] === 'document-select').props.onChange({target: {value: ref.document_id}}); }
  };
}
'''


def test_source_merge_uses_actual_picker_read_protocol_and_discards_unmounted_reads():
    _run_source_ui(_COMPONENT + _ACTUAL_PICKER + r'''
(async () => {
  const p = panel(), picker = actualPicker(p);
  await picker.settle();
  p.start(); await picker.settle();
  picker.select(); await picker.settle();
  assert.equal(picker.requests.length, 1);
  equal([picker.requests[0].material, picker.requests[0].document], [ref.material_id, ref.document_id]);
  picker.requests[0].resolve({...ref, text: sourceText});
  await picker.settle();
  p.quote(measured); p.confirm();
  assert.equal(p.button('sourceMerge.applyExtension').props.disabled, false);
  p.button('sourceMerge.applyExtension').props.onClick();
  assert.equal(p.changes.length, 1);
  assert.equal(p.changes[0].field_sources[0].quote, measured);

  const q = panel(), pending = actualPicker(q);
  await pending.settle(); q.start(); await pending.settle();
  pending.select(); await pending.settle();
  q.start(2); await pending.settle();
  pending.requests[0].resolve({...ref, text: sourceText});
  await pending.settle();
  q.quote(nonquant); q.confirm();
  assert.equal(q.button('sourceMerge.applyExtension').props.disabled, true);
  q.button('sourceMerge.applyExtension').props.onClick();
  assert.equal(q.changes.length, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
''')


def test_source_merge_keeps_read_document_when_ordinary_append_changes_field():
    _run_source_ui(_COMPONENT + _ACTUAL_PICKER + r'''
(async () => {
  const p = panel(), picker = actualPicker(p);
  await picker.settle();
  p.nodes().find(node => node.props['aria-label'] === 'sourceMerge.material').props.onChange({target: {value: ref.material_id}});
  await picker.settle();
  picker.select(); await picker.settle();
  picker.requests[0].resolve({...ref, text: sourceText}); await picker.settle();
  p.nodes().find(node => node.props['aria-label'] === 'sourceMerge.field').props.onChange({target: {value: 'results'}});
  await picker.settle();
  p.quote(nonquant); p.confirm();
  assert.equal(p.button('sourceMerge.append').props.disabled, false, '选字段不应丢掉已经读取的文档');
  p.button('sourceMerge.append').props.onClick();
  assert.equal(p.changes.length, 1);
  equal(p.changes[0].results, [...makeDraft().results, nonquant]);
  assert.equal(picker.requests.length, 1);

  const firstApply = p.button('sourceMerge.append').props.onClick;
  p.render();
  p.setProps({draft: p.changes[0]});
  await picker.settle();
  firstApply();
  assert.equal(p.changes.length, 1, '草稿更新后不能重放旧采用回调');
  p.nodes().find(node => node.props['aria-label'] === 'sourceMerge.field').props.onChange({target: {value: 'actions'}});
  await picker.settle();
  p.quote('复盘故障链路，并记录待验证项。'); p.confirm();
  assert.equal(p.button('sourceMerge.append').props.disabled, false, '同一文档应能连续补充第二个字段');
  p.button('sourceMerge.append').props.onClick();
  assert.equal(p.changes.length, 2);
  equal(p.changes[1].actions, [...makeDraft().actions, '复盘故障链路，并记录待验证项。']);
  assert.equal(picker.requests.length, 1);
})().catch(error => { console.error(error); process.exitCode = 1; });
''')


def test_source_merge_ordinary_draft_change_invalidates_confirmation_before_effects():
    _run_source_ui(_COMPONENT + r'''
const p = panel();
p.nodes().find(node => node.props['aria-label'] === 'sourceMerge.material').props.onChange({target: {value: ref.material_id}});
p.render(); p.read();
p.nodes().find(node => node.props['aria-label'] === 'sourceMerge.field').props.onChange({target: {value: 'results'}});
p.render(); p.quote(nonquant); p.confirm();
const stale = p.button('sourceMerge.append').props.onClick;
p.setProps({draft: {...makeDraft(), title: '合成标题修订'}}, false);
assert.equal(p.nodes().find(node => node.type === 'input' && node.props.type === 'checkbox').props.checked, false);
assert.equal(p.button('sourceMerge.append').props.disabled, true);
stale(); assert.equal(p.changes.length, 0);
p.render(); p.confirm();
assert.equal(p.button('sourceMerge.append').props.disabled, false, '普通草稿变化仅撤确认，仍沿用同一已读文档');
p.button('sourceMerge.append').props.onClick();
assert.equal(p.changes.length, 1);
assert.equal(p.changes[0].title, '合成标题修订');
''')


def test_source_merge_keeps_multiline_fact_position_and_does_not_merge_separate_items():
    _run_source_ui(r'''
const d = makeDraft();
const complete = '在隔离测试环境、固定数据集下，\nP95 从 200 ms 降至 120 ms；生产效果未知。';
d.results = [complete, '完善故障排查文档'];
d.field_sources = d.field_sources.map((binding, index) =>
  index < 2 ? {...binding, value: complete, quote: index === 0 ? complete : '合成复核材料：\n' + complete} : binding);
const original = JSON.stringify(d);
const fullQuote = '本次测试摘录：\n' + complete + '\n测量窗口只覆盖本次隔离测试。';
const next = merge.extendSourceQuote(d, {field: 'results', index: 0, value: complete},
  d.field_sources[0], ref, fullQuote, fullQuote);
equal(next.results, [complete, '完善故障排查文档']);
assert.equal(next.results.length, 2);
assert.equal(next.field_sources[0].value, complete);
assert.equal(next.field_sources[0].quote, fullQuote);
equal(next.field_sources.slice(1), d.field_sources.slice(1));
assert.equal(JSON.stringify(d), original);
const repeated = {...d, results: [...d.results, '完善故障排查文档']};
const addition = '补充成果保持同一条：\n已交付合成操作说明。';
const appended = merge.adoptSource(repeated, 'results', addition, ref);
equal(appended.results, [...repeated.results, addition]);
assert.equal(appended.field_sources.at(-1).value, addition);
assert.equal(appended.field_sources.at(-1).quote, addition);
''')
