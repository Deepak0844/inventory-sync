import { Button } from "./Button";

/** Empty, loading and error states live inside the block that has them, never full screen. */
export function BlockState(props: {
  kind: "empty" | "loading" | "error";
  message?: string;
  onRetry?: () => void;
}) {
  if (props.kind === "loading") {
    return (
      <div aria-busy="true" className="flex flex-col gap-2" data-testid="block-loading">
        <div className="h-4 w-1/3 rounded-control bg-active" />
        <div className="h-4 w-2/3 rounded-control bg-active" />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 py-4 text-body text-muted" role={props.kind === "error" ? "alert" : undefined}>
      <p>{props.message}</p>
      {props.kind === "error" && props.onRetry ? (
        <Button look="text" onClick={props.onRetry}>Retry</Button>
      ) : null}
    </div>
  );
}
