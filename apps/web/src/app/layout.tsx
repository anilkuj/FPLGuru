import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

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
          <span className="text-gray-400">FDR</span>
          <span className="text-gray-400">Live</span>
        </nav>
        {children}
      </body>
    </html>
  );
}
