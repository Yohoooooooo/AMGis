from flask import render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_required, current_user
from app.purchase_orders import purchase_orders
from app.purchase_orders.forms import PurchaseOrderForm
from app.models import PurchaseOrder, RFQ, Client, POAttachment, ContactPerson, Role
from app import db
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import or_, join


@purchase_orders.route('/')
@login_required
def index():
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view Purchase Orders.', 'danger')
        return redirect(url_for('main.index'))

    # Get search parameters
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status_filter')
    sort_order = request.args.get('sort_order', 'desc')
    role_filter = request.args.get('role', '')

    # Base query - join with RFQ and Role tables to get role information
    query = PurchaseOrder.query.outerjoin(RFQ, PurchaseOrder.rfq_id == RFQ.id)

    # Apply search if provided
    if search_query:
        search_term = f"%{search_query}%"
        query = query.join(PurchaseOrder.client).filter(
            or_(
                PurchaseOrder.items_ordered.ilike(search_term),
                PurchaseOrder.remarks.ilike(search_term),
                PurchaseOrder.status.ilike(search_term),
                Client.company_name.ilike(search_term)
            )
        )

    # Apply sorting
    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter)

    # Apply role filter if provided
    if role_filter:
        query = query.filter(RFQ.assigned_role == role_filter)

    # Execute query
    pos_list = query.all()

    # Check if search returned no results
    no_results = False
    if search_query and not pos_list:
        no_results = True
        search_query = ''  # Clear the search query
        pos_list = PurchaseOrder.query.outerjoin(RFQ, PurchaseOrder.rfq_id == RFQ.id).order_by(
            PurchaseOrder.last_updated.desc() if sort_order == 'desc' else PurchaseOrder.last_updated.asc()
        ).all()

    # Get all available roles for filtering
    roles = Role.query.all()
    role_choices = [(role.code, role.name) for role in roles]

    return render_template('purchase_orders/index.html',
                           purchase_orders=pos_list,
                           search_query=search_query,
                           status_filter=status_filter,
                           sort_order=sort_order,
                           role_filter=role_filter,
                           roles=role_choices,
                           no_results=no_results)


# Fix the add_po route to match the template
@purchase_orders.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    # Check if user has permission to add purchase orders
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add purchase orders.', 'danger')
        return redirect(url_for('purchase_orders.index'))

    form = PurchaseOrderForm()

    # Pre-populate from RFQ if provided
    rfq_id = request.args.get('rfq_id', type=int)
    if rfq_id and request.method == 'GET':
        # Check if RFQ already has a PO
        existing_po = PurchaseOrder.query.filter_by(rfq_id=rfq_id).first()
        if existing_po:
            flash('This RFQ already has a Purchase Order. Redirecting to the existing PO.', 'warning')
            return redirect(url_for('purchase_orders.view', id=existing_po.id))

        rfq = RFQ.query.get(rfq_id)
        if rfq:
            # Check if user has permission to create PO for this RFQ based on role
            if not current_user.is_admin() and not current_user.can_edit_role(rfq.assigned_role):
                flash('You do not have permission to create Purchase Orders for RFQs with this assigned role.',
                      'danger')
                return redirect(url_for('rfqs.view', id=rfq_id))

            form.rfq_id.data = rfq.id
            if rfq.client:
                form.client_name.data = rfq.client.company_name
                form.client_id.data = rfq.client_id
            form.items_ordered.data = rfq.item_description
            form.remarks.data = rfq.remarks

            # Set contact if available
            if rfq.contact_id:
                contact = ContactPerson.query.get(rfq.contact_id)
                if contact:
                    form.contact_id.data = contact.id

    if form.validate_on_submit():
        try:
            # Get or create client
            client_id = form.client_id.data
            if not client_id:
                # Check if client exists by name
                client = Client.query.filter_by(company_name=form.client_name.data).first()
                if not client:
                    # Store PO info in session and redirect to add client
                    session['pending_client'] = {
                        'name': form.client_name.data,
                        'redirect_after': 'purchase_orders.add_po',
                        'po_data': {
                            'rfq_id': form.rfq_id.data,
                            'items_ordered': form.items_ordered.data,
                            'total_amount': form.total_amount.data,
                            'payment_terms': form.payment_terms.data,
                            'payment_status': form.payment_status.data,
                            'delivery_details': form.delivery_details.data,
                            'delivery_address': form.delivery_address.data,
                            'delivery_date': form.delivery_date.data.strftime(
                                '%Y-%m-%d') if form.delivery_date.data else '',
                            'collection_details': form.collection_details.data,
                            'collection_date': form.collection_date.data.strftime(
                                '%Y-%m-%d') if form.collection_date.data else '',
                            'status': form.status.data,
                            'remarks': form.remarks.data
                        }
                    }
                    flash('Please add the client first before creating the Purchase Order.', 'info')
                    return redirect(url_for('clients.add_client'))
                client_id = client.id

            # Create purchase order
            # Validate contact_id exists in the database
            contact_id = None
            if form.contact_id.data:
                contact = ContactPerson.query.get(form.contact_id.data)
                if contact:
                    contact_id = contact.id

            po = PurchaseOrder(
                rfq_id=form.rfq_id.data if form.rfq_id.data != 0 else None,
                client_id=client_id,
                contact_id=contact_id,
                items_ordered=form.items_ordered.data,
                total_amount=form.total_amount.data,
                payment_terms=form.payment_terms.data,
                payment_status=form.payment_status.data,
                delivery_details=form.delivery_details.data,
                delivery_address=form.delivery_address.data,
                delivery_date=form.delivery_date.data,
                collection_details=form.collection_details.data,
                collection_date=form.collection_date.data,
                status=form.status.data,
                remarks=form.remarks.data,
                created_by_user_id=current_user.id  # Track who created this PO
            )
            db.session.add(po)
            db.session.flush()  # Get PO ID

            # Handle file uploads
            if form.attachments.data and hasattr(form.attachments.data, 'filename') and form.attachments.data.filename:
                file = form.attachments.data
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}_{original_filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                attachment = POAttachment(
                    po_id=po.id,
                    filename=filename,
                    original_filename=original_filename
                )
                db.session.add(attachment)

            # Update RFQ status if this PO is linked to an RFQ
            if form.rfq_id.data != 0:
                rfq = RFQ.query.get(form.rfq_id.data)
                if rfq:
                    rfq.proposal_status = 'Purchase Order'

            db.session.commit()
            flash('Purchase Order added successfully.', 'success')
            return redirect(url_for('purchase_orders.view', id=po.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding Purchase Order: {str(e)}', 'danger')

    return render_template('purchase_orders/form.html', form=form, title='Add Purchase Order')


@purchase_orders.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    po = PurchaseOrder.query.get_or_404(id)

    # Check if user has permission to edit purchase orders
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to edit purchase orders.', 'danger')
        return redirect(url_for('purchase_orders.view', id=id))

    # Check if this PO is linked to an RFQ and if user has permission to edit that RFQ's role
    if po.rfq_id and not current_user.is_admin():
        rfq = RFQ.query.get(po.rfq_id)
        if rfq and not current_user.can_edit_role(rfq.assigned_role):
            flash('You do not have permission to edit Purchase Orders for this sales person.', 'danger')
            return redirect(url_for('purchase_orders.view', id=id))

    # Check if user can edit this specific PO based on creator
    if not current_user.is_admin() and not current_user.can_edit_user_records(po.created_by_user_id,
                                                                              rfq.assigned_role if po.rfq_id and rfq else None):
        flash('You do not have permission to edit purchase orders created by other users.', 'danger')
        return redirect(url_for('purchase_orders.view', id=id))

    form = PurchaseOrderForm(obj=po)

    # Pre-populate client name
    if request.method == 'GET':
        form.client_name.data = po.client.company_name
        form.client_id.data = po.client_id
        if po.contact_id:
            form.contact_id.data = po.contact_id

    if form.validate_on_submit():
        try:
            # Get or create client
            client_id = form.client_id.data
            if not client_id or form.client_name.data != po.client.company_name:
                # Check if client exists by name
                client = Client.query.filter_by(company_name=form.client_name.data).first()
                if not client:
                    # Store PO info in session and redirect to add client
                    session['pending_client'] = {
                        'name': form.client_name.data,
                        'redirect_after': 'purchase_orders.edit',
                        'redirect_id': id,
                        'po_data': {
                            'rfq_id': form.rfq_id.data,
                            'items_ordered': form.items_ordered.data,
                            'total_amount': form.total_amount.data,
                            'payment_terms': form.payment_terms.data,
                            'payment_status': form.payment_status.data,
                            'delivery_details': form.delivery_details.data,
                            'delivery_address': form.delivery_address.data,
                            'delivery_date': form.delivery_date.data.strftime(
                                '%Y-%m-%d') if form.delivery_date.data else '',
                            'collection_details': form.collection_details.data,
                            'collection_date': form.collection_date.data.strftime(
                                '%Y-%m-%d') if form.collection_date.data else '',
                            'status': form.status.data,
                            'remarks': form.remarks.data
                        }
                    }
                    flash('Please add the client first before updating the Purchase Order.', 'info')
                    return redirect(url_for('clients.add'))
                client_id = client.id

            # Update purchase order
            # Validate contact_id exists in the database
            contact_id = None
            if form.contact_id.data:
                contact = ContactPerson.query.get(form.contact_id.data)
                if contact:
                    contact_id = contact.id

            po.rfq_id = form.rfq_id.data if form.rfq_id.data != 0 else None
            po.client_id = client_id
            po.contact_id = contact_id
            po.items_ordered = form.items_ordered.data
            po.total_amount = form.total_amount.data
            po.payment_terms = form.payment_terms.data
            po.payment_status = form.payment_status.data
            po.delivery_details = form.delivery_details.data
            po.delivery_address = form.delivery_address.data
            po.delivery_date = form.delivery_date.data
            po.collection_details = form.collection_details.data
            po.collection_date = form.collection_date.data
            po.status = form.status.data
            po.remarks = form.remarks.data

            # Handle file uploads
            if form.attachments.data and hasattr(form.attachments.data, 'filename') and form.attachments.data.filename:
                file = form.attachments.data
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}_{original_filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                attachment = POAttachment(
                    po_id=po.id,
                    filename=filename,
                    original_filename=original_filename
                )
                db.session.add(attachment)

            db.session.commit()
            flash('Purchase Order updated successfully.', 'success')
            return redirect(url_for('purchase_orders.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating Purchase Order: {str(e)}', 'danger')

    # Set rfq_id to 0 if None for the form
    if po.rfq_id is None:
        form.rfq_id.data = 0

    return render_template('purchase_orders/form.html', form=form, title='Edit Purchase Order',
                           attachments=po.attachments.all())


@purchase_orders.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    # Check if user has permission to edit (delete requires edit permission)
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to delete Purchase Orders.', 'danger')
        return redirect(url_for('purchase_orders.index'))

    po = PurchaseOrder.query.get_or_404(id)

    # Check if this PO is linked to an RFQ and if user has permission to edit that RFQ's role
    if po.rfq_id and not current_user.is_admin():
        rfq = RFQ.query.get(po.rfq_id)
        if rfq and not current_user.can_edit_role(rfq.assigned_role):
            flash('You do not have permission to delete Purchase Orders for this sales person.', 'danger')
            return redirect(url_for('purchase_orders.view', id=id))

    try:
        # Delete attachments
        for attachment in po.attachments:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], attachment.filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        db.session.delete(po)
        db.session.commit()
        flash('Purchase Order deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting Purchase Order: {str(e)}', 'danger')

    return redirect(url_for('purchase_orders.index'))


@purchase_orders.route('/view/<int:id>')
@login_required
def view(id):
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view Purchase Orders.', 'danger')
        return redirect(url_for('main.index'))

    po = PurchaseOrder.query.get_or_404(id)
    return render_template('purchase_orders/view.html', po=po)


@purchase_orders.route('/delete-attachment/<int:id>', methods=['POST'])
@login_required
def delete_attachment(id):
    # Check if user has permission to delete attachments
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to delete attachments.', 'danger')
        return redirect(url_for('purchase_orders.index'))

    attachment = POAttachment.query.get_or_404(id)
    po_id = attachment.po_id

    # Check if user can edit this specific PO based on role
    po = PurchaseOrder.query.get(po_id)
    if po.rfq_id and not current_user.is_admin():
        rfq = RFQ.query.get(po.rfq_id)
        if rfq and not current_user.can_edit_role(rfq.assigned_role):
            flash('You do not have permission to delete attachments for Purchase Orders with this sales person.',
                  'danger')
            return redirect(url_for('purchase_orders.view', id=po_id))

    try:
        # Delete file
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], attachment.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(attachment)
        db.session.commit()
        flash('Attachment deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting attachment: {str(e)}', 'danger')

    return redirect(url_for('purchase_orders.edit', id=po_id))


@purchase_orders.route('/get-clients')
@login_required
def get_clients():
    """API endpoint to get clients for autocomplete"""
    search = request.args.get('term', '')
    clients = Client.query.filter(Client.company_name.ilike(f'%{search}%')).all()
    results = [{'id': client.id, 'text': client.company_name} for client in clients]
    return jsonify(results)


@purchase_orders.route('/get-contacts/<int:client_id>')
@login_required
def get_contacts(client_id):
    """API endpoint to get contacts for a client"""
    client = Client.query.get_or_404(client_id)
    contacts = []
    for contact in client.contacts:
        # Get primary email, phone, and mobile if they exist
        primary_email = contact.primary_email()
        primary_phone = contact.primary_phone()
        primary_mobile = contact.primary_mobile()

        contact_info = {
            'id': contact.id,
            'name': contact.name,
            'position': contact.position or '',
            'email': primary_email.email if primary_email else '',
            'phone': primary_phone.phone if primary_phone else '',
            'mobile': primary_mobile.mobile if primary_mobile else ''
        }
        contacts.append(contact_info)
    return jsonify(contacts)
