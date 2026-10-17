import { PageHeader } from "../components/Layout";

export function Placeholder({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <p className="text-zinc-400">Připravuje se.</p>
    </>
  );
}
