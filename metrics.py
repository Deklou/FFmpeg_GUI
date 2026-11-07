"""Calculs et formats des statistiques de compression et des durées."""
import math
def format_bytes(size):
    """Unités binaires affichées en français (Mo = 1024**2 octets)."""
    size = int(size)
    if size < 1024:
        return f'{size} o'
    if size < 1024 ** 2:
        return f'{size / 1024:.1f} Ko'
    if size < 1024 ** 3:
        return f'{size / 1024 ** 2:.1f} Mo'
    return f'{size / 1024 ** 3:.2f} Go'

def reduction_percentage(input_bytes, output_bytes):
    """Pourcentage positif = réduction ; négatif = augmentation."""
    if input_bytes is None or int(input_bytes) <= 0 or output_bytes is None:
        return None
    return (1 - int(output_bytes) / int(input_bytes)) * 100

def calculate_summary(input_sizes, output_sizes):
    """output_sizes associe l'index de la ligne à sa taille de sortie confirmée."""
    inputs = [int(value) for value in input_sizes]
    known = {int(index): int(value) for index, value in output_sizes.items() if 0 <= int(index) < len(inputs) and value is not None}
    known_input = sum((inputs[index] for index in known))
    known_output = sum(known.values())
    return {'count': len(inputs), 'total_input': sum(inputs), 'known_count': len(known), 'known_input': known_input, 'known_output': known_output, 'known_reduction': reduction_percentage(known_input, known_output)}

def format_duration(seconds):
    if seconds is None or seconds < 0 or (not math.isfinite(seconds)):
        return '—'
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

def parse_speed(value):
    """Convertit speed=1.27x ; valeur inconnue -> None."""
    try:
        speed = float(value.strip().removesuffix('x'))
    except (AttributeError, TypeError, ValueError):
        return None
    return speed if math.isfinite(speed) and speed > 0 else None

def parse_out_time(data):
    """FFmpeg renvoie un temps en microsecondes malgré la clé historique *_ms."""
    for key in ('out_time_us', 'out_time_ms'):
        if key in data:
            try:
                value = float(data[key]) / 1000000
                return value if math.isfinite(value) and value >= 0 else None
            except (TypeError, ValueError):
                pass
    text = data.get('out_time')
    if not text:
        return None
    try:
        hours, minutes, seconds = text.split(':')
        result = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None

def estimate_remaining(duration, out_time, speed):
    if duration is None or out_time is None or speed is None or (speed <= 0):
        return None
    return max(0.0, (duration - out_time) / speed)

def format_reduction(value):
    """Pas de signe + pour une réduction ; signe - si le fichier grossit."""
    if value is None:
        return '—'
    return f'{value:.1f} %'
