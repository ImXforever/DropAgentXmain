import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DropAgentX — Social Commerce OS",
  description: "A creator-first social commerce experience for Telegram and the open web.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
