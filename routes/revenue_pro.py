from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import (db, OmniProperty, RoomType, CompSetEntry,
                    PropertyPerformance, PropertyMarket, OmniAnalysis)

revenue_pro_bp = Blueprint('revenue_pro', __name__, url_prefix='/revenue-pro')


def _can_access(prop):
    if current_user.role in ('owner', 'admin'):
        return prop.account_id == current_user.account_id
    return prop.owner_user_id == current_user.id


# ── Portfolio ──────────────────────────────────────────────────────────────────

@revenue_pro_bp.route('/')
@login_required
def portfolio():
    if current_user.role in ('owner', 'admin'):
        properties = OmniProperty.query.filter_by(
            account_id=current_user.account_id
        ).order_by(OmniProperty.created_at.desc()).all()
    else:
        properties = OmniProperty.query.filter_by(
            owner_user_id=current_user.id
        ).all()
    last_analyses = {}
    for p in properties:
        last = (OmniAnalysis.query
                .filter_by(property_id=p.id)
                .order_by(OmniAnalysis.created_at.desc())
                .first())
        last_analyses[p.id] = last
    return render_template('revenue_pro/portfolio.html',
                           properties=properties,
                           last_analyses=last_analyses)


# ── New property ───────────────────────────────────────────────────────────────

@revenue_pro_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_property():
    if request.method == 'POST':
        try:
            total_rooms = int(request.form.get('total_rooms', 0))
            price_floor = float(str(request.form.get('price_floor', 0)).replace(',', ''))
        except (ValueError, TypeError):
            total_rooms = 0
            price_floor = 0

        if total_rooms < 1 or price_floor < 1:
            flash('Cantidad de habitaciones y tarifa mínima son requeridas.', 'error')
            return render_template('revenue_pro/property_new.html')

        prop = OmniProperty(
            account_id=current_user.account_id,
            total_rooms=total_rooms,
            price_floor=price_floor,
            name=request.form.get('name') or None,
            city=request.form.get('city') or None,
            property_type=request.form.get('property_type', 'hotel'),
            positioning=request.form.get('positioning', 'midscale'),
            currency=request.form.get('currency', 'COP'),
        )
        db.session.add(prop)
        db.session.flush()

        standard = RoomType(
            property_id=prop.id, name='Standard',
            units=total_rooms, is_base=True,
            multiplier=1.0, pax_max=2, occupancy_pct=55
        )
        db.session.add(standard)
        db.session.commit()
        flash('Propiedad creada. Completa el perfil para un análisis más preciso.', 'success')
        return redirect(url_for('revenue_pro.setup', property_id=prop.id, step='rooms'))

    return render_template('revenue_pro/property_new.html')


# ── Setup (multi-step) ─────────────────────────────────────────────────────────

SETUP_STEPS = ['rooms', 'performance', 'market']


@revenue_pro_bp.route('/<int:property_id>/setup', methods=['GET', 'POST'])
@revenue_pro_bp.route('/<int:property_id>/setup/<step>', methods=['GET', 'POST'])
@login_required
def setup(property_id, step='rooms'):
    prop = OmniProperty.query.get_or_404(property_id)
    if not _can_access(prop):
        flash('Sin acceso a esta propiedad.', 'error')
        return redirect(url_for('revenue_pro.portfolio'))

    if step not in SETUP_STEPS:
        step = 'rooms'

    perf    = PropertyPerformance.query.filter_by(property_id=property_id).first()
    market  = PropertyMarket.query.filter_by(property_id=property_id).first()
    room_types = RoomType.query.filter_by(property_id=property_id).all()
    compset = CompSetEntry.query.filter_by(property_id=property_id).all()

    if request.method == 'POST':
        if step == 'rooms':
            _save_rooms(prop, request.form)
            return redirect(url_for('revenue_pro.setup',
                                    property_id=property_id, step='performance'))
        elif step == 'performance':
            _save_performance(property_id, request.form)
            return redirect(url_for('revenue_pro.setup',
                                    property_id=property_id, step='market'))
        elif step == 'market':
            _save_market(property_id, request.form)
            return redirect(url_for('revenue_pro.analysis', property_id=property_id))

    return render_template('revenue_pro/setup.html',
                           prop=prop, step=step, steps=SETUP_STEPS,
                           room_types=room_types, compset=compset,
                           perf=perf, market=market)


def _fv(val, default=None):
    if val is None:
        return default
    s = str(val).replace(',', '').replace('$', '').strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _save_rooms(prop, form):
    prop.name          = form.get('name') or prop.name
    prop.city          = form.get('city') or prop.city
    prop.property_type = form.get('property_type', prop.property_type)
    prop.positioning   = form.get('positioning', prop.positioning)
    prop.star_rating   = int(form.get('star_rating') or prop.star_rating or 3)
    prop.brand_strength= form.get('brand_strength', prop.brand_strength)
    prop.usp_text      = form.get('usp_text') or prop.usp_text
    prop.amenities     = form.get('amenities') or prop.amenities
    prop.services      = form.get('services') or prop.services
    prop.extras        = form.get('extras') or prop.extras
    prop.checkin_hours = form.get('checkin_hours') or prop.checkin_hours
    prop.checkout_hours= form.get('checkout_hours') or prop.checkout_hours
    prop.sunny_days    = int(form.get('sunny_days') or 0) or prop.sunny_days
    prop.climate_type  = form.get('climate_type') or prop.climate_type
    prop.currency      = form.get('currency', prop.currency)
    if form.get('pms_raw_data', '').strip():
        prop.pms_raw_data = form.get('pms_raw_data').strip()

    # Room types — replace all
    names     = form.getlist('rt_name[]')
    units_l   = form.getlist('rt_units[]')
    pax_l     = form.getlist('rt_pax[]')
    mult_l    = form.getlist('rt_mult[]')
    bkf_l     = form.getlist('rt_bkf[]')
    occ_l     = form.getlist('rt_occ[]')

    RoomType.query.filter_by(property_id=prop.id).delete()
    total = 0
    for i, name in enumerate(names):
        if not name.strip():
            continue
        units = int(units_l[i]) if i < len(units_l) and units_l[i] else 1
        total += units
        rt = RoomType(
            property_id=prop.id,
            name=name.strip(),
            units=units,
            is_base=(i == 0),
            multiplier=float(mult_l[i]) if i < len(mult_l) and mult_l[i] else 1.0,
            pax_max=int(pax_l[i]) if i < len(pax_l) and pax_l[i] else 2,
            breakfast_per_pax=_fv(bkf_l[i] if i < len(bkf_l) else None, 0),
            occupancy_pct=_fv(occ_l[i] if i < len(occ_l) else None, 55),
        )
        db.session.add(rt)

    if total > 0:
        prop.total_rooms = total

    # CompSet — replace all
    c_names = form.getlist('comp_name[]')
    c_types = form.getlist('comp_type[]')
    c_rates = form.getlist('comp_rate[]')
    c_pos   = form.getlist('comp_pos[]')
    c_rooms = form.getlist('comp_rooms[]')

    CompSetEntry.query.filter_by(property_id=prop.id).delete()
    for i, cname in enumerate(c_names):
        if not cname.strip():
            continue
        ce = CompSetEntry(
            property_id=prop.id,
            name=cname.strip(),
            comp_type=c_types[i] if i < len(c_types) else '',
            avg_rate=_fv(c_rates[i] if i < len(c_rates) else None),
            position=c_pos[i] if i < len(c_pos) else 'similar',
            rooms=int(c_rooms[i]) if i < len(c_rooms) and c_rooms[i] else None,
        )
        db.session.add(ce)

    db.session.commit()


def _save_performance(property_id, form):
    from models import OmniProperty
    prop = OmniProperty.query.get(property_id)
    if prop and form.get('pms_raw_data', '').strip():
        prop.pms_raw_data = form.get('pms_raw_data').strip()
    perf = PropertyPerformance.query.filter_by(property_id=property_id).first()
    if not perf:
        perf = PropertyPerformance(property_id=property_id)
        db.session.add(perf)
    perf.occupancy_pct       = _fv(form.get('occupancy_pct'))
    perf.adr                 = _fv(form.get('adr'))
    perf.revpar              = _fv(form.get('revpar'))
    perf.booking_window_days = _fv(form.get('booking_window_days'))
    perf.avg_los             = _fv(form.get('avg_los'))
    perf.cancellation_pct    = _fv(form.get('cancellation_pct'))
    perf.channel_direct_pct  = _fv(form.get('channel_direct_pct'), 0)
    perf.channel_booking_pct = _fv(form.get('channel_booking_pct'), 0)
    perf.channel_expedia_pct = _fv(form.get('channel_expedia_pct'), 0)
    perf.channel_airbnb_pct  = _fv(form.get('channel_airbnb_pct'), 0)
    perf.channel_corp_pct    = _fv(form.get('channel_corp_pct'), 0)
    perf.channel_other_pct   = _fv(form.get('channel_other_pct'), 0)
    perf.feeder_markets      = form.get('feeder_markets')
    perf.guest_segment       = form.get('guest_segment')
    perf.city_avg_occ_pct    = _fv(form.get('city_avg_occ_pct'))
    db.session.commit()


def _save_market(property_id, form):
    market = PropertyMarket.query.filter_by(property_id=property_id).first()
    if not market:
        market = PropertyMarket(property_id=property_id)
        db.session.add(market)
    market.market_avg_rate = _fv(form.get('market_avg_rate'))
    market.demand_level    = form.get('demand_level', 'medium')
    market.seasonality     = form.get('seasonality')
    market.upcoming_events = form.get('upcoming_events')
    market.demand_drivers  = form.get('demand_drivers')
    db.session.commit()


# ── Analysis ───────────────────────────────────────────────────────────────────

@revenue_pro_bp.route('/<int:property_id>/analysis')
@login_required
def analysis(property_id):
    prop = OmniProperty.query.get_or_404(property_id)
    if not _can_access(prop):
        return redirect(url_for('revenue_pro.portfolio'))
    last = (OmniAnalysis.query
            .filter_by(property_id=property_id)
            .order_by(OmniAnalysis.created_at.desc())
            .first())
    return render_template('revenue_pro/analysis.html', prop=prop, analysis=last)


@revenue_pro_bp.route('/<int:property_id>/analyze', methods=['POST'])
@login_required
def run_analysis(property_id):
    from flask_login import current_user
    prop = OmniProperty.query.get_or_404(property_id)
    if not _can_access(prop):
        return jsonify({'error': 'Sin acceso'}), 403

    room_types = RoomType.query.filter_by(property_id=property_id).all()
    compset    = CompSetEntry.query.filter_by(property_id=property_id).all()
    perf       = PropertyPerformance.query.filter_by(property_id=property_id).first()
    market     = PropertyMarket.query.filter_by(property_id=property_id).first()

    data = {
        'property': {
            'name': prop.name, 'city': prop.city,
            'total_rooms': prop.total_rooms, 'price_floor': prop.price_floor,
            'currency': prop.currency, 'property_type': prop.property_type,
            'positioning': prop.positioning, 'star_rating': prop.star_rating,
            'brand_strength': prop.brand_strength, 'usp_text': prop.usp_text,
            'amenities': prop.amenities, 'extras': prop.extras,
            'sunny_days': prop.sunny_days, 'climate_type': prop.climate_type,
            'pms_raw_data': prop.pms_raw_data,
        },
        'room_types': [
            {'name': rt.name, 'units': rt.units, 'pax_max': rt.pax_max,
             'derived_rate': rt.derived_rate(prop.price_floor),
             'breakfast_per_pax': rt.breakfast_per_pax,
             'occupancy_pct': rt.occupancy_pct}
            for rt in room_types
        ],
        'compset': [
            {'name': c.name, 'comp_type': c.comp_type, 'avg_rate': c.avg_rate,
             'position': c.position, 'rooms': c.rooms}
            for c in compset
        ],
        'performance': {
            'occupancy_pct': perf.occupancy_pct if perf else None,
            'adr': perf.adr if perf else None,
            'revpar': perf.revpar if perf else None,
            'booking_window_days': perf.booking_window_days if perf else None,
            'avg_los': perf.avg_los if perf else None,
            'cancellation_pct': perf.cancellation_pct if perf else None,
            'channel_direct_pct': perf.channel_direct_pct if perf else 0,
            'channel_booking_pct': perf.channel_booking_pct if perf else 0,
            'channel_expedia_pct': perf.channel_expedia_pct if perf else 0,
            'channel_airbnb_pct': perf.channel_airbnb_pct if perf else 0,
            'channel_corp_pct': perf.channel_corp_pct if perf else 0,
            'guest_segment': perf.guest_segment if perf else None,
            'feeder_markets': perf.feeder_markets if perf else None,
            'city_avg_occ_pct': perf.city_avg_occ_pct if perf else None,
        } if perf else {},
        'market': {
            'demand_level': market.demand_level if market else 'medium',
            'market_avg_rate': market.market_avg_rate if market else None,
            'seasonality': market.seasonality if market else None,
            'upcoming_events': market.upcoming_events if market else None,
            'demand_drivers': market.demand_drivers if market else None,
        } if market else {},
    }

    try:
        from services.gemini_revenue import generate_omni_analysis
        result = generate_omni_analysis(data)
        ana = OmniAnalysis(
            property_id=property_id,
            created_by_user_id=current_user.id,
            raw_response=result['raw'],
            currency=prop.currency,
        )
        for key, val in result['sections'].items():
            setattr(ana, f'section_{key}', val)
        db.session.add(ana)
        db.session.commit()
        flash('Análisis generado exitosamente.', 'success')
        return redirect(url_for('revenue_pro.analysis', property_id=property_id))
    except Exception as e:
        flash(f'Error al generar análisis: {str(e)}', 'error')
        return redirect(url_for('revenue_pro.analysis', property_id=property_id))


# ── PMS File Upload ───────────────────────────────────────────────────────────

@revenue_pro_bp.route('/<int:property_id>/upload-pms', methods=['POST'])
@login_required
def upload_pms(property_id):
    prop = OmniProperty.query.get_or_404(property_id)
    if not _can_access(prop):
        return jsonify({'error': 'Sin acceso'}), 403

    f = request.files.get('pms_file')
    if not f or not f.filename:
        return jsonify({'error': 'No se seleccionó archivo'}), 400

    filename = f.filename.lower()
    allowed = ('.pdf', '.xlsx', '.xls', '.csv', '.txt',
               '.doc', '.docx', '.ppt', '.pptx',
               '.jpg', '.jpeg', '.png', '.webp')
    if not any(filename.endswith(ext) for ext in allowed):
        return jsonify({'error': 'Formato no soportado. Usa PDF, Excel, CSV, Word, imagen.'}), 400

    # Images → use Groq vision or describe
    if any(filename.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
        extracted = f'[Imagen adjunta: {f.filename}]\nContenido visual del reporte PMS. Analiza según el contexto de la propiedad.'
    elif any(filename.endswith(ext) for ext in ('.doc', '.docx', '.ppt', '.pptx')):
        # Extract as text best-effort
        data = f.read()
        try:
            extracted = data.decode('utf-8', errors='replace')[:3000]
        except Exception:
            extracted = f'[Archivo {f.filename} — contenido adjunto para análisis]'
    else:
        from services.file_parser import extract_text
        extracted = extract_text(f)

    if not extracted or not extracted.strip():
        return jsonify({'error': 'No se pudo extraer texto del archivo'}), 400

    prop.pms_raw_data = f'[Archivo: {f.filename}]\n\n{extracted[:4000]}'
    db.session.commit()

    return jsonify({
        'ok': True,
        'filename': f.filename,
        'preview': extracted[:200] + ('...' if len(extracted) > 200 else '')
    })


# ── Invite owner ───────────────────────────────────────────────────────────────

@revenue_pro_bp.route('/<int:property_id>/invite', methods=['GET', 'POST'])
@login_required
def invite_owner(property_id):
    if current_user.role not in ('owner', 'admin'):
        flash('Solo la agencia puede invitar propietarios.', 'error')
        return redirect(url_for('revenue_pro.portfolio'))

    prop = OmniProperty.query.get_or_404(property_id)
    if prop.account_id != current_user.account_id:
        return redirect(url_for('revenue_pro.portfolio'))

    if request.method == 'POST':
        email     = (request.form.get('email') or '').lower().strip()
        full_name = (request.form.get('full_name') or '').strip()
        password  = (request.form.get('password') or '').strip()

        if not email or not full_name or not password:
            flash('Todos los campos son requeridos.', 'error')
        else:
            from models import User
            existing = User.query.filter_by(email=email).first()
            if existing:
                prop.owner_user_id = existing.id
                db.session.commit()
                flash(f'Acceso otorgado a {email}.', 'success')
            else:
                new_user = User(
                    email=email, full_name=full_name,
                    account_id=current_user.account_id,
                    role='editor'
                )
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.flush()
                prop.owner_user_id = new_user.id
                db.session.commit()
                flash(f'Usuario {email} creado y vinculado a {prop.name or "la propiedad"}.', 'success')
            return redirect(url_for('revenue_pro.analysis', property_id=property_id))

    return render_template('revenue_pro/invite.html', prop=prop)
