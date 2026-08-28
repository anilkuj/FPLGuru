import { PageHeader } from "@/components/PageHeader";
import { ToolsHub } from "./ToolsHub";

export default function ToolsPage() {
  return (
    <>
      <PageHeader
        title="Free tools"
        description="Everything below is computed from the live FPL data — no login."
      />
      <ToolsHub />
    </>
  );
}
