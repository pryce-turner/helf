import { Dumbbell, TrendingUp } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Exercises section: the catalog, and progress on it.
 *
 * Progress was a nav item of its own; it moved here to free the slot that
 * Nutrition (Food + Supplements) now holds — the mobile bar is full at five
 * (`docs/decisions/0006-food-is-a-tab-under-body-not-a-sixth-nav-item.md`).
 */
const EXERCISE_SECTION = [
    { path: "/exercises", label: "Exercises", icon: Dumbbell },
    { path: "/progression", label: "Progress", icon: TrendingUp },
];

const ExerciseSectionTabs = () => <SectionTabs tabs={EXERCISE_SECTION} />;

export default ExerciseSectionTabs;
