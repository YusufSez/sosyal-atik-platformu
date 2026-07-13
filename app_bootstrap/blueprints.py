def register_blueprints(app):
    from blueprints.admin_ministry import admin_ministry_bp
    from blueprints.belediye import belediye_bp
    from blueprints.gamification import gamification_bp
    from blueprints.kurum import kurum_bp
    from blueprints.admin import admin_bp
    from blueprints.admin_moderation import admin_moderation_bp
    from blueprints.admin_reports import admin_reports_bp
    from blueprints.api import api_bp
    from blueprints.atik import atik_bp
    from blueprints.auth import auth_bp
    from blueprints.ilan import ilan_bp
    from blueprints.impact import impact_bp
    from blueprints.kaynak import kaynak_bp
    from blueprints.main import main_bp
    from blueprints.messages import messages_bp
    from blueprints.support import support_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(kaynak_bp)
    app.register_blueprint(atik_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(ilan_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(kurum_bp)
    app.register_blueprint(belediye_bp)
    app.register_blueprint(admin_ministry_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_moderation_bp)
    app.register_blueprint(admin_reports_bp)
