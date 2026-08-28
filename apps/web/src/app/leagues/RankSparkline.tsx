import type { RankPoint } from "@/lib/api";

export function RankSparkline({
  points,
  width = 240,
  height = 40,
}: {
  points: RankPoint[];
  width?: number;
  height?: number;
}) {
  const vals = points.map((p) => p.overall_rank).filter((r): r is number => r != null);
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  // lower rank = better = higher on the chart
  const d = vals
    .map((r, i) => {
      const x = (i / (vals.length - 1)) * (width - 2) + 1;
      const y = ((r - min) / span) * (height - 2) + 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="text-sky-400" aria-label="overall rank trend">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
