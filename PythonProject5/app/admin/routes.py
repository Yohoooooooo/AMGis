from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.admin import admin
from app.admin.forms import RoleForm, UserForm, EditUserForm, SettingsForm
from app.models import Role, User, SystemSettings, Client, RFQ, PurchaseOrder, UserPermission
from app import db
from werkzeug.security import generate_password_hash
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@admin.route('/')
@login_required
def index():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    # Get counts for dashboard
    users_count = User.query.count()
    clients_count = Client.query.count()
    rfqs_count = RFQ.query.count()
    purchase_orders_count = PurchaseOrder.query.count()
    roles_count = Role.query.count()

    # Get recent users and RFQs
    recent_users = User.query.order_by(User.date_created.desc()).limit(5).all()
    recent_rfqs = RFQ.query.order_by(RFQ.last_updated.desc()).limit(5).all()

    return render_template('admin/index.html',
                           users_count=users_count,
                           clients_count=clients_count,
                           rfqs_count=rfqs_count,
                           purchase_orders_count=purchase_orders_count,
                           roles_count=roles_count,
                           recent_users=recent_users,
                           recent_rfqs=recent_rfqs)


@admin.route('/roles')
@login_required
def roles():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    roles_list = Role.query.all()
    return render_template('admin/roles.html', roles=roles_list)


@admin.route('/roles/add', methods=['GET', 'POST'])
@login_required
def add_role():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    form = RoleForm()
    if form.validate_on_submit():
        role = Role(
            name=form.name.data,
            code=form.code.data
        )
        db.session.add(role)
        db.session.commit()
        flash('Role added successfully.', 'success')
        return redirect(url_for('admin.roles'))
    return render_template('admin/role_form.html', form=form, title='Add Role')


@admin.route('/roles/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_role(id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    role = Role.query.get_or_404(id)
    form = RoleForm(obj=role, original_code=role.code)
    if form.validate_on_submit():
        role.name = form.name.data
        role.code = form.code.data
        db.session.commit()
        flash('Role updated successfully.', 'success')
        return redirect(url_for('admin.roles'))
    return render_template('admin/role_form.html', form=form, title='Edit Role')


@admin.route('/roles/delete/<int:id>', methods=['POST'])
@login_required
def delete_role(id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    role = Role.query.get_or_404(id)

    # Check if role is in use
    rfqs_with_role = RFQ.query.filter_by(assigned_role=role.code).count()
    if rfqs_with_role > 0:
        flash(f'Cannot delete role: {role.name} is assigned to {rfqs_with_role} RFQs.', 'danger')
        return redirect(url_for('admin.roles'))

    try:
        db.session.delete(role)
        db.session.commit()
        flash('Role deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting role: {str(e)}', 'danger')
    return redirect(url_for('admin.roles'))


@admin.route('/users')
@login_required
def users():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    users_list = User.query.all()
    return render_template('admin/users.html', users=users_list, current_user=current_user)


@admin.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    # Get all roles for the allowed_roles field
    roles = Role.query.all()

    form = UserForm()
    # Populate the allowed_roles choices
    form.allowed_roles.choices = [('all', 'All Roles')] + [(role.code, role.name) for role in roles]

    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data or None,
            role=form.role.data,
            is_active=form.is_active.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # Flush to get the user ID

        # Create user permissions
        allowed_roles = ','.join(form.allowed_roles.data) if form.allowed_roles.data else 'all'
        edit_scope = 'all' if 'all' in form.allowed_roles.data else 'own'

        permissions = UserPermission(
            user_id=user.id,
            can_view=form.can_view.data,
            can_add=form.can_add.data,
            can_edit=form.can_edit.data,
            can_update=form.can_update.data,
            allowed_roles=allowed_roles,
            edit_scope=edit_scope
        )
        db.session.add(permissions)
        db.session.commit()

        flash('User added successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, title='Add User')


@admin.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    user = User.query.get_or_404(id)
    logger.debug(f"Editing user: {user.username} (ID: {user.id})")

    # Get all roles for the allowed_roles field
    roles = Role.query.all()

    form = EditUserForm(obj=user, original_username=user.username)
    # Populate the allowed_roles choices
    form.allowed_roles.choices = [('all', 'All Roles')] + [(role.code, role.name) for role in roles]

    # If user has permissions, populate the form with them
    if user.permissions:
        logger.debug(f"User has existing permissions: {user.permissions}")
        form.can_view.data = user.permissions.can_view
        form.can_add.data = user.permissions.can_add
        form.can_edit.data = user.permissions.can_edit
        form.can_update.data = user.permissions.can_update

        # Set the allowed roles
        if user.permissions.allowed_roles:
            allowed_roles = user.permissions.get_allowed_roles()
            logger.debug(f"Setting allowed_roles to: {allowed_roles}")
            form.allowed_roles.data = allowed_roles

    if form.validate_on_submit():
        logger.debug(f"Form validated successfully for user {user.username}")
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        user.is_active = form.is_active.data

        # Only update password if provided
        if form.password.data:
            user.set_password(form.password.data)

        # Update or create permissions
        allowed_roles = form.allowed_roles.data if form.allowed_roles.data else ['all']
        allowed_roles_str = ','.join(allowed_roles)
        edit_scope = 'all' if 'all' in allowed_roles else 'own'

        logger.debug(
            f"Permissions data: view={form.can_view.data}, add={form.can_add.data}, edit={form.can_edit.data}, update={form.can_update.data}")
        logger.debug(f"Allowed roles: {allowed_roles_str}, edit_scope: {edit_scope}")

        # Check if user has permissions
        if user.permissions:
            logger.debug(f"Updating existing permissions for user {user.username}")
            user.permissions.can_view = form.can_view.data
            user.permissions.can_add = form.can_add.data
            user.permissions.can_edit = form.can_edit.data
            user.permissions.can_update = form.can_update.data
            user.permissions.allowed_roles = allowed_roles_str
            user.permissions.edit_scope = edit_scope
        else:
            # Create new permissions
            logger.debug(f"Creating new permissions for user {user.username}")
            permissions = UserPermission(
                user_id=user.id,
                can_view=form.can_view.data,
                can_add=form.can_add.data,
                can_edit=form.can_edit.data,
                can_update=form.can_update.data,
                allowed_roles=allowed_roles_str,
                edit_scope=edit_scope
            )
            db.session.add(permissions)
            db.session.commit()
    return render_template('admin/user_form.html', form=form, title='Edit User')


@admin.route('/users/delete/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    # Prevent deleting yourself
    if id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))

    user = User.query.get_or_404(id)
    try:
        # The permissions will be automatically deleted due to cascade
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    return redirect(url_for('admin.users'))


@admin.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access the admin panel.', 'danger')
        return redirect(url_for('main.index'))

    # Get or create system settings
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings()
        db.session.add(settings)
        db.session.commit()

    form = SettingsForm(obj=settings)

    if form.validate_on_submit():
        settings.company_name = form.company_name.data
        settings.company_address = form.company_address.data
        settings.company_phone = form.company_phone.data
        settings.company_email = form.company_email.data
        settings.company_website = form.company_website.data
        settings.default_currency = form.default_currency.data

        db.session.commit()
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', form=form, title='System Settings')
