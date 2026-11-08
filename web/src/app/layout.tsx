import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Equity Research",
  description: "Evidence-first research for NSE and BSE listed companies",
};

const NAV = [
  { href: "/", label: "Stocks" },
  { href: "/options/desk", label: "Trade desk" },
  { href: "/options", label: "Options lab" },
  { href: "/runs", label: "Saved" },
  { href: "/sources", label: "Data sources" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
            <Link href="/" className="flex items-center gap-2 font-black tracking-tight">
              <span className="h-3 w-3 rounded-full bg-cyan" style={{ boxShadow: "0 0 4px var(--neon-cyan), 0 0 3px var(--neon-purple)" }} />
              <span className="bg-gradient-to-r from-cyan to-purple bg-clip-text text-transparent">EQUITY·RESEARCH</span>
            </Link>
            <nav className="flex gap-1 text-sm font-semibold">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="rounded-full px-3 py-1 text-muted transition hover:bg-cyan-bg hover:text-cyan">
                  {n.label}
                </Link>
              ))}
            </nav>
            <span className="ml-auto rounded-full border border-purple/40 bg-purple-bg px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-purple">
              Research only
            </span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t border-line/70 py-4 text-center text-[11px] text-faint">
          Not investment advice · development build on unlicensed, delayed data · no orders are placed
        </footer>
      </body>
    </html>
  );
}
