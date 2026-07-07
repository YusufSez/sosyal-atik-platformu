"""Kurumsal sayfa içerikleri ve footer bağlantıları."""

FOOTER_COLUMNS = [
    {
        "baslik": "Kurumsal",
        "linkler": [
            {"etiket": "Hakkımızda", "endpoint": "main.kurumsal_sayfa", "slug": "hakkimizda"},
            {"etiket": "Vizyon & Misyon", "endpoint": "main.kurumsal_sayfa", "slug": "vizyon-misyon"},
            {"etiket": "Hedeflerimiz", "endpoint": "main.kurumsal_sayfa", "slug": "hedeflerimiz"},
            {"etiket": "Sürdürülebilirlik", "endpoint": "main.kurumsal_sayfa", "slug": "surdurulebilirlik"},
            {"etiket": "Çevresel Etki Metodolojisi", "endpoint": "impact.metodoloji"},
            {"etiket": "Haberler", "endpoint": "main.kurumsal_sayfa", "slug": "haberler"},
            {"etiket": "Site Haritası", "endpoint": "main.site_haritasi"},
            {"etiket": "İletişim", "endpoint": "main.iletisim"},
        ],
    },
    {
        "baslik": "Platformumuz",
        "linkler": [
            {"etiket": "Kaynak Paylaşımı", "endpoint": "kaynak.kaynak_panel"},
            {"etiket": "Atık Paylaşımı", "endpoint": "atik.atik_panel"},
            {"etiket": "Çevresel Etki Paneli", "endpoint": "impact.etki_panelim", "login_required": True},
            {"etiket": "Harita & Atık Merkezleri", "endpoint": "atik.atik_panel"},
            {"etiket": "Liderlik Tablosu", "endpoint": "gamification.liderlik"},
            {"etiket": "Rozetlerim", "endpoint": "gamification.rozetlerim", "login_required": True},
            {"etiket": "Kurum Analiz Paneli", "endpoint": "kurum.analiz_paneli", "login_required": True},
            {"etiket": "AI Moderasyon", "endpoint": "main.kurumsal_sayfa", "slug": "ai-moderasyon"},
            {"etiket": "Mesajlaşma", "endpoint": "messages.mesajlarim", "login_required": True},
        ],
    },
    {
        "baslik": "Gizlilik ve Kullanım",
        "linkler": [
            {"etiket": "Güvenli Paylaşım İpuçları", "endpoint": "main.kurumsal_sayfa", "slug": "guvenli-paylasim"},
            {"etiket": "Kullanım Koşulları", "endpoint": "main.kurumsal_sayfa", "slug": "kullanim-kosullari"},
            {"etiket": "Gizlilik & KVKK", "endpoint": "main.kurumsal_sayfa", "slug": "gizlilik-kvkk"},
            {"etiket": "Çerez Politikası", "endpoint": "main.kurumsal_sayfa", "slug": "cerez-politikasi"},
        ],
    },
    {
        "baslik": "Yardım",
        "linkler": [
            {"etiket": "Yardım Merkezi", "endpoint": "main.kurumsal_sayfa", "slug": "yardim"},
            {"etiket": "Sık Sorulan Sorular", "endpoint": "main.kurumsal_sayfa", "slug": "sss"},
            {"etiket": "Nasıl İlan Verilir?", "endpoint": "main.kurumsal_sayfa", "slug": "nasil-ilan-verilir"},
            {"etiket": "İlan Durumları", "endpoint": "main.kurumsal_sayfa", "slug": "ilan-durumlari"},
        ],
    },
]

# Üst navbar Kurumsal menüsü (misafir kullanıcılar)
NAVBAR_KURUMSAL = FOOTER_COLUMNS[0]["linkler"]

SOSYAL_MEDYA = [
    {"etiket": "Instagram", "url": "#", "icon": "bi-instagram"},
    {"etiket": "X (Twitter)", "url": "#", "icon": "bi-twitter-x"},
    {"etiket": "LinkedIn", "url": "https://www.linkedin.com/in/yusufcan-s-434932254/", "icon": "bi-linkedin"},
    {"etiket": "YouTube", "url": "#", "icon": "bi-youtube"},
]

KURUMSAL_SAYFALAR = {
    "hakkimizda": {
        "title": "Hakkımızda",
        "ozet": "AtıkPort, kaynak ve atıkların paylaşımıyla döngüsel ekonomiyi destekleyen yapay zekâ destekli bir platformdur.",
        "bolumler": [
            {
                "baslik": "Biz Kimiz?",
                "icerik": (
                    "AtıkPort; kullanılmayan eşyaların yeniden değerlendirilmesi ve atıkların doğru kanallara "
                    "yönlendirilmesi için geliştirilmiş bir dijital paylaşım platformudur. Teknoloji ve "
                    "sürdürülebilirlik odaklı yaklaşımımızla bireylerin, kurumların ve toplumun aynı ekosistemde "
                    "buluşmasını hedefliyoruz."
                ),
            },
            {
                "baslik": "Neden Varız?",
                "icerik": (
                    "Her yıl tonlarca kullanılabilir eşya çöpe giderken, birçok ihtiyaç sahibi bu kaynaklara "
                    "ulaşamıyor. AtıkPort bu kopukluğu gidererek kaynak israfını azaltır, geri dönüşüm bilincini "
                    "artırır ve paylaşım ekonomisini güvenli bir dijital ortamda mümkün kılar."
                ),
            },
            {
                "baslik": "Teknoloji",
                "icerik": (
                    "Platformumuz Google Gemini yapay zekâsı ile görsel moderasyon ve kategori tahmini yapar; "
                    "harita entegrasyonu ile atık merkezlerini gösterir; çevresel etki paneli ile her teslim "
                    "edilen paylaşımın tahmini CO₂, su ve atık tasarrufunu hesaplar. Oyunlaştırma sistemi "
                    "rozet ve seviyelerle katılımı teşvik eder; akıllı öneriler ilanları size göre eşleştirir; "
                    "kurum analiz paneli belediyelere bölgesel ısı haritası sunar."
                ),
            },
        ],
    },
    "vizyon-misyon": {
        "title": "Vizyon & Misyon",
        "ozet": "Sıfır atık ve döngüsel ekonomi vizyonuyla hareket ediyoruz.",
        "bolumler": [
            {
                "baslik": "Vizyonumuz",
                "icerik": (
                    "Türkiye'nin en güvenilir ve erişilebilir kaynak-atık paylaşım platformu olarak, "
                    "her ilde sürdürülebilir tüketim ve üretim alışkanlıklarının yaygınlaştığı bir ekosistem "
                    "oluşturmak."
                ),
            },
            {
                "baslik": "Misyonumuz",
                "icerik": (
                    "Kullanıcıların kullanılabilir eşyalarını ve atıklarını kolayca paylaşmasını sağlamak; "
                    "yapay zekâ destekli güvenli moderasyon ile topluluk güvenini korumak; çevresel etkiyi "
                    "ölçülebilir kılarak farkındalık yaratmak ve yerel geri dönüşüm ağlarını dijital harita "
                    "üzerinden görünür kılmak."
                ),
            },
            {
                "baslik": "Değerlerimiz",
                "icerik": (
                    "Şeffaflık, topluluk güveni, çevresel sorumluluk, erişilebilirlik ve yenilikçilik "
                    "temel değerlerimizdir. Her özellik bu değerlere hizmet edecek şekilde tasarlanır."
                ),
            },
        ],
    },
    "hedeflerimiz": {
        "title": "Hedeflerimiz",
        "ozet": "Kısa ve orta vadede ulaşmayı planladığımız somut hedefler.",
        "bolumler": [
            {
                "baslik": "Çevresel Hedefler",
                "icerik": (
                    "• Yıllık binlerce kg CO₂e tasarrufu sağlamak\n"
                    "• Geri dönüşüme yönlendirilen atık miktarını artırmak\n"
                    "• Yeniden kullanım oranını ölçülebilir şekilde raporlamak"
                ),
            },
            {
                "baslik": "Topluluk Hedefleri",
                "icerik": (
                    "• Aktif kullanıcı ve teslim edilen ilan sayısını büyütmek\n"
                    "• Güven puanı sistemiyle güvenilir paylaşım kültürü oluşturmak\n"
                    "• İl ve ilçe bazında yerel paylaşım ağları kurmak"
                ),
            },
            {
                "baslik": "Teknoloji Hedefleri",
                "icerik": (
                    "• AI moderasyon doğruluğunu sürekli iyileştirmek\n"
                    "• Mobil uyumlu deneyimi geliştirmek\n"
                    "• Belediye ve geri dönüşüm merkezleriyle veri entegrasyonunu genişletmek"
                ),
            },
        ],
    },
    "surdurulebilirlik": {
        "title": "Sürdürülebilirlik",
        "ozet": "Döngüsel ekonomi ve sıfır atık ilkeleri platformun merkezindedir.",
        "bolumler": [
            {
                "baslik": "Döngüsel Ekonomi",
                "icerik": (
                    "Doğrusal \"üret-tüket-at\" modeli yerine kaynakların mümkün olduğunca uzun süre "
                    "ekonomide kalmasını destekliyoruz. Kaynak paylaşımı ve atık yönlendirmesi bu döngünün "
                    "iki temel koludur."
                ),
            },
            {
                "baslik": "Sıfır Atık",
                "icerik": (
                    "Atıkların kaynağında azaltılması, ayrı toplanması ve geri kazanımı sıfır atık "
                    "yaklaşımının özüdür. Platformumuz kullanıcıları doğru atık kategorileri ve "
                    "toplama noktaları konusunda bilgilendirir."
                ),
            },
            {
                "baslik": "Ölçüm ve Raporlama",
                "icerik": (
                    "Çevresel Etki Paneli ile her teslim edilen paylaşımın tahmini karbon, su ve atık "
                    "tasarrufu hesaplanır. Detaylı metodoloji için "
                    "Çevresel Etki Metodolojisi sayfamıza bakabilirsiniz."
                ),
            },
        ],
    },
    "haberler": {
        "title": "Haberler",
        "ozet": "AtıkPort'tan güncellemeler ve duyurular.",
        "bolumler": [
            {
                "baslik": "Çevresel Etki Paneli Yayında",
                "icerik": (
                    "Kullanıcılar artık teslim ettikleri paylaşımların tahmini çevresel etkisini "
                    "kişisel panelden takip edebiliyor. Platform geneli özet admin panelinde görüntüleniyor."
                ),
            },
            {
                "baslik": "Çoklu Fotoğraf Desteği",
                "icerik": "Kaynak ve atık ilanlarına en fazla 10 fotoğraf yüklenebiliyor; galeri görünümü eklendi.",
            },
            {
                "baslik": "Harita Entegrasyonu",
                "icerik": (
                    "Atık panelinde kullanıcı ilanları ve İBB atık toplama merkezleri harita üzerinde "
                    "gösteriliyor."
                ),
            },
        ],
    },
    "guvenli-paylasim": {
        "title": "Güvenli Paylaşım İpuçları",
        "ozet": "Güvenli ve sorunsuz paylaşım için öneriler.",
        "bolumler": [
            {
                "baslik": "Buluşma ve Teslim",
                "icerik": (
                    "Mümkünse kalabalık ve açık alanlarda buluşun. Teslim sonrası ilan durumunu "
                    "\"Teslim Edildi\" olarak güncelleyin; bu hem çevresel etki hesabını hem güven "
                    "puanınızı etkiler."
                ),
            },
            {
                "baslik": "İletişim",
                "icerik": (
                    "Platform içi mesajlaşmayı tercih edin. Telefon numaranız yalnızca giriş yapmış "
                    "kullanıcılara görünür; yine de kişisel bilgilerinizi dikkatli paylaşın."
                ),
            },
            {
                "baslik": "İçerik ve Fotoğraf",
                "icerik": (
                    "Gerçek ve güncel fotoğraflar kullanın. Yanıltıcı veya uygunsuz içerikler AI "
                    "moderasyon ve şikayet sistemi ile engellenir."
                ),
            },
        ],
    },
    "kullanim-kosullari": {
        "title": "Kullanım Koşulları",
        "ozet": "AtıkPort platformunu kullanırken uyulması gereken kurallar.",
        "bolumler": [
            {
                "baslik": "Genel Kurallar",
                "icerik": (
                    "Platform yalnızca yasal kaynak ve atık paylaşımı içindir. Sahte ilan, spam, "
                    "nefret söylemi ve yasadışı içerik yasaktır. İhlal durumunda ilan silinebilir "
                    "ve hesap kısıtlanabilir."
                ),
            },
            {
                "baslik": "İlan Sorumluluğu",
                "icerik": (
                    "İlan içeriğinden paylaşan kullanıcı sorumludur. Yanlış kategori, eksik açıklama "
                    "veya yanıltıcı görseller diğer kullanıcıların güvenini zedeler."
                ),
            },
            {
                "baslik": "Hizmet Kapsamı",
                "icerik": (
                    "AtıkPort aracı bir platformdur; taraflar arasındaki fiziksel teslimat ve "
                    "ürün/atık kalitesinden doğrudan sorumlu değildir."
                ),
            },
        ],
    },
    "gizlilik-kvkk": {
        "title": "Gizlilik & KVKK",
        "ozet": "Kişisel verilerinizin korunması hakkında bilgi.",
        "bolumler": [
            {
                "baslik": "Toplanan Veriler",
                "icerik": (
                    "Kayıt sırasında kullanıcı adı, e-posta, il, ilçe, telefon ve isteğe bağlı konum "
                    "bilgisi toplanır. İlanlarınız ve mesajlarınız platformda saklanır."
                ),
            },
            {
                "baslik": "Verilerin Kullanımı",
                "icerik": (
                    "Veriler hesap yönetimi, ilan gösterimi, mesajlaşma, çevresel etki hesaplama ve "
                    "güvenlik amacıyla işlenir. Üçüncü taraflarla izinsiz paylaşım yapılmaz."
                ),
            },
            {
                "baslik": "Haklarınız",
                "icerik": (
                    "KVKK kapsamında verilerinize erişim, düzeltme ve silme talebinde bulunabilirsiniz. "
                    "Talepler için İletişim sayfasından bize ulaşın."
                ),
            },
        ],
    },
    "cerez-politikasi": {
        "title": "Çerez Politikası",
        "ozet": "Çerez ve yerel depolama kullanımı.",
        "bolumler": [
            {
                "baslik": "Zorunlu Çerezler",
                "icerik": (
                    "Oturum yönetimi ve CSRF güvenliği için teknik çerezler kullanılır; bunlar "
                    "platformun çalışması için gereklidir."
                ),
            },
            {
                "baslik": "Tercih Çerezleri",
                "icerik": (
                    "Karanlık/aydınlık tema tercihiniz tarayıcınızın yerel depolamasında (localStorage) "
                    "saklanır; sunucuya gönderilmez."
                ),
            },
        ],
    },
    "yardim": {
        "title": "Yardım Merkezi",
        "ozet": "Platformu kullanmaya başlamak için rehber.",
        "bolumler": [
            {
                "baslik": "Hesap Oluşturma",
                "icerik": "Kayıt Ol → e-posta ve şifre → Profil Tamamla (il, ilçe, telefon) adımlarını izleyin.",
            },
            {
                "baslik": "İlan Verme",
                "icerik": (
                    "Kaynak veya Atık panelinden \"Paylaş\" butonuna tıklayın; fotoğraf, açıklama ve "
                    "konum ekleyin. AI kategori ve moderasyon kontrolü otomatik yapılır."
                ),
            },
            {
                "baslik": "Mesajlaşma ve Favoriler",
                "icerik": (
                    "İlan detayından sahibiyle iletişime geçebilir, ilanları favorilere ekleyebilirsiniz."
                ),
            },
        ],
    },
    "sss": {
        "title": "Sık Sorulan Sorular",
        "ozet": "En çok merak edilen konular.",
        "bolumler": [
            {
                "baslik": "Platform ücretsiz mi?",
                "icerik": "Evet, kayıt ve ilan paylaşımı ücretsizdir.",
            },
            {
                "baslik": "Telefon numaram herkese görünür mü?",
                "icerik": "Hayır. Telefon numaranız yalnızca giriş yapmış kullanıcılara ilan detayında gösterilir.",
            },
            {
                "baslik": "Çevresel etki nasıl hesaplanır?",
                "icerik": (
                    "İlan \"Teslim Edildi\" yapıldığında kategori bazlı katsayılarla tahmini tasarruf "
                    "hesaplanır. Detay için Çevresel Etki Metodolojisi sayfasına bakın."
                ),
            },
            {
                "baslik": "İlanım neden moderasyonda reddedildi?",
                "icerik": (
                    "AI, uygunsuz veya platform dışı içerikleri engeller. Atık fotoğrafları (pil, elektronik vb.) "
                    "normal kabul edilir; sorun devam ederse açıklamaya atık türünü yazın."
                ),
            },
        ],
    },
    "nasil-ilan-verilir": {
        "title": "Nasıl İlan Verilir?",
        "ozet": "Adım adım ilan oluşturma rehberi.",
        "bolumler": [
            {"baslik": "1. Giriş yapın", "icerik": "Kayıtlı değilseniz önce ücretsiz hesap oluşturun."},
            {
                "baslik": "2. Panel seçin",
                "icerik": "Kaynak (eşya) veya Atık paneline gidin ve \"Paylaş\" / \"Yükle\" butonuna tıklayın.",
            },
            {
                "baslik": "3. Bilgileri doldurun",
                "icerik": "Başlık, açıklama, kategori ve fotoğraf ekleyin. Konum izni verin; haritada görünmesi için gereklidir.",
            },
            {
                "baslik": "4. Yayınlayın",
                "icerik": "AI kontrolünden geçen ilanınız panelde listelenir. Mesajlar üzerinden iletişim kurabilirsiniz.",
            },
        ],
    },
    "ilan-durumlari": {
        "title": "İlan Durumları",
        "ozet": "Aktif, Rezerve ve Teslim Edildi durumlarının anlamı.",
        "bolumler": [
            {
                "baslik": "Aktif",
                "icerik": "İlan herkese açık ve paylaşıma hazırdır.",
            },
            {
                "baslik": "Rezerve",
                "icerik": "Bir kullanıcıyla anlaşıldığını belirtir; ilan hâlâ görünür ancak süreç devam ediyor olabilir.",
            },
            {
                "baslik": "Teslim Edildi",
                "icerik": (
                    "Paylaşım tamamlandığında seçilir. Çevresel etki kaydı oluşur ve güven puanınız artar. "
                    "Geri alırsanız etki kaydı silinir."
                ),
            },
        ],
    },
    "ai-moderasyon": {
        "title": "AI Moderasyon",
        "ozet": "Yapay zekâ destekli içerik güvenliği.",
        "bolumler": [
            {
                "baslik": "Nasıl Çalışır?",
                "icerik": (
                    "Yüklenen görseller Google Gemini ile analiz edilir: kategori tahmini, risk skoru "
                    "ve uygunsuzluk kontrolü yapılır. Metin moderasyonu da desteklenir."
                ),
            },
            {
                "baslik": "Atık Fotoğrafları",
                "icerik": (
                    "Pil, akü ve elektronik atık gibi görseller geri dönüşüm bağlamında normal kabul edilir; "
                    "yanlış pozitifler için özel düzeltme kuralları uygulanır."
                ),
            },
            {
                "baslik": "Şikayet Sistemi",
                "icerik": "Kullanıcılar uygunsuz ilanları şikayet edebilir; admin panelinden incelenir.",
            },
        ],
    },
}

SITE_HARITASI_GRUPLARI = [
    {
        "baslik": "Ana Sayfalar",
        "linkler": [
            {"etiket": "Anasayfa", "endpoint": "main.anasayfa"},
            {"etiket": "Kaynak Paneli", "endpoint": "kaynak.kaynak_panel"},
            {"etiket": "Atık Paneli", "endpoint": "atik.atik_panel"},
            {"etiket": "Liderlik Tablosu", "endpoint": "gamification.liderlik"},
            {"etiket": "Giriş", "endpoint": "auth.giris"},
            {"etiket": "Kayıt", "endpoint": "auth.kayit"},
        ],
    },
    {
        "baslik": "Kullanıcı",
        "linkler": [
            {"etiket": "İlanlarım", "endpoint": "ilan.ilanlarim"},
            {"etiket": "Favorilerim", "endpoint": "api.favorilerim"},
            {"etiket": "Çevresel Etki Panelim", "endpoint": "impact.etki_panelim"},
            {"etiket": "Rozetlerim", "endpoint": "gamification.rozetlerim"},
            {"etiket": "Kurum Analiz Paneli", "endpoint": "kurum.analiz_paneli"},
            {"etiket": "Mesajlarım", "endpoint": "messages.mesajlarim"},
            {"etiket": "Profil", "endpoint": "auth.profil"},
        ],
    },
    {
        "baslik": "Kurumsal",
        "linkler": [
            {"etiket": "Hakkımızda", "endpoint": "main.kurumsal_sayfa", "slug": "hakkimizda"},
            {"etiket": "Vizyon & Misyon", "endpoint": "main.kurumsal_sayfa", "slug": "vizyon-misyon"},
            {"etiket": "İletişim", "endpoint": "main.iletisim"},
        ],
    },
]
