from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey, Table, Column, Integer, String, Boolean, DateTime, Text, Float, Enum
import enum
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Role {self.code}>'


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        print(f"Error loading user: {e}")
        return None


class UserPermission(db.Model):
    """Stores user permissions for system access control"""
    __tablename__ = 'user_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    can_view = db.Column(db.Boolean, default=True)
    can_add = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_update = db.Column(db.Boolean, default=False)
    # Store comma-separated role codes that this user can edit
    allowed_roles = db.Column(db.Text, default='all')
    edit_scope = db.Column(db.String(20), default='all')  # 'all' or 'own'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_allowed_roles(self):
        """Return a list of role codes this user is allowed to edit"""
        logger.debug(f"Getting allowed roles from: {self.allowed_roles}")
        if not self.allowed_roles:
            return ['all']
        return [role.strip() for role in self.allowed_roles.split(',') if role.strip()]

    def __repr__(self):
        return f'<UserPermission for user_id={self.user_id}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # Increased length for hash
    email = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(20), default='employee')  # 'admin' or 'employee'
    is_active = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to permissions - ensure it's properly loaded
    permissions = db.relationship('UserPermission', backref='user', uselist=False,
                                  cascade='all, delete-orphan', single_parent=True,
                                  lazy='joined')  # Changed to joined loading

    def set_password(self, password):
        if not password:
            raise ValueError("Password cannot be empty")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        if not password:
            return False
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def can_view(self):
        if self.is_admin():
            return True
        return self.permissions is not None and self.permissions.can_view

    def can_add(self):
        if self.is_admin():
            return True
        return self.permissions is not None and self.permissions.can_add

    def can_edit(self):
        if self.is_admin():
            return True
        return self.permissions is not None and self.permissions.can_edit

    def can_update(self):
        if self.is_admin():
            return True
        return self.permissions is not None and self.permissions.can_update

    def can_edit_role(self, role_code):
        """Check if user can edit records with the specified role code"""
        if self.is_admin():
            return True
        if not self.permissions or not (self.permissions.can_edit or self.permissions.can_update):
            return False

        # Check if user has permission for all roles or for this specific role
        allowed_roles = self.permissions.get_allowed_roles()
        return 'all' in allowed_roles or role_code in allowed_roles

    def can_edit_user_records(self, created_by_user_id, assigned_role=None):
        """
        Check if user can edit records created by another user

        Args:
            created_by_user_id: The ID of the user who created the record
            assigned_role: The role code assigned to the record (e.g., sales person)

        Returns:
            bool: True if the user can edit the record, False otherwise
        """
        if self.is_admin():
            return True

        if not self.permissions or not (self.permissions.can_edit or self.permissions.can_update):
            return False

        # If edit_scope is 'all', user can edit any record
        if self.permissions.edit_scope == 'all':
            return True

        # If assigned_role is provided, check if user has permission for this role
        if assigned_role and self.can_edit_role(assigned_role):
            return True

        # Otherwise, user can only edit their own records
        return created_by_user_id == self.id

    def __repr__(self):
        return f'<User {self.username}>'


class Client(db.Model):
    """Represents a company/client in the system"""
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False, unique=True)
    company_address = db.Column(db.Text, nullable=True)
    company_website = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(50), nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contacts = db.relationship('ContactPerson', backref='client', lazy='dynamic',
                               cascade='all, delete-orphan')
    rfqs = db.relationship('RFQ', backref='client', lazy='dynamic')
    purchase_orders = db.relationship('PurchaseOrder', backref='client', lazy='dynamic')

    def __repr__(self):
        return f'<Client {self.company_name}>'


class ContactPerson(db.Model):
    """Represents a contact person associated with a client"""
    __tablename__ = 'contact_persons'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Changed from full_name to name
    position = db.Column(db.String(100), nullable=True)
    is_primary = db.Column(db.Boolean, default=False)  # Added to mark primary contacts
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Contact information
    emails = db.relationship('ContactEmail', backref='contact', lazy='dynamic', cascade='all, delete-orphan')
    phones = db.relationship('ContactPhone', backref='contact', lazy='dynamic', cascade='all, delete-orphan')
    mobiles = db.relationship('ContactMobile', backref='contact', lazy='dynamic', cascade='all, delete-orphan')

    def primary_email(self):
        """Returns the first email for this contact, or None if no emails exist"""
        return self.emails.first()

    def primary_phone(self):
        """Returns the first phone for this contact, or None if no phones exist"""
        return self.phones.first()

    def primary_mobile(self):
        """Returns the first mobile for this contact, or None if no mobiles exist"""
        return self.mobiles.first()

    def __repr__(self):
        return f'<ContactPerson {self.name}>'


class ContactEmail(db.Model):
    """Stores email addresses for contact persons"""
    __tablename__ = 'contact_emails'

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact_persons.id', ondelete='CASCADE'), nullable=False)
    email = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<ContactEmail {self.email}>'


class ContactPhone(db.Model):
    """Stores phone numbers for contact persons"""
    __tablename__ = 'contact_phones'

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact_persons.id', ondelete='CASCADE'), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<ContactPhone {self.phone}>'


class ContactMobile(db.Model):
    """Stores mobile numbers for contact persons"""
    __tablename__ = 'contact_mobiles'

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact_persons.id', ondelete='CASCADE'), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<ContactMobile {self.mobile}>'


class RFQ(db.Model):
    __tablename__ = 'rfqs'

    id = db.Column(db.Integer, primary_key=True)
    date_received = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact_persons.id'), nullable=True)
    contact_person = db.Column(db.String(100))  # Legacy field, kept for backward compatibility
    item_description = db.Column(db.Text, nullable=False)
    assigned_role = db.Column(db.String(20), nullable=True)
    bid_closing_date = db.Column(db.Date, nullable=True)
    proposal_status = db.Column(db.String(20), default="Pending")
    remarks = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_restored = db.Column(db.Boolean, default=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    contact = db.relationship('ContactPerson', foreign_keys=[contact_id], backref='rfqs')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], backref='created_rfqs')
    purchase_orders = db.relationship('PurchaseOrder', backref='rfq', lazy='dynamic')
    attachments = db.relationship('RFQAttachment', backref='rfq', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RFQ {self.id}>'


class RFQAttachment(db.Model):
    __tablename__ = 'rfq_attachments'

    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey('rfqs.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<RFQAttachment {self.original_filename}>'


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey('rfqs.id'))
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact_persons.id'), nullable=True)
    items_ordered = db.Column(db.Text, nullable=False)
    currency = db.Column(db.String(3), default='PHP')
    total_amount = db.Column(db.Float, nullable=False)
    payment_terms = db.Column(db.String(100))
    payment_status = db.Column(db.String(20), default="Pending")
    delivery_details = db.Column(db.String(200))
    delivery_address = db.Column(db.Text)
    delivery_date = db.Column(db.Date)
    collection_details = db.Column(db.Text)
    collection_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="On Hold")
    remarks = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    contact = db.relationship('ContactPerson', foreign_keys=[contact_id], backref='purchase_orders')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], backref='created_purchase_orders')
    attachments = db.relationship('POAttachment', backref='purchase_order', lazy='dynamic',
                                  cascade='all, delete-orphan')

    def __repr__(self):
        return f'<PurchaseOrder {self.id}>'

    def get_currency_symbol(self):
        return {
            'PHP': '₱',
            'USD': '$',
            'EUR': '€',
            'JPY': '¥',
            'GBP': '£'
        }.get(self.currency, '')

    def formatted_total(self):
        return f"{self.get_currency_symbol()} {self.total_amount:,.2f}"


class POAttachment(db.Model):
    __tablename__ = 'po_attachments'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<POAttachment {self.original_filename}>'


# Add SystemSettings model
class SystemSettings(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default="A.M.G. Industrial Services")
    company_address = db.Column(db.Text)
    company_phone = db.Column(db.String(20))
    company_email = db.Column(db.String(100))
    company_website = db.Column(db.String(100))
    default_currency = db.Column(db.String(10), default="USD")
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SystemSettings {self.company_name}>'

