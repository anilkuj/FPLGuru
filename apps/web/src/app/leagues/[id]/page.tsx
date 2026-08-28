import { StandingsView } from "./StandingsView";

export default async function LeaguePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <StandingsView leagueId={Number(id)} />;
}
