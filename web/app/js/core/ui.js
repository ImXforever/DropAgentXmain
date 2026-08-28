/* DropAgentX — UI helpers */
DGX.$ = s => document.querySelector(s);
DGX.esc = s => (s ?? '').toString().replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
DGX.fmt = n => Number(n || 0).toLocaleString('en-US');

DGX.usd = credits => {
  const per = DGX.perUsdt || 1000;
  const v = (+credits || 0) / per;
  return '≈' + (v >= 100 ? v.toFixed(0) : v.toFixed(2)) + '$';
};

DGX.kfmt = n => {
  n = +n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + 'K';
  return String(n);
};

DGX.timeAgo = ts => {
  const s = Math.max(1, (Date.now() / 1000) - (+ts || 0));
  if (s < 60) return 'همین حالا';
  if (s < 3600) return Math.floor(s / 60) + ' دقیقه پیش';
  if (s < 86400) return Math.floor(s / 3600) + ' ساعت پیش';
  return Math.floor(s / 86400) + ' روز پیش';
};

let _toastT = null;
DGX.toast = (m, bad) => {
  const t = DGX.$('#toast');
  t.textContent = m; t.className = 'show' + (bad ? ' err' : ' ok');
  clearTimeout(_toastT);
  _toastT = setTimeout(() => t.className = '', bad ? 3600 : 2300);
};

DGX.haptic = kind => {
  if (!DGX.hapticSupported) return;   // old Telegram clients log warnings
  try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(kind || 'light'); } catch (_) {}
};
DGX.hselect = () => {
  try { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged(); } catch (_) {}
};

DGX.skelCards = n => Array.from({ length: n }, () => `
  <div class="post">
    <div class="post-head"><div class="skel" style="width:40px;height:40px;border-radius:99px"></div>
      <div style="flex:1"><div class="skel" style="height:12px;width:45%;margin-bottom:6px"></div>
      <div class="skel" style="height:9px;width:30%"></div></div></div>
    <div class="skel" style="height:190px;border-radius:0"></div>
    <div style="padding:12px"><div class="skel" style="height:13px;width:70%;margin-bottom:8px"></div>
      <div class="skel" style="height:11px;width:40%"></div></div>
  </div>`).join('');

/* engagement stat pill for post cards */
DGX.statBtn = (icon, count, cls, attr) =>
  `<button class="stat ${cls || ''}" ${attr}>
     <svg><use href="#${icon}"/></svg><span>${DGX.kfmt(count)}</span></button>`;

/* product card → HTML (used by home/explore/search/profile) */
DGX.postCard = p => `
  <article class="post" data-pid="${+p.id}">
    <div class="post-head">
      <img class="avatar" src="/app/assets/logo.jpg" loading="lazy"
           onerror="this.style.opacity=.25">
      <div>
        <div class="p-name">${DGX.esc(p.creator_name || p.creator_username || 'سازنده')}
          <span class="vf">✔</span></div>
        <div class="p-sub">@${DGX.esc(p.creator_username || 'dropagentx')} ·
          ${DGX.timeAgo(p.created_at || (Date.now() / 1000))}</div>
      </div>
      ${p.is_featured ? '<span class="p-more" style="color:var(--gold)">⭐</span>' : ''}
    </div>
    <a class="post-media" href="#/product?id=${+p.id}">
      ${p.photo_url
        ? `<img src="${DGX.esc(p.photo_url)}" alt="" loading="lazy"
               onerror="this.parentNode.innerHTML='<div style=&quot;height:170px&quot;></div>'">`
        : `<div style="height:170px;display:flex;align-items:center;justify-content:center;
             background:linear-gradient(135deg,#101613,#0b0f0d);font-size:44px">📦</div>`}
      ${p.is_featured ? '<span class="badge-drop">DROP ویژه</span>' : ''}
    </a>
    <div class="post-body">
      <a class="post-title" href="#/product?id=${+p.id}"
         style="text-decoration:none;color:inherit">${DGX.esc(p.title)}</a>
      <div class="post-desc">${DGX.esc(p.description || '')}</div>
      <div class="price-row">
        <span class="price num">${DGX.fmt(p.price_credits)} <small>کردیت</small></span>
        <span class="usd num">≈${(+p.usd || 0).toFixed(2)}$</span>
        <span style="margin-inline-start:auto;color:var(--dim2);font-size:11px">
          🛒 ${DGX.kfmt(p.sales_count)} فروش</span>
      </div>
    </div>
    <div class="post-stats">
      ${DGX.statBtn(p.liked ? 'i-heart-f' : 'i-heart', p.like_count,
                    p.liked ? 'on like' : '', `data-eng="like"`)}
      ${DGX.statBtn('i-dislike', p.dislike_count, p.disliked ? 'on dislike' : '',
                    `data-eng="dislike"`)}
      ${DGX.statBtn('i-comment', p.comment_count, '', `data-comments="1"`)}
      ${DGX.statBtn('i-save', p.save_count, p.saved ? 'on save' : '', `data-eng="save"`)}
      ${DGX.statBtn('i-repost', 0, '', `data-share="1"`)}
      <span class="stat ctr"><svg><use href="#i-eye"/></svg>
        <span>${DGX.kfmt(p.views)}</span> · CTR ${p.views ? Math.max(1, Math.round((+p.sales_count || 0) * 100 / p.views)) : '—'}%</span>
    </div>
    <div class="post-actions">
      <button class="btn btn-primary" data-buy="${+p.id}">🛒 خرید فوری</button>
      <button class="btn btn-ghost" onclick="location.hash='#/product?id=${+p.id}'">جزئیات ↗</button>
    </div>
  </article>`;
