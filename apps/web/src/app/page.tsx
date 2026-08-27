import { fetchStatus } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default async function Home() {
  let asOf = "unknown";
  try {
    const s = await fetchStatus(API);
    asOf = s.sources.fpl_bootstrap?.as_of ?? "unknown";
  } catch {
    asOf = "unavailable";
  }
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">FPLGuru</h1>
      <p className="text-sm text-gray-500">FPL data as of {asOf}</p>
    </main>
  );
}
