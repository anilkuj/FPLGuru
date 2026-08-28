import { AlertFeed } from "./AlertFeed";
import { PushToggle } from "./PushToggle";

export default function AlertsPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Alerts</h1>
      <PushToggle />
      <AlertFeed />
    </main>
  );
}
