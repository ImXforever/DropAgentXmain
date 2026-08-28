/* DropAgentX — ACTIVITY: purchases / sales */
DGX.pages = DGX.pages || {};

DGX.pages.activity = async (view) => {
  view.innerHTML = `
    <div class="seg" style="margin-bottom:14px">
      <button class="on" data-t="bought">🛒 خریدهای من</button>
      <button data-t="sold">💰 فروش‌های من</button>
    </div>
    <div id="actOut">${DGX.skelCards(2)}</div>`;
  const out = DGX.$('#actOut');
  let tab = 'bought';

  const d = await DGX.api('/api/app/activity');

  function render() {
    const rows = d[tab];
    if (!rows.length) {
      out.innerHTML = `<div class="empty"><div class="big">${tab === 'bought' ? '🛍' : '🏷'}</div>
        ${tab === 'bought' ? 'هنوز چیزی نخریدی — فید خانه پر از ایده است!' :
          'هنوز فروشی نداشتی — محصولت را منتشر کن و بفروش!'}</div>`;
      return;
    }
    out.innerHTML = rows.map(r => `
      <div class="rank-row">
        <span class="ic" style="width:42px;height:42px;border-radius:11px;flex:none;
          background:var(--surface2);display:flex;align-items:center;
          justify-content:center;font-size:19px">📦</span>
        <div style="flex:1;min-width:0">
          <div class="rank-t">${DGX.esc(r.title)}</div>
          <div class="rank-s">${tab === 'bought'
            ? (r.download_url
               ? `<a href="${DGX.esc(r.download_url)}" target="_blank"
                    style="color:var(--em)">⬇️ دانلود فایل</a>`
               : 'محصول متن/لینکی')
            : '👤 ' + DGX.esc(r.buyer || '—')} · ${DGX.timeAgo(r.purchased_at)}</div>
        </div>
        <span class="num" style="font-weight:800;color:${tab === 'bought' ? 'var(--red)' : 'var(--em)'}">
          ${tab === 'bought' ? '-' : '+'}${DGX.fmt(r.price_credits)}</span>
      </div>`).join('');
  }

  view.querySelectorAll('.seg button').forEach(b => b.onclick = () => {
    tab = b.dataset.t;
    view.querySelectorAll('.seg button').forEach(z => z.classList.remove('on'));
    b.classList.add('on');
    render();
  });
  render();
};
