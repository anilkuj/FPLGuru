import {
  Bell,
  CalendarRange,
  Crown,
  Home,
  Radio,
  Swords,
  Trophy,
  Users,
  Wand2,
  Wrench,
} from "lucide-react";

export const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/squad", label: "Squad", icon: Users },
  { href: "/optimize", label: "Optimize", icon: Wand2 },
  { href: "/fdr", label: "Fixtures", icon: CalendarRange },
  { href: "/live", label: "Live", icon: Radio },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/leagues", label: "Leagues", icon: Trophy },
  { href: "/h2h", label: "H2H", icon: Swords },
  { href: "/captain", label: "Captain", icon: Crown },
  { href: "/alerts", label: "Alerts", icon: Bell },
] as const;
