from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, session
from flask_login import login_required, current_user
from app.rfqs import rfqs
from app.rfqs.forms import RFQForm
from app.models import RFQ, Client, ContactPerson, RFQAttachment, PurchaseOrder, ContactEmail, ContactPhone, \
    ContactMobile, Role
from app import db
from datetime import datetime
from sqlalchemy import or_, and_, join
import os
from werkzeug.utils import secure_filename


@rfqs.route('/')
@login_required
def index():
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view RFQs.', 'danger')
        return redirect(url_for('main.index'))

    # Get filter and sort parameters
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    role_filter = request.args.get('role', '')
    sort_by = request.args.get('sort_by', 'date_received')
    sort_order = request.args.get('sort_order', 'desc')

    # Clear search if requested
    if request.args.get('clear_search'):
        return redirect(url_for('rfqs.index'))

    # Base query - join with Role table to get role names
    query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code)

    # Apply search if provided
    if search_query:
        search_term = f"%{search_query}%"
        query = query.outerjoin(RFQ.client).filter(
            or_(
                RFQ.contact_person.ilike(search_term),
                RFQ.item_description.ilike(search_term),
                RFQ.remarks.ilike(search_term),
                Client.company_name.ilike(search_term)
            )
        )

    # Apply status filter
    if status_filter:
        query = query.filter(RFQ.proposal_status == status_filter)

    # Apply role filter
    if role_filter:
        query = query.filter(RFQ.assigned_role == role_filter)

    # Always exclude Lost, Declined, and Purchase Order RFQs from the main list
    if not status_filter or status_filter not in ['Lost', 'Declined', 'Purchase Order']:
        query = query.filter(~RFQ.proposal_status.in_(['Lost', 'Declined', 'Purchase Order']))

    # Apply sorting
    if sort_by == 'date_received':
        if sort_order == 'asc':
            query = query.order_by(RFQ.date_received.asc())
        else:
            query = query.order_by(RFQ.date_received.desc())
    elif sort_by == 'client':
        query = query.outerjoin(RFQ.client)
        if sort_order == 'asc':
            query = query.order_by(Client.company_name.asc())
        else:
            query = query.order_by(Client.company_name.desc())
    elif sort_by == 'status':
        if sort_order == 'asc':
            query = query.order_by(RFQ.proposal_status.asc())
        else:
            query = query.order_by(RFQ.proposal_status.desc())
    elif sort_by == 'role':
        if sort_order == 'asc':
            query = query.order_by(Role.name.asc())
        else:
            query = query.order_by(Role.name.desc())

    # Execute query
    rfqs_list = query.all()

    # Check if search returned no results
    no_results = False
    if search_query and not rfqs_list:
        no_results = True
        search_query = ''  # Clear the search query
        # Re-run the query without the search term
        query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code)
        if status_filter:
            query = query.filter(RFQ.proposal_status == status_filter)
        if role_filter:
            query = query.filter(RFQ.assigned_role == role_filter)
        if not status_filter or status_filter not in ['Lost', 'Declined', 'Purchase Order']:
            query = query.filter(~RFQ.proposal_status.in_(['Lost', 'Declined', 'Purchase Order']))
        rfqs_list = query.all()

    # Get all available roles for filtering
    roles = Role.query.all()
    role_choices = [(role.code, role.name) for role in roles]

    return render_template('rfqs/index.html',
                           rfqs=rfqs_list,
                           search_query=search_query,
                           status_filter=status_filter,
                           role_filter=role_filter,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           roles=role_choices,
                           no_results=no_results)


@rfqs.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    # Check if user has permission to add RFQs
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add RFQs.', 'danger')
        return redirect(url_for('rfqs.index'))

    form = RFQForm()
    if form.validate_on_submit():
        try:
            # Check if client exists by name
            client = None
            client_id = form.client_id.data
            if client_id:
                client = Client.query.get(client_id)

            # Check if contact exists
            contact = None
            contact_id = form.contact_id.data
            if contact_id:
                contact = ContactPerson.query.get(contact_id)

            # Create RFQ - allow it to proceed even if client/contact doesn't exist in database
            rfq = RFQ(
                date_received=form.date_received.data,
                client_id=client.id if client else None,
                contact_id=contact.id if contact else None,
                contact_person=form.contact_person.data,
                item_description=form.item_description.data,
                assigned_role=form.assigned_role.data,
                bid_closing_date=form.bid_closing_date.data,
                proposal_status=form.proposal_status.data,
                remarks=form.remarks.data,
                created_by_user_id=current_user.id  # Track who created this RFQ
            )

            # If client doesn't exist, store the client name in the RFQ
            if not client and form.client_name.data:
                rfq.client_name_temp = form.client_name.data

            db.session.add(rfq)
            db.session.flush()  # Get RFQ ID

            # Handle file uploads
            if form.attachments.data and hasattr(form.attachments.data, 'filename') and form.attachments.data.filename:
                file = form.attachments.data
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}_{original_filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                attachment = RFQAttachment(
                    rfq_id=rfq.id,
                    filename=filename,
                    original_filename=original_filename
                )
                db.session.add(attachment)

            db.session.commit()

            # Show appropriate message based on whether client exists
            if not client and form.client_name.data:
                flash('RFQ added successfully. Note: The client is not yet recorded in the database.', 'warning')
            else:
                flash('RFQ added successfully.', 'success')

            return redirect(url_for('rfqs.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding RFQ: {str(e)}', 'danger')

    # Pre-populate form from session if coming from client/contact creation
    if 'rfq_data' in session:
        rfq_data = session.pop('rfq_data', None)
        if rfq_data:
            if 'date_received' in rfq_data:
                form.date_received.data = datetime.strptime(rfq_data['date_received'], '%Y-%m-%d')
            if 'client_id' in rfq_data:
                form.client_id.data = rfq_data['client_id']
            if 'client_name' in rfq_data:
                form.client_name.data = rfq_data['client_name']
            if 'contact_id' in rfq_data:
                form.contact_id.data = rfq_data['contact_id']
            if 'contact_person' in rfq_data:
                form.contact_person.data = rfq_data['contact_person']
            if 'item_description' in rfq_data:
                form.item_description.data = rfq_data['item_description']
            if 'assigned_role' in rfq_data:
                form.assigned_role.data = rfq_data['assigned_role']
            if 'bid_closing_date' in rfq_data and rfq_data['bid_closing_date']:
                form.bid_closing_date.data = datetime.strptime(rfq_data['bid_closing_date'], '%Y-%m-%d')
            if 'proposal_status' in rfq_data:
                form.proposal_status.data = rfq_data['proposal_status']
            if 'remarks' in rfq_data:
                form.remarks.data = rfq_data['remarks']

    return render_template('rfqs/form.html', form=form, title='Add RFQ')


@rfqs.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    rfq = RFQ.query.get_or_404(id)

    # Check if user has permission to edit this RFQ
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to edit RFQs.', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    # Check if user can edit this specific RFQ based on assigned role and creator
    if not current_user.is_admin():
        # First check if user has permission for this role
        if not current_user.can_edit_role(rfq.assigned_role):
            flash('You do not have permission to edit RFQs with this assigned role.', 'danger')
            return redirect(url_for('rfqs.view', id=id))

        # Then check if user can edit records created by other users
        if not current_user.can_edit_user_records(rfq.created_by_user_id, rfq.assigned_role):
            flash('You do not have permission to edit RFQs created by other users.', 'danger')
            return redirect(url_for('rfqs.view', id=id))

    form = RFQForm(obj=rfq)

    # Pre-populate client name and contact person
    if request.method == 'GET':
        if rfq.client:
            form.client_name.data = rfq.client.company_name
            form.client_id.data = rfq.client_id
        elif hasattr(rfq, 'client_name_temp') and rfq.client_name_temp:
            form.client_name.data = rfq.client_name_temp
            form.client_id.data = None

        form.contact_id.data = rfq.contact_id
        if rfq.contact_id:
            contact = ContactPerson.query.get(rfq.contact_id)
            if contact:
                form.contact_person.data = contact.name
        else:
            form.contact_person.data = rfq.contact_person

    if form.validate_on_submit():
        try:
            # Check if client exists by name
            client = None
            client_id = form.client_id.data
            if client_id:
                client = Client.query.get(client_id)

            # Check if contact exists
            contact = None
            contact_id = form.contact_id.data
            if contact_id:
                contact = ContactPerson.query.get(contact_id)

            # Update RFQ - allow it to proceed even if client/contact doesn't exist in database
            rfq.date_received = form.date_received.data
            rfq.client_id = client.id if client else None
            rfq.contact_id = contact.id if contact else None
            rfq.contact_person = form.contact_person.data
            rfq.item_description = form.item_description.data
            rfq.assigned_role = form.assigned_role.data
            rfq.bid_closing_date = form.bid_closing_date.data
            rfq.proposal_status = form.proposal_status.data
            rfq.remarks = form.remarks.data

            # If client doesn't exist, store the client name in the RFQ
            if not client and form.client_name.data:
                rfq.client_name_temp = form.client_name.data
            else:
                # Clear temporary client name if a real client is selected
                if hasattr(rfq, 'client_name_temp'):
                    rfq.client_name_temp = None

            # Handle file uploads
            if form.attachments.data and hasattr(form.attachments.data, 'filename') and form.attachments.data.filename:
                file = form.attachments.data
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}_{original_filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                attachment = RFQAttachment(
                    rfq_id=rfq.id,
                    filename=filename,
                    original_filename=original_filename
                )
                db.session.add(attachment)

            db.session.commit()

            # Show appropriate message based on whether client exists
            if not client and form.client_name.data:
                flash('RFQ updated successfully. Note: The client is not yet recorded in the database.', 'warning')
            else:
                flash('RFQ updated successfully.', 'success')

            return redirect(url_for('rfqs.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating RFQ: {str(e)}', 'danger')

    # Pre-populate form from session if coming from client/contact creation
    if 'rfq_data' in session:
        rfq_data = session.pop('rfq_data', None)
        if rfq_data:
            if 'date_received' in rfq_data:
                form.date_received.data = datetime.strptime(rfq_data['date_received'], '%Y-%m-%d')
            if 'client_id' in rfq_data:
                form.client_id.data = rfq_data['client_id']
            if 'client_name' in rfq_data:
                form.client_name.data = rfq_data['client_name']
            if 'contact_id' in rfq_data:
                form.contact_id.data = rfq_data['contact_id']
            if 'contact_person' in rfq_data:
                form.contact_person.data = rfq_data['contact_person']
            if 'item_description' in rfq_data:
                form.item_description.data = rfq_data['item_description']
            if 'assigned_role' in rfq_data:
                form.assigned_role.data = rfq_data['assigned_role']
            if 'bid_closing_date' in rfq_data and rfq_data['bid_closing_date']:
                form.bid_closing_date.data = datetime.strptime(rfq_data['bid_closing_date'], '%Y-%m-%d')
            if 'proposal_status' in rfq_data:
                form.proposal_status.data = rfq_data['proposal_status']
            if 'remarks' in rfq_data:
                form.remarks.data = rfq_data['remarks']

    return render_template('rfqs/form.html', form=form, title='Edit RFQ', attachments=rfq.attachments.all())


@rfqs.route('/update-status/<int:id>', methods=['POST'])
@login_required
def update_status(id):
    # Get the RFQ ID from the form if it's coming from the index page
    rfq_id = request.form.get('rfq_id')
    if rfq_id:
        id = int(rfq_id)

    rfq = RFQ.query.get_or_404(id)

    # Check if user has permission to update status
    if not current_user.is_admin() and not current_user.can_update():
        flash('You do not have permission to update RFQ status.', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    # Check if user can update this specific RFQ based on assigned role
    if not current_user.is_admin() and not current_user.can_edit_role(rfq.assigned_role):
        flash('You do not have permission to update RFQs with this assigned role.', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    new_status = request.form.get('status')
    remarks = request.form.get('remarks')

    if not new_status:
        flash('No status provided', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    # Check if remarks are required for this status change
    if new_status in ['Submitted', 'Lost', 'Declined', 'Purchase Order'] and not remarks:
        flash(f'Remarks are required when changing status to {new_status}', 'warning')
        return redirect(url_for('rfqs.view', id=id))

    try:
        # If status is changed to Purchase Order, check if client and contact are in database
        if new_status == 'Purchase Order':
            # Check if RFQ already has a PO
            existing_po = PurchaseOrder.query.filter_by(rfq_id=id).first()
            if existing_po:
                flash('This RFQ already has a Purchase Order. Redirecting to the existing PO.', 'warning')
                return redirect(url_for('purchase_orders.view', id=existing_po.id))

            # Check if client is in database
            if not rfq.client_id:
                flash('You must add the client to the database before creating a Purchase Order.', 'warning')
                return redirect(url_for('rfqs.add_client_from_rfq', rfq_id=id))

            # Check if contact is in database
            if not rfq.contact_id and rfq.contact_person:
                flash('You must add the contact person to the database before creating a Purchase Order.', 'warning')
                # Store contact name in session for pre-populating the form
                session['pending_contact'] = {
                    'name': rfq.contact_person,
                    'client_id': rfq.client_id,
                    'redirect_after': 'rfqs.update_status',
                    'redirect_id': id,
                    'status': new_status
                }
                return redirect(url_for('clients.add_contact', client_id=rfq.client_id))

        rfq.proposal_status = new_status
        if remarks:
            rfq.remarks = remarks
        db.session.commit()
        flash(f'RFQ status updated to {new_status}', 'success')

        # If status is changed to Purchase Order, redirect to create PO form
        if new_status == 'Purchase Order':
            if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                return redirect(url_for('purchase_orders.add', rfq_id=id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'danger')

    # For AJAX requests, return a JSON response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})

    # Check if the request came from the index page
    if rfq_id:
        return redirect(url_for('rfqs.index'))

    return redirect(url_for('rfqs.view', id=id))


@rfqs.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    # Check if user has permission to edit (delete requires edit permission)
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to delete RFQs.', 'danger')
        return redirect(url_for('rfqs.index'))

    rfq = RFQ.query.get_or_404(id)

    # Check if user can delete this specific RFQ based on assigned role
    if not current_user.is_admin() and not current_user.can_edit_role(rfq.assigned_role):
        flash('You do not have permission to delete RFQs with this assigned role.', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    try:
        # Delete attachments
        for attachment in rfq.attachments:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], attachment.filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        db.session.delete(rfq)
        db.session.commit()
        flash('RFQ deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting RFQ: {str(e)}', 'danger')
    return redirect(url_for('rfqs.index'))


@rfqs.route('/view/<int:id>')
@login_required
def view(id):
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view RFQs.', 'danger')
        return redirect(url_for('main.index'))

    rfq = RFQ.query.get_or_404(id)

    # Get all available roles for the dropdown
    roles = Role.query.all()
    role_choices = [(role.code, role.name) for role in roles]

    # Get role name for the assigned role
    role_name = None
    if rfq.assigned_role:
        role = Role.query.filter_by(code=rfq.assigned_role).first()
        if role:
            role_name = role.name

    # Get contact details if contact_id is available
    contact_details = None
    if rfq.contact_id:
        contact = ContactPerson.query.get(rfq.contact_id)
        if contact:
            contact_details = {
                'name': contact.name,
                'position': contact.position,
                'emails': [email.email for email in contact.emails] if contact.emails else [],
                'phones': [phone.phone for phone in contact.phones] if contact.phones else [],
                'mobiles': [mobile.mobile for mobile in contact.mobiles] if contact.mobiles else []
            }

    # Check if client exists in database
    client_in_db = rfq.client_id is not None

    # Get client name (either from database or temporary field)
    client_name = rfq.client.company_name if rfq.client else (
        rfq.client_name_temp if hasattr(rfq, 'client_name_temp') and rfq.client_name_temp else "Unknown Client"
    )

    return render_template('rfqs/view.html',
                           rfq=rfq,
                           roles=role_choices,
                           role_name=role_name,
                           contact_details=contact_details,
                           client_in_db=client_in_db,
                           client_name=client_name)


@rfqs.route('/delete-attachment/<int:id>', methods=['POST'])
@login_required
def delete_attachment(id):
    # Check if user has permission to delete
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to delete attachments.', 'danger')
        return redirect(url_for('rfqs.index'))

    attachment = RFQAttachment.query.get_or_404(id)
    rfq_id = attachment.rfq_id

    # Check if user can edit this specific RFQ based on assigned role
    rfq = RFQ.query.get(rfq_id)
    if not current_user.is_admin() and not current_user.can_edit_role(rfq.assigned_role):
        flash('You do not have permission to delete attachments for RFQs with this assigned role.', 'danger')
        return redirect(url_for('rfqs.view', id=rfq_id))

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

    return redirect(url_for('rfqs.edit', id=rfq_id))


@rfqs.route('/restore/<int:id>', methods=['POST'])
@login_required
def restore(id):
    # Check if user has permission to update
    if not current_user.is_admin() and not current_user.can_update():
        flash('You do not have permission to restore RFQs.', 'danger')
        return redirect(url_for('rfqs.lost_declined'))

    rfq = RFQ.query.get_or_404(id)

    # Check if user can update this specific RFQ based on assigned role
    if not current_user.is_admin() and not current_user.can_edit_role(rfq.assigned_role):
        flash('You do not have permission to restore RFQs with this assigned role.', 'danger')
        return redirect(url_for('rfqs.view', id=id))

    if rfq.proposal_status not in ['Lost', 'Declined']:
        flash('Only Lost or Declined RFQs can be restored.', 'warning')
    else:
        rfq.proposal_status = 'Pending'
        rfq.is_restored = True
        db.session.commit()
        flash('RFQ restored successfully.', 'success')

    return redirect(url_for('rfqs.lost_declined'))


@rfqs.route('/lost-declined')
@login_required
def lost_declined():
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view RFQs.', 'danger')
        return redirect(url_for('main.index'))

    # Get filter parameters
    search_query = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')

    # Clear search if requested
    if request.args.get('clear_search'):
        return redirect(url_for('rfqs.lost_declined'))

    # Base query - only show Lost and Declined
    query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code).filter(
        RFQ.proposal_status.in_(['Lost', 'Declined']))

    # Apply search if provided
    if search_query:
        search_term = f"%{search_query}%"
        query = query.outerjoin(RFQ.client).filter(
            or_(
                RFQ.contact_person.ilike(search_term),
                RFQ.item_description.ilike(search_term),
                RFQ.remarks.ilike(search_term),
                Client.company_name.ilike(search_term)
            )
        )

    # Apply role filter
    if role_filter:
        query = query.filter(RFQ.assigned_role == role_filter)

    # Apply status filter (Lost or Declined)
    if status_filter:
        query = query.filter(RFQ.proposal_status == status_filter)

    # Execute query
    rfqs_list = query.all()

    # Check if search returned no results
    no_results = False
    if search_query and not rfqs_list:
        no_results = True
        search_query = ''  # Clear the search query
        # Re-run the query without the search term
        query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code).filter(
            RFQ.proposal_status.in_(['Lost', 'Declined']))
        if role_filter:
            query = query.filter(RFQ.assigned_role == role_filter)
        if status_filter:
            query = query.filter(RFQ.proposal_status == status_filter)
        rfqs_list = query.all()

    # Get all available roles for filtering
    roles = Role.query.all()
    role_choices = [(role.code, role.name) for role in roles]

    return render_template('rfqs/lost_declined.html',
                           rfqs=rfqs_list,
                           search_query=search_query,
                           role_filter=role_filter,
                           status_filter=status_filter,
                           roles=role_choices,
                           no_results=no_results)


@rfqs.route('/purchase-orders')
@login_required
def purchase_orders():
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view RFQs.', 'danger')
        return redirect(url_for('main.index'))

    # Get filter parameters
    search_query = request.args.get('search', '')
    role_filter = request.args.get('role', '')

    # Clear search if requested
    if request.args.get('clear_search'):
        return redirect(url_for('rfqs.purchase_orders'))

    # Base query - only show Purchase Order status
    query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code).filter(RFQ.proposal_status == 'Purchase Order')

    # Apply search if provided
    if search_query:
        search_term = f"%{search_query}%"
        query = query.outerjoin(RFQ.client).filter(
            or_(
                RFQ.contact_person.ilike(search_term),
                RFQ.item_description.ilike(search_term),
                RFQ.remarks.ilike(search_term),
                Client.company_name.ilike(search_term)
            )
        )

    # Apply role filter
    if role_filter:
        query = query.filter(RFQ.assigned_role == role_filter)

    # Execute query
    rfqs_list = query.all()

    # Check if search returned no results
    no_results = False
    if search_query and not rfqs_list:
        no_results = True
        search_query = ''  # Clear the search query
        # Re-run the query without the search term
        query = RFQ.query.outerjoin(Role, RFQ.assigned_role == Role.code).filter(
            RFQ.proposal_status == 'Purchase Order')
        if role_filter:
            query = query.filter(RFQ.assigned_role == role_filter)
        rfqs_list = query.all()

    # Get all available roles for filtering
    roles = Role.query.all()
    role_choices = [(role.code, role.name) for role in roles]

    return render_template('rfqs/purchase_orders.html',
                           rfqs=rfqs_list,
                           search_query=search_query,
                           role_filter=role_filter,
                           roles=role_choices,
                           no_results=no_results)


@rfqs.route('/add-client/<int:rfq_id>', methods=['GET'])
@login_required
def add_client_from_rfq(rfq_id):
    """Add client from RFQ"""
    # Check if user has permission to add clients
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add clients.', 'danger')
        return redirect(url_for('rfqs.index'))

    rfq = RFQ.query.get_or_404(rfq_id)

    # Get client name from RFQ
    client_name = rfq.client_name_temp if hasattr(rfq,
                                                  'client_name_temp') and rfq.client_name_temp else "Unknown Client"

    # Store RFQ info in session
    session['pending_client'] = {
        'name': client_name,
        'redirect_after': 'rfqs.view',
        'redirect_id': rfq_id
    }

    # Redirect to add client form
    return redirect(url_for('clients.add', name=client_name))


@rfqs.route('/get-clients')
@login_required
def get_clients():
    """API endpoint to get clients for autocomplete"""
    search = request.args.get('term', '')
    clients = Client.query.filter(Client.company_name.ilike(f'%{search}%')).all()
    results = [{'id': client.id, 'text': client.company_name} for client in clients]
    return jsonify(results)


@rfqs.route('/get-contacts/<int:client_id>')
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
