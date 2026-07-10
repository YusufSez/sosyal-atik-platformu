def run_scheduled_backup(app):
    """Zamanlanmış veritabanı yedeklemesini çalıştırır."""
    try:
        from services.backup import maybe_run_scheduled_backup

        backup_path = maybe_run_scheduled_backup(app)
        if backup_path:
            app.logger.info("Otomatik veritabanı yedeği oluşturuldu: %s", backup_path)
    except Exception as exc:
        app.logger.warning("Otomatik yedekleme başarısız: %s", exc)
