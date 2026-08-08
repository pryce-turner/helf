"""Utility functions for calculations."""


def calculate_estimated_1rm(weight: float, reps: int) -> float:
    """
    Calculate estimated 1RM using the Epley formula: (0.033 × reps × weight) + weight

    Args:
        weight: Weight lifted
        reps: Number of reps

    Returns:
        Estimated 1RM value

    Raises:
        TypeError: if either argument is None or not a number.

    Deliberately unguarded. This used to return 0.0 for unusable input, which put
    a fake data point on the progression chart that was indistinguishable from a
    genuine measurement of zero. Callers must skip rows with a missing weight or
    reps before calling - all three already do.
    """
    return round((0.033 * reps * weight) + weight, 1)


def calculate_moving_average(values: list[float | None], window: int = 7) -> list[float | None]:
    """
    Calculate moving average with given window size.

    Args:
        values: List of values (None values are skipped)
        window: Window size for moving average

    Returns:
        List of moving average values
    """
    ma = []
    for i in range(len(values)):
        if values[i] is None:
            ma.append(None)
        else:
            # Get window of valid values
            window_values = [v for v in values[max(0, i - window + 1) : i + 1] if v is not None]
            if window_values:
                ma.append(round(sum(window_values) / len(window_values), 2))
            else:
                ma.append(None)
    return ma
