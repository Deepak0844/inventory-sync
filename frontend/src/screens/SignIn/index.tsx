import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { useLoginMutation } from "../../api/api";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";

const schema = z.object({
  username: z.string().min(1, "Enter your username"),
  password: z.string().min(1, "Enter your password"),
  totp: z.string().regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator"),
});
type Values = z.infer<typeof schema>;

export default function SignIn() {
  const navigate = useNavigate();
  const [login, { isLoading, isError }] = useLoginMutation();
  const { register, handleSubmit, formState: { errors } } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = (values: Values) => login(values).unwrap().then(() => navigate("/", { replace: true })).catch(() => {});

  return (
    <div className="flex min-h-full items-center justify-center bg-ground p-4">
      <form onSubmit={handleSubmit(onSubmit)} className="flex w-full max-w-sm flex-col gap-4 rounded-sheet border bg-surface p-pad">
        <h1 className="text-title font-semibold">Sign in</h1>
        <TextField label="Username" autoComplete="username" error={errors.username?.message} {...register("username")} />
        <TextField label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
        <TextField label="Code" inputMode="numeric" autoComplete="one-time-code" error={errors.totp?.message} {...register("totp")} />
        {isError ? <p role="alert" className="text-small text-negative">Sign in failed</p> : null}
        <Button type="submit" disabled={isLoading}>Sign in</Button>
      </form>
    </div>
  );
}
