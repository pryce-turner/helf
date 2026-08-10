import { Weight, Utensils, Pill } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Body section: composition and intake.
 *
 * They are one loop, not two features. `v_daily_summary.kcal_target` is a
 * Katch-McArdle RMR computed from the lean mass a DEXA scan measured, so
 * intake without the target is a number with nothing to compare it to, and the
 * target without intake is never used. Defined once and rendered by both pages
 * so the pair cannot drift.
 */
const BODY_SECTION = [
    { path: "/body-composition", label: "Composition", icon: Weight },
    { path: "/food", label: "Food", icon: Utensils },
    // The third tab is why `SectionTabs` takes a list. ADR-0006 predicted it:
    // "the next thing that belongs beside an existing page has somewhere to go
    // without touching the nav".
    { path: "/supplements", label: "Supplements", icon: Pill },
];

const BodySectionTabs = () => <SectionTabs tabs={BODY_SECTION} />;

export default BodySectionTabs;
