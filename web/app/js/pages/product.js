/* DropAgentX — PRODUCT detail: hero, comments, buy with game-motion */
DGX.pages = DGX.pages || {};

DGX.pages.product = async (view, params) => {
  const pid = +params.id;
  if (!pid) { location.hash = '#/home'; return; }
  view.innerHTML = `<div class="skel" style="height:260px"></div>
    <div class="skel" style="height:60px;margin-top:12px"></div>
    <div class="buybar"><span style="flex:1;color:var(--dim);font-size:13px">…</span></div>`;

  const d = await DGX.api('/api/app/product/' + pid);
  const p = d.item, per = DGX.perUsdt || 1000;
  const owned = params.owned;

  view.innerHTML = `
    <a href="#/home" style="color:var(--dim);font-size:12px;text-decoration:none">‹ برگشت به فید</a>
    <img class="hero burst" src="${p.photo_url ? DGX.esc(p.photo_url) : ''}"
         onerror="this.src=''" alt="" style="${p.photo_url ? '' : 'display:flex;align-items:center;justify-content:center;font-size:64px'}">
    <h1 style="font-size:19px;margin:14px 0 6px;line-height:1.7">${DGX.esc(p.title)}</h1>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
      <span class="pill p-ok" style="font-size:11px">⭐ ${d.stars} (${d.reviews} دیدگاه)</span>
      <span style="color:var(--dim);font-size:12px">🛒 ${DGX.kfmt(p.sales_count)} فروش</span>
      <span style="color:var(--dim2);font-size:12px">👁 ${DGX.kfmt(p.views)}</span>
    </div>
    <div style="background:var(--surface);border:1px solid var(--line);border-radius:var(--r-m);
                padding:13px 15px;font-size:13.5px;line-height:2.1;color:#dbe3dd">
      ${(p.description || '—').replace(/\n/g, '<br>')}
    </div>

    <h3 style="margin:18px 0 8px">💬 دیدگاه‌ها (${p.comment_count || 0})</h3>
    <div id="cList">${(d.comments || []).map(c => `
      <div class="comment">
        <img class="avatar" src="/app/assets/logo.jpg">
        <div><span class="c-name">${DGX.esc(c.first_name || c.username || 'کاربر')}</span>
          <span class="c-time">${DGX.timeAgo(c.created_at)}</span>
          <div class="c-text">${DGX.esc(c.text)}</div></div>
      </div>`).join('') || '<div style="color:var(--dim);font-size:12.5px">اولین نظر رو بذار 💬</div>'}
    </div>
    <div class="search-bar2" style="margin-top:10px;padding:8px 10px">
      <input id="cIn" placeholder="نظرت را بنویس…" maxlength="500"
             style="padding:8px;background:none;border:0">
      <button class="btn btn-primary" id="cSend" style="flex:none;padding:9px 16px">ارسال</button>
    </div>

    <div style="height:70px"></div>
    <div class="buybar">
      <div>
        <b class="num" style="color:var(--em);font-size:17px">${DGX.fmt(p.price_credits)} کردیت</b><br>
        <small style="color:var(--dim)">≈${(+p.usd).toFixed(2)}$</small>
      </div>
      ${owned ? `<button class="btn btn-ghost" onclick="history.back()">✓ خریده‌ای</button>`
              : `<button class="btn btn-primary" id="buyNow" style="flex:1">🛒 خرید فوری</button>`}
    </div>`;

  // buy with celebration
  const buyBtn = DGX.$('#buyNow');
  if (buyBtn) buyBtn.onclick = async () => {
    DGX.haptic('medium');
    buyBtn.disabled = true; buyBtn.innerHTML = '⏳ پردازش…';
    try {
      const r = await DGX.api(`/api/app/buy/${pid}`, { body: {} });
      buyBtn.outerHTML = `
        <div style="flex:1;text-align:center">
          <div class="burst success-ring" style="width:44px;height:44px;border-radius:99px;
            background:var(--em);color:#03130a;display:inline-flex;align-items:center;
            justify-content:center;font-size:22px;font-weight:900">✓</div>
          <div style="font-size:12px;color:var(--em);margin-top:4px">خرید موفق 🎉</div>
        </div>`;
      DGX.toast('مبارک! محصول مال تو شد 🎉');
      if (r.file_url) open(r.file_url, '_blank');
    } catch (e) { buyBtn.disabled = false; buyBtn.textContent = '🛒 خرید فوری';
                  DGX.toast(e.msg || '', true); }
  };

  const send = DGX.$('#cSend');
  send.onclick = async () => {
    const inp = DGX.$('#cIn'), text = inp.value.trim();
    if (!text) return;
    send.disabled = true;
    try {
      await DGX.api('/api/app/comment', { body: { product_id: pid, text } });
      inp.value = ''; DGX.toast('نظر ثبت شد +۱ کردیت 💬');
      DGX.pages.product(view, params);
    } catch (e) { DGX.toast(e.msg || '', true); send.disabled = false; }
  };
};
