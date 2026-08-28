# DropAgentX Next.js Experience

The new mobile-first Next.js App Router frontend for DropAgentX, inspired by the
VisionWEB specification. It is intentionally a separate app so the hardened
Python/Telegram backend continues to run while the web experience is migrated.

## Run

```bash
npm install
npm run dev
```

The app binds to `0.0.0.0`. Set `BACKEND_URL` to the Python API when connecting
real data; browser requests should use relative `/backend/*` URLs through the
Next rewrite and never call localhost directly.

## Current scope

- Premium dark/light responsive social-commerce shell
- Home feed, stories, composer, Explore, marketplace, seller profile, messages,
  wallet, orders, saved collections, analytics, settings and admin views
- Optimistic local interactions for likes, saves, follows, publishing and cart
- 100-feature Feature Lab mapped from `VisionWEB.txt`
- CSS-only visual system with mobile bottom navigation and desktop sidebar

The demo data is deliberately local and safe. Production data wiring should be
added through typed server actions/API clients after the PostgreSQL/Redis/S3
migration is provisioned.
