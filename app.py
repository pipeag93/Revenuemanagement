import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from models import db, User

load_dotenv()

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY']                  = os.environ.get('SECRET_KEY', 'omni-revenue-change-me')
    db_url = os.environ.get('DATABASE_URL', 'sqlite:////tmp/omni.db')
    # Railway PostgreSQL URLs start with postgres:// but SQLAlchemy needs postgresql://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED']            = True
    app.config['GEMINI_API_KEY']              = os.environ.get('GEMINI_API_KEY', '')

    db.init_app(app)
    csrf.init_app(app)

    with app.app_context():
        db.create_all()
        _seed()

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicia sesión para continuar.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.revenue_pro import revenue_pro_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(revenue_pro_bp)
    csrf.exempt(revenue_pro_bp)

    @app.route('/')
    def index():
        return redirect(url_for('revenue_pro.portfolio'))

    return app


def _seed():
    from models import Account, User
    if User.query.first():
        return
    acct = Account(name='Mi Agencia', slug='agencia')
    db.session.add(acct)
    db.session.flush()
    admin = User(
        email='admin@omnirevenue.com',
        full_name='Admin',
        account_id=acct.id,
        role='owner'
    )
    admin.set_password('omni2026')
    db.session.add(admin)
    db.session.commit()
    print('Seed OK — admin@omnirevenue.com / omni2026')


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
