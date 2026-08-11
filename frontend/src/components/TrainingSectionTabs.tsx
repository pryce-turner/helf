import { ListTodo, Activity } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Upcoming section: planned lifting, and planned mobility.
 *
 * Both are prescriptions waiting to be copied onto a date — the same table,
 * even — but they are written by different authors. A lifting program comes
 * from a Liftoscript script the user edits; a mobility session is written one
 * at a time by the agent from the last session's feedback. Two tabs rather
 * than one page because the second has no editor and the first has no
 * rationale to read.
 *
 * A tab and not a sixth nav item: the mobile bar is full at five
 * (`docs/decisions/0006-food-is-a-tab-under-body-not-a-sixth-nav-item.md`).
 */
const TRAINING_SECTION = [
    { path: "/upcoming", label: "Lifting", icon: ListTodo },
    { path: "/mobility", label: "Mobility", icon: Activity },
];

const TrainingSectionTabs = () => <SectionTabs tabs={TRAINING_SECTION} />;

export default TrainingSectionTabs;
