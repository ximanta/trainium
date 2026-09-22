export default function TrainiumAdminPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-2xl font-semibold">Admin</h1>
      <p className="mt-2 text-muted-foreground">
        Upload material and configure personas here. This route is reserved for the
        admin role. When Auth0 lands, this route group is where the role check gets
        enforced.
      </p>
    </main>
  );
}
