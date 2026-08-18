import type { UpcomingWorkout } from "./upcoming";

/** One set as it was logged, with whatever was written about it afterwards. */
export interface MobilityLoggedSet {
    exercise: string;
    weight: number | null;
    reps: number | null;
    time: string | null;
    comment: string | null;
    order: number;
    completed: boolean;
}

export interface MobilityLastSession {
    date: string;
    rationale: string;
    sets: MobilityLoggedSet[];
}

/**
 * The mobility tab's whole state, in one response.
 *
 * `ready` is the discriminator between the page's two states and is derived on
 * the server from whether a pending session has any items — there is no status
 * to fall out of step with the rows. `last_session` comes back in both states:
 * when nothing is pending it is what makes the empty state actionable, because
 * it carries the comments the next session gets written from.
 */
export interface MobilityPending {
    ready: boolean;
    items: UpcomingWorkout[];
    rationale: string | null;
    generated_at: string | null;
    last_session: MobilityLastSession | null;
}

/**
 * Whether one day was a mobility day.
 *
 * Derived on the server from the marker note rather than stored as a flag on
 * the day, for the same reason `ready` is derived — the marker *is* the fact,
 * and the agent reads the marked day back to write the next session from.
 * `rationale` is null both when the day is unmarked and when it was marked by
 * hand, since nothing was prescribed for it either way.
 */
export interface MobilityDay {
    date: string;
    is_mobility: boolean;
    rationale: string | null;
}

export interface MobilityTransferResponse {
    date: string;
    count: number;
    message: string;
}
