import os
from dotenv import load_dotenv
load_dotenv(override=True)

from datetime import datetime, timedelta, timezone
from flask import Flask, g, request, session
from extensions import csrf, limiter
from utils import close_db, query_one, execute

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config["DATABASE"] = os.path.join(BASE_DIR, "users.db")
    
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    csrf.init_app(app)
    limiter.init_app(app)

    @app.teardown_appcontext
    def teardown_db(error=None):
        close_db(error)

    @app.before_request
    def load_logged_in_user():
        ref = request.args.get("ref")
        if ref and ref.isdigit():
            session["ref"] = ref

        user_id = session.get("user_id")
        g.user = None

        if user_id:
            user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
            if user:
                status = user["status"]
                expires_at = user["expires_at"]
                if status in ("active", "trial") and expires_at:
                    try:
                        exp_dt = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) > exp_dt:
                            execute("UPDATE users SET status = 'expired' WHERE id = ?", (user_id,))
                            user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
                    except Exception:
                        pass
            g.user = user

    CONTACT_TELEGRAM = os.environ.get("CONTACT_TELEGRAM", "@yourcontact")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@example.com")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "+49 000 000 0000")

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "contact_telegram": CONTACT_TELEGRAM,
            "contact_email": CONTACT_EMAIL,
            "contact_phone": CONTACT_PHONE,
        }

    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.payment import payment_bp
    from routes.dashboard import dashboard_bp
    from routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
