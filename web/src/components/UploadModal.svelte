<script>
  import { fade, fly, scale } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import Icon from './Icon.svelte';
  import { uploads, addFiles, closeUpload, clearFinished, busyCount, doneOk, retry, cancel, cancelAll } from '../lib/uploads.svelte.js';
  import { screen, ms } from '../lib/state.svelte.js';
  import { navigate } from '../lib/router.svelte.js';
  import { bytes } from '../lib/format.js';

  let input = $state();
  let over = $state(false);
  let list = $state();

  const busy = $derived(busyCount() > 0);
  const ok = $derived(doneOk());
  const finished = $derived(uploads.items.filter((i) => i.state !== 'wait' && i.state !== 'up').length);

  function pick(e) {
    addFiles(e.currentTarget.files);
    e.currentTarget.value = '';
    queueMicrotask(() => list && (list.scrollTop = list.scrollHeight));
  }
  function drop(e) {
    over = false;
    if (!e.dataTransfer?.files?.length) return; // let the page explain what to drop
    e.preventDefault();
    addFiles(e.dataTransfer.files);
    queueMicrotask(() => list && (list.scrollTop = list.scrollHeight));
  }
  function later() {
    clearFinished();
    closeUpload();
  }
  function now() {
    const first = ok[0];
    clearFinished();
    closeUpload();
    navigate(ok.length === 1 && first ? `/documents/${first.docId}/review` : '/review');
  }
  function key(e) {
    if (e.key === 'Escape') closeUpload();
  }
  function panelIn(node) {
    return screen.wide
      ? scale(node, { start: 0.96, duration: ms(220), easing: cubicOut })
      : fly(node, { y: 400, duration: ms(240), easing: cubicOut, opacity: 1 });
  }
  function panelOut(node) {
    return screen.wide
      ? scale(node, { start: 0.97, duration: ms(150), easing: cubicOut })
      : fly(node, { y: 400, duration: ms(200), easing: cubicOut, opacity: 1 });
  }
</script>

{#if uploads.open}
  <div class="scrim" transition:fade={{ duration: ms(200) }} onclick={closeUpload} role="presentation"></div>
  <div class="panel" class:sheet={!screen.wide} role="dialog" aria-modal="true" aria-labelledby="up-title" tabindex="-1" onkeydown={key} in:panelIn out:panelOut>
    {#if !screen.wide}<div class="grab"></div>{/if}
    <div class="head">
      <h2 id="up-title">อัปโหลดเอกสาร</h2>
      <button class="icon-btn" onclick={closeUpload} aria-label="ปิด"><Icon name="x" /></button>
    </div>

    <label
      class="drop"
      class:over
      ondragenter={() => (over = true)}
      ondragleave={(e) => !e.currentTarget.contains(e.relatedTarget) && (over = false)}
      ondrop={drop}
    >
      <Icon name="upload" size={28} />
      <b>{screen.wide ? 'ลากไฟล์ PDF มาวางที่นี่' : 'เลือกไฟล์ PDF จากเครื่อง'}</b>
      <small>เลือกได้หลายไฟล์ · รับเฉพาะไฟล์สแกน PDF ไม่เกิน 100 MB</small>
      <span class="btn small">เลือกไฟล์</span>
      <input bind:this={input} class="sr-only" type="file" accept="application/pdf,.pdf" multiple onchange={pick} />
    </label>

    {#if uploads.items.length}
      <div class="list-head">
        <span class="muted">ไฟล์ที่เลือก {uploads.items.length} ไฟล์</span>
        {#if busy}<button class="link-btn" onclick={cancelAll}>ยกเลิกที่เหลือทั้งหมด</button>{/if}
      </div>
    {/if}
    <div class="list" bind:this={list}>
      {#each uploads.items as it (it.id)}
        {@const done = it.state !== 'wait' && it.state !== 'up'}
        <div class="item enter" class:done class:gone={it.state === 'undone'}>
          <span class="ficon" class:bad={it.state === 'bad'} aria-hidden="true">PDF</span>
          <div class="info">
            <div class="line">
              <span class="name" title={it.name}>{it.name}</span>
              <span class="size num">{bytes(it.size)}</span>
            </div>
            <div class="status">
              {#if it.state === 'wait'}
                <span class="muted">รอคิว</span>
              {:else if it.state === 'up'}
                <span class="muted num">กำลังอัปโหลด {Math.round(it.progress * 100)}%</span>
              {:else if it.state === 'ok'}
                <span class="badge processing">อัปโหลดแล้ว · ระบบกำลังอ่านเอกสาร</span>
                {#if it.message}<span class="err">{it.message}</span>{/if}
              {:else if it.state === 'undoing'}
                <span class="muted">กำลังยกเลิก…</span>
              {:else if it.state === 'undone'}
                <span class="muted">{it.message}</span>
              {:else if it.state === 'dup'}
                <span class="badge needs_review">{it.message}</span>
                {#if it.docId}<a href="/documents/{it.docId}" onclick={closeUpload}>เปิดเอกสารเดิม</a>{/if}
              {:else}
                <span class="badge failed">{it.message}</span>
                {#if it.retryable}<button class="link-btn" onclick={() => retry(it.id)}>ลองใหม่</button>{/if}
              {/if}
            </div>
            {#if !done}<div class="bar"><i style="transform: scaleX({it.progress})"></i></div>{/if}
          </div>
          {#if it.state !== 'undoing'}
            <button
              class="icon-btn x"
              onclick={() => cancel(it.id)}
              title={it.state === 'ok' ? 'ยกเลิกไฟล์นี้ (ย้ายไปถังขยะ)' : done ? 'เอาออกจากรายการ' : 'ยกเลิกไฟล์นี้'}
              aria-label="{it.state === 'ok' ? 'ยกเลิกการอัปโหลด' : done ? 'เอาออก' : 'ยกเลิก'} {it.name}"
            ><Icon name="x" size={17} /></button>
          {/if}
        </div>
      {:else}
        <p class="empty muted">ยังไม่ได้เลือกไฟล์</p>
      {/each}
    </div>

    <div class="foot">
      <p class="sum muted">
        {#if busy}
          เสร็จ {finished} จาก {uploads.items.length} ไฟล์ · ปิดหน้าต่างนี้ได้ ระบบจะอัปโหลดต่อให้
        {:else if ok.length}
          อัปโหลดแล้ว {ok.length} ไฟล์ · ตรวจข้อมูลตอนนี้หรือทีหลังก็ได้ เอกสารจะรออยู่ในแท็บ “รอตรวจสอบ”
        {:else}
          แก้ไขข้อมูลเอกสารได้ทุกเมื่อหลังอัปโหลด
        {/if}
      </p>
      <div class="acts">
        <button class="btn ghost" onclick={later} disabled={busy || !ok.length}>ไว้ทีหลัง</button>
        <button class="btn" onclick={now} disabled={busy || !ok.length}>ตรวจเลย{ok.length ? ` (${ok.length})` : ''}</button>
      </div>
    </div>
  </div>
{/if}

<svelte:window onkeydown={(e) => uploads.open && key(e)} />

<style>
  .scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 40; }
  .panel {
    position: fixed; z-index: 41; left: 50%; top: 50%; translate: -50% -50%;
    width: min(540px, calc(100vw - 32px)); max-height: min(640px, calc(100vh - 48px));
    background: var(--surface); border-radius: 16px; box-shadow: var(--shadow);
    display: flex; flex-direction: column; gap: 14px; padding: 20px;
  }
  .panel.sheet {
    left: 0; right: 0; top: auto; bottom: 0; translate: none; width: auto;
    max-height: 90vh; border-radius: 20px 20px 0 0;
    padding: 8px 16px calc(16px + env(safe-area-inset-bottom));
  }
  .grab { width: 38px; height: 4px; border-radius: 2px; background: var(--border-strong); margin: 0 auto 2px; }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .drop {
    display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center;
    padding: 22px 16px; border: 2px dashed var(--drop-line); border-radius: 14px; background: var(--primary-soft);
    color: var(--primary-text); cursor: pointer; flex: none;
    transition: transform var(--t-fast) var(--ease-out), border-color var(--t-fast);
  }
  .drop b { font-family: var(--f-display); font-weight: 500; font-size: 16px; color: var(--text); }
  .drop small { color: var(--muted); font-size: 12.5px; }
  .drop .btn { margin-top: 6px; pointer-events: none; }
  .drop.over { transform: scale(1.015); border-color: var(--primary); }
  .drop:focus-within { outline: 3px solid var(--accent); outline-offset: 2px; }
  .list-head { display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: -8px; }
  .list { overflow: auto; min-height: 48px; flex: 1; display: flex; flex-direction: column; }
  .empty { text-align: center; font-size: 13px; padding: 10px; }
  .item { display: flex; gap: 12px; align-items: center; padding: 10px 2px; border-top: 1px solid var(--border); transition: opacity var(--t-med); }
  .item:first-child { border-top: 0; }
  .item.gone { opacity: 0.55; }
  .ficon {
    flex: none; width: 34px; height: 42px; border-radius: 4px 10px 4px 4px; display: grid; place-items: end center;
    padding-bottom: 5px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.04em;
    background: var(--primary-soft); color: var(--primary-text); border: 1px solid var(--border);
  }
  .ficon.bad { background: var(--bad-soft); color: var(--bad); border-color: transparent; }
  .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .x { flex: none; width: 32px; height: 32px; }
  .x:hover { color: var(--bad); background: var(--bad-soft); }
  .err { color: var(--bad); font-size: 12.5px; }
  .line { display: flex; gap: 10px; align-items: baseline; }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 500; }
  .size { font-size: 12px; color: var(--muted); }
  .status { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12.5px; }
  .status a { font-size: 13px; font-weight: 500; }
  .bar { height: 4px; background: var(--subtle); border-radius: 2px; overflow: hidden; margin-top: 3px; }
  .bar i { display: block; height: 100%; background: var(--primary); transform-origin: left; transition: transform 250ms linear; }
  .foot { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid var(--border); padding-top: 12px; }
  .sum { font-size: 13px; }
  .acts { display: flex; gap: 8px; justify-content: flex-end; }
  .sheet .acts .btn { flex: 1; min-height: 46px; }
</style>
