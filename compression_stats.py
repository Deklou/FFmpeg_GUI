"""Statistiques de compression calculées exclusivement sur des tailles réelles."""


def format_bytes(size):
    """Unités binaires affichées en français (Mo = 1024**2 octets)."""
    size = int(size)
    if size < 1024:
        return f"{size} o"
    if size < 1024**2:
        return f"{size / 1024:.1f} Ko"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} Mo"
    return f"{size / 1024**3:.2f} Go"


def reduction_percentage(input_bytes, output_bytes):
    """Pourcentage positif = réduction ; négatif = augmentation."""
    if input_bytes is None or int(input_bytes) <= 0 or output_bytes is None:
        return None
    return (1 - int(output_bytes) / int(input_bytes)) * 100


def calculate_summary(input_sizes, output_sizes):
    """output_sizes associe l'index de la ligne à sa taille de sortie confirmée."""
    inputs = [int(value) for value in input_sizes]
    known = {
        int(index): int(value)
        for index, value in output_sizes.items()
        if 0 <= int(index) < len(inputs) and value is not None
    }
    known_input = sum(inputs[index] for index in known)
    known_output = sum(known.values())
    return {
        "count": len(inputs),
        "total_input": sum(inputs),
        "known_count": len(known),
        "known_input": known_input,
        "known_output": known_output,
        "known_reduction": reduction_percentage(known_input, known_output),
    }
