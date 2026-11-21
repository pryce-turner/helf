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
    /** Null for a session the user flagged by hand: nothing prescribed it. */
    rationale: string | null;
    sets: MobilityLoggedSet[];
}
