"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { NAV_ITEMS } from "@/components/nav-items";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  Button,
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui";
import { getAlerts } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 px-2 py-1">
      <span className="h-2.5 w-2.5 rounded-full bg-primary shadow-[0_0_12px] shadow-primary/60" />
      <span className="text-sm font-semibold tracking-tight">FPLGuru</span>
    </Link>
  );
}

function NavList({ unseen, onNavigate }: { unseen: number; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active
                ? "bg-primary/10 text-fg"
                : "text-fg-muted hover:bg-surface-2 hover:text-fg",
            )}
          >
            {active && (
              <span className="absolute left-0 top-1.5 h-[calc(100%-0.75rem)] w-0.5 rounded-full bg-primary" />
            )}
            <Icon className="size-4 shrink-0" />
            <span className="flex-1">{label}</span>
            {label === "Alerts" && unseen > 0 && (
              <span className="rounded-full bg-danger px-1.5 text-xs font-medium text-white">
                {unseen}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [unseen, setUnseen] = useState(0);
  const [entryId, setEntryId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const id = getStoredEntryId();
    setEntryId(id);
    if (id == null) return;
    const tick = () =>
      getAlerts(API, id)
        .then((f) => setUnseen(f.unseen))
        .catch(() => undefined);
    tick();
    const t = setInterval(tick, 60000);
    return () => clearInterval(t);
  }, []);

  const pageLabel =
    NAV_ITEMS.find((n) =>
      n.href === "/" ? pathname === "/" : pathname.startsWith(n.href),
    )?.label ?? "";

  return (
    <div className="min-h-dvh md:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-border bg-surface md:flex">
        <div className="p-3">
          <Logo />
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <NavList unseen={unseen} />
        </div>
        <div className="flex items-center justify-between border-t border-border p-3">
          <span className="text-xs text-fg-muted">v0.1</span>
          <ThemeToggle />
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur md:px-8">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Menu">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <div className="mb-3">
              <Logo />
            </div>
            <NavList unseen={unseen} onNavigate={() => setOpen(false)} />
            <div className="mt-4 border-t border-border pt-3">
              <SheetClose asChild>
                <ThemeToggle />
              </SheetClose>
            </div>
          </SheetContent>
        </Sheet>

        <span className="text-sm font-medium tracking-tight">{pageLabel}</span>

        <div className="ml-auto">
          {entryId == null ? (
            <Button asChild size="sm" variant="outline">
              <Link href="/">Link team</Link>
            </Button>
          ) : (
            <Button asChild size="sm" variant="ghost">
              <Link href="/squad">Team #{entryId}</Link>
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8">{children}</main>
    </div>
  );
}
