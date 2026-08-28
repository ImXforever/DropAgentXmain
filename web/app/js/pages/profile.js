/* DropAgentX — PROFILE: personal store (avatar 1:1 + cover 16:9) */
DGX.pages = DGX.pages || {};

DGX.pages.profile = async (view, params) => {
  if (!DGX.user) await DGX.refreshMe();
  const uid = +(params.uid || (DGX.user && DGX.user.id) || 0);
  if (!uid) { DGX.needTelegram(); return; }

  const d = await DGX.api(`/api/app/store/${uid}`);
  const per = DGX.perUsdt || 1000;
  const isMe = !!d.is_me;

  view.innerHTML = `
    <div class="cover-wrap" id="coverWrap">
      ${d.cover_url ? `<img src="${DGX.esc(d.cover_url)}">` :
        `<div style="height:100%;display:flex;align-items:center;justify-content:center;
           color:#1e2a24;font-size:15px;font-weight:800;letter-spacing:2px">
           DROPAGENTX · ${DGX.kfmt(d.total_sales)} SALES</div>`}
    </div>
    <div style="display:flex;align-items:flex-end;gap:12px;padding:0 var(--pad)">
      <img class="avatar-big" id="avImg"
           src="${d.avatar_url ? DGX.esc(d.avatar_url) : '/app/assets/logo.jpg'}">
      <div style="flex:1;padding-bottom:6px">
        <b style="font-size:17px">${DGX.esc(d.name || 'شهروند')} ✔</b>
        <div style="color:var(--dim);font-size:11.5px">@${DGX.esc(d.username || 'dropagentx')}
          ${d.following_me ? '· شما را فالو می‌کند' : ''}</div>
      </div>
      ${!isMe ? `<button class="follow-btn ${d.following_me ? 'on' : ''}" id="folBtn">
        ${d.following_me ? '✓ فالو شد' : '+ فالو'}</button>` : ''}
      ${isMe ? `<button class="pill-btn" onclick="DGX.upPhoto('avatar')">🖼 آواتار</button>
                <button class="pill-btn" onclick="DGX.upPhoto('cover')">🎨 کاور</button>` : ''}
    </div>
    <input type="file" id="phFile" accept="image/jpeg,image/png" hidden>

    <div style="padding:0 var(--pad)">
      <div class="stat3">
        <div><b>${DGX.kfmt(d.followers)}</b><span>فالوور</span></div>
        <div><b>${d.products.length}</b><span>محصول</span></div>
        <div><b>${DGX.kfmt(d.total_sales)}</b><span>فروش</span></div>
        <div><b class="num">${(d.products.reduce((s, p) => s + (+p.price_credits || 0), 0) / 1000).toFixed(2)}$</b><span>ارزش مغازه</span></div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <a class="btn btn-ghost" href="#/wallet">💰 کیف پول</a>
        <a class="btn btn-ghost" href="#/activity">📜 فعالیت</a>
      </div>
      <h3 style="margin-bottom:10px">🏪 ویترین ${isMe ? 'من' : 'این سازنده'}</h3>
      <div class="grid3" id="storeGrid"></div>
      <div style="height:80px"></div>
    </div>`;

  const grid = DGX.$('#storeGrid');
  grid.innerHTML = d.products.length ? d.products.map(p => `
    <a class="g-item" href="#/product?id=${+p.id}">
      ${p.photo_url ? `<img src="${DGX.esc(p.photo_url)}" loading="lazy">` : '📦'}
      <span class="g-price">${DGX.fmt(p.price_credits)}</span></a>`).join('')
    : `<div style="grid-column:1/-1;text-align:center;color:var(--dim);padding:26px;line-height:2">
         ${isMe ? 'هنوز محصولی نساختی 🌱<br>' : ''}
         <button class="btn btn-primary" onclick="location.hash='#/create'"
           style="${isMe ? '' : 'display:none'};max-width:220px;margin-top:8px">➕ ساخت اولین محصول</button>
       </div>`;

  if (!isMe) {
    DGX.$('#folBtn').onclick = async () => {
      const on = !d.following_me;
      try {
        await DGX.api('/api/app/follow', { body: { target: uid, on } });
        DGX.toast(on ? `فالو کردی ✅` : 'آنفالو شد');
        DGX.pages.profile(view, params);
      } catch (e) { DGX.toast(e.msg || '', true); }
    };
  }
};

DGX.upPhoto = kind => {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = 'image/jpeg,image/png';
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    // client-side aspect hint: avatar→square, cover→16:9 (server stores raw)
    const fd = new FormData(); fd.append('file', f);
    DGX.haptic('medium');
    try {
      const r = await fetch(`/api/app/me/photo/${kind}`, {
        method: 'POST', headers: { 'X-Requested-With': 'fetch',
                                   Authorization: 'Bearer ' + DGX.token },
        body: fd });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw d.detail || 'آپلود ناموفق';
      DGX.toast(kind === 'avatar' ? 'آواتار ۱:۱ ست شد ✨' : 'کاور ۱۶:۹ ست شد ✨');
      location.reload();
    } catch (e) { DGX.toast(typeof e === 'string' ? e : 'آپلود ناموفق', true); }
  };
  inp.click();
};
