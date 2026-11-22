import { ListTodo, ScrollText } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Workouts section: the planned queue (with its program editor), and the
 * hand-built presets. Reads like Exercises/Progress and Supplements/Food.
 * Defined once and rendered by both pages so the pair cannot drift.
 */
const WORKOUT_SECTION = [
    { path: "/upcoming", label: "Upcoming", icon: ListTodo },
    { path: "/presets", label: "Preset", icon: ScrollText },
];

const WorkoutSectionTabs = () => <SectionTabs tabs={WORKOUT_SECTION} />;

export default WorkoutSectionTabs;
