/* DropAgentX — EXPLORE: trending + categories */
DGX.pages = DGX.pages || {};

DGX.pages.explore = async (view, params) => {
  view.innerHTML = `
    <div class="chips" id="exRange">
      <button class="chip on" data-r="trend">🔥 ترند</button>
      <button class="chip" data-r="new">🆕 جدید</button>
      <button class="chip" data-r="featured">⭐ ویژه</button>
      <button class="chip" data-r="budget">💰 ارزان‌ها (زیر ۱۰۰)</button>
    </div>
    <div id="rankBox">${DGX.skelCards(3)}</div>
    <h2 style="margin:18px 0 10px">🗂 دسته‌بندی‌ها</h2>
    <div class="cat-grid" id="catGrid"></div>
    <div id="gridOut"></div>`;

  let mode = params.r || 'trend';
  const rankBox = DGX.$('#rankBox'), grid = DGX.$('#catGrid');

  async function loadRank() {
    rankBox.innerHTML = DGX.skelCards(3);
    try {
      let items;
      if (mode === 'featured') {
        items = (await DGX.api('/api/app/trending?limit=20')).items.filter(x => x.is_featured);
      } else if (mode === 'new') {
        items = (await DGX.api('/api/app/feed?mode=foryou&cursor=0')).items
          .sort((a, b) => b.id - a.id);
      } else if (mode === 'budget') {
        items = (await DGX.api('/api/app/feed?mode=foryou&cursor=0')).items
          .filter(x => x.price_credits < 100)
          .sort((a, b) => a.price_credits - b.price_credits);
      } else {
        items = (await DGX.api('/api/app/trending?limit=10')).items;
      }
      if (!items.length) { rankBox.innerHTML =
        '<div class="empty"><div class="big">🕳</div>فعلاً چیزی اینجا نیست</div>'; return; }
      rankBox.innerHTML = items.map(p => `
        <a class="rank-row ${p.rank === 1 ? 'rank-1' : ''}" href="#/product?id=${+p.id}"
           style="text-decoration:none;color:inherit">
          <span class="rank-num">#${p.rank || '•'}</span>
          ${p.photo_url ? `<img class="rank-img" src="${DGX.esc(p.photo_url)}" loading="lazy">`
                        : `<div class="rank-img" style="display:flex;align-items:center;justify-content:center">📦</div>`}
          <div class="rank-info">
            <div class="rank-t">${DGX.esc(p.title)}</div>
            <div class="rank-s">@${DGX.esc(p.creator_username || p.creator_name || '')} ·
              🛒 ${DGX.kfmt(p.sales_count)} فروش</div>
          </div>
          <span class="num" style="color:var(--em);font-weight:800;font-size:12px;white-space:nowrap">
            ${DGX.fmt(p.price_credits)}</span>
        </a>`).join('');
    } catch (e) { rankBox.innerHTML = `<div class="empty">⚠️ ${e.msg || ''}</div>`; }
  }

  try {
    const cats = (await DGX.api('/api/app/categories')).items;
    grid.innerHTML = cats.map(c => `
      <div class="cat-card" data-c="${c.key}">
        <div class="ic">${c.icon}</div><div class="nm">${c.fa}</div>
        <div class="ct num">${DGX.kfmt(c.count)}</div></div>`).join('');
    grid.querySelectorAll('.cat-card').forEach(el => el.onclick = () => {
      location.hash = `#/explore?r=${mode}&cat=${el.dataset.c}`;
    });
  } catch (_) {}

  view.querySelectorAll('#exRange .chip').forEach(ch => ch.onclick = () => {
    mode = ch.dataset.r;
    view.querySelectorAll('#exRange .chip').forEach(z => z.classList.remove('on'));
    ch.classList.add('on');
    loadRank();
  });

  await loadRank();
};
