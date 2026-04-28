from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('revenue_pro.portfolio'))
    if request.method == 'POST':
        email    = (request.form.get('email') or '').lower().strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            return redirect(request.args.get('next') or url_for('revenue_pro.portfolio'))
        flash('Email o contraseña incorrectos.', 'error')
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('revenue_pro.portfolio'))
    if request.method == 'POST':
        email     = (request.form.get('email') or '').lower().strip()
        full_name = (request.form.get('full_name') or '').strip()
        password  = (request.form.get('password') or '').strip()
        agency    = (request.form.get('agency') or 'Mi Agencia').strip()

        if not email or not full_name or not password:
            flash('Todos los campos son requeridos.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Este email ya está registrado.', 'error')
            return render_template('auth/register.html')

        from models import db, Account
        import re
        slug = re.sub(r'[^\w]', '-', agency.lower())[:60]
        existing = Account.query.filter_by(slug=slug).first()
        if existing:
            acct = existing
        else:
            acct = Account(name=agency, slug=slug)
            db.session.add(acct)
            db.session.flush()

        user = User(email=email, full_name=full_name,
                    account_id=acct.id, role='owner')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        flash(f'Bienvenido, {full_name}!', 'success')
        return redirect(url_for('revenue_pro.portfolio'))

    return render_template('auth/register.html')
