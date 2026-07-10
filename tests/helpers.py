"""Test yardımcıları."""


def kayit_form(**overrides):
    """Kayıt endpoint testleri için varsayılan form verisi."""
    data = {
        "ad": "Test",
        "soyad": "Kullanıcı",
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPass1",
        "password_tekrar": "TestPass1",
        "kullanim_kosullari": "on",
    }
    data.update(overrides)
    return data
