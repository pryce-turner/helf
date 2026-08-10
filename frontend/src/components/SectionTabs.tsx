import { Link, useLocation } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

export interface SectionTab {
    path: string;
    label: string;
    icon: LucideIcon;
}

/**
 * A strip of sibling routes that share one nav entry.
 *
 * Exists because the mobile bottom bar is full at five items and Food would
 * have been the sixth — see
 * `docs/decisions/0006-food-is-a-tab-under-body-not-a-sixth-nav-item.md`.
 * Each tab keeps its own URL, so a tab is bookmarkable and installable as a
 * home-screen shortcut; the section is a grouping in the navigation, not a
 * single page with internal state.
 */
const SectionTabs = ({ tabs }: { tabs: SectionTab[] }) => {
    const { pathname } = useLocation();

    return (
        <div className="section-tabs animate-in" role="tablist">
            {tabs.map(({ path, label, icon: Icon }) => {
                const active = pathname === path || pathname.startsWith(`${path}/`);
                return (
                    <Link
                        key={path}
                        to={path}
                        role="tab"
                        aria-selected={active}
                        className={`section-tab ${active ? "section-tab--active" : ""}`}
                    >
                        <Icon style={{ width: "15px", height: "15px" }} />
                        {label}
                    </Link>
                );
            })}
        </div>
    );
};

export default SectionTabs;
