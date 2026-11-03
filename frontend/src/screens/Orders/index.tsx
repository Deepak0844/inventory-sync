import { BlockState } from "../../components/ui/BlockState";

export default function Orders() {
  return (
    <>
      <h1 className="mb-4 text-title font-semibold">Orders</h1>
      <BlockState kind="empty" message="This screen is coming." />
    </>
  );
}
