def register_template_filters(app):
    from utils import format_datetime, local_now, unescape_stored_text
    from services.impact import format_etki_sayi
    from services.ilan_images import ilan_fotograf_listesi, kapak_resim
    from content.kurumsal import FOOTER_COLUMNS, NAVBAR_KURUMSAL, SOSYAL_MEDYA

    @app.template_filter("format_dt")
    def format_dt_filter(value, fmt="%d.%m.%Y %H:%M"):
        return format_datetime(value, fmt)

    @app.template_filter("display_text")
    def display_text_filter(value):
        return unescape_stored_text(value)

    @app.template_filter("format_etki")
    def format_etki_filter(value, birim=""):
        return format_etki_sayi(value, birim)

    @app.template_filter("kapak_resim")
    def kapak_resim_filter(ilan):
        return kapak_resim(ilan)

    @app.template_filter("ilan_fotograflari")
    def ilan_fotograflari_filter(ilan):
        return ilan_fotograf_listesi(ilan)

    @app.context_processor
    def inject_site_footer():
        return {
            "footer_columns": FOOTER_COLUMNS,
            "navbar_kurumsal": NAVBAR_KURUMSAL,
            "sosyal_medya": SOSYAL_MEDYA,
            "now_year": local_now().year,
        }

    @app.context_processor
    def inject_demo_banner():
        from flask_login import current_user

        show = False
        try:
            if current_user.is_authenticated:
                role = getattr(current_user, "role", None)
                is_admin = role in ("admin", "superadmin") or getattr(
                    current_user, "is_admin", False
                )
                if is_admin:
                    from services.demo_manager import is_demo_mode

                    show = is_demo_mode()
        except Exception:
            show = False
        return {"show_demo_mode_banner": show}
