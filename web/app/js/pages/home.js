/* DropAgentX — HOME: algorithmic feed (following-first + trending) */
DGX.pages = DGX.pages || {};

DGX.pages.home = async (view, params) => {
  const mode = params.tab === 'following' ? 'following' : 'foryou';
  const cat = params.cat || 'all';
  let cursor = parseInt(params.cursor || 0, 10);
  let busy = false, ended = false;

  view.innerHTML = `
    <div class="seg" style="margin-bottom:10px">
      <button data-tab="foryou" class="${mode === 'foryou' ? 'on' : ''}">🔥 برای تو</button>
      <button data-tab="following" class="${mode === 'following' ? 'on' : ''}">👥 فالوینگ‌ها</button>
    </div>
    <div class="chips" id="homeCats"></div>
    <div id="feed">${DGX.skelCards(3)}</div>
    <div id="more" style="text-align:center;color:var(--dim2);padding:14px"></div>`;

  // categories chips
  try {
    const cats = (await DGX.api('/api/app/categories')).items;
    const box = DGX.$('#homeCats');
    if (box) {
      box.innerHTML = `<button class="chip ${cat === 'all' ? 'on' : ''}"
        data-c="all">همه</button>` +
        cats.filter(c => c.count > 0 || c.key === cat).map(c =>
          `<button class="chip ${cat === c.key ? 'on' : ''}" data-c="${c.key}">
             ${c.icon} ${c.fa}${c.count ? ` · ${DGX.kfmt(c.count)}` : ''}</button>`).join('');
      box.querySelectorAll('.chip').forEach(ch => ch.onclick = () => {
        location.hash = `#/home?tab=${mode}&cat=${ch.dataset.c}`;
      });
    }
  } catch (_) {}

  view.querySelectorAll('.seg button').forEach(b => b.onclick = () => {
    location.hash = `#/home?tab=${b.dataset.tab}&cat=${cat}`;
  });

  const feed = DGX.$('#feed'), more = DGX.$('#more');

  async function load(reset) {
    if (busy || (!reset && ended)) return;
    busy = true;
    more.textContent = reset ? '' : '…';
    if (reset) { cursor = 0; ended = false; feed.innerHTML = DGX.skelCards(3); }
    try {
      const d = await DGX.api(
        `/api/app/feed?mode=${mode}&cat=${encodeURIComponent(cat)}&cursor=${cursor}`);
      if (reset) feed.innerHTML = '';
      ended = d.next === null;
      for (const p of d.items) feed.insertAdjacentHTML('beforeend', DGX.postCard(p));
      wire(feed);
      cursor = d.next ?? cursor;
      if (ended && !d.items.length && reset)
        feed.innerHTML = `<div class="empty"><div class="big">🌱</div>
          هنوز پستی نیست — اولین سازنده باش!<br><br>
          <button class="btn btn-primary" onclick="location.hash='#/create'">➕ ساخت محصول</button></div>`;
      more.textContent = ended ? (d.items.length ? '✨ همه را دیدی' : '') : '…';
    } catch (e) {
      if (reset) feed.innerHTML =
        `<div class="empty"><div class="big">📡</div>${e.msg || 'خطا'}
         <br><br><button class="btn btn-ghost" onclick="location.reload()">تلاش مجدد</button></div>`;
    }
    busy = false;
  }

  function wire(root) {
    root.querySelectorAll('[data-eng]').forEach(btn => btn.onclick = async () => {
      const card = btn.closest('.post');
      const pid = +card.dataset.pid;
      const type = btn.dataset.eng;
      DGX.haptic('light');
      try {
        const r = await DGX.api('/api/app/engage', { body: { product_id: pid, type } });
        const cnt = btn.querySelector('span');
        cnt.textContent = DGX.kfmt(Math.max(0, (+cnt.textContent.replace(/[KM]/g,
          m => m === 'K' ? '000' : m === 'M' ? '00000' : '') || 0) + (r.on ? 1 : -1)));
        btn.classList.toggle('on', r.on);
        if (type === 'like') {
          const ic = btn.querySelector('use');
          ic.setAttribute('href', r.on ? '#i-heart-f' : '#i-heart');
        }
      } catch (e) { DGX.toast(e.msg || '', true); }
    });
    root.querySelectorAll('[data-comments]').forEach(btn => btn.onclick = () => {
      const card = btn.closest('.post');
      location.hash = '#/product?id=' + card.dataset.pid + '&comments=1';
    });
    root.querySelectorAll('[data-share]').forEach(btn => btn.onclick = async () => {
      const card = btn.closest('.post');
      const url = location.origin + '/#/product?id=' + card.dataset.pid;
      try {
        if (navigator.share) await navigator.share({ url, title: 'DropAgentX' });
        else { await navigator.clipboard.writeText(url); DGX.toast('لینک کپی شد 🔗'); }
      } catch (_) {}
      DGX.haptic('medium');
    });
    root.querySelectorAll('[data-buy]').forEach(btn => btn.onclick = async () => {
      const pid = +btn.dataset.buy;
      DGX.haptic('medium');
      btn.disabled = true; btn.textContent = '⏳ در حال پردازش…';
      try {
        const r = await DGX.api(`/api/app/buy/${pid}`, { body: {} });
        DGX.toast(`خرید شد! 🎉 مانده: ${DGX.fmt(r.balance)} کردیت`);
        btn.textContent = '✅ خریده‌شد';
        if (r.file_url) open(r.file_url, '_blank');
      } catch (e) {
        btn.disabled = false; btn.textContent = '🛒 خرید فوری';
        DGX.toast(e.msg || 'خرید ناموفق', true);
      }
    });
  }

  // infinite scroll
  const io = new IntersectionObserver(es => {
    if (es.some(x => x.isIntersecting)) load(false);
  }, { rootMargin: '600px' });
  io.observe(more);

  await load(true);
};
