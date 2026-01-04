def format_as_seconds(duration: float):
    if duration < 0.000001:  # Less than a microsecond
        return f"{duration:.9f}"
    elif duration < 0.001:   # Less than a millisecond
        return f"{duration:.6f}"
    else:
        return f"{duration:.3f}"