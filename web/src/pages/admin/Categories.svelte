<script>
  // Category groups and options used for filters and auto-tagging (never created automatically).
  import { get, post, patch, del, errorText } from '../../lib/api.js';
  import { toast } from '../../lib/state.svelte.js';
  import { resetCatalog } from '../../lib/catalog.js';
  import Modal from '../../components/Modal.svelte';
  import Icon from '../../components/Icon.svelte';

  let groups = $state(null);
  let error = $state('');
  let editing = $state(null); // { kind: 'option'|'group', ... }
  let formError = $state('');

  async function load() {
    try {
      groups = await get('/categories', { include_inactive: true });
      resetCatalog();
    } catch (err) {
      error = errorText(err);
    }
  }
  load();

  function addOption(g) {
    formError = '';
    editing = { kind: 'option', group: g, name_th: '', name_en: '' };
  }
  function editOption(g, o) {
    formError = '';
    editing = { kind: 'option', group: g, id: o.id, name_th: o.name_th, name_en: o.name_en || '' };
  }
  function addGroup() {
    formError = '';
    editing = { kind: 'group', key: '', name_th: '', name_en: '', multi: false };
  }
  function editGroup(g) {
    formError = '';
    editing = { kind: 'group', id: g.id, key: g.key, name_th: g.name_th, name_en: g.name_en || '', multi: g.multi };
  }

  async function save() {
    formError = '';
    const e = editing;
    try {
      if (e.kind === 'option') {
        const body = { name_th: e.name_th.trim(), name_en: e.name_en.trim() || null };
        if (e.id) await patch(`/admin/categories/${e.id}`, body);
        else await post('/admin/categories', { ...body, group_id: e.group.id, sort: e.group.options.length });
      } else {
        const body = { name_th: e.name_th.trim(), name_en: e.name_en.trim() || null, multi: e.multi };
        if (e.id) await patch(`/admin/category-groups/${e.id}`, body);
        else await post('/admin/category-groups', { ...body, key: e.key.trim(), sort: groups.length });
      }
      toast('บันทึกแล้ว');
      editing = null;
      load();
    } catch (err) {
      formError = errorText(err);
    }
  }
  async function setActive(o, active) {
    try {
      await patch(`/admin/categories/${o.id}`, { active });
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function removeOption(o) {
    try {
      await del(`/admin/categories/${o.id}`);
      toast('ลบตัวเลือกแล้ว');
      load();
    } catch (err) {
      toast(err.status === 409 ? 'มีเอกสารใช้หมวดหมู่นี้อยู่ ให้ปิดการใช้งานแทน' : errorText(err), 'bad');
    }
  }
</script>

<div class="stack">
  <div class="row"><h1>หมวดหมู่</h1><span class="spacer"></span><button class="btn ghost" onclick={addGroup}><Icon name="plus" size={17} />เพิ่มกลุ่ม</button></div>
  <p class="hint">ระบบจับคู่ช่องที่ติ๊กในแบบฟอร์มกับตัวเลือกเหล่านี้ ถ้าไม่ตรงกับตัวเลือกไหน จะแนะนำเป็นแท็กแทน (ไม่สร้างหมวดหมู่ใหม่เอง)</p>
  {#if error}<div class="notice bad">{error}</div>{/if}
  {#if groups === null}
    <div class="card pad"><div class="skel" style="width:40%"></div></div>
  {:else}
    {#each groups as g (g.id)}
      <section class="card pad group">
        <div class="row">
          <h3>{g.name_th}</h3>
          <small class="muted mono">{g.key}</small>
          <span class="badge neutral">{g.multi ? 'เลือกได้หลายข้อ' : 'เลือกได้ข้อเดียว'}</span>
          <span class="spacer"></span>
          <button class="link-btn" onclick={() => editGroup(g)}>แก้ไขกลุ่ม</button>
          <button class="link-btn" onclick={() => addOption(g)}>+ เพิ่มตัวเลือก</button>
        </div>
        <ul>
          {#each g.options as o (o.id)}
            <li class:off={!o.active}>
              <span class="grow">{o.name_th}{#if o.name_en}<small class="muted"> · {o.name_en}</small>{/if}{#if !o.active}<span class="badge neutral">ปิดใช้งาน</span>{/if}</span>
              <button class="link-btn" onclick={() => editOption(g, o)}>แก้ไข</button>
              <button class="link-btn" onclick={() => setActive(o, !o.active)}>{o.active ? 'ปิดใช้งาน' : 'เปิดใช้งาน'}</button>
              <button class="link-btn danger" onclick={() => removeOption(o)}>ลบ</button>
            </li>
          {:else}
            <li class="muted">ยังไม่มีตัวเลือก</li>
          {/each}
        </ul>
      </section>
    {/each}
  {/if}
</div>

{#if editing}
  <Modal title={editing.kind === 'group' ? (editing.id ? 'แก้ไขกลุ่ม' : 'เพิ่มกลุ่ม') : editing.id ? 'แก้ไขตัวเลือก' : `เพิ่มตัวเลือกใน “${editing.group.name_th}”`} onclose={() => (editing = null)}>
    {#if editing.kind === 'group' && !editing.id}
      <label class="field"><span>รหัสกลุ่ม (ภาษาอังกฤษตัวเล็ก)</span><input id="g-key" class="mono" bind:value={editing.key} placeholder="research_type" /><small>ใช้ a–z, 0–9 และ _ เปลี่ยนภายหลังไม่ได้</small></label>
    {/if}
    <label class="field"><span>ชื่อภาษาไทย</span><input id="c-th" bind:value={editing.name_th} /></label>
    <label class="field"><span>ชื่อภาษาอังกฤษ (ไม่บังคับ)</span><input id="c-en" bind:value={editing.name_en} /></label>
    {#if editing.kind === 'group'}
      <label class="check"><input id="g-multi" type="checkbox" bind:checked={editing.multi} />เลือกได้หลายข้อ</label>
    {/if}
    {#if formError}<div class="notice bad">{formError}</div>{/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (editing = null)}>ยกเลิก</button>
      <button class="btn" onclick={save} disabled={!editing.name_th.trim()}>บันทึก</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .group { display: flex; flex-direction: column; gap: 8px; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: flex; gap: 8px; align-items: center; padding: 7px 0; border-top: 1px solid var(--border); font-size: 14px; flex-wrap: wrap; }
  li:first-child { border-top: 0; }
  li.off { opacity: 0.6; }
  .grow { flex: 1 1 220px; min-width: 0; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .danger { color: var(--bad); }
</style>
