import { matchRoute } from "../app/routes";
import { AppShell } from "../components/AppShell";
import { NotFoundPage } from "./NotFoundPage";
import { PlaceholderPage } from "./PlaceholderPage";

export function WorkspacePage({ pathname }: { pathname: string }) {
  const matched = matchRoute(pathname);
  if (!matched) return <NotFoundPage />;
  const { meta } = matched;

  return (
    <AppShell pathname={pathname} pattern={meta.pattern} title={meta.title} eyebrow={meta.eyebrow} description={meta.description}>
      <PlaceholderPage title={meta.title} week={meta.week} />
    </AppShell>
  );
}
