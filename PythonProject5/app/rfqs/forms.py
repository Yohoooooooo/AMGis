from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Optional
from app.models import Client, Role


class RFQForm(FlaskForm):
    date_received = DateField('Date Received', validators=[DataRequired()])
    client_name = StringField('Client', validators=[DataRequired()])
    client_id = HiddenField('Client ID')
    contact_id = HiddenField('Contact ID')
    contact_person = StringField('Contact Person', validators=[DataRequired()])
    item_description = TextAreaField('Item Description', validators=[DataRequired()])
    bid_closing_date = DateField('Bid Closing Date', validators=[Optional()])
    proposal_status = SelectField('Proposal Status',
                                  choices=[('Pending', 'Pending'),
                                           ('Submitted', 'Submitted'),
                                           ('Purchase Order', 'Purchase Order'),
                                           ('Declined', 'Declined'),
                                           ('Lost', 'Lost')],
                                  default='Pending')
    remarks = TextAreaField('Remarks')
    attachments = FileField('Attachment (Optional)', validators=[
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx', 'jpg', 'png', 'xls', 'xlsx'],
                    'Only PDF, DOC, DOCX, JPG, PNG, XLS, and XLSX files are allowed!')
    ])
    submit = SubmitField('Submit')
    assigned_role = SelectField('Assigned Role', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        super(RFQForm, self).__init__(*args, **kwargs)
        # Dynamically populate assigned_role choices from database
        roles = Role.query.all()
        role_choices = [(role.code, role.code) for role in roles]

        # Set choices for the existing field
        self.assigned_role.choices = role_choices

