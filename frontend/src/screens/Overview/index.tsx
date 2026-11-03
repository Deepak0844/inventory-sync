import { BlockState } from "../../components/ui/BlockState";

export default function Overview() {
  return (
    <>
      <h1 className="mb-4 text-title font-semibold">Overview</h1>
      <BlockState kind="empty" message="This screen is coming." />
    </>
  );
}
