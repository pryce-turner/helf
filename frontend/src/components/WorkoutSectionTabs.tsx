import { ListTodo, Library } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Workouts section: the planned queue (with its program editor), and the
 * library of programs and blocks it is generated from (plan 0022). Reads like
 * Exercises/Progress and Supplements/Food; defined once for both pages.
 */
const WORKOUT_SECTION = [
    { path: "/upcoming", label: "Upcoming", icon: ListTodo },
    { path: "/library", label: "Library", icon: Library },
];

const WorkoutSectionTabs = () => <SectionTabs tabs={WORKOUT_SECTION} />;

export default WorkoutSectionTabs;
