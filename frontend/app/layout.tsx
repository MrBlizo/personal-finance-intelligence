import type { Metadata } from "next";
import { ReactNode } from "react";
import AppFrame from "@/components/AppFrame";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personal Finance Intelligence",
  description: "Track, forecast and analyse your personal finances.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body><AppFrame>{children}</AppFrame></body>
    </html>
  );
}
