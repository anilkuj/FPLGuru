import {
  Bell,
  CalendarRange,
  Crown,
  Radio,
  Trophy,
  Wrench,
} from "lucide-react";
import Link from "next/link";

import { LinkTeamCard } from "./LinkTeamCard";
import { Button, Card } from "@/components/ui";

const FEATURES = [
  {
    href: "/fdr",
    icon: CalendarRange,
    title: "Fixture difficulty",
    body: "Platform FDR blending opponent strength with recent form, attack/defence split, 1–10 horizon.",
  },
  {
    href: "/live",
    icon: Radio,
    title: "GW Live",
    body: "Live points and a BPS-based bonus projection that updates during matches over SSE.",
  },
  {
    href: "/alerts",
    icon: Bell,
    title: "Smart alerts",
    body: "Ranked feed: availability changes, blank/double gameweeks, deadline reminders.",
  },
  {
    href: "/captain",
    icon: Crown,
    title: "AI captain",
    body: "Best captain from your XI and globally, by projected points, with a plain-English rationale.",
  },
  {
    href: "/leagues",
    icon: Trophy,
    title: "Leaderboard",
    body: "Your mini-leagues, weekly rank movement, standings search, overall-rank trend.",
  },
  {
    href: "/tools",
    icon: Wrench,
    title: "Free tools",
    body: "GW trends, template XI, DGW/BGW calendar, overpowered XI, xG snapshot.",
  },
] as const;

export default function Home() {
  return (
    <div className="space-y-10">
      <section className="pt-4">
        <p className="text-sm font-medium text-primary">FPLGuru</p>
        <h1 className="mt-2 max-w-2xl text-4xl font-semibold tracking-tight md:text-5xl">
          Your FPL edge, in one place.
        </h1>
        <p className="mt-3 max-w-xl text-fg-muted">
          Expected points, fixture difficulty, live scores, an AI captain and a smart alert
          feed — built on the official FPL data, free.
        </p>
        <div className="mt-5 flex gap-3">
          <Button asChild>
            <a href="#link">Link your team</a>
          </Button>
          <Button asChild variant="outline">
            <Link href="/tools">Explore the tools</Link>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ href, icon: Icon, title, body }) => (
          <Link key={href} href={href}>
            <Card className="h-full p-5 transition-colors hover:border-primary/40 hover:bg-surface-2">
              <div className="flex size-9 items-center justify-center rounded-md bg-primary/15 text-primary">
                <Icon className="size-5" />
              </div>
              <h3 className="mt-3 text-sm font-semibold tracking-tight">{title}</h3>
              <p className="mt-1 text-sm text-fg-muted">{body}</p>
            </Card>
          </Link>
        ))}
      </section>

      <section>
        <LinkTeamCard />
      </section>
    </div>
  );
}
