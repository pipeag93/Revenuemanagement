from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Account(db.Model):
    __tablename__ = 'accounts'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    slug       = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    users      = db.relationship('User', backref='account', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Account {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name     = db.Column(db.String(120), nullable=False)
    role          = db.Column(db.String(20), default='editor')  # owner | admin | editor
    revenue_role  = db.Column(db.String(30), nullable=True)     # agency_admin | property_owner
    account_id    = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class OmniProperty(db.Model):
    __tablename__ = 'omni_properties'
    id             = db.Column(db.Integer, primary_key=True)
    account_id     = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    owner_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    total_rooms    = db.Column(db.Integer, nullable=False)
    price_floor    = db.Column(db.Float, nullable=False)
    name           = db.Column(db.String(200), nullable=True)
    city           = db.Column(db.String(200), nullable=True)
    property_type  = db.Column(db.String(50), default='hotel')
    positioning    = db.Column(db.String(50), default='midscale')
    star_rating    = db.Column(db.Integer, default=3)
    brand_strength = db.Column(db.String(20), default='low')
    usp_text       = db.Column(db.Text, nullable=True)
    amenities      = db.Column(db.Text, nullable=True)
    services       = db.Column(db.Text, nullable=True)
    extras         = db.Column(db.Text, nullable=True)
    checkin_hours  = db.Column(db.String(100), nullable=True)
    checkout_hours = db.Column(db.String(100), nullable=True)
    sunny_days     = db.Column(db.Integer, nullable=True)
    climate_type   = db.Column(db.String(50), nullable=True)
    currency       = db.Column(db.String(10), default='COP')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room_types  = db.relationship('RoomType', backref='omni_property', lazy='dynamic',
                                  cascade='all, delete-orphan')
    compset     = db.relationship('CompSetEntry', backref='omni_property', lazy='dynamic',
                                  cascade='all, delete-orphan')
    analyses    = db.relationship('OmniAnalysis', backref='omni_property', lazy='dynamic',
                                  cascade='all, delete-orphan')
    performance = db.relationship('PropertyPerformance', backref='omni_property',
                                  uselist=False, cascade='all, delete-orphan')
    market      = db.relationship('PropertyMarket', backref='omni_property',
                                  uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<OmniProperty {self.name or self.id}>'


class RoomType(db.Model):
    __tablename__ = 'omni_room_types'
    id                = db.Column(db.Integer, primary_key=True)
    property_id       = db.Column(db.Integer, db.ForeignKey('omni_properties.id'), nullable=False)
    name              = db.Column(db.String(100), nullable=False)
    units             = db.Column(db.Integer, nullable=False, default=1)
    is_base           = db.Column(db.Boolean, default=False)
    multiplier        = db.Column(db.Float, default=1.0)
    pax_max           = db.Column(db.Integer, default=2)
    breakfast_per_pax = db.Column(db.Float, default=0)
    occupancy_pct     = db.Column(db.Float, default=55)
    max_rate          = db.Column(db.Float, nullable=True)

    def derived_rate(self, base_floor):
        return round(base_floor * self.multiplier)

    def monthly_revenue(self, base_floor):
        adr = self.derived_rate(base_floor) + (self.breakfast_per_pax * self.pax_max)
        return round(self.units * 30 * adr * (self.occupancy_pct / 100))

    def __repr__(self):
        return f'<RoomType {self.name}>'


class CompSetEntry(db.Model):
    __tablename__ = 'omni_compset'
    id          = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('omni_properties.id'), nullable=False)
    name        = db.Column(db.String(200), nullable=False)
    comp_type   = db.Column(db.String(100), nullable=True)
    rooms       = db.Column(db.Integer, nullable=True)
    avg_rate    = db.Column(db.Float, nullable=True)
    position    = db.Column(db.String(20), default='similar')
    notes       = db.Column(db.Text, nullable=True)


class PropertyPerformance(db.Model):
    __tablename__ = 'omni_performance'
    id                  = db.Column(db.Integer, primary_key=True)
    property_id         = db.Column(db.Integer, db.ForeignKey('omni_properties.id'),
                                    unique=True, nullable=False)
    occupancy_pct       = db.Column(db.Float, nullable=True)
    adr                 = db.Column(db.Float, nullable=True)
    revpar              = db.Column(db.Float, nullable=True)
    booking_window_days = db.Column(db.Float, nullable=True)
    avg_los             = db.Column(db.Float, nullable=True)
    cancellation_pct    = db.Column(db.Float, nullable=True)
    channel_direct_pct  = db.Column(db.Float, default=0)
    channel_booking_pct = db.Column(db.Float, default=0)
    channel_expedia_pct = db.Column(db.Float, default=0)
    channel_airbnb_pct  = db.Column(db.Float, default=0)
    channel_corp_pct    = db.Column(db.Float, default=0)
    channel_other_pct   = db.Column(db.Float, default=0)
    feeder_markets      = db.Column(db.String(300), nullable=True)
    guest_segment       = db.Column(db.String(50), nullable=True)
    city_avg_occ_pct    = db.Column(db.Float, nullable=True)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PropertyMarket(db.Model):
    __tablename__ = 'omni_market'
    id              = db.Column(db.Integer, primary_key=True)
    property_id     = db.Column(db.Integer, db.ForeignKey('omni_properties.id'),
                                unique=True, nullable=False)
    market_avg_rate = db.Column(db.Float, nullable=True)
    demand_level    = db.Column(db.String(20), default='medium')
    seasonality     = db.Column(db.String(200), nullable=True)
    upcoming_events = db.Column(db.Text, nullable=True)
    demand_drivers  = db.Column(db.Text, nullable=True)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OmniAnalysis(db.Model):
    __tablename__ = 'omni_analyses'
    id                   = db.Column(db.Integer, primary_key=True)
    property_id          = db.Column(db.Integer, db.ForeignKey('omni_properties.id'), nullable=False)
    created_by_user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    raw_response         = db.Column(db.Text, nullable=False)
    currency             = db.Column(db.String(10), default='COP')
    section_dna          = db.Column(db.Text, nullable=True)
    section_diagnosis    = db.Column(db.Text, nullable=True)
    section_forecast     = db.Column(db.Text, nullable=True)
    section_matrix       = db.Column(db.Text, nullable=True)
    section_rates        = db.Column(db.Text, nullable=True)
    section_restrictions = db.Column(db.Text, nullable=True)
    section_channels     = db.Column(db.Text, nullable=True)
    section_upsell       = db.Column(db.Text, nullable=True)
    section_action       = db.Column(db.Text, nullable=True)
    section_kpis         = db.Column(db.Text, nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    def __getitem__(self, key):
        return getattr(self, key, None)

    def __repr__(self):
        return f'<OmniAnalysis {self.property_id}>'
