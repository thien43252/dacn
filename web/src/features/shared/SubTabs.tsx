/**
 * Sub-tabs inside one sidebar route.
 *
 * The active tab lives in the query string, so a sub-screen is linkable, survives a refresh and works with
 * the browser back button instead of being lost in component state.
 */

import type { ReactNode } from "react";

import { navigate, useLocation } from "../../app/router";

export interface SubTab {
  id: string;
  label: string;
  /** One line under the tab row explaining what the open sub-screen does. */
  description?: string;
  /** Items waiting on this tab, shown as a red count; absent or zero shows nothing. */
  badge?: number | null;
  render: () => ReactNode;
}

interface SubTabsProps {
  tabs: SubTab[];
  ariaLabel: string;
  /** Query parameter that carries the active tab. */
  param?: string;
  /** Prefix of the tab/panel DOM IDs; nested tab rows need their own so `aria-controls` stays unique. */
  idPrefix?: string;
  /** Stable `data-guide` name so the onboarding guide can point at the tab row. */
  guide?: string;
}

export function SubTabs({ tabs, ariaLabel, param = "tab", idPrefix = "subtab", guide }: SubTabsProps) {
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const requested = params.get(param);
  const active = tabs.find((tab) => tab.id === requested) ?? tabs[0];

  function open(id: string) {
    const next = new URLSearchParams(search);
    if (id === tabs[0].id) {
      next.delete(param);
    } else {
      next.set(param, id);
    }
    const query = next.toString();
    navigate(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <div className="subtabs">
      <div aria-label={ariaLabel} className="subtabs__bar" role="tablist" data-guide={guide}>
        {tabs.map((tab) => (
          <button
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            aria-describedby={tab.badge != null && tab.badge > 0 ? `${idPrefix}-${tab.id}-badge` : undefined}
            aria-selected={tab.id === active.id}
            className={tab.id === active.id ? "subtabs__tab is-active" : "subtabs__tab"}
            id={`${idPrefix}-${tab.id}`}
            key={tab.id}
            onClick={() => open(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
            {/* Hidden from the tab's name (tests and readers find the tab by its label) but read as its description. */}
            {tab.badge != null && tab.badge > 0 && (
              <em className="subtabs__badge" id={`${idPrefix}-${tab.id}-badge`} aria-hidden="true">
                {tab.badge > 99 ? "99+" : tab.badge}
                <span className="visually-hidden"> mục đang chờ</span>
              </em>
            )}
          </button>
        ))}
      </div>

      {active.description && <p className="subtabs__lead">{active.description}</p>}

      <div
        aria-labelledby={`${idPrefix}-${active.id}`}
        className="subtabs__panel"
        id={`${idPrefix}-panel-${active.id}`}
        role="tabpanel"
      >
        {active.render()}
      </div>
    </div>
  );
}
