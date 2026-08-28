"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import { cn } from "@/lib/utils";

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  className?: string;
  value?: (row: T) => string | number;
  render?: (row: T) => React.ReactNode;
};

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  initialSort,
  rowKey,
  emptyTitle = "Nothing to show",
  emptyHint,
}: {
  columns: Column<T>[];
  rows: T[];
  initialSort?: { key: string; dir: "asc" | "desc" };
  rowKey: (row: T, i: number) => string | number;
  emptyTitle?: string;
  emptyHint?: string;
}) {
  const [sort, setSort] = useState(initialSort);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const get = col.value ?? ((r: T) => r[sort.key] as string | number);
    return [...rows].sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      const c = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? c : -c;
    });
  }, [rows, sort, columns]);

  if (rows.length === 0) return <EmptyState title={emptyTitle} hint={emptyHint} />;

  const alignCls = (a?: string) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {columns.map((c) => (
            <TableHead
              key={c.key}
              className={cn(alignCls(c.align), c.sortable && "cursor-pointer select-none", c.className)}
              onClick={() =>
                c.sortable &&
                setSort((s) =>
                  s?.key === c.key
                    ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" }
                    : { key: c.key, dir: "desc" },
                )
              }
            >
              {c.header}
              {sort?.key === c.key && (sort.dir === "asc" ? " ▲" : " ▼")}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((row, i) => (
          <TableRow key={rowKey(row, i)}>
            {columns.map((c) => (
              <TableCell key={c.key} className={cn(alignCls(c.align), c.className)}>
                {c.render ? c.render(row) : String((c.value ?? ((r: T) => r[c.key]))(row) ?? "")}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
