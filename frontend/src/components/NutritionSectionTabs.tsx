import { Utensils, Pill } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Nutrition section: what goes in — food and supplements.
 *
 * Its own nav item since Progress moved under Exercises and freed a slot on
 * the five-item mobile bar (ADR-0006). Body is now the body-composition page
 * alone. Defined once and rendered by both pages so the pair cannot drift.
 */
const NUTRITION_SECTION = [
    { path: "/supplements", label: "Supplements", icon: Pill },
    { path: "/food", label: "Food", icon: Utensils },
];

const NutritionSectionTabs = () => <SectionTabs tabs={NUTRITION_SECTION} />;

export default NutritionSectionTabs;
