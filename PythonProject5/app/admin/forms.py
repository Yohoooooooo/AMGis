from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField, SelectMultipleField, widgets
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length, Optional
from app.models import User, Role


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=3)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[('employee', 'Employee'), ('admin', 'Administrator')])
    is_active = BooleanField('Active', default=True)

    # Permission fields
    can_view = BooleanField('View Only', default=True)
    can_add = BooleanField('Can Add', default=False)
    can_edit = BooleanField('Can Edit', default=False)
    can_update = BooleanField('Can Update', default=False)
    allowed_roles = MultiCheckboxField('Limit Edits To', coerce=str)

    submit = SubmitField('Add User')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already exists. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already exists. Please choose a different one.')


class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('password')])
    role = SelectField('Role', choices=[('employee', 'Employee'), ('admin', 'Administrator')])
    is_active = BooleanField('Active', default=True)

    # Permission fields
    can_view = BooleanField('View Only', default=True)
    can_add = BooleanField('Can Add', default=False)
    can_edit = BooleanField('Can Edit', default=False)
    can_update = BooleanField('Can Update', default=False)
    allowed_roles = MultiCheckboxField('Limit Edits To', coerce=str)

    submit = SubmitField('Update User')

    def __init__(self, original_username=None, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Username already exists. Please choose a different one.')


class RoleForm(FlaskForm):
    code = StringField('Role Code', validators=[DataRequired(), Length(min=2, max=10)])
    name = StringField('Role Name', validators=[DataRequired(), Length(min=2, max=50)])
    submit = SubmitField('Save Role')

    def __init__(self, original_code=None, *args, **kwargs):
        super(RoleForm, self).__init__(*args, **kwargs)
        self.original_code = original_code

    def validate_code(self, code):
        if self.original_code is None or code.data != self.original_code:
            role = Role.query.filter_by(code=code.data).first()
            if role:
                raise ValidationError('Role code already exists. Please choose a different one.')


class SettingsForm(FlaskForm):
    company_name = StringField('Company Name', validators=[DataRequired(), Length(max=100)])
    company_address = TextAreaField('Company Address', validators=[Optional(), Length(max=200)])
    company_phone = StringField('Company Phone', validators=[Optional(), Length(max=20)])
    company_email = StringField('Company Email', validators=[Optional(), Email(), Length(max=100)])
    company_website = StringField('Company Website', validators=[Optional(), Length(max=100)])
    default_currency = StringField('Default Currency', validators=[Optional(), Length(max=10)])
    submit = SubmitField('Save Settings')
