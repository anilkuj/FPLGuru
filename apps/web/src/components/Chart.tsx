"use client";

import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  YAxis,
} from "recharts";

/** Rank-history line — lower rank is better, so the Y axis is reversed. */
export function RankLine({ data }: { data: { gw: number; rank: number | null }[] }) {
  const pts = data.filter((d) => d.rank != null) as { gw: number; rank: number }[];
  if (pts.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={56}>
      <LineChart data={pts} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <YAxis hide reversed domain={["dataMin", "dataMax"]} />
        <Line
          type="monotone"
          dataKey="rank"
          stroke="var(--primary)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function MiniBars({ value, max = 5 }: { value: number; max?: number }) {
  return (
    <ResponsiveContainer width={64} height={20}>
      <BarChart data={[{ v: value }]} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
        <YAxis hide domain={[0, max]} />
        <Bar dataKey="v" fill="var(--primary)" radius={2} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
