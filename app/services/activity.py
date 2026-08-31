# MET values (Metabolic Equivalent of Task) per activity + intensity
# Source: ACSM standards
MET_TABLE = {
    "rower": {"lekka": 3.5, "umiarkowana": 5.8, "intensywna": 8.5},
    "pływanie": {"lekka": 4.8, "umiarkowana": 7.0, "intensywna": 10.0},
    "bieganie": {"lekka": 5.0, "umiarkowana": 8.3, "intensywna": 12.0},
    "ćwiczenia siłowe": {"lekka": 3.0, "umiarkowana": 6.0, "intensywna": 8.0},
    "marsz szybki": {"lekka": 3.0, "umiarkowana": 4.0, "intensywna": 5.0},
}


def calculate_kcal(activity: str, intensity: str, duration_minutes: int, weight_kg: float) -> int:
    """kcal = MET × masa_kg × czas_h"""
    met = MET_TABLE.get(activity, {}).get(intensity, 5.0)
    duration_hours = duration_minutes / 60.0
    kcal = met * weight_kg * duration_hours
    return round(kcal)
