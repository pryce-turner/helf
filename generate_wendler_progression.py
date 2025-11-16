#!/usr/bin/env python3
"""
Wendler 5/3/1 Progression Generator

Generates a complete CSV file with Wendler 5/3/1 progression for multiple cycles.
Allows setting target 1RMs and automatically calculates progression until targets are reached.
"""

import csv


def calculate_weights(max_weight, week):
    """
    Calculate weights for a given 1RM and week in Wendler 5/3/1 program.

    Args:
        max_weight: Current 1RM for the lift
        week: Week number (1-4)

    Returns:
        List of tuples (weight, reps) for each set
    """
    percentages = {
        1: [(0.65, 5), (0.75, 5), (0.85, '5+')],
        2: [(0.70, 3), (0.80, 3), (0.90, '3+')],
        3: [(0.75, 5), (0.85, 3), (0.95, '1+')],
        4: [(0.40, 5), (0.50, 5), (0.60, 5)]  # Deload
    }

    weights = []
    for pct, reps in percentages[week]:
        weight = max_weight * pct
        # Round to nearest 5
        weight = round(weight / 5) * 5
        # If ends in 0, subtract 5 (no 2.5 lb plates available)
        if weight % 10 == 0:
            weight -= 5
        weights.append((int(weight), reps))

    return weights


def generate_progression(
    starting_squat=335,
    starting_bench=295,
    starting_deadlift=385,
    target_squat=405,
    target_bench=315,
    target_deadlift=495,
    output_file='upcoming_workouts.csv'
):
    """
    Generate complete Wendler 5/3/1 progression CSV.

    Args:
        starting_squat: Starting 1RM for squat
        starting_bench: Starting 1RM for bench
        starting_deadlift: Starting 1RM for deadlift
        target_squat: Target 1RM for squat
        target_bench: Target 1RM for bench
        target_deadlift: Target 1RM for deadlift
        output_file: Path to output CSV file
    """
    # Calculate number of cycles needed
    squat_cycles = (target_squat - starting_squat) // 10 + 1
    bench_cycles = (target_bench - starting_bench) // 5 + 1
    deadlift_cycles = (target_deadlift - starting_deadlift) // 10 + 1

    num_cycles = max(squat_cycles, bench_cycles, deadlift_cycles)

    # Define progression for each cycle
    cycles = []
    for i in range(num_cycles):
        squat_max = min(starting_squat + i * 10, target_squat)
        bench_max = min(starting_bench + i * 5, target_bench)
        deadlift_max = min(starting_deadlift + i * 10, target_deadlift)
        cycles.append({
            'squat': squat_max,
            'bench': bench_max,
            'deadlift': deadlift_max
        })

    # Build CSV content
    rows = []
    session_num = 1

    for cycle_idx, cycle in enumerate(cycles):
        for week in range(1, 5):
            # Day 1 - Squat
            squat_weights = calculate_weights(cycle['squat'], week)
            week_label = f"Week {week}" if week < 4 else "Week 4 Deload"

            for set_idx, (weight, reps) in enumerate(squat_weights, 1):
                amrap_note = " AMRAP" if '+' in str(reps) else ""
                rows.append([
                    session_num, 'Barbell Squat', 'Legs', weight, 'lbs', reps,
                    '', '', '', f'{week_label} - Set {set_idx}{amrap_note}'
                ])
            rows.append([session_num, 'Pull Up', 'Back', 0, 'lbs', '', '', '', '', 'Bodyweight'])
            rows.append([session_num, 'Incline Dumbbell Press', 'Chest', '', '', '', '', '', '', ''])
            rows.append([session_num, 'Decline Crunch', 'Core', '', '', '', '', '', '', ''])
            session_num += 1

            # Day 2 - Bench
            bench_weights = calculate_weights(cycle['bench'], week)
            for set_idx, (weight, reps) in enumerate(bench_weights, 1):
                amrap_note = " AMRAP" if '+' in str(reps) else ""
                rows.append([
                    session_num, 'Flat Barbell Bench Press', 'Chest', weight, 'lbs', reps,
                    '', '', '', f'{week_label} - Set {set_idx}{amrap_note}'
                ])
            rows.append([session_num, 'Front Squat', 'Legs', '', '', '', '', '', '', ''])
            rows.append([session_num, 'Dumbbell Row', 'Back', '', '', '', '', '', '', ''])
            rows.append([session_num, 'Landmines', 'Core', '', '', '', '', '', '', ''])
            session_num += 1

            # Day 3 - Deadlift
            deadlift_weights = calculate_weights(cycle['deadlift'], week)
            for set_idx, (weight, reps) in enumerate(deadlift_weights, 1):
                amrap_note = " AMRAP" if '+' in str(reps) else ""
                rows.append([
                    session_num, 'Deadlift', 'Back', weight, 'lbs', reps,
                    '', '', '', f'{week_label} - Set {set_idx}{amrap_note}'
                ])
            rows.append([session_num, 'Parallel Bar Triceps Dip', 'Chest', 0, 'lbs', '', '', '', '', 'Bodyweight'])
            rows.append([session_num, 'Bulgarian Split Squat', 'Legs', '', '', '', '', '', '', ''])
            rows.append([session_num, 'Cable side bend', 'Core', '', '', '', '', '', '', ''])
            session_num += 1

    # Write to file
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Session', 'Exercise', 'Category', 'Weight', 'Weight Unit',
            'Reps', 'Distance', 'Distance Unit', 'Time', 'Comment'
        ])
        writer.writerows(rows)

    # Print summary
    print(f"Generated {session_num - 1} sessions across {len(cycles)} cycles")
    print(f"Output written to: {output_file}")
    print(f"\nProgression summary:")
    for i, cycle in enumerate(cycles, 1):
        print(f"Cycle {i:2d}: Squat {cycle['squat']}, Bench {cycle['bench']}, Deadlift {cycle['deadlift']}")


if __name__ == '__main__':
    # Generate progression with default values
    generate_progression()
