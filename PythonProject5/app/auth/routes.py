from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app.auth import auth
from app.auth.forms import LoginForm, RegistrationForm
from app.models import User, UserPermission
from app import db
import logging


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        # Print form data for debugging
        print(f"Login attempt - Username: {form.username.data}")

        user = User.query.filter_by(username=form.username.data).first()

        # Debug logging
        if user:
            print(f"User found: {user.username}, ID: {user.id}")
            print(f"Password hash: {user.password_hash}")
            password_check = user.check_password(form.password.data)
            print(f"Password check result: {password_check}")
        else:
            print(f"No user found with username: {form.username.data}")

        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account is inactive. Please contact an administrator.', 'danger')
            return redirect(url_for('auth.login'))

        # Login the user
        login_user(user, remember=form.remember_me.data)
        print(f"User logged in successfully: {user.username}")

        # Create default permissions if they don't exist
        if not user.permissions and not user.is_admin():
            permissions = UserPermission(
                user_id=user.id,
                can_view=True,
                can_add=False,
                can_edit=False,
                can_update=False,
                edit_scope='all',
                allowed_roles='all'
            )
            db.session.add(permissions)
            db.session.commit()
            print(f"Created default permissions for user: {user.username}")

        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')

        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(next_page)

    return render_template('auth/login.html', title='Sign In', form=form)


@auth.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Register', form=form)


@auth.route('/reset-admin', methods=['GET'])
def reset_admin():
    """Emergency route to reset admin password"""
    try:
        admin = User.query.filter_by(username='admin').first()
        if admin:
            admin.set_password('adminpassword')
            db.session.commit()
            flash('Admin password has been reset to "adminpassword"', 'success')
        else:
            # Create admin if it doesn't exist
            admin = User(username='admin', role='admin', is_active=True)
            admin.set_password('adminpassword')
            db.session.add(admin)
            db.session.commit()
            flash('Admin account created with password "adminpassword"', 'success')
    except Exception as e:
        flash(f'Error resetting admin password: {str(e)}', 'danger')

    return redirect(url_for('auth.login'))
