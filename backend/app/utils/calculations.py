"""Utility functions for calculations."""


def calculate_estimated_1rm(weight: float, reps: int | str) -> float:
    """
    Calculate estimated 1RM using the formula: (0.033 × reps × weight) + weight

    Args:
        weight: Weight lifted
        reps: Number of reps (can be string like "5+" or int)

    Returns:
        Estimated 1RM value
    """
    try:
        # Handle reps like "5+" by extracting the number
        if isinstance(reps, str):
            reps_num = int(reps.replace("+", ""))
        else:
            reps_num = int(reps)

        weight_num = float(weight)

        # Formula: (0.033 × reps × weight) + weight
        estimated_1rm = (0.033 * reps_num * weight_num) + weight_num
        return round(estimated_1rm, 1)
    except (ValueError, TypeError):
        return 0.0


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
            window_values = [
                v for v in values[max(0, i - window + 1):i + 1]
                if v is not None
            ]
            if window_values:
                ma.append(round(sum(window_values) / len(window_values), 2))
            else:
                ma.append(None)
    return ma
