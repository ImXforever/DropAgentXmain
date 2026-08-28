/* DropAgentX — AGENT: هرمسا embedded chat (uses platform engine + memory + skills) */
DGX.pages = DGX.pages || {};

DGX.pages.agent = async (view) => {
  if (!DGX.user) await DGX.refreshMe();
  view.innerHTML = `
    <div style="background:var(--em-dim);border:1px solid var(--line);border-radius:14px;
         padding:11px 15px;margin-bottom:12px;font-size:12px;line-height:1.9">
      💗 <b>هرمسا آنلاینه</b> — هر پیام ۱ کردیت · حافظه و مهارت‌هاش همیشه همراهشه
    </div>
    <div class="chat-scroll" id="chatScroll">
      <div class="bubble bub-bot">سلام عزیزم! من هرمسام 😊<br>هر چی لازم داری بپرس — گپ، ایده، ساخت فایل…</div>
    </div>
    <div class="agent-input">
      <textarea id="agIn" rows="1" placeholder="پیامت را بنویس…"
        maxlength="800"></textarea>
      <button class="btn btn-primary" id="agSend" style="flex:none;width:64px">➤</button>
    </div>`;
  const scroll = DGX.$('#chatScroll'), inp = DGX.$('#agIn'), send = DGX.$('#agSend');

  const bubble = (text, me) => {
    const b = document.createElement('div');
    b.className = 'bubble ' + (me ? 'bub-me' : 'bub-bot');
    b.textContent = text;
    scroll.appendChild(b);
    scroll.scrollTop = scroll.scrollHeight;
    return b;
  };

  let busy = false;
  async function sendMsg() {
    const text = inp.value.trim();
    if (!text || busy) return;
    busy = true; inp.value = ''; inp.style.height = 'auto';
    bubble(text, true); DGX.haptic('light');
    const typing = bubble('', false);
    typing.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
    try {
      const r = await DGX.api('/api/app/agent', { body: { text } });
      typing.textContent = r.answer || '…';
      DGX.refreshMe();
      DGX.haptic('medium');
    } catch (e) {
      typing.innerHTML = `⚠️ ${(e && e.msg) || 'ارور'}${(e && e.msg || '').includes('کردیت') ? '' : ''}`;
    }
    scroll.scrollTop = scroll.scrollHeight;
    busy = false;
  }

  send.onclick = sendMsg;
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
  });
  inp.addEventListener('input', () => {
    inp.style.height = 'auto';
    inp.style.height = Math.min(120, inp.scrollHeight) + 'px';
  });
};
