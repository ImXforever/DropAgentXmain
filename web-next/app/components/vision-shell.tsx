"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { allFeatures, categories, creators, featureGroups, notifications, posts as seedPosts, products } from "../lib/demo-data";
import { NavKey, Post, Product } from "../lib/types";

type Toast = { text: string; kind?: "success" | "info" };

type IconProps = { children: string; className?: string };
function Icon({ children, className = "" }: IconProps) {
  return <span className={`icon ${className}`} aria-hidden="true">{children}</span>;
}

function Avatar({ initials, tone, size = "md" }: { initials: string; tone: string; size?: "sm" | "md" | "lg" }) {
  return <div className={`avatar avatar-${tone} avatar-${size}`}>{initials}</div>;
}

function SectionTitle({ eyebrow, title, action, onAction }: { eyebrow?: string; title: string; action?: string; onAction?: () => void }) {
  return (
    <div className="section-title">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {action && <button className="text-button" onClick={onAction}>{action} <span>←</span></button>}
    </div>
  );
}

function ProductCard({ product, onBuy, compact = false }: { product: Product; onBuy: (product: Product) => void; compact?: boolean }) {
  return (
    <article className={`product-card ${compact ? "product-card-compact" : ""}`}>
      <div className={`product-visual tone-${product.tone}`}>
        <span className="visual-grid" />
        <span className="product-glyph">{product.icon}</span>
        {product.badge && <span className="floating-badge">{product.badge}</span>}
        <button className="save-chip" aria-label="ذخیره محصول"><Icon>🔖</Icon></button>
      </div>
      <div className="product-info">
        <span className="mini-label">{product.category}</span>
        <h3>{product.title}</h3>
        <div className="seller-row"><Avatar initials={product.seller.slice(0, 1)} tone={product.tone} size="sm" /><span>{product.seller}</span><span className="verified">✓</span></div>
        <div className="product-bottom">
          <div><strong>${product.price.toFixed(2)}</strong>{product.oldPrice && <del>${product.oldPrice.toFixed(2)}</del>}</div>
          <span className="rating">★ {product.rating}</span>
        </div>
        {!compact && <button className="buy-button" onClick={() => onBuy(product)}><span>افزودن به سبد</span><Icon>＋</Icon></button>}
      </div>
    </article>
  );
}

function PostCard({ post, onLike, onSave, onComment, onBuy }: { post: Post; onLike: () => void; onSave: () => void; onComment: () => void; onBuy: (product: Product) => void }) {
  const attached = post.productId ? products.find((product) => product.id === post.productId) : undefined;
  return (
    <article className="post-card">
      <div className="post-head">
        <Avatar initials={post.initials} tone={post.tone} />
        <div className="post-author"><strong>{post.author} <span className="verified">✓</span></strong><span>{post.handle} · {post.time}</span></div>
        <button className="more-button" aria-label="گزینه‌های بیشتر">•••</button>
      </div>
      <p className="post-copy">{post.text}</p>
      <div className="tag-row">{post.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      {attached && (
        <button className={`embedded-product tone-${attached.tone}`} onClick={() => onBuy(attached)}>
          <span className="embedded-art">{attached.icon}</span>
          <span className="embedded-copy"><small>محصول معرفی‌شده</small><strong>{attached.title}</strong><span>{attached.seller} · ★ {attached.rating}</span></span>
          <span className="embedded-price">${attached.price.toFixed(2)} <Icon>↗</Icon></span>
        </button>
      )}
      <div className="post-actions">
        <button className={post.liked ? "active-like" : ""} onClick={onLike}><Icon>{post.liked ? "♥" : "♡"}</Icon><span>{post.likes}</span></button>
        <button onClick={onComment}><Icon>◌</Icon><span>{post.comments}</span></button>
        <button><Icon>⤴</Icon><span>{post.reposts}</span></button>
        <button className={`action-end ${post.saved ? "active-save" : ""}`} onClick={onSave}><Icon>{post.saved ? "🔖" : "♧"}</Icon></button>
      </div>
    </article>
  );
}

const navItems: { key: NavKey; icon: string; label: string; short?: string }[] = [
  { key: "home", icon: "⌂", label: "خانه" },
  { key: "explore", icon: "⌕", label: "اکسپلور" },
  { key: "shop", icon: "◈", label: "مارکت" },
  { key: "create", icon: "＋", label: "ساختن" },
  { key: "activity", icon: "♢", label: "فعالیت" },
  { key: "profile", icon: "◎", label: "پروفایل" },
];

const moreNav: { key: NavKey; icon: string; label: string }[] = [
  { key: "messages", icon: "◌", label: "پیام‌ها" },
  { key: "wallet", icon: "₿", label: "کیف پول" },
  { key: "orders", icon: "▣", label: "سفارش‌ها" },
  { key: "saved", icon: "♧", label: "ذخیره‌ها" },
  { key: "collections", icon: "▦", label: "مجموعه‌ها" },
  { key: "analytics", icon: "⌁", label: "آنالیتیکس" },
];

export default function VisionShell() {
  const [active, setActive] = useState<NavKey>("home");
  const [posts, setPosts] = useState<Post[]>(seedPosts);
  const [marketProducts, setMarketProducts] = useState<Product[]>(products);
  const [backendOnline, setBackendOnline] = useState(false);
  const [cart, setCart] = useState<Product[]>([]);
  const [followed, setFollowed] = useState<string[]>(["@hadi"]);
  const [query, setQuery] = useState("");
  const [featureQuery, setFeatureQuery] = useState("");
  const [featureGroup, setFeatureGroup] = useState("همه");
  const [toast, setToast] = useState<Toast | null>(null);
  const [composer, setComposer] = useState("");
  const [composerMode, setComposerMode] = useState("پست");
  const [profileTab, setProfileTab] = useState("پست‌ها");
  const [darkMode, setDarkMode] = useState(true);
  const [compactMode, setCompactMode] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/backend/api/pub/catalog?limit=24", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("backend")))
      .then((payload: { items?: Array<Record<string, unknown>> }) => {
        if (cancelled || !Array.isArray(payload.items) || payload.items.length === 0) return;
        const tones = ["mint", "violet", "blue", "orange", "cyan", "pink", "gold", "green"];
        const live = payload.items.map((item, index) => ({
          id: Number(item.id ?? index + 1),
          title: String(item.title ?? "محصول بدون عنوان"),
          category: String(item.category ?? "عمومی"),
          price: Number(item.price_usd ?? Number(item.price_credits ?? 0) / 1000),
          rating: Number(item.stars ?? 0),
          sales: Number(item.sales_count ?? 0),
          seller: String(item.creator_name ?? "سازنده DropAgentX"),
          sellerHandle: String(item.creator_username ? `@${item.creator_username}` : "@creator"),
          icon: ["✦", "◈", "⌘", "▶", "⚡", "✺", "₿", "▦"][index % 8],
          tone: tones[index % tones.length],
          badge: index === 0 ? "از API" : undefined,
        } satisfies Product));
        setMarketProducts(live);
        setBackendOnline(true);
      })
      .catch(() => { if (!cancelled) setBackendOnline(false); });
    return () => { cancelled = true; };
  }, []);

  const showToast = (text: string, kind: Toast["kind"] = "success") => {
    setToast({ text, kind });
    window.setTimeout(() => setToast(null), 2800);
  };

  const addToCart = (product: Product) => {
    setCart((current) => current.some((item) => item.id === product.id) ? current : [...current, product]);
    showToast(`${product.title} به سبد اضافه شد`);
  };

  const toggleLike = (id: number) => {
    setPosts((current) => current.map((post) => post.id === id ? { ...post, liked: !post.liked, likes: post.likes + (post.liked ? -1 : 1) } : post));
  };

  const toggleSave = (id: number) => {
    setPosts((current) => current.map((post) => post.id === id ? { ...post, saved: !post.saved } : post));
    showToast("لیست ذخیره‌ها به‌روزرسانی شد", "info");
  };

  const doFollow = (handle: string) => {
    setFollowed((current) => current.includes(handle) ? current.filter((item) => item !== handle) : [...current, handle]);
    showToast(followed.includes(handle) ? "دنبال‌کردن لغو شد" : "حالا این سازنده را دنبال می‌کنی", "info");
  };

  const submitPost = (event: FormEvent) => {
    event.preventDefault();
    if (!composer.trim()) return;
    const newPost: Post = { id: Date.now(), author: "کیامد مکس", handle: "@kiamad", initials: "ک", tone: "mint", time: "همین حالا", text: composer.trim(), tags: ["#DropAgentX"], likes: 0, comments: 0, reposts: 0 };
    setPosts((current) => [newPost, ...current]);
    setComposer("");
    setActive("home");
    showToast("پستت منتشر شد ✦");
  };

  const filteredProducts = useMemo(() => marketProducts.filter((product) => !query || `${product.title} ${product.category} ${product.seller}`.toLowerCase().includes(query.toLowerCase())), [marketProducts, query]);
  const filteredFeatures = useMemo(() => allFeatures.filter((feature) => (!featureQuery || feature.name.toLowerCase().includes(featureQuery.toLowerCase())) && (featureGroup === "همه" || feature.group === featureGroup)), [featureGroup, featureQuery]);
  const savedPosts = posts.filter((post) => post.saved);
  const unread = notifications.filter((item) => item.unread).length;

  const pageTitle: Record<NavKey, string> = { home: "خانه", explore: "اکسپلور", shop: "مارکت", create: "ساختن", activity: "فعالیت", profile: "پروفایل", messages: "پیام‌ها", wallet: "کیف پول", orders: "سفارش‌ها", saved: "ذخیره‌ها", collections: "مجموعه‌ها", analytics: "آنالیتیکس", settings: "تنظیمات", admin: "مدیریت", features: "Feature Lab" };

  return (
    <div className={`vision-app ${darkMode ? "is-dark" : "is-light"} ${compactMode ? "is-compact" : ""}`}>
      <aside className="sidebar">
        <div className="brand" onClick={() => setActive("home")} role="button" tabIndex={0}>
          <div className="brand-mark"><span>✦</span></div><div><strong>DROP<span>AGENT</span>X</strong><small>social commerce OS</small></div>
        </div>
        <div className="profile-mini"><Avatar initials="ک" tone="mint" /><div><strong>کیامد مکس</strong><span>@kiamad · Creator</span></div><button aria-label="تنظیمات" onClick={() => setActive("settings")}>⚙</button></div>
        <nav className="main-nav" aria-label="ناوبری اصلی">
          <span className="nav-label">Workspace</span>
          {navItems.map((item) => <button key={item.key} className={active === item.key ? "active" : ""} onClick={() => setActive(item.key)}><Icon>{item.icon}</Icon><span>{item.label}</span>{item.key === "activity" && unread > 0 && <b className="nav-badge">{unread}</b>}</button>)}
          <span className="nav-label nav-label-spaced">Manage</span>
          {moreNav.map((item) => <button key={item.key} className={active === item.key ? "active" : ""} onClick={() => setActive(item.key)}><Icon>{item.icon}</Icon><span>{item.label}</span>{item.key === "messages" && <i className="online-dot" />}</button>)}
        </nav>
        <div className="sidebar-bottom"><button onClick={() => setActive("features")} className="feature-lab-button"><Icon>⌁</Icon><span><strong>Feature Lab</strong><small>100 capabilities mapped</small></span><em>100</em></button><button className="sidebar-settings" onClick={() => setActive("settings")}><Icon>⚙</Icon><span>تنظیمات</span></button></div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <div className="mobile-brand"><div className="brand-mark"><span>✦</span></div><strong>DROP<span>AGENT</span>X</strong></div>
          <div className="mobile-page-title">{pageTitle[active]}</div>
          <label className="global-search"><Icon>⌕</Icon><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && setActive("explore")} placeholder="جستجو در پست‌ها، محصولات، سازنده‌ها..." /><kbd>⌘ K</kbd></label>
          <div className="top-actions"><span className={`api-status ${backendOnline ? "online" : "demo"}`} title={backendOnline ? "اتصال به Backend برقرار است" : "حالت Demo فعال است"}><i />{backendOnline ? "LIVE" : "DEMO"}</span><button className="icon-button" aria-label="تغییر تم" onClick={() => setDarkMode((value) => !value)}>{darkMode ? "☼" : "☾"}</button><button className="icon-button notification-button" aria-label="اعلان‌ها" onClick={() => setActive("activity")}>♢{unread > 0 && <i />}</button><button className="top-avatar" onClick={() => setActive("profile")}><Avatar initials="ک" tone="mint" size="sm" /></button></div>
        </header>

        <div className="page-scroll">
          {active === "home" && <HomeView posts={posts} onLike={toggleLike} onSave={toggleSave} onComment={() => showToast("بخش گفتگو آماده است", "info")} onBuy={addToCart} composer={composer} setComposer={setComposer} onSubmit={submitPost} setActive={setActive} />}
          {active === "explore" && <ExploreView query={query} products={filteredProducts} onBuy={addToCart} followed={followed} onFollow={doFollow} setActive={setActive} />}
          {active === "shop" && <ShopView products={filteredProducts} onBuy={addToCart} query={query} setQuery={setQuery} />}
          {active === "create" && <CreateView mode={composerMode} setMode={setComposerMode} composer={composer} setComposer={setComposer} onSubmit={submitPost} showToast={showToast} />}
          {active === "activity" && <ActivityView onRead={() => showToast("همه اعلان‌ها خوانده شدند", "info")} />}
          {active === "profile" && <ProfileView tab={profileTab} setTab={setProfileTab} posts={posts} products={products} onBuy={addToCart} onLike={toggleLike} onSave={toggleSave} onComment={() => showToast("گفتگو آماده است", "info")} setActive={setActive} />}
          {active === "messages" && <MessagesView showToast={showToast} />}
          {active === "wallet" && <WalletView showToast={showToast} />}
          {active === "orders" && <OrdersView />}
          {active === "saved" && <SavedView posts={savedPosts} products={products.slice(0, 3)} onBuy={addToCart} onLike={toggleLike} onSave={toggleSave} onComment={() => showToast("گفتگو آماده است", "info")} />}
          {active === "collections" && <CollectionsView showToast={showToast} />}
          {active === "analytics" && <AnalyticsView />}
          {active === "settings" && <SettingsView darkMode={darkMode} setDarkMode={setDarkMode} compactMode={compactMode} setCompactMode={setCompactMode} showToast={showToast} />}
          {active === "features" && <FeatureLab query={featureQuery} setQuery={setFeatureQuery} group={featureGroup} setGroup={setFeatureGroup} features={filteredFeatures} />}
          {active === "admin" && <AdminView />}
        </div>
      </main>

      <nav className="mobile-nav">{navItems.map((item) => <button key={item.key} className={active === item.key ? "active" : ""} onClick={() => setActive(item.key)}><Icon>{item.icon}</Icon><span>{item.label}</span></button>)}</nav>
      {cart.length > 0 && <div className="cart-dock"><div><span className="cart-count">{cart.length}</span><span>آیتم در سبد خرید</span></div><button onClick={() => setActive("orders")}>مشاهده سبد <span>${cart.reduce((sum, product) => sum + product.price, 0).toFixed(2)}</span> ↗</button></div>}
      {toast && <div className={`toast toast-${toast.kind || "success"}`}><span>{toast.kind === "info" ? "◆" : "✓"}</span>{toast.text}</div>}
    </div>
  );
}

function HomeView({ posts, onLike, onSave, onComment, onBuy, composer, setComposer, onSubmit, setActive }: { posts: Post[]; onLike: (id: number) => void; onSave: (id: number) => void; onComment: () => void; onBuy: (product: Product) => void; composer: string; setComposer: (value: string) => void; onSubmit: (event: FormEvent) => void; setActive: (key: NavKey) => void }) {
  const stories = [{ name: "داستان تو", initials: "＋", tone: "new" }, ...creators.map((creator) => ({ name: creator.name, initials: creator.initials, tone: creator.tone }))];
  return <>
    <div className="welcome-row"><div><span className="eyebrow">THURSDAY · 27 AUG 2026</span><h1>جریان تو، <span>بازار تو.</span></h1><p>اینجا جاییه که ایده‌ها به ارتباط و ارتباط‌ها به درآمد تبدیل می‌شن.</p></div><div className="live-indicator"><i /> <span>۲٬۴۸۱ سازنده آنلاین</span></div></div>
    <div className="story-strip"><div className="story-header"><strong>Stories</strong><button onClick={() => setActive("create")}>مشاهده همه <span>←</span></button></div><div className="stories-row">{stories.map((story, index) => <button className="story-item" key={story.name} onClick={() => setActive(index === 0 ? "create" : "profile")}><div className={`story-ring story-${story.tone}`}><Avatar initials={story.initials} tone={story.tone} /></div><span>{story.name}</span></button>)}</div></div>
    <form className="composer-card" onSubmit={onSubmit}><Avatar initials="ک" tone="mint" /><div className="composer-body"><input value={composer} onChange={(event) => setComposer(event.target.value)} placeholder="چه چیزی در ذهنته؟ محصول جدیدت رو معرفی کن..." /><div className="composer-toolbar"><div><button type="button" onClick={() => setActive("create")}>▧ <span>رسانه</span></button><button type="button" onClick={() => setActive("create")}>◉ <span>محصول</span></button><button type="button" onClick={() => setActive("create")}>☷ <span>نظرسنجی</span></button></div><button className="publish-button" type="submit">انتشار <span>↗</span></button></div></div></form>
    <div className="feed-toolbar"><div className="feed-tabs"><button className="active">برای تو</button><button>دنبال‌شده‌ها</button><button>ترند</button><button>محصولات</button></div><button className="filter-button">☷ فیلتر</button></div>
    <div className="feed-list">{posts.map((post) => <PostCard key={post.id} post={post} onLike={() => onLike(post.id)} onSave={() => onSave(post.id)} onComment={onComment} onBuy={onBuy} />)}</div>
  </>;
}

function ExploreView({ query, products, onBuy, followed, onFollow, setActive }: { query: string; products: Product[]; onBuy: (product: Product) => void; followed: string[]; onFollow: (handle: string) => void; setActive: (key: NavKey) => void }) {
  return <><div className="page-heading"><div><span className="eyebrow">DISCOVER SOMETHING NEW</span><h1>اکسپلور <span>∞</span></h1><p>{query ? `نتایج جستجو برای «${query}»` : "ایده‌ها، سازنده‌ها و محصولاتی که ارزش کشف کردن دارند."}</p></div><button className="outline-button" onClick={() => setActive("features")}>نمایش ۱۰۰ قابلیت <span>✦</span></button></div><div className="trend-banner"><div><span className="eyebrow">TRENDING NOW · ۲ ساعت اخیر</span><h2>Creator commerce در حال تغییر بازیه.</h2><p>+۴۷٪ رشد تعامل در محتوای فروش‌محور</p></div><div className="trend-bars"><i /><i /><i /><i /><i /><i /><i /></div><span className="trend-score">+47<span>%</span></span></div><SectionTitle eyebrow="TRENDING TOPICS" title="موضوعات داغ" action="همه موضوعات" /><div className="topic-grid">{["هوش مصنوعی", "Creator Economy", "طراحی محصول", "اتوماسیون", "کریپتو", "ساختن در تلگرام"].map((topic, index) => <button key={topic} className={`topic-card topic-${index}`} onClick={() => setActive("shop")}><span>{["✦", "◈", "◌", "⚡", "₿", "⌘"][index]}</span><strong>{topic}</strong><small>{["۲۴.۸K پست", "۱۷.۲K پست", "۹.۶K پست", "۸.۴K پست", "۶.۱K پست", "۴.۹K پست"][index]}</small><em>↗</em></button>)}</div><SectionTitle eyebrow="POPULAR PRODUCTS" title="محصولات پیشنهادی" action="رفتن به مارکت" onAction={() => setActive("shop")} /><div className="product-grid">{products.slice(0, 4).map((product) => <ProductCard product={product} onBuy={onBuy} key={product.id} />)}</div><SectionTitle eyebrow="CREATORS TO WATCH" title="سازنده‌های محبوب" action="مشاهده همه" /><div className="creator-grid">{creators.map((creator) => <div className="creator-card" key={creator.handle}><div className={`creator-cover tone-${creator.tone}`} /><Avatar initials={creator.initials} tone={creator.tone} size="lg" /><div className="creator-card-content"><strong>{creator.name} <span className="verified">✓</span></strong><span>{creator.handle}</span><div className="creator-stats"><span><b>{creator.followers}</b> دنبال‌کننده</span><span><b>{creator.sales}</b> فروش</span></div><button className={followed.includes(creator.handle) ? "following-button" : "follow-button"} onClick={() => onFollow(creator.handle)}>{followed.includes(creator.handle) ? "دنبال می‌کنی ✓" : "دنبال کردن ＋"}</button></div></div>)}</div></>;
}

function ShopView({ products, onBuy, query, setQuery }: { products: Product[]; onBuy: (product: Product) => void; query: string; setQuery: (value: string) => void }) {
  const [selectedCategory, setSelectedCategory] = useState("همه");
  const visible = products.filter((product) => selectedCategory === "همه" || product.category === selectedCategory);
  return <><div className="page-heading shop-heading"><div><span className="eyebrow">THE CREATOR MARKET</span><h1>بازار <span>ایده‌ها.</span></h1><p>چیزهایی که سازنده‌ها برای سازنده‌ها ساخته‌اند.</p></div><div className="shop-actions"><button className="outline-button">▣ فروشگاه من</button><button className="primary-button">＋ محصول جدید</button></div></div><div className="shop-hero"><div><span className="hero-kicker">DROP OF THE WEEK</span><h2>آینده را<br /><strong>همین امروز بساز.</strong></h2><p>۱۲ محصول منتخب از سازنده‌های مستقل</p><button className="light-button">کشف مجموعه <span>↗</span></button></div><div className="hero-orbit"><span>✦</span><span>◈</span><span>⚡</span><b>DROP<br />01</b></div></div><div className="shop-controls"><div className="category-pills">{categories.map((category) => <button key={category} className={selectedCategory === category ? "active" : ""} onClick={() => setSelectedCategory(category)}>{category}</button>)}</div><label className="shop-search">⌕<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="جستجوی مارکت" /></label></div><div className="shop-meta"><strong>{visible.length * 18 + 72} محصول</strong><span>مرتب‌سازی: <button>مرتبط‌ترین⌄</button></span></div><div className="product-grid product-grid-large">{visible.map((product) => <ProductCard key={product.id} product={product} onBuy={onBuy} />)}</div></>;
}

function CreateView({ mode, setMode, composer, setComposer, onSubmit, showToast }: { mode: string; setMode: (value: string) => void; composer: string; setComposer: (value: string) => void; onSubmit: (event: FormEvent) => void; showToast: (text: string, kind?: Toast["kind"]) => void }) {
  const modes = [{ name: "پست", icon: "✦", text: "با جامعه‌ات حرف بزن" }, { name: "محصول", icon: "◈", text: "چیزی برای فروش بساز" }, { name: "استوری", icon: "◌", text: "یک لحظه را ثبت کن" }, { name: "ریلز", icon: "▶", text: "ویدیوی کوتاه بساز" }, { name: "نظرسنجی", icon: "☷", text: "نظر جمع کن" }, { name: "مجموعه", icon: "▦", text: "چیزهای خوب را جمع کن" }];
  return <><div className="page-heading"><div><span className="eyebrow">CREATE STUDIO</span><h1>چیزی <span>بساز.</span></h1><p>ایده‌ها وقتی منتشر می‌شن، قدرت پیدا می‌کنن.</p></div><span className="draft-status">● ذخیره خودکار فعال</span></div><div className="create-layout"><div className="create-types">{modes.map((item) => <button key={item.name} className={mode === item.name ? "active" : ""} onClick={() => setMode(item.name)}><span className="create-type-icon">{item.icon}</span><span><strong>{item.name}</strong><small>{item.text}</small></span>{mode === item.name && <b>✓</b>}</button>)}</div><div className="create-editor"><div className="editor-head"><div><Avatar initials="ک" tone="mint" /><span><strong>کیامد مکس</strong><small>@kiamad · عمومی</small></span></div><button>•••</button></div><form onSubmit={onSubmit}><textarea value={composer} onChange={(event) => setComposer(event.target.value)} placeholder={mode === "محصول" ? "محصولت را در چند کلمه معرفی کن..." : "داستانت را با دنیا به اشتراک بگذار..."} autoFocus /><div className="editor-preview">{mode === "پست" ? <><span>✦</span><strong>پست متنی</strong><small>عکس، ویدیو یا محصول اضافه کن</small></> : <><span>{modes.find((item) => item.name === mode)?.icon}</span><strong>{mode} آماده ساخت است</strong><small>این بخش با انتشار بعدی به API متصل می‌شود</small></>}</div><div className="editor-tools"><div><button type="button">▧</button><button type="button">◉</button><button type="button">⌁</button><button type="button">☷</button><button type="button">☺</button></div><button className="primary-button" type="submit">{mode === "پست" ? "انتشار پست" : `ساخت ${mode}`} <span>↗</span></button></div></form></div></div><div className="create-suggestions"><span className="eyebrow">QUICK START</span><h3>از AI کمک بگیر</h3><p>هر ایده‌ای داری بگو؛ هرمس آن را به محتوای آماده انتشار تبدیل می‌کند.</p><button className="ai-button" onClick={() => { setComposer("یک پست جذاب درباره ساختن درآمد از محصولات دیجیتال بنویس"); showToast("پیشنهاد AI در ادیتور قرار گرفت", "info"); }}>✦ ساخت با Hermes <span>↗</span></button></div></>;
}

function ActivityView({ onRead }: { onRead: () => void }) {
  return <><div className="page-heading"><div><span className="eyebrow">YOUR ACTIVITY</span><h1>اتفاق‌ها <span>اینجا هستند.</span></h1><p>تعامل‌ها، فروش‌ها و خبرهای مهم را از دست نده.</p></div><button className="text-button" onClick={onRead}>خوانده‌شدن همه ✓</button></div><div className="activity-summary"><div><span>تعامل این هفته</span><strong>+۲۸٪</strong><small>در مقایسه با هفته قبل</small></div><div><span>فروش جدید</span><strong>۱۲</strong><small>از ۳ محصول</small></div><div><span>دنبال‌کننده جدید</span><strong>+۱۸۴</strong><small>رشد ارگانیک</small></div></div><div className="notification-list">{notifications.map((item) => <div className={`notification-item ${item.unread ? "unread" : ""}`} key={item.id}><div className={`notification-icon notification-${item.type}`}>{item.icon}</div><div><strong>{item.title}</strong><p>{item.text}</p><span>{item.time}</span></div>{item.unread && <i className="unread-dot" />}</div>)}</div></>;
}

function ProfileView({ tab, setTab, posts, products, onBuy, onLike, onSave, onComment, setActive }: { tab: string; setTab: (value: string) => void; posts: Post[]; products: Product[]; onBuy: (product: Product) => void; onLike: (id: number) => void; onSave: (id: number) => void; onComment: () => void; setActive: (key: NavKey) => void }) {
  const tabs = ["پست‌ها", "پاسخ‌ها", "رسانه", "محصولات", "مجموعه‌ها"];
  return <><div className="profile-cover tone-mint"><div className="cover-noise" /><button>✎ ویرایش کاور</button></div><div className="profile-hero"><Avatar initials="ک" tone="mint" size="lg" /><button className="outline-button profile-edit">ویرایش پروفایل</button><div className="profile-name"><h1>کیامد مکس <span className="verified">✓</span></h1><span>@kiamad · Builder, creator & market maker</span></div><p>در حال ساختن جایی که هر ایده می‌تونه یک کسب‌وکار باشه. 🟢</p><div className="profile-links"><span>◉ Lelystad, NL</span><span>↗ dropagentx.com</span><span>◷ عضو از ۲۰۲۴</span></div><div className="profile-numbers"><span><b>۲٫۴K</b> دنبال‌کننده</span><span><b>۱۸۹</b> دنبال‌شونده</span><span><b>۴۲</b> محصول</span><span><b>$۸٫۴K</b> درآمد</span></div></div><div className="profile-tabs">{tabs.map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>{tab === "محصولات" ? <><SectionTitle eyebrow="MY STORE" title="محصولات من" action="مدیریت فروشگاه" onAction={() => setActive("shop")} /><div className="product-grid">{products.slice(0, 4).map((product) => <ProductCard key={product.id} product={product} onBuy={onBuy} />)}</div></> : tab === "مجموعه‌ها" ? <CollectionsView showToast={() => undefined} /> : <div className="feed-list profile-feed">{posts.slice(0, 2).map((post) => <PostCard key={post.id} post={post} onLike={() => onLike(post.id)} onSave={() => onSave(post.id)} onComment={onComment} onBuy={onBuy} />)}</div>}</>;
}

function MessagesView({ showToast }: { showToast: (text: string, kind?: Toast["kind"]) => void }) {
  const chats = [{ name: "سارا محمدی", initials: "س", tone: "violet", preview: "این پکیج برای تیم ما عالیه، یک سوال داشتم...", time: "۲دقیقه", active: true }, { name: "Hadi AI", initials: "H", tone: "blue", preview: "فایل‌ها رو برات فرستادم ✦", time: "۲۱دقیقه" }, { name: "Mitra Motion", initials: "M", tone: "orange", preview: "بله، نسخه Pro هم موجوده", time: "۱ساعت" }, { name: "Atlas Research", initials: "A", tone: "mint", preview: "Let’s build something useful.", time: "دیروز" }];
  return <><div className="page-heading"><div><span className="eyebrow">DIRECT MESSAGES</span><h1>گفتگوها <span>زنده‌اند.</span></h1><p>با سازنده‌ها، مشتری‌ها و هم‌تیمی‌ها در ارتباط باش.</p></div><button className="primary-button" onClick={() => showToast("گفتگوی جدید آماده است", "info")}>＋ گفتگوی جدید</button></div><div className="messages-layout"><div className="chat-list"><label className="chat-search">⌕ <input placeholder="جستجوی گفتگو" /></label>{chats.map((chat) => <button key={chat.name} className={`chat-preview ${chat.active ? "active" : ""}`}><Avatar initials={chat.initials} tone={chat.tone} /><span><strong>{chat.name}</strong><small>{chat.preview}</small></span><time>{chat.time}</time></button>)}</div><div className="chat-window"><div className="chat-window-head"><Avatar initials="س" tone="violet" /><div><strong>سارا محمدی</strong><span><i /> فعال همین حالا</span></div><button>•••</button></div><div className="chat-messages"><div className="message message-them">سلام! پکیج AI Creator Launch Kit رو دیدم. برای یک برند شخصی مناسبه؟<small>۱۲:۴۱</small></div><div className="message message-me">قطعاً. برای لانچ اولت تمام قالب‌های لازم رو داره؛ از برنامه محتوا تا صفحه فروش.</div><div className="shared-product tone-mint"><span>✦</span><div><small>محصول به اشتراک‌گذاشته‌شده</small><strong>AI Creator Launch Kit</strong><b>$12.50</b></div><span>↗</span></div></div><form className="chat-input" onSubmit={(event) => { event.preventDefault(); showToast("پیام ارسال شد"); }}><button type="button">＋</button><input placeholder="پیامت را بنویس..." /><button className="send-message" type="submit">↗</button></form></div></div></>;
}

function WalletView({ showToast }: { showToast: (text: string, kind?: Toast["kind"]) => void }) {
  return <><div className="page-heading"><div><span className="eyebrow">CREATOR WALLET</span><h1>ارزش <span>در جریان.</span></h1><p>درآمد، کمیسیون و پرداخت‌هایت را در یک نگاه ببین.</p></div><button className="outline-button" onClick={() => showToast("درخواست برداشت ثبت می‌شود", "info")}>برداشت وجه ↗</button></div><div className="wallet-card"><div className="wallet-orb">✦</div><span className="eyebrow">AVAILABLE BALANCE</span><strong>$۸٬۴۲۶<span>.۳۸</span></strong><div className="wallet-card-bottom"><span>≈ ۸٬۴۲۶ کردیت</span><span className="growth">↗ +۱۲٫۸٪ این ماه</span></div></div><div className="wallet-metrics"><Metric label="درآمد این ماه" value="$۲٬۱۸۴" change="+۲۸٪" /><Metric label="در انتظار تسویه" value="$۳۴۲" change="۱۲ سفارش" /><Metric label="درآمد افیلیت" value="$۶۸۶" change="+۱۶٪" /></div><SectionTitle eyebrow="LEDGER" title="آخرین تراکنش‌ها" action="مشاهده همه" /><div className="transaction-list">{[["فروش محصول", "AI Creator Launch Kit", "+$۱۲٫۵۰", "امروز · ۱۲:۴۱", "plus", "🛒"], ["کمیسیون افیلیت", "از خرید @hadi", "+$۲٫۸۰", "امروز · ۰۹:۱۸", "plus", "↗"], ["تسویه بانکی", "حساب **** ۴۲۸۱", "−$۴۵۰٫۰۰", "۲۵ اوت", "minus", "↓"], ["فروش محصول", "Minimal Brand System", "+$۱۶٫۰۰", "۲۴ اوت", "plus", "🛒"]].map((row) => <div className="transaction-row" key={row[1]}><span className={`transaction-icon ${row[4]}`}>{row[5]}</span><div><strong>{row[0]}</strong><small>{row[1]}</small></div><time>{row[3]}</time><b className={row[4]}>{row[2]}</b></div>)}</div></>;
}

function Metric({ label, value, change }: { label: string; value: string; change: string }) { return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>↗ {change}</small></div>; }

function OrdersView() { return <><div className="page-heading"><div><span className="eyebrow">ORDER CENTER</span><h1>سفارش‌ها <span>مرتب‌اند.</span></h1><p>وضعیت خریدها و تحویل محصولاتت را مدیریت کن.</p></div><button className="outline-button">▣ فروشگاه من</button></div><div className="order-tabs"><button className="active">همه <b>۸۳</b></button><button>در انتظار <b>۷</b></button><button>تکمیل‌شده <b>۷۲</b></button><button>لغوشده <b>۴</b></button></div><div className="orders-table"><div className="orders-header"><span>سفارش</span><span>محصول</span><span>خریدار</span><span>مبلغ</span><span>وضعیت</span><span>تاریخ</span></div>{[["#DGX-2048", "AI Creator Launch Kit", "@sara", "$۱۲٫۵۰", "تکمیل‌شده", "امروز"], ["#DGX-2047", "Neon Commerce UI Pack", "@mohsen", "$۱۸٫۰۰", "در انتظار", "امروز"], ["#DGX-2046", "Prompt Engineering Mastery", "@roya", "$۹٫۹۰", "تکمیل‌شده", "دیروز"], ["#DGX-2045", "Persian Reels Templates", "@nima", "$۷٫۵۰", "تکمیل‌شده", "۲۵ اوت"], ["#DGX-2044", "Solopreneur Automation", "@atlas", "$۲۹٫۰۰", "Refund", "۲۵ اوت"]].map((order) => <div className="orders-row" key={order[0]}><strong>{order[0]}</strong><span>{order[1]}</span><span>{order[2]}</span><b>{order[3]}</b><span className={`status status-${order[4] === "تکمیل‌شده" ? "done" : order[4] === "در انتظار" ? "pending" : "refund"}`}>{order[4]}</span><time>{order[5]}</time></div>)}</div></>; }

function SavedView({ posts, products, onBuy, onLike, onSave, onComment }: { posts: Post[]; products: Product[]; onBuy: (product: Product) => void; onLike: (id: number) => void; onSave: (id: number) => void; onComment: () => void }) { return <><div className="page-heading"><div><span className="eyebrow">YOUR LIBRARY</span><h1>چیزهای <span>خوب ذخیره‌شده.</span></h1><p>الهام‌ها و محصولاتی که نمی‌خواهی از دست بدهی.</p></div><button className="primary-button">＋ پوشه جدید</button></div><div className="saved-folders"><button className="active"><span>♧</span><b>همه ذخیره‌ها</b><small>۲۴ مورد</small></button><button><span>✦</span><b>ایده‌های AI</b><small>۸ مورد</small></button><button><span>◈</span><b>برای خرید</b><small>۶ مورد</small></button><button><span>◌</span><b>الهام طراحی</b><small>۱۰ مورد</small></button></div><SectionTitle eyebrow="RECENTLY SAVED" title="ذخیره‌های اخیر" /><div className="saved-layout"><div className="feed-list">{posts.length ? posts.map((post) => <PostCard key={post.id} post={post} onLike={() => onLike(post.id)} onSave={() => onSave(post.id)} onComment={onComment} onBuy={onBuy} />) : <div className="empty-state">هنوز پستی ذخیره نکرده‌ای.</div>}</div><div className="saved-products"><h3>محصولات ذخیره‌شده</h3>{products.map((product) => <ProductCard key={product.id} product={product} onBuy={onBuy} compact />)}</div></div></>; }

function CollectionsView({ showToast }: { showToast: (text: string, kind?: Toast["kind"]) => void }) { return <><div className="collection-grid">{[{ name: "AI Stack", count: "۱۲ محصول", icon: "✦", tone: "mint" }, { name: "Launch Inspiration", count: "۲۸ پست", icon: "◈", tone: "violet" }, { name: "For Later", count: "۰ آیتم", icon: "＋", tone: "blue" }].map((collection) => <button className="collection-card" key={collection.name} onClick={() => showToast("مجموعه باز شد", "info")}><div className={`collection-art tone-${collection.tone}`}><span>{collection.icon}</span></div><strong>{collection.name}</strong><small>{collection.count}</small></button>)}</div><button className="new-collection" onClick={() => showToast("مجموعه جدید ساخته شد")}>＋ ساخت مجموعه جدید</button></>; }

function AnalyticsView() { return <><div className="page-heading"><div><span className="eyebrow">CREATOR INTELLIGENCE</span><h1>داده‌ها <span>حرف می‌زنند.</span></h1><p>تصمیم‌های بهتر با دیدن رفتار واقعی مخاطب.</p></div><select className="period-select" defaultValue="30"><option value="30">۳۰ روز اخیر⌄</option><option value="7">۷ روز اخیر</option></select></div><div className="analytics-top"><Metric label="بازدید پروفایل" value="۱۲٫۴K" change="+۲۱٫۴٪" /><Metric label="تعامل محتوا" value="۸٫۸٪" change="+۱٫۹٪" /><Metric label="نرخ تبدیل" value="۳٫۸٪" change="+۰٫۸٪" /><Metric label="درآمد خالص" value="$۲٫۱۸۴" change="+۲۸٪" /></div><div className="analytics-grid"><div className="chart-card"><div className="chart-head"><div><span className="eyebrow">AUDIENCE GROWTH</span><h3>رشد مخاطب</h3></div><strong>+۱٬۲۸۴ <small>دنبال‌کننده</small></strong></div><div className="line-chart"><svg viewBox="0 0 700 220" role="img" aria-label="نمودار رشد مخاطب"><defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#48f6a4" stopOpacity=".3" /><stop offset="1" stopColor="#48f6a4" stopOpacity="0" /></linearGradient></defs><path d="M0 185 C55 180 70 160 120 167 S185 135 230 143 S286 119 335 128 S390 95 435 108 S500 80 545 86 S605 34 700 43 L700 220 L0 220Z" fill="url(#chartFill)" /><path d="M0 185 C55 180 70 160 120 167 S185 135 230 143 S286 119 335 128 S390 95 435 108 S500 80 545 86 S605 34 700 43" fill="none" stroke="#48f6a4" strokeWidth="3" /></svg><div className="chart-labels"><span>۱ مرداد</span><span>۸ مرداد</span><span>۱۵ مرداد</span><span>۲۲ مرداد</span><span>امروز</span></div></div></div><div className="funnel-card"><span className="eyebrow">COMMERCE FUNNEL</span><h3>از کشف تا خرید</h3><div className="funnel"><div style={{ width: "100%" }}><span>بازدید</span><b>۱۲٬۴۰۰</b></div><div style={{ width: "78%" }}><span>کلیک محصول</span><b>۹٬۶۷۲</b></div><div style={{ width: "48%" }}><span>افزودن به سبد</span><b>۵٬۹۵۲</b></div><div style={{ width: "28%" }}><span>خرید</span><b>۳٬۴۱۶</b></div></div></div></div><div className="insight-card"><span>✦</span><div><strong>یک insight برای تو</strong><p>پست‌هایی که بین ساعت ۱۸ تا ۲۱ منتشر می‌کنی، <b>۲٫۴ برابر</b> نرخ تبدیل بالاتری دارند.</p></div><button>برنامه‌ریزی پست ↗</button></div></>; }

function SettingsView({ darkMode, setDarkMode, compactMode, setCompactMode, showToast }: { darkMode: boolean; setDarkMode: (value: boolean) => void; compactMode: boolean; setCompactMode: (value: boolean) => void; showToast: (text: string, kind?: Toast["kind"]) => void }) { return <><div className="page-heading"><div><span className="eyebrow">CONTROL CENTER</span><h1>تنظیمات <span>تو، قوانین تو.</span></h1><p>تجربه‌ات را شخصی‌سازی و امنیتت را مدیریت کن.</p></div></div><div className="settings-layout"><div className="settings-nav"><button className="active">عمومی</button><button>حساب کاربری</button><button>اعلان‌ها</button><button>حریم خصوصی</button><button>امنیت</button><button>اتصال‌ها</button></div><div className="settings-content"><div className="settings-section"><SectionTitle eyebrow="APPEARANCE" title="ظاهر برنامه" /><div className="setting-row"><div><strong>حالت تاریک</strong><small>برای تمرکز بیشتر روی محتوا</small></div><button className={`toggle ${darkMode ? "on" : ""}`} onClick={() => setDarkMode(!darkMode)}><i /></button></div><div className="setting-row"><div><strong>حالت فشرده</strong><small>محتوای بیشتر در هر صفحه، مناسب دسکتاپ</small></div><button className={`toggle ${compactMode ? "on" : ""}`} onClick={() => setCompactMode(!compactMode)}><i /></button></div><div className="setting-row"><div><strong>رنگ تاکیدی</strong><small>رنگ برند و دکمه‌ها</small></div><div className="color-picker"><i /><i /><i /><i /></div></div><div className="setting-row"><div><strong>زبان برنامه</strong><small>زبان رابط کاربری</small></div><button className="select-button">فارسی (FA)⌄</button></div></div><div className="settings-section"><SectionTitle eyebrow="NOTIFICATIONS" title="اعلان‌ها" /><div className="setting-row"><div><strong>فعالیت‌های اجتماعی</strong><small>لایک، کامنت و دنبال‌کننده جدید</small></div><button className="toggle on"><i /></button></div><div className="setting-row"><div><strong>فروش و درآمد</strong><small>خرید، کمیسیون و تسویه</small></div><button className="toggle on"><i /></button></div></div><button className="save-settings" onClick={() => showToast("تنظیمات ذخیره شد")}>ذخیره تغییرات <span>↗</span></button></div></div></>; }

function FeatureLab({ query, setQuery, group, setGroup, features }: { query: string; setQuery: (value: string) => void; group: string; setGroup: (value: string) => void; features: { name: string; group: string; color: string }[] }) { return <><div className="page-heading feature-heading"><div><span className="eyebrow">VISIONWEB × DROPAGENTX</span><h1>Feature <span>Lab.</span></h1><p>۱۰۰ قابلیت برای یک Social Commerce Super-App؛ از کشف تا درآمد.</p></div><div className="feature-total"><strong>100</strong><span>capabilities<br />mapped</span></div></div><div className="feature-progress"><div><span>معماری محصول</span><strong>۴۰٪</strong></div><div className="progress-track"><i style={{ width: "40%" }} /></div><small>هستهٔ اجتماعی و commerce آمادهٔ اتصال به API است.</small></div><div className="feature-controls"><label className="global-search"><Icon>⌕</Icon><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="جستجوی قابلیت..." /></label><div className="feature-filters"><button className={group === "همه" ? "active" : ""} onClick={() => setGroup("همه")}>همه <b>100</b></button>{featureGroups.map((item) => <button key={item.title} className={group === item.title ? "active" : ""} onClick={() => setGroup(item.title)}>{item.title}<b>25</b></button>)}</div></div><div className="feature-grid">{features.map((feature, index) => <div className={`feature-card feature-${feature.color}`} key={feature.name}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{feature.name}</strong><small>{feature.group}</small></div><i>✓</i></div>)}</div></>; }

function AdminView() { return <><div className="page-heading"><div><span className="eyebrow">PLATFORM CONTROL</span><h1>مدیریت <span>کل سیستم.</span></h1><p>سلامت شبکه، تجارت و جامعه را از یک نقطه کنترل کن.</p></div><span className="live-indicator"><i /> همه سیستم‌ها عملیاتی</span></div><div className="admin-kpis"><Metric label="کاربران فعال" value="۲۴٫۸K" change="+۱۲٪" /><Metric label="GMV این ماه" value="$۸۶٫۴K" change="+۲۸٪" /><Metric label="محصولات فعال" value="۳٫۲K" change="+۸٪" /><Metric label="گزارش‌های باز" value="۲۳" change="−۴۲٪" /></div><div className="admin-panels"><div><SectionTitle eyebrow="MODERATION QUEUE" title="صف بررسی" action="مشاهده همه" /><div className="moderation-list">{[["محصول جدید", "Prompt Pack فارسی", "در انتظار بررسی", "pending"], ["گزارش محتوا", "@unknown · spam", "نیازمند اقدام", "danger"], ["درخواست فروشنده", "@roya · Pro plan", "جدید", "new"]].map((item) => <div key={item[1]}><span className={`mod-dot ${item[3]}`} /><div><strong>{item[0]}</strong><small>{item[1]}</small></div><b>{item[2]}</b><button>›</button></div>)}</div></div><div className="health-panel"><span className="eyebrow">SYSTEM HEALTH</span><h3>همه‌چیز روان است.</h3><div className="health-ring"><strong>۹۹<span>.۸</span>%</strong><small>uptime</small></div><div className="health-lines"><span><i /> API latency <b>۸۴ms</b></span><span><i /> Queue status <b>نامحدود</b></span><span><i /> Storage <b>۳۴٪</b></span></div></div></div></>; }
