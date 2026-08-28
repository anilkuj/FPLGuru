export function Delta({ value, invert = false }: { value: number | null; invert?: boolean }) {
  if (value == null || value === 0) return <span className="text-fg-muted">–</span>;
  const good = invert ? value < 0 : value > 0;
  const mag = Math.abs(value).toLocaleString();
  return (
    <span className={good ? "text-positive" : "text-danger"}>
      {good ? "▲" : "▼"} {mag}
    </span>
  );
}
