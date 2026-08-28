import {
  Bell,
  CalendarRange,
  Crown,
  Home,
  Radio,
  Trophy,
  Users,
  Wrench,
} from "lucide-react";

export const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/squad", label: "Squad", icon: Users },
  { href: "/fdr", label: "Fixtures", icon: CalendarRange },
  { href: "/live", label: "Live", icon: Radio },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/leagues", label: "Leagues", icon: Trophy },
  { href: "/captain", label: "Captain", icon: Crown },
  { href: "/alerts", label: "Alerts", icon: Bell },
] as const;
