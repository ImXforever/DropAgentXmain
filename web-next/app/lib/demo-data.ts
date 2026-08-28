import { Notification, Post, Product } from "./types";

export const products: Product[] = [
  { id: 1, title: "AI Creator Launch Kit", category: "هوش مصنوعی", price: 12.5, oldPrice: 24, rating: 4.9, sales: 128, seller: "KIA Studio", sellerHandle: "@kia", icon: "✦", tone: "mint", badge: "پرفروش" },
  { id: 2, title: "Neon Commerce UI Pack", category: "طراحی", price: 18, rating: 4.8, sales: 84, seller: "Nima Design", sellerHandle: "@nima", icon: "◈", tone: "violet", badge: "جدید" },
  { id: 3, title: "Prompt Engineering Mastery", category: "آموزش", price: 9.9, oldPrice: 14, rating: 4.7, sales: 241, seller: "Hadi AI", sellerHandle: "@hadi", icon: "⌘", tone: "blue", badge: "ویژه" },
  { id: 4, title: "Persian Reels Templates", category: "محتوا", price: 7.5, rating: 4.6, sales: 67, seller: "Mitra Motion", sellerHandle: "@mitra", icon: "▶", tone: "orange" },
  { id: 5, title: "Solopreneur Automation", category: "اتوماسیون", price: 29, rating: 5, sales: 32, seller: "Flow Lab", sellerHandle: "@flowlab", icon: "⚡", tone: "cyan" },
  { id: 6, title: "Minimal Brand System", category: "برندینگ", price: 16, rating: 4.9, sales: 103, seller: "Saba Works", sellerHandle: "@saba", icon: "✺", tone: "pink" },
  { id: 7, title: "Crypto Research Dashboard", category: "کریپتو", price: 22, rating: 4.5, sales: 49, seller: "Atlas Research", sellerHandle: "@atlas", icon: "₿", tone: "gold" },
  { id: 8, title: "Creator Notion OS", category: "ابزار", price: 11, rating: 4.8, sales: 190, seller: "Roya Systems", sellerHandle: "@roya", icon: "▦", tone: "green" },
];

export const posts: Post[] = [
  { id: 1, author: "کیامد مکس", handle: "@kiamad", initials: "ک", tone: "mint", time: "۱۲ دقیقه پیش", text: "وقتی محتوا و محصول در یک حلقه قرار می‌گیرند، هر پست می‌تواند یک فروشگاه کوچک باشد. این همان چیزی است که داریم می‌سازیم. 🚀", tags: ["#DropAgentX", "#CreatorEconomy"], likes: 328, comments: 42, reposts: 18, productId: 1 },
  { id: 2, author: "سارا محمدی", handle: "@sara", initials: "س", tone: "violet", time: "۴۵ دقیقه پیش", text: "نسخه جدید پکیج قالب‌های من منتشر شد. برای سازنده‌هایی که می‌خواهند در کمتر از یک ساعت یک لانچ تمیز داشته باشند.", tags: ["#Design", "#Launch"], likes: 174, comments: 21, reposts: 9, productId: 2 },
  { id: 3, author: "Atlas Research", handle: "@atlas", initials: "A", tone: "blue", time: "۲ ساعت پیش", text: "سه سیگنال برای بررسی قبل از ورود به یک بازار جدید: رشد واقعی، نقدشوندگی سالم و جامعه‌ای که فقط عدد نیست.", tags: ["#Research", "#Crypto"], likes: 91, comments: 16, reposts: 12, productId: 7 },
];

export const notifications: Notification[] = [
  { id: 1, type: "sale", title: "فروش جدید", text: "AI Creator Launch Kit توسط یک نفر خریداری شد.", time: "۳ دقیقه پیش", unread: true, icon: "🛒" },
  { id: 2, type: "like", title: "تعامل جدید", text: "سارا و ۳۲ نفر دیگر پستت را پسندیدند.", time: "۲۵ دقیقه پیش", unread: true, icon: "♥" },
  { id: 3, type: "follow", title: "دنبال‌کننده جدید", text: "محمدرضا تو را دنبال کرد.", time: "۱ ساعت پیش", unread: true, icon: "＋" },
  { id: 4, type: "comment", title: "پاسخ جدید", text: "«این ایده برای فروشنده‌های کوچک عالیه»", time: "۲ ساعت پیش", unread: false, icon: "◌" },
  { id: 5, type: "system", title: "گزارش هفتگی آماده است", text: "نرخ تبدیل فروشگاهت ۱۸٪ بهتر شده است.", time: "دیروز", unread: false, icon: "◈" },
];

export const categories = ["همه", "هوش مصنوعی", "طراحی", "آموزش", "محتوا", "اتوماسیون", "کریپتو", "ابزار", "برندینگ"];

export const creators = [
  { name: "KIA Studio", handle: "@kia", followers: "۱۲.۸K", sales: "۳۴۲", tone: "mint", initials: "K" },
  { name: "Hadi AI", handle: "@hadi", followers: "۸.۴K", sales: "۲۴۱", tone: "blue", initials: "H" },
  { name: "Mitra Motion", handle: "@mitra", followers: "۶.۲K", sales: "۱۶۸", tone: "orange", initials: "M" },
  { name: "Atlas Research", handle: "@atlas", followers: "۴.۹K", sales: "۹۲", tone: "violet", initials: "A" },
];

export const featureGroups = [
  { title: "Social graph", color: "mint", items: ["For You feed", "Following feed", "Trending posts", "Text posts", "Image posts", "Video posts", "Carousels", "Polls", "Questions", "Threads", "Replies", "Nested replies", "Reposts", "Quote reposts", "Mentions", "Hashtags", "Bookmarks", "Share links", "Stories", "Story viewer", "Story replies", "Reels feed", "Watch time", "Creator profiles", "Verified badges"] },
  { title: "Commerce engine", color: "violet", items: ["Marketplace", "Product detail", "Digital products", "Physical products", "Services", "Product variants", "Inventory", "SKU tracking", "Cart", "Multi-seller cart", "Checkout", "Order timeline", "Digital entitlements", "Secure downloads", "Refunds", "Disputes", "Verified reviews", "Helpful votes", "Coupons", "Collections", "Seller storefront", "Store themes", "Featured products", "Product posts", "Product analytics"] },
  { title: "Creator economy", color: "blue", items: ["Creator dashboard", "Seller dashboard", "Affiliate links", "Affiliate attribution", "Campaigns", "Referral rewards", "Commission ledger", "Pending balance", "Wallet", "Withdrawals", "Revenue chart", "Conversion funnel", "Traffic sources", "Customer list", "Audience insights", "Creator tips", "Sponsored content", "Subscriptions", "Live commerce", "Community rooms", "Moderation queue", "Reports", "Admin controls", "Feature flags", "Audit trail"] },
  { title: "Platform layer", color: "orange", items: ["Telegram auth", "Theme detection", "Haptic feedback", "Deep links", "Share target", "Cloud storage", "Search suggestions", "Search history", "Category filters", "Price filters", "Notifications", "Notification preferences", "Read states", "Direct messages", "Product sharing", "Offline state", "Skeleton loading", "Optimistic UI", "Infinite scroll", "Cursor pagination", "Image optimization", "CDN-ready media", "AI recommendations", "Personal memory", "A2A automation"] },
];

export const allFeatures = featureGroups.flatMap((group) => group.items.map((name) => ({ name, group: group.title, color: group.color })));
