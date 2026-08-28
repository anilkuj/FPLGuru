import { StandingsView } from "./StandingsView";

export default async function LeaguePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">League standings</h1>
      <StandingsView leagueId={Number(id)} />
    </main>
  );
}
