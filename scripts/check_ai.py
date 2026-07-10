"""
AI manuel kontrol scripti — terminalden çalıştır:
python scripts/check_ai.py
"""

import os
import sys


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print(
            "❌ GEMINI_API_KEY bulunamadı. Lütfen .env veya ortam değişkeni üzerinden tanımlayın."
        )
        return 1

    import google.genai as genai
    from google.genai import types

    # Test resmi bul
    test_images = [
        "static/item_pics/default.jpg",
        "static/profile_pics/default.jpg",
    ]

    resim_yolu = None
    for path in test_images:
        if os.path.exists(path):
            resim_yolu = path
            break

    if not resim_yolu:
        print("❌ Test için resim bulunamadı")
        return 1

    print(f"📷 Test resmi: {resim_yolu}")

    with open(resim_yolu, "rb") as f:
        image_bytes = f.read()

    print("🔄 AI'ye istek gönderiliyor...")

    try:
        print(f"🔑 API Key: {api_key[:20]}...")

        client = genai.Client(api_key=api_key)
        print("✅ Client oluşturuldu")

        # Mevcut modelleri listele
        print("📋 Mevcut modelleri listeliyorum...")
        models = client.models.list()
        for m in models:
            print(f"  - {m.name}")
        print()

        # Text part
        text_part = types.Part(
            text=(
                "Bu görseldeki nesneyi analiz et ve bir kategori seç: Mobilya, Elektronik, "
                "Giysi, Kitap, Spor, Oyun, Mutfak, Bahçe, Beyaz Eşya, Diğer. "
                'SADECE JSON formatında döndür: {"kategori": "seçilen kategori"}'
            )
        )

        # Image part
        image_part = types.Part(
            inline_data=types.Blob(data=image_bytes, mime_type="image/jpeg")
        )

        # Her modeli dene
        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
            try:
                print(f"🔄 {model_name} deneniyor...")
                result = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Content(
                            parts=[text_part, image_part]
                        )
                    ],
                )
                print(f"✅ AI Yanıtı ({model_name}): {result.text}")
                break
            except Exception as e:
                print(f"❌ {model_name} hatası: {type(e).__name__}: {str(e)[:100]}")
                continue

    except Exception as e:
        print(f"❌ HATA: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
