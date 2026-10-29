<script>
  // Frame for one chart: title, short note, legend, and a table view for screen readers / exact numbers.
  let { title, note = '', legend = [], children, table, wide = false, id = undefined } = $props();
  let showTable = $state(false);
</script>

<section class="card chart-card" class:wide {id}>
  <header>
    <div class="titles">
      <h3>{title}</h3>
      {#if note}<p class="muted">{note}</p>{/if}
    </div>
    {#if table}
      <button class="link-btn" onclick={() => (showTable = !showTable)} aria-pressed={showTable}>{showTable ? 'ดูกราฟ' : 'ดูเป็นตาราง'}</button>
    {/if}
  </header>
  {#if legend.length > 1 && !showTable}
    <ul class="legend">
      {#each legend as l (l.label)}<li><span class="sw" style="background:{l.color}"></span>{l.label}</li>{/each}
    </ul>
  {/if}
  <div class="body">
    {#if showTable && table}<div class="table-wrap">{@render table()}</div>{:else}{@render children()}{/if}
  </div>
</section>

<style>
  .chart-card { padding: 16px 18px 14px; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .chart-card.wide { grid-column: 1 / -1; }
  header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .titles p { font-size: 12.5px; margin-top: 2px; }
  h3 { font-size: 16px; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 16px; list-style: none; margin: 0; padding: 0; font-size: 12.5px; color: var(--muted); }
  .legend li { display: inline-flex; align-items: center; gap: 6px; }
  .sw { width: 10px; height: 10px; border-radius: 3px; }
  .body { min-width: 0; position: relative; }
  header .link-btn { flex: none; white-space: nowrap; }
  .table-wrap { overflow-x: auto; margin: 0 -4px; }
  .chart-card { scroll-margin-top: calc(var(--header-h) + 60px); }
  @media (max-width: 767px) {
    .chart-card { padding: 14px 14px 12px; border-radius: 14px; }
    h3 { font-size: 15.5px; }
  }
</style>
