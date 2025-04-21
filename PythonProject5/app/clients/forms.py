from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, BooleanField, FieldList, FormField, HiddenField
from wtforms.validators import DataRequired, Email, Optional, ValidationError
from app.models import Client, ContactPerson  # Changed from Contact to ContactPerson


class EmailForm(FlaskForm):
    email = StringField('Email', validators=[Optional(), Email()])

    class Meta:
        csrf = False


class PhoneForm(FlaskForm):
    phone = StringField('Phone')

    class Meta:
        csrf = False


class MobileForm(FlaskForm):
    mobile = StringField('Mobile')

    class Meta:
        csrf = False


class ContactPersonForm(FlaskForm):  # Changed from ContactForm to ContactPersonForm
    name = StringField('Full Name', validators=[DataRequired()])  # Changed from full_name to name
    position = StringField('Position', validators=[Optional()])
    is_primary = BooleanField('Primary Contact')
    client_id = HiddenField()  # Added to store client_id

    # Contact details
    emails = FieldList(FormField(EmailForm), min_entries=1)
    phones = FieldList(FormField(PhoneForm), min_entries=1)
    mobiles = FieldList(FormField(MobileForm), min_entries=1)

    submit = SubmitField('Save Contact')  # Added submit button

    def __init__(self, *args, **kwargs):
        super(ContactPersonForm, self).__init__(*args, **kwargs)
        # Ensure we have at least one entry for each field list
        if len(self.emails) == 0:
            self.emails.append_entry()
        if len(self.phones) == 0:
            self.phones.append_entry()
        if len(self.mobiles) == 0:
            self.mobiles.append_entry()

    class Meta:
        csrf = False


class ClientForm(FlaskForm):
    company_name = StringField('Company Name', validators=[DataRequired()])
    company_address = TextAreaField('Company Address', validators=[Optional()])
    company_website = StringField('Website', validators=[Optional()])
    industry = StringField('Industry', validators=[Optional()])

    # Nested contact forms
    contacts = FieldList(FormField(ContactPersonForm), min_entries=1)  # Changed from ContactForm to ContactPersonForm

    submit = SubmitField('Submit')


class CombinedClientContactForm(FlaskForm):
    # Client fields
    company_name = StringField('Company Name', validators=[DataRequired()])
    company_address = TextAreaField('Company Address', validators=[Optional()])
    company_website = StringField('Website', validators=[Optional()])
    industry = StringField('Industry', validators=[Optional()])

    # Contact fields
    name = StringField('Full Name', validators=[DataRequired()])  # Changed from full_name to name
    position = StringField('Position', validators=[Optional()])

    # Contact details
    emails = FieldList(FormField(EmailForm), min_entries=1)
    phones = FieldList(FormField(PhoneForm), min_entries=1)
    mobiles = FieldList(FormField(MobileForm), min_entries=1)

    submit = SubmitField('Save')

    def __init__(self, *args, original_company_name=None, **kwargs):
        super(CombinedClientContactForm, self).__init__(*args, **kwargs)
        self.original_company_name = original_company_name

    def validate_company_name(self, field):
        if field.data != self.original_company_name:
            client = Client.query.filter_by(company_name=field.data).first()
            if client:
                raise ValidationError('Company name already exists. Please use a different name.')


class ContactEmailForm(FlaskForm):
    contact_id = HiddenField()
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Add Email')


class ContactPhoneForm(FlaskForm):
    contact_id = HiddenField()
    phone = StringField('Phone Number', validators=[DataRequired()])
    submit = SubmitField('Add Phone')


class ContactMobileForm(FlaskForm):
    contact_id = HiddenField()
    mobile = StringField('Mobile Number', validators=[DataRequired()])
    submit = SubmitField('Add Mobile')

