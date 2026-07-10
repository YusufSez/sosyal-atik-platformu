from constants import DEFAULT_LAT, DEFAULT_LNG


def parse_coordinates(lat_raw, lng_raw, user=None):
    try:
        lat = float(lat_raw) if lat_raw not in (None, "") else None
        lng = float(lng_raw) if lng_raw not in (None, "") else None
    except (TypeError, ValueError):
        lat, lng = None, None

    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng, False

    if user and getattr(user, "latitude", None) is not None and getattr(user, "longitude", None) is not None:
        return user.latitude, user.longitude, False

    return DEFAULT_LAT, DEFAULT_LNG, True


def is_varsayilan_konum(lat, lng, epsilon=0.001):
    """Koordinatların varsayılan İstanbul merkezine denk gelip gelmediğini kontrol eder."""
    if lat is None or lng is None:
        return True
    return abs(lat - DEFAULT_LAT) < epsilon and abs(lng - DEFAULT_LNG) < epsilon


def harita_noktalari(ilanlar):
    """Haritada gösterilecek ilanları gruplar; varsayılan konumdakileri hariç tutar."""
    gruplar = {}
    konumsuz = 0
    for ilan in ilanlar:
        if is_varsayilan_konum(ilan.latitude, ilan.longitude):
            konumsuz += 1
            continue
        anahtar = f"{round(ilan.latitude, 5)}:{round(ilan.longitude, 5)}"
        gruplar.setdefault(anahtar, []).append({
            "id": ilan.id,
            "baslik": ilan.baslik,
            "lat": ilan.latitude,
            "lng": ilan.longitude,
        })

    noktalar = []
    for grup in gruplar.values():
        noktalar.append({
            "lat": grup[0]["lat"],
            "lng": grup[0]["lng"],
            "ilanlar": grup,
        })
    return noktalar, konumsuz


def mesafe_hesapla(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
