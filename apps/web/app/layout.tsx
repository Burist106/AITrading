import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Aurum Console · DEMO ONLY",
    template: "%s · Aurum Console",
  },
  description: "หน้าจอวิจัย XAU/USD แบบอ่านอย่างเดียวในโหมด SHADOW",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="th" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
