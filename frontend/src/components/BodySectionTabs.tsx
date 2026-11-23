import { Watch, Weight } from "lucide-react";
import SectionTabs from "./SectionTabs";

/**
 * The Body section: what the instruments measure — the scale and DEXA on one
 * tab, the watch on the other. A tab rather than a sixth nav item (ADR-0006).
 * Defined once and rendered by both pages so the pair cannot drift.
 */
const BODY_SECTION = [
    { path: "/body-composition", label: "Composition", icon: Weight },
    { path: "/watch", label: "Watch", icon: Watch },
];

const BodySectionTabs = () => <SectionTabs tabs={BODY_SECTION} />;

export default BodySectionTabs;
