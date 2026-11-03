import { BlockState } from "../../components/ui/BlockState";

export default function Notifications() {
  return (
    <>
      <h1 className="mb-4 text-title font-semibold">Notifications</h1>
      <BlockState kind="empty" message="This screen is coming." />
    </>
  );
}
