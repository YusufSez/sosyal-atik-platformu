def _wrap_user_text(text):
    """Prompt injection riskini azaltmak için kullanıcı girdisini ayırır."""
    if not text:
        return "yok"
    cleaned = str(text).replace("<<<", "").replace(">>>", "")
    return f"<<<KULLANICI_GIRISI>>>\n{cleaned}\n<<<SON>>>"


def _metin_normalize(metin):
    from services.ai_moderation import _metin_normalize as _norm
    return _norm(metin)
