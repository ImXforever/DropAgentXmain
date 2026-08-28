/* DropAgentX — CREATE: 4-step wizard (info → price → images → publish) */
DGX.pages = DGX.pages || {};

DGX.pages.create = async (view) => {
  let step = 1;
  const data = { title: '', description: '', category: 'other', price_credits: 0 };
  const images = { main: null, feed: null, story: null };   // File objects
  const previews = { main: null, feed: null, story: null }; // object URLs
  let cats = [];
  try { cats = (await DGX.api('/api/app/categories')).items; } catch (_) {}

  view.innerHTML = `<div id="wiz"></div>`;

  const IMG_SPECS = {
    main:  { ratio: '۱:۱',  w: 1080, h: 1080, hint: 'عکس اصلی محصول در صفحهٔ جزئیات', icon: '🖼️' },
    feed:  { ratio: '۱۶:۹', w: 1920, h: 1080, hint: 'نمایش در فید خانه — مثل تامبنیل یوتیوب، جذاب‌تر بهتر', icon: '📺' },
    story: { ratio: '۹:۱۶', w: 1080, h: 1920, hint: 'نمایش در اکسپلور — معرفی کوتاه محصول', icon: '📱' },
  };

  function render() {
    const w = DGX.$('#wiz');
    if (step === 1) {
      w.innerHTML = `
        <div class="step-dots"><i class="on"></i><i></i><i></i><i></i></div>
        <h2 style="margin-bottom:4px">📦 محصولت را معرفی کن</h2>
        <p style="color:var(--dim);font-size:12.5px;margin-bottom:6px">اول چی می‌فروشی؟</p>
        <div class="field"><label>عنوان</label>
          <input id="wTitle" maxlength="120" value="${DGX.esc(data.title)}"
                 placeholder="مثلاً: پکیج ۵۰ پرامپت سینمایی AI"></div>
        <div class="field"><label>توضیحات</label>
          <textarea id="wDesc" rows="5" maxlength="1000"
            placeholder="ویژگی‌ها، دستاوردها، برای کی مناسب است…">${DGX.esc(data.description)}</textarea></div>
        <button class="btn btn-primary" id="wNext">بعدی ←</button>`;
      w.querySelector('#wNext').onclick = () => {
        data.title = w.querySelector('#wTitle').value.trim();
        data.description = w.querySelector('#wDesc').value.trim();
        if (data.title.length < 3) return DGX.toast('عنوان حداقل ۳ حرف', true);
        step = 2; render(); DGX.haptic('light');
      };
    } else if (step === 2) {
      w.innerHTML = `
        <div class="step-dots"><i class="on"></i><i class="on"></i><i></i><i></i></div>
        <h2 style="margin-bottom:10px">🗂 دسته و قیمت</h2>
        <div class="field"><label>دسته‌بندی</label>
          <select id="wCat">${cats.map(c =>
            `<option value="${c.key}" ${data.category === c.key ? 'selected' : ''}>
               ${c.icon} ${c.fa}</option>`).join('')}</select></div>
        <div class="field"><label>قیمت (کردیت) — ۱۰۰۰ کردیت ≈ ۱$</label>
          <input id="wPrice" type="number" min="5" max="200000"
            value="${data.price_credits || ''}" placeholder="مثلاً ۲۵۰۰">
          <div style="color:var(--dim);font-size:11px;margin-top:6px">
            معادل: ≈<span id="usdLive">${data.price_credits ? (data.price_credits / 1000).toFixed(2) : '0.00'}</span>$
            · کمیسیون پلتفرم بعد از فروش کسر می‌شود</div></div>
        <div style="display:flex;gap:9px">
          <button class="btn btn-ghost" onclick="DGX.pages.create._go(1)">→ قبل</button>
          <button class="btn btn-primary" id="wNext" style="flex:1">بعدی ← عکس‌ها 🖼️</button></div>`;
      const pr = w.querySelector('#wPrice');
      pr.oninput = () => {
        const v = +pr.value || 0;
        w.querySelector('#usdLive').textContent = (v / 1000).toFixed(2);
      };
      w.querySelector('#wNext').onclick = () => {
        data.category = w.querySelector('#wCat').value;
        data.price_credits = Math.round(+pr.value || 0);
        if (data.price_credits < 5 || data.price_credits > 200000)
          return DGX.toast('قیمت بین ۵ تا ۲۰۰٬۰۰۰ کردیت', true);
        step = 3; render(); DGX.haptic('light');
      };
    } else if (step === 3) {
      // ── IMAGE UPLOAD STEP ──
      w.innerHTML = `
        <div class="step-dots"><i class="on"></i><i class="on"></i><i class="on"></i><i></i></div>
        <h2 style="margin-bottom:4px">🖼️ سه عکس لازم است</h2>
        <p style="color:var(--dim);font-size:11.5px;margin-bottom:14px;line-height:2">
          سیستم خودکار برش می‌زند و به اندازهٔ درست تبدیل می‌کند.<br>
          کیفیت بالاتر = نمایش بهتر = فروش بیشتر ✨</p>
        ${Object.entries(IMG_SPECS).map(([key, spec]) => `
          <div class="field">
            <label>${spec.icon} ${key.toUpperCase()} (${spec.ratio}) — ${spec.hint}</label>
            <div style="display:flex;gap:10px;align-items:center">
              <label class="dropzone" style="flex:none;width:${key==='story'?'70':'110'}px;
                height:${key==='main'||key==='feed'?'70':'110'}px;padding:0;display:flex;
                align-items:center;justify-content:center;font-size:22px;cursor:pointer;
                border-radius:12px;border:2px dashed var(--line);overflow:hidden"
                id="dz_${key}">
                ${previews[key] ? `<img src="${previews[key]}" style="width:100%;height:100%;object-fit:cover">` : `📷`}
              </label>
              <div style="flex:1;font-size:11px;color:var(--dim)">
                ${spec.ratio} · ${spec.w}×${spec.h}px<br>
                <span id="sz_${key}">${images[key] ? '✓ انتخاب شد (' + Math.round(images[key].size/1024) + 'KB)' : 'انتخاب نشده'}</span>
              </div>
            </div>
            <input type="file" id="file_${key}" accept="image/jpeg,image/png,image/webp" hidden
              onchange="DGX.pages.create._pick('${key}',this)">
          </div>`).join('')}
        <div style="background:#fff3;color:var(--gold);border-radius:10px;padding:9px 14px;
             font-size:11px;margin:12px 0;line-height:1.9">
          ⚠️ هر ۳ عکس اجباری هستند — بدون عکس محصول ذخیره نمی‌شود.
          سیستم خودکار برش می‌زند و resize می‌کند.</div>
        <div style="display:flex;gap:9px">
          <button class="btn btn-ghost" onclick="DGX.pages.create._go(2)">→ قبل</button>
          <button class="btn btn-primary" id="wNext" style="flex:1">بعدی ← چک نهایی</button></div>`;

      // wire file inputs
      Object.keys(IMG_SPECS).forEach(key => {
        const inp = w.querySelector(`#file_${key}`);
        if (!inp) return;
        inp.onchange = () => {
          const f = inp.files[0]; if (!f) return;
          images[key] = f;
          previews[key] = URL.createObjectURL(f);
          render();
          DGX.haptic('light');
        };
        // click dropzone triggers file input
        const dz = w.querySelector(`#dz_${key}`);
        if (dz) dz.onclick = () => inp.click();
      });

      w.querySelector('#wNext').onclick = () => {
        const missing = Object.keys(images).filter(k => !images[k]);
        if (missing.length) return DGX.toast(`${missing.length} عکس انتخاب نشده!`, true);
        step = 4; render(); DGX.haptic('light');
      };
    } else {
      // Step 4 — final check with real image previews
      const catIcon = (cats.find(c => c.key === data.category) || {}).icon || '📦';
      const heroSrc = previews.feed || previews.main ||
        `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="225"><rect fill="#101613"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" font-size="48">' + catIcon + '</text></svg>')}`;

      w.innerHTML = `
        <div class="step-dots"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i></div>
        <h2 style="margin-bottom:12px">✅ پیش‌نمایش نهایی</h2>

        <!-- feed preview -->
        <div class="post">
          <div class="post-head"><img class="avatar" src="/app/assets/logo.jpg">
            <div><div class="p-name">${DGX.esc(DGX.user?.name || 'تو')} ✔</div>
              <div class="p-sub">@${DGX.esc(DGX.user?.username || 'dropagentx')} · الان</div></div></div>
          <div class="post-media">${heroSrc.startsWith('data:')
            ? `<img src="${heroSrc}" style="width:100%">`
            : `<img src="${heroSrc}" style="width:100%;aspect-ratio:16/9;object-fit:cover">`}</div>
          <div class="post-body">
            <div class="post-title">${DGX.esc(data.title)}</div>
            <div class="post-desc">${DGX.esc(data.description)}</div>
            <div class="price-row"><span class="price num">
              ${DGX.fmt(data.price_credits)} <small>کردیت</small></span>
              <span class="usd num">≈${(data.price_credits / 1000).toFixed(2)}$</span></div>
          </div></div>

        <!-- 3 image thumbnails -->
        <div style="display:flex;gap:8px;margin:10px 0">
          ${Object.entries(previews).map(([k, url]) => url ? `
            <div style="flex:1;text-align:center">
              <img src="${url}" style="width:100%;aspect-ratio:${k === 'main' ? '1' : k === 'feed' ? '16/9' : '9/16'};
                   object-fit:cover;border-radius:8px;border:1px solid var(--line)">
              <div style="font-size:9px;color:var(--dim);margin-top:3px">${IMG_SPECS[k].icon} ${k}</div>
            </div>` : '').join('')}
        </div>

        <div style="background:#fff3;color:var(--gold);border-radius:12px;padding:10px 14px;
             font-size:11.5px;line-height:1.9;margin-bottom:12px">
          ⏳ پس از انتشار، ادمین بررسی می‌کند و در مارکت منتشر می‌شود.</div>
        <div style="display:flex;gap:9px">
          <button class="btn btn-ghost" onclick="DGX.pages.create._go(3)">→ قبل</button>
          <button class="btn btn-primary" id="wPub" style="flex:1">🚀 انتشار محصول</button></div>
        <div style="height:80px"></div>`;

      w.querySelector('#wPub').onclick = async () => {
        const b = w.querySelector('#wPub');
        b.disabled = true; b.textContent = '⏳ در حال انتشار…';
        try {
          // Step A: create product (JSON)
          const r = await DGX.api('/api/app/create-product', { body: data });
          const newPid = r.id;

          // Step B: upload 3 images (multipart)
          const fd = new FormData();
          fd.append('img_main', images.main);
          fd.append('img_feed', images.feed);
          fd.append('img_story', images.story);
          const upRes = await fetch(`/api/app/product/${newPid}/images`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + DGX.token, 'X-Requested-With': 'fetch' },
            body: fd
          });
          if (!upRes.ok) {
            const ed = await upRes.json().catch(() => ({}));
            throw new Error(ed.detail || 'آپلود عکس ناموفق');
          }

          b.textContent = '🎉 منتشر شد!';
          DGX.haptic('heavy');
          view.innerHTML = `
            <div class="empty" style="padding-top:90px">
              <div class="burst success-ring" style="width:74px;height:74px;border-radius:99px;
                background:var(--em);color:#03130a;display:inline-flex;align-items:center;
                justify-content:center;font-size:36px;margin-bottom:14px">🚀</div>
              <b style="font-size:17px">محصولت با ۳ عکس ثبت شد!</b><br>
              شماره: #${newPid}<br>${r.note}<br><br>
              <button class="btn btn-primary" onclick="location.hash='#/home'">برگشت به فید</button>
            </div>`;
        } catch (e) {
          b.disabled = false; b.textContent = '🚀 انتشار محصول';
          DGX.toast(e.msg || e.message || '', true);
        }
      };
    }
  }

  // navigation helper (re-render with target step)
  DGX.pages.create._go = s => { step = s; render(); };

  render();
};
