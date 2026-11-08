import { FutureWorkspacePreview } from "@/components/common/FutureWorkspace";
import { PageHeader } from "@/components/common/PageHeader";

export default function ComingSoon({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <FutureWorkspacePreview />
    </div>
  );
}
