import { Icon } from "../components/Icon";

/** Stands in for a screen whose backend lands in a later plan week, so navigation can be exercised end to end. */
export function PlaceholderPage({ title, week }: { title: string; week: number }) {
  return (
    <section className="placeholder-page">
      <Icon name="clock" />
      <h2>{title}</h2>
      <p>Màn hình này sẽ được hoàn thiện ở tuần {week} của kế hoạch.</p>
    </section>
  );
}
