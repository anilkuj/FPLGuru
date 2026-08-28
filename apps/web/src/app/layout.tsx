import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppShell } from "@/components/AppShell";
import { Providers } from "@/components/providers";
import { PwaSetup } from "./PwaSetup";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FPLGuru — your FPL edge",
  description: "Fantasy Premier League analytics: xP, FDR, live scores, AI captain, alerts.",
  manifest: "/manifest.json",
};

export const viewport: Viewport = { themeColor: "#0b0e14" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} antialiased`}
    >
      <body className="min-h-dvh bg-bg text-fg">
        <Providers>
          <AppShell>{children}</AppShell>
          <PwaSetup />
        </Providers>
      </body>
    </html>
  );
}
