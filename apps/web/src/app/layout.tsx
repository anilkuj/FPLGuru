import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { NavAlerts } from "./NavAlerts";
import { PwaSetup } from "./PwaSetup";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FPLGuru",
  description: "FPL tracking + predictive analytics",
  manifest: "/manifest.json",
};

export const viewport: Viewport = { themeColor: "#0b0f19" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <nav className="border-b px-6 py-3 text-sm flex gap-4">
          <a href="/" className="font-semibold">FPLGuru</a>
          <a href="/squad">Squad</a>
          <span className="text-gray-400">xP</span>
          <a href="/fdr">FDR</a>
          <a href="/live">Live</a>
          <NavAlerts />
          <PwaSetup />
        </nav>
        {children}
      </body>
    </html>
  );
}
