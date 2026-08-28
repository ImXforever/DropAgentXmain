/* DropAgentX — core namespace + Telegram bridge
   Strategy: ALWAYS route to home. Auth enhances but never blocks browsing. */
window.DGX = { user: null, ready: false, isLoggedIn: false };

(() => {
  const tg = window.Telegram?.WebApp;
  const VER = parseFloat(tg?.version || '0') || 0;
  const has = min => VER >= min;

  if (tg) {
    try {
      tg.ready(); tg.expand();
      if (has(6.1)) { tg.setHeaderColor('#050505'); tg.setBackgroundColor('#050505'); }
      if (has(7.7) && tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (_) {}
  }

  DGX.tgVersion = VER;

  DGX.boot = async () => {
    DGX.renderNav(); DGX.renderTopbar('خانه');

    // Step 1: Try Telegram auto-auth
    const init = tg?.initData || '';
    let authed = false;

    if (init) {
      try {
        authed = await DGX.tgAuth();
        console.log('[DGX] tgAuth result:', authed ? 'SUCCESS' : 'FAILED');
      } catch (e) {
        console.warn('[DGX] tgAuth error:', e);
      }
    }

    // Step 2: Fallback to cached browser token
    if (!authed && !DGX.isLoggedIn) {
      const saved = localStorage.getItem('dgx_token');
      if (saved) {
        DGX.token = saved;
        // verify it works
        try {
          const r = await fetch('/api/app/me', {
            headers: { 'Authorization': 'Bearer ' + DGX.token }
          });
          if (r.ok) {
            DGX.user = await r.json();
            DGX.isLoggedIn = true;
          } else {
            DGX.token = ''; // stale, clear it
          }
        } catch (_) {}
      }
    }

    // Step 3: ALWAYS route to home regardless of auth status
    location.hash || (location.hash = '#/home');
    window.addEventListener('hashchange', () => DGX.route());
    DGX.route();
    DGX.ready = true;
  };
})();
