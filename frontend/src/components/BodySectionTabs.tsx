import { Weight, Utensils } from "lucide-react";
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
];

const BodySectionTabs = () => <SectionTabs tabs={BODY_SECTION} />;

export default BodySectionTabs;
