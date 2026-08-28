/* DropAgentX — WALLET: credits with Web3 skin + game-motion */
DGX.pages = DGX.pages || {};

DGX.pages.wallet = async (view) => {
  if (!DGX.user) await DGX.refreshMe();
  view.innerHTML = `<div class="skel" style="height:150px"></div>${DGX.skelCards(1)}`;

  const d = await DGX.api('/api/app/wallet');
  DGX.perUsdt = d.per_usdt;
  const usd = (d.credits / d.per_usdt).toFixed(2);

  const icon = { deposit: ['📥', 'pos'], withdraw: ['📤', 'neg'],
                 purchase: ['🛒', 'neg'], sale: ['💰', 'pos'],
                 task_completion: ['✅', 'pos'], referral_bonus: ['🎁', 'pos'],
                 ref_commission: ['🤝', 'pos'], mystery_box: ['🎁', 'pos'],
                 admin_grant: ['🛡', 'pos'], admin_deduct: ['🛡', 'neg'],
                 welcome: ['🎉', 'pos'] };

  const txHtml = d.txs.length ? d.txs.map(t => {
    const [ic, cls] = icon[t.tx_type] || ['•', t.amount >= 0 ? 'pos' : 'neg'];
    return `<div class="tx">
      <span class="ic">${ic}</span>
      <div style="flex:1;min-width:0">
        <div style="font-size:12.5px;font-weight:700">${esc(t.description) || t.tx_type}</div>
        <div style="color:var(--dim2);font-size:10px">${DGX.timeAgo(t.created_at)}</div></div>
      <span class="amt ${cls}">${t.amount >= 0 ? '+' : ''}${DGX.fmt(t.amount)}</span>
    </div>`;
  }).join('') : '<div class="empty">هنوز تراکنشی نداری</div>';

  function esc(s) { return DGX.esc(s); }

  view.innerHTML = `
    <div class="wcard burst">
      <div class="lbl">💳 موجودی DropAgentX</div>
      <div class="bal num">${DGX.fmt(d.credits)} <small style="font-size:15px;color:var(--dim)">کردیت</small></div>
      <div class="addr">≈ ${usd} USDT · wallet: ${String(DGX.user?.id || '0x0000').slice(-6)}…${String(DGX.user?.id || '').slice(-4)}</div>
      <div class="w-actions">
        <div class="w-btn" onclick="location.hash='#/activity'"><span class="ic">📜</span>تاریخچه</div>
        <div class="w-btn" onclick="DGX.openBot('/start')"><span class="ic">📥</span>واریز</div>
        <div class="w-btn" onclick="DGX.openBot('/start')"><span class="ic">📤</span>برداشت</div>
        <div class="w-btn" onclick="location.hash='#/create'"><span class="ic">🚀</span>بفروش</div>
      </div>
    </div>

    <div class="stat3">
      <div><b class="num">${DGX.fmt(d.earned)}</b><span>کل درآمد</span></div>
      <div><b class="num">${DGX.fmt(d.spent)}</b><span>کل خرج</span></div>
      <div><b>${(d.earned / d.per_usdt).toFixed(2)}$</b><span>ارزش کل</span></div>
    </div>

    <h3 style="margin:16px 0 6px">⚡ تراکنش‌های اخیر</h3>
    ${txHtml}
    <div style="color:var(--dim2);font-size:10.5px;text-align:center;margin-top:14px">
      🔒 موجودی روی زیرساخت امن DropAgentX · نرخ ثابت ۱٬۰۰۰ کردیت = ۱ USDT</div>`;

  // count-up animation on load (game-motion)
  const balEl = view.querySelector('.bal');
  const target = d.credits, dur = 900, t0 = performance.now();
  (function tick(t) {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    balEl.firstChild.textContent = DGX.fmt(Math.round(target * e)) + ' ';
    if (k < 1) requestAnimationFrame(tick);
  })(t0);
};

DGX.openBot = path => {
  const u = window.Telegram?.WebApp?.initDataUnsafe?.user?.username;
  location.href = `https://t.me/DropAgentXBot${path ? '?start=' + encodeURIComponent(path.replace('/', '')) : ''}`;
};
