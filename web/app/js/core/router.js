/* DropAgentX — hash router + bottom nav + topbar */
DGX.pages = {};

DGX.renderNav = () => {
  const items = [
    ['#/home', 'i-home', 'خانه'],
    ['#/explore', 'i-compass', 'کشف'],
    ['CREATE', null, null],                       // special ➕
    ['#/agent', 'i-spark', 'هرمسا'],
    ['#/profile', 'i-user', 'من'],
  ];
  const nav = document.getElementById('nav');
  nav.innerHTML = '';
  for (const [hash, icon, label] of items) {
    if (hash === 'CREATE') {
      const d = document.createElement('div');
      d.className = 'bn-create';
      d.innerHTML = `<button title="ساخت محصول" aria-label="ساخت محصول">+</button>`;
      d.querySelector('button').onclick = () => location.hash = '#/create';
      nav.appendChild(d);
      continue;
    }
    const a = document.createElement('a');
    a.className = 'bn-item'; a.href = hash; a.dataset.hash = hash;
    a.innerHTML = `<svg><use href="#${icon}"/></svg><span>${label}</span>`;
    nav.appendChild(a);
  }
};

DGX.renderTopbar = (title) => {
  const tb = document.getElementById('topbar');
  tb.innerHTML = `
    <img class="logo" src="/app/assets/logo.jpg" alt="DropAgentX">
    <span class="title">${title || ''}</span>
    <span class="spacer"></span>
    <button class="icon-btn" style="position:relative" data-badge="1" onclick="location.hash='#/activity'" title="فعالیت">
      <svg width="18" height="18"><use href="#i-bell"/></svg><span class="dot"></span>
    </button>
    <button class="icon-btn" onclick="location.hash='#/search'" title="جستجو">
      <svg width="18" height="18"><use href="#i-search"/></svg>
    </button>`;
};

DGX.route = () => {
  const raw = (location.hash || '#/home').slice(2);          // "home?x=1"
  const [name, qs] = raw.split('?');
  const params = Object.fromEntries(new URLSearchParams(qs || ''));
  const page = name || 'home';
  const fn = DGX.pages[page];
  document.querySelectorAll('.bn-item').forEach(a =>
    a.classList.toggle('on', a.dataset.hash === '#/' + page));
  const titles = { home: 'خانه', explore: 'کشف', search: 'جستجو',
                   product: 'محصول', create: 'ساخت محصول', profile: 'پروفایل',
                   wallet: 'کیف پول', activity: 'فعالیت', agent: 'هرمسا' };
  DGX.renderTopbar(titles[page] || '');
  const view = document.getElementById('view');
  view.className = 'page';
  if (!fn) { location.hash = '#/home'; return; }
  fn(view, params).catch(e => {
    if (e && e.silent) return;
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div>${(e && e.msg) || 'خطا'}
      <br><br><button class="btn btn-ghost" onclick="history.back()">برگشت</button></div>`;
  });
};
