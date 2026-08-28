/* DropAgentX — SEARCH: products + users */
DGX.pages = DGX.pages || {};

DGX.pages.search = async (view, params) => {
  const q0 = params.q || '';
  view.innerHTML = `
    <div class="search-bar2">
      <svg width="18" height="18" style="color:var(--dim);flex:none"><use href="#i-search"/></svg>
      <input id="sq" placeholder="محصول یا کاربر…" value="${DGX.esc(q0)}" autocomplete="off">
    </div>
    <div id="sOut"><div class="empty"><div class="big">🔍</div>دنبال چی می‌گردی؟<br>
      اسم محصول، دسته یا سازنده را بنویس</div></div>`;
  const inp = DGX.$('#sq'), out = DGX.$('#sOut');
  inp.focus();

  let deb = null, lastQ = '';
  async function run(q) {
    if (q.length < 2) {
      out.innerHTML = `<div class="empty"><div class="big">🔍</div>حداقل ۲ حرف…</div>`;
      return;
    }
    lastQ = q;
    out.innerHTML = DGX.skelCards(2);
    try {
      const d = await DGX.api('/api/app/search?q=' + encodeURIComponent(q));
      if (lastQ !== q) return;                       // stale guard
      let html = '';
      if (d.users.length) {
        html += '<h2 style="margin:4px 0 8px">👥 کاربران</h2>';
        html += d.users.map(u => `
          <div class="user-row">
            <img class="avatar" src="/app/assets/logo.jpg" style="width:38px;height:38px">
            <div style="flex:1;min-width:0">
              <b style="font-size:13px">${DGX.esc(u.first_name || 'کاربر')}</b>
              ${u.username ? `<div style="color:var(--dim);font-size:11px">@${DGX.esc(u.username)}</div>` : ''}
            </div>
            <button class="follow-btn" data-fu="${u.user_id}">فالو +</button>
          </div>`).join('');
      }
      if (d.products.length) {
        html += `<h2 style="margin:14px 0 10px">📦 محصولات</h2>` +
          d.products.map(DGX.postCard).join('');
      }
      out.innerHTML = html || `<div class="empty"><div class="big">🫥</div>
        برای «${DGX.esc(q)}» چیزی پیدا نشد</div>`;

      // follow buttons
      out.querySelectorAll('[data-fu]').forEach(b => b.onclick = async () => {
        const on = !b.classList.contains('on');
        try {
          await DGX.api('/api/app/follow', { body: { target: +b.dataset.fu, on } });
          b.classList.toggle('on', on);
          b.textContent = on ? '✓ فالو شد' : 'فالو +';
          DGX.haptic('light');
        } catch (e) { DGX.toast(e.msg || '', true); }
      });
      // product card interactions (like/buy reuse home wiring)
      DGX.wireFeed && DGX.wireFeed(out);
    } catch (e) { out.innerHTML = `<div class="empty">⚠️ ${e.msg}</div>`; }
  }

  inp.oninput = () => { clearTimeout(deb); deb = setTimeout(() => run(inp.value.trim()), 380); };
  inp.onkeydown = e => { if (e.key === 'Enter') { clearTimeout(deb); run(inp.value.trim()); } };
  if (q0) run(q0);
};
