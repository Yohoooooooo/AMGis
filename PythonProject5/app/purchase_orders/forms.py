from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, FloatField, IntegerField, SubmitField, DateField, HiddenField
from wtforms.validators import DataRequired, Optional
from app.models import Client, RFQ

class PurchaseOrderForm(FlaskForm):
    # Purchase Order Details & Status
    rfq_id = SelectField('RFQ', coerce=int, validators=[Optional()])
    client_name = StringField('Client', validators=[DataRequired()])
    client_id = HiddenField('Client ID')
    contact_id = HiddenField('Contact ID')
    items_ordered = TextAreaField('Items Ordered', validators=[DataRequired()])
    currency = SelectField('Currency',
                           choices=[('PHP', '₱ Philippine Peso'),
                                    ('USD', '$ US Dollar'),
                                    ('EUR', '€ Euro'),
                                    ('JPY', '¥ Japanese Yen'),
                                    ('GBP', '£ British Pound')
    ], validators=[DataRequired()])
    total_amount = FloatField('Total Amount', validators=[DataRequired()])
    status = SelectField('Status',
                         choices=[('On Hold', 'On Hold'),
                                  ('On Process', 'On Process'),
                                  ('For Ordering', 'For Ordering'),
                                  ('For Collection', 'For Collection'),
                                  ('For Delivery', 'For Delivery'),
                                  ('Completed', 'Completed')],
                         default='On Hold')

    # Payment Details
    payment_terms = StringField('Payment Terms')
    payment_status = SelectField('Payment Status',
                               choices=[('Pending', 'Pending'),
                                       ('Partial', 'Partial'),
                                       ('Paid', 'Paid')],
                               default='Pending')

    # Delivery & Collection Details
    delivery_details = StringField('Delivery Details')
    delivery_address = TextAreaField('Delivery Address')
    delivery_date = DateField('Delivery Date', validators=[Optional()])
    collection_details = TextAreaField('Collection Details')
    collection_date = DateField('Collection Date', validators=[Optional()])

    # Additional fields
    remarks = TextAreaField('Remarks')

    attachments = FileField('Attachment (Optional)', validators=[
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx', 'jpg', 'png', 'xls', 'xlsx'], 'Only PDF, DOC, DOCX, JPG, PNG, XLS, and XLSX files are allowed!')
    ])

    submit = SubmitField('Submit')

    def __init__(self, *args, **kwargs):
        super(PurchaseOrderForm, self).__init__(*args, **kwargs)
        self.rfq_id.choices = [(0, 'None')] + [(r.id, f'RFQ #{r.id}') for r in RFQ.query.all()]

