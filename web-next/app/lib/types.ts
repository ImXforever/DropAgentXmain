export type NavKey =
  | "home"
  | "explore"
  | "shop"
  | "create"
  | "activity"
  | "profile"
  | "messages"
  | "wallet"
  | "orders"
  | "saved"
  | "collections"
  | "analytics"
  | "settings"
  | "admin"
  | "features";

export type Product = {
  id: number;
  title: string;
  category: string;
  price: number;
  oldPrice?: number;
  rating: number;
  sales: number;
  seller: string;
  sellerHandle: string;
  icon: string;
  tone: string;
  badge?: string;
};

export type Post = {
  id: number;
  author: string;
  handle: string;
  initials: string;
  tone: string;
  time: string;
  text: string;
  tags: string[];
  likes: number;
  comments: number;
  reposts: number;
  productId?: number;
  liked?: boolean;
  saved?: boolean;
};

export type Notification = {
  id: number;
  type: "like" | "sale" | "follow" | "comment" | "system";
  title: string;
  text: string;
  time: string;
  unread: boolean;
  icon: string;
};
