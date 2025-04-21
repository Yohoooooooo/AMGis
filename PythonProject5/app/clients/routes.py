from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, session
from flask_login import login_required, current_user
from app.clients import clients
from app.clients.forms import CombinedClientContactForm, ContactPersonForm, ContactEmailForm, ContactPhoneForm, \
    ContactMobileForm, EmailForm, PhoneForm, MobileForm
from app.models import Client, ContactPerson, ContactEmail, ContactPhone, ContactMobile, RFQ, PurchaseOrder
from app import db
from sqlalchemy import or_
import traceback
import os
from werkzeug.utils import secure_filename
from datetime import datetime


@clients.route('/')
@login_required
def index():
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view clients.', 'danger')
        return redirect(url_for('main.index'))

    # Get search parameters
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'company_name')
    sort_order = request.args.get('sort_order', 'asc')

    # Clear search if requested
    if request.args.get('clear_search'):
        return redirect(url_for('clients.index'))

    # Base query
    query = Client.query

    # Apply search if provided
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                Client.company_name.ilike(search_term),
                Client.company_address.ilike(search_term),
                Client.company_website.ilike(search_term),
                Client.industry.ilike(search_term)
            )
        )

    # Apply sorting
    if sort_by == 'company_name':
        if sort_order == 'desc':
            query = query.order_by(Client.company_name.desc())
        else:
            query = query.order_by(Client.company_name.asc())
    elif sort_by == 'date_created':
        if sort_order == 'desc':
            query = query.order_by(Client.date_created.desc())
        else:
            query = query.order_by(Client.date_created.asc())
    elif sort_by == 'last_updated':
        if sort_order == 'desc':
            query = query.order_by(Client.last_updated.desc())
        else:
            query = query.order_by(Client.last_updated.asc())
    elif sort_by == 'industry':
        if sort_order == 'desc':
            query = query.order_by(Client.industry.desc())
        else:
            query = query.order_by(Client.industry.asc())

    # Execute query
    clients_list = query.all()

    # Check if search returned no results
    no_results = False
    if search_query and not clients_list:
        no_results = True
        search_query = ''  # Clear the search query
        clients_list = Client.query.all()  # Get all clients instead

    return render_template('clients/index.html',
                           clients=clients_list,
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           no_results=no_results)


@clients.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    # Check if user has permission to add
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add clients.', 'danger')
        return redirect(url_for('clients.index'))

    form = CombinedClientContactForm()

    # Check if there's pending client data in session
    pending_client = session.pop('pending_client', None)
    if pending_client and request.method == 'GET':
        form.company_name.data = pending_client.get('name', '')

    # Check if name is provided in URL (from "New" button)
    client_name = request.args.get('name', '')
    if client_name and request.method == 'GET':
        form.company_name.data = client_name

    # Handle dynamic form actions (add email, phone, mobile)
    if request.method == 'POST':
        if 'add_email' in request.form:
            form.emails.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Add Client & Contact')

        if 'add_phone' in request.form:
            form.phones.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Add Client & Contact')

        if 'add_mobile' in request.form:
            form.mobiles.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Add Client & Contact')

        # Save form state if minimize button is clicked
        if 'minimize_form' in request.form:
            form_data = {
                'company_name': form.company_name.data,
                'company_address': form.company_address.data,
                'company_website': form.company_website.data,
                'industry': form.industry.data,
                'name': form.name.data,
                'position': form.position.data,
                'emails': [email_form.email.data for email_form in form.emails],
                'phones': [phone_form.phone.data for phone_form in form.phones],
                'mobiles': [mobile_form.mobile.data for mobile_form in form.mobiles]
            }
            session['minimized_client_form'] = form_data
            flash('Form has been minimized. You can continue later from the dashboard.', 'info')
            return redirect(url_for('main.index'))

        # Regular form submission - validate and save
        if form.validate_on_submit():
            try:
                # Create client
                client = Client(
                    company_name=form.company_name.data,
                    company_address=form.company_address.data,
                    company_website=form.company_website.data,
                    industry=form.industry.data
                )
                db.session.add(client)
                db.session.flush()  # Get client ID

                # Create contact
                contact = ContactPerson(
                    client_id=client.id,
                    name=form.name.data,
                    position=form.position.data
                )
                db.session.add(contact)
                db.session.flush()  # Get contact ID

                # Process emails
                for email_form in form.emails:
                    if email_form.email.data:  # Only add if email is provided
                        email = ContactEmail(
                            contact_id=contact.id,
                            email=email_form.email.data
                        )
                        db.session.add(email)

                # Process phones
                for phone_form in form.phones:
                    if phone_form.phone.data:  # Only add if phone is provided
                        phone = ContactPhone(
                            contact_id=contact.id,
                            phone=phone_form.phone.data
                        )
                        db.session.add(phone)

                # Process mobiles
                for mobile_form in form.mobiles:
                    if mobile_form.mobile.data:  # Only add if mobile is provided
                        mobile = ContactMobile(
                            contact_id=contact.id,
                            mobile=mobile_form.mobile.data
                        )
                        db.session.add(mobile)

                db.session.commit()
                flash('Client and contact added successfully.', 'success')

                # Check if we need to redirect to another page after adding client
                if pending_client and 'redirect_after' in pending_client:
                    redirect_route = pending_client.get('redirect_after')

                    # Store RFQ data in session if needed
                    if 'rfq_data' in pending_client:
                        rfq_data = pending_client.get('rfq_data', {})
                        rfq_data['client_id'] = client.id
                        rfq_data['client_name'] = client.company_name
                        session['rfq_data'] = rfq_data

                    # Handle redirect with ID if needed
                    if 'redirect_id' in pending_client:
                        redirect_id = pending_client.get('redirect_id')
                        return redirect(url_for(redirect_route, id=redirect_id))

                    # Handle redirect with rfq_id if needed
                    if 'rfq_id' in pending_client:
                        rfq_id = pending_client.get('rfq_id')
                        return redirect(url_for(redirect_route, rfq_id=rfq_id))

                    return redirect(url_for(redirect_route))

                # Clear minimized form data if it exists
                if 'minimized_client_form' in session:
                    session.pop('minimized_client_form')

                return redirect(url_for('clients.contacts', client_id=client.id))
            except Exception as e:
                db.session.rollback()
                print(traceback.format_exc())  # Print detailed error for debugging
                flash(f'Error adding client and contact: {str(e)}', 'danger')

    # Restore form data if it was minimized
    if 'minimized_client_form' in session and request.method == 'GET':
        form_data = session.get('minimized_client_form')
        form.company_name.data = form_data.get('company_name', '')
        form.company_address.data = form_data.get('company_address', '')
        form.company_website.data = form_data.get('company_website', '')
        form.industry.data = form_data.get('industry', '')
        form.name.data = form_data.get('name', '')
        form.position.data = form_data.get('position', '')

        # Clear default entries
        while len(form.emails) > 0:
            form.emails.pop_entry()
        while len(form.phones) > 0:
            form.phones.pop_entry()
        while len(form.mobiles) > 0:
            form.mobiles.pop_entry()

        # Add saved emails
        for email in form_data.get('emails', []):
            if email:
                email_form = EmailForm()
                email_form.email.data = email
                form.emails.append_entry(email_form.data)

        # Add saved phones
        for phone in form_data.get('phones', []):
            if phone:
                phone_form = PhoneForm()
                phone_form.phone.data = phone
                form.phones.append_entry(phone_form.data)

        # Add saved mobiles
        for mobile in form_data.get('mobiles', []):
            if mobile:
                mobile_form = MobileForm()
                mobile_form.mobile.data = mobile
                form.mobiles.append_entry(mobile_form.data)

        # Ensure at least one entry for each
        if len(form.emails) == 0:
            form.emails.append_entry()
        if len(form.phones) == 0:
            form.phones.append_entry()
        if len(form.mobiles) == 0:
            form.mobiles.append_entry()

        flash('Your minimized form has been restored. You can continue where you left off.', 'info')

    return render_template('clients/combined_form.html', form=form, title='Add Client & Contact')


@clients.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    # Check if user has permission to edit
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to edit clients.', 'danger')
        return redirect(url_for('clients.index'))

    client = Client.query.get_or_404(id)

    # Check if user has permission to edit clients
    # if not current_user.is_admin() and not current_user.can_edit():
    #    flash('You do not have permission to edit clients.', 'danger')
    #    return redirect(url_for('clients.view', id=id))

    form = CombinedClientContactForm(obj=client, original_company_name=client.company_name)

    # Pre-populate the form with existing contact if available
    contact = client.contacts.first()

    if request.method == 'GET':
        form.name.data = contact.name if contact else ""
        form.position.data = contact.position if contact else ""

        # Clear default entries
        while len(form.emails) > 0:
            form.emails.pop_entry()

        while len(form.phones) > 0:
            form.phones.pop_entry()

        while len(form.mobiles) > 0:
            form.mobiles.pop_entry()

        # Add emails
        if contact:
            for email in contact.emails:
                email_form = EmailForm()
                email_form.email.data = email.email
                form.emails.append_entry(email_form.data)

            # Add phones
            for phone in contact.phones:
                phone_form = PhoneForm()
                phone_form.phone.data = phone.phone
                form.phones.append_entry(phone_form.data)

            # Add mobiles
            for mobile in contact.mobiles:
                mobile_form = ContactMobileForm()
                mobile_form.mobile.data = mobile.mobile
                form.mobiles.append_entry(mobile_form.data)

        # If no emails/phones/mobiles, add empty entry
        if len(form.emails) == 0:
            form.emails.append_entry()
        if len(form.phones) == 0:
            form.phones.append_entry()
        if len(form.mobiles) == 0:
            form.mobiles.append_entry()

    # Handle dynamic form actions
    if request.method == 'POST':
        if 'add_email' in request.form:
            form.emails.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Edit Client & Contact',
                                   client=client)

        if 'add_phone' in request.form:
            form.phones.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Edit Client & Contact',
                                   client=client)

        if 'add_mobile' in request.form:
            form.mobiles.append_entry()
            return render_template('clients/combined_form.html', form=form, title='Edit Client & Contact',
                                   client=client)

        # Save form state if minimize button is clicked
        if 'minimize_form' in request.form:
            form_data = {
                'client_id': client.id,
                'company_name': form.company_name.data,
                'company_address': form.company_address.data,
                'company_website': form.company_website.data,
                'industry': form.industry.data,
                'name': form.name.data,
                'position': form.position.data,
                'emails': [email_form.email.data for email_form in form.emails],
                'phones': [phone_form.phone.data for phone_form in form.phones],
                'mobiles': [mobile_form.mobile.data for mobile_form in form.mobiles],
                'contact_id': contact.id if contact else None
            }
            session['minimized_client_edit_form'] = form_data
            flash('Form has been minimized. You can continue later from the dashboard.', 'info')
            return redirect(url_for('main.index'))

        # Regular form submission
        if form.validate_on_submit():
            try:
                # Update client
                client.company_name = form.company_name.data
                client.company_address = form.company_address.data
                client.company_website = form.company_website.data
                client.industry = form.industry.data

                # Update or create contact
                if contact:
                    contact.name = form.name.data
                    contact.position = form.position.data

                    # Delete existing contact details
                    for email in contact.emails:
                        db.session.delete(email)

                    for phone in contact.phones:
                        db.session.delete(phone)

                    for mobile in contact.mobiles:
                        db.session.delete(mobile)
                else:
                    contact = ContactPerson(
                        client_id=client.id,
                        name=form.name.data,
                        position=form.position.data
                    )
                    db.session.add(contact)
                    db.session.flush()  # Get contact ID

                # Process emails
                for email_form in form.emails:
                    if email_form.email.data:  # Only add if email is provided
                        email = ContactEmail(
                            contact_id=contact.id,
                            email=email_form.email.data
                        )
                        db.session.add(email)

                # Process phones
                for phone_form in form.phones:
                    if phone_form.phone.data:  # Only add if phone is provided
                        phone = ContactPhone(
                            contact_id=contact.id,
                            phone=phone_form.phone.data
                        )
                        db.session.add(phone)

                # Process mobiles
                for mobile_form in form.mobiles:
                    if mobile_form.mobile.data:  # Only add if mobile is provided
                        mobile = ContactMobile(
                            contact_id=contact.id,
                            mobile=mobile_form.mobile.data
                        )
                        db.session.add(mobile)

                db.session.commit()
                flash('Client and contact updated successfully.', 'success')

                # Clear minimized form data if it exists
                if 'minimized_client_edit_form' in session:
                    session.pop('minimized_client_edit_form')

                return redirect(url_for('clients.contacts', client_id=client.id))
            except Exception as e:
                db.session.rollback()
                print(traceback.format_exc())  # Print detailed error for debugging
                flash(f'Error updating client and contact: {str(e)}', 'danger')

    # Restore form data if it was minimized
    if 'minimized_client_edit_form' in session and request.method == 'GET':
        form_data = session.get('minimized_client_edit_form')
        if form_data.get('client_id') == id:  # Make sure we're restoring the right form
            form.company_name.data = form_data.get('company_name', '')
            form.company_address.data = form_data.get('company_address', '')
            form.company_website.data = form_data.get('company_website', '')
            form.industry.data = form_data.get('industry', '')
            form.name.data = form_data.get('name', '')
            form.position.data = form_data.get('position', '')

            # Clear default entries
            while len(form.emails) > 0:
                form.emails.pop_entry()
            while len(form.phones) > 0:
                form.phones.pop_entry()
            while len(form.mobiles) > 0:
                form.mobiles.pop_entry()

            # Add saved emails
            for email in form_data.get('emails', []):
                if email:
                    email_form = EmailForm()
                    email_form.email.data = email
                    form.emails.append_entry(email_form.data)

            # Add saved phones
            for phone in form_data.get('phones', []):
                if phone:
                    phone_form = PhoneForm()
                    phone_form.phone.data = phone
                    form.phones.append_entry(phone_form.data)

            # Add saved mobiles
            for mobile in form_data.get('mobiles', []):
                if mobile:
                    mobile_form = ContactMobileForm()
                    mobile_form.mobile.data = mobile
                    form.mobiles.append_entry(mobile_form.data)

            # Ensure at least one entry for each
            if len(form.emails) == 0:
                form.emails.append_entry()
            if len(form.phones) == 0:
                form.phones.append_entry()
            if len(form.mobiles) == 0:
                form.mobiles.append_entry()

            flash('Your minimized form has been restored. You can continue where you left off.', 'info')

    return render_template('clients/combined_form.html', form=form, title='Edit Client & Contact', client=client)


@clients.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    # Check if user has permission to edit (delete requires edit permission)
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to delete clients.', 'danger')
        return redirect(url_for('clients.index'))

    client = Client.query.get_or_404(id)
    try:
        db.session.delete(client)
        db.session.commit()
        flash('Client deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting client: {str(e)}', 'danger')
    return redirect(url_for('clients.index'))


@clients.route('/view/<int:id>')
@login_required
def view(id):
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view clients.', 'danger')
        return redirect(url_for('main.index'))

    client = Client.query.get_or_404(id)
    return render_template('clients/view.html',
                           client=client,
                           RFQ=RFQ,
                           PurchaseOrder=PurchaseOrder)


@clients.route('/contacts/<int:client_id>')
@login_required
def contacts(client_id):
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view contacts.', 'danger')
        return redirect(url_for('main.index'))

    client = Client.query.get_or_404(client_id)
    return render_template('clients/contacts.html', client=client)


@clients.route('/contacts/view/<int:id>')
@login_required
def view_contact(id):
    # Check if user has view permission
    if not current_user.is_admin() and not current_user.can_view():
        flash('You do not have permission to view contacts.', 'danger')
        return redirect(url_for('main.index'))

    contact = ContactPerson.query.get_or_404(id)
    client = Client.query.get_or_404(contact.client_id)
    return render_template('clients/contact_view.html', contact=contact, client=client)


@clients.route('/contacts/add/<int:client_id>', methods=['GET', 'POST'])
@login_required
def add_contact(client_id):
    # Check if user has permission to add contacts
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add contacts.', 'danger')
        return redirect(url_for('clients.contacts', client_id=client_id))

    client = Client.query.get_or_404(client_id)
    form = ContactPersonForm()
    form.client_id.data = client_id

    # Check if there's pending contact data in session
    pending_contact = session.pop('pending_contact', None)
    if pending_contact and request.method == 'GET':
        form.name.data = pending_contact.get('name', '')

    # Check if name is provided in URL (from "New" button)
    contact_name = request.args.get('name', '')
    if contact_name and request.method == 'GET':
        form.name.data = contact_name

    # Handle dynamic form actions
    if request.method == 'POST':
        if 'add_email' in request.form:
            form.emails.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Add Contact', client=client)

        if 'add_phone' in request.form:
            form.phones.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Add Contact', client=client)

        if 'add_mobile' in request.form:
            form.mobiles.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Add Contact', client=client)

        # Save form state if minimize button is clicked
        if 'minimize_form' in request.form:
            form_data = {
                'client_id': client_id,
                'name': form.name.data,
                'position': form.position.data,
                'emails': [email_form.email.data for email_form in form.emails],
                'phones': [phone_form.phone.data for phone_form in form.phones],
                'mobiles': [mobile_form.mobile.data for mobile_form in form.mobiles]
            }
            session['minimized_contact_form'] = form_data
            flash('Form has been minimized. You can continue later from the dashboard.', 'info')
            return redirect(url_for('main.index'))

        # Regular form submission
        if form.validate_on_submit():
            try:
                contact = ContactPerson(
                    client_id=client_id,
                    name=form.name.data,
                    position=form.position.data
                )
                db.session.add(contact)
                db.session.flush()  # Get contact ID

                # Process emails
                for email_form in form.emails:
                    if email_form.email.data:  # Only add if email is provided
                        email = ContactEmail(
                            contact_id=contact.id,
                            email=email_form.email.data
                        )
                        db.session.add(email)

                # Process phones
                for phone_form in form.phones:
                    if phone_form.phone.data:  # Only add if phone is provided
                        phone = ContactPhone(
                            contact_id=contact.id,
                            phone=phone_form.phone.data
                        )
                        db.session.add(phone)

                # Process mobiles
                for mobile_form in form.mobiles:
                    if mobile_form.mobile.data:  # Only add if mobile is provided
                        mobile = ContactMobile(
                            contact_id=contact.id,
                            mobile=mobile_form.mobile.data
                        )
                        db.session.add(mobile)

                db.session.commit()
                flash('Contact added successfully.', 'success')

                # Check if we need to redirect to another page after adding contact
                if pending_contact and 'redirect_after' in pending_contact:
                    redirect_route = pending_contact.get('redirect_after')

                    # Store RFQ data in session if needed
                    if 'rfq_data' in pending_contact:
                        rfq_data = pending_contact.get('rfq_data', {})
                        rfq_data['contact_id'] = contact.id
                        rfq_data['contact_person'] = contact.name
                        session['rfq_data'] = rfq_data

                    # Handle redirect with ID if needed
                    if 'redirect_id' in pending_contact:
                        redirect_id = pending_contact.get('redirect_id')
                        return redirect(url_for(redirect_route, id=redirect_id))

                    # Handle redirect with rfq_id if needed
                    if 'rfq_id' in pending_contact:
                        rfq_id = pending_contact.get('rfq_id')
                        return redirect(url_for(redirect_route, rfq_id=rfq_id))

                    return redirect(url_for(redirect_route))

                # Clear minimized form data if it exists
                if 'minimized_contact_form' in session:
                    session.pop('minimized_contact_form')

                return redirect(url_for('clients.contacts', client_id=client_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding contact: {str(e)}', 'danger')

    # Restore form data if it was minimized
    if 'minimized_contact_form' in session and request.method == 'GET':
        form_data = session.get('minimized_contact_form')
        if form_data.get('client_id') == client_id:  # Make sure we're restoring the right form
            form.name.data = form_data.get('name', '')
            form.position.data = form_data.get('position', '')

            # Clear default entries
            while len(form.emails) > 0:
                form.emails.pop_entry()
            while len(form.phones) > 0:
                form.phones.pop_entry()
            while len(form.mobiles) > 0:
                form.mobiles.pop_entry()

            # Add saved emails
            for email in form_data.get('emails', []):
                if email:
                    email_form = EmailForm()
                    email_form.email.data = email
                    form.emails.append_entry(email_form.data)

            # Add saved phones
            for phone in form_data.get('phones', []):
                if phone:
                    phone_form = PhoneForm()
                    phone_form.phone.data = phone
                    form.phones.append_entry(phone_form.data)

            # Add saved mobiles
            for mobile in form_data.get('mobiles', []):
                if mobile:
                    mobile_form = ContactMobileForm()
                    mobile_form.mobile.data = mobile
                    form.mobiles.append_entry(mobile_form.data)

            # Ensure at least one entry for each
            if len(form.emails) == 0:
                form.emails.append_entry()
            if len(form.phones) == 0:
                form.phones.append_entry()
            if len(form.mobiles) == 0:
                form.mobiles.append_entry()

            flash('Your minimized form has been restored. You can continue where you left off.', 'info')

    return render_template('clients/contact_form.html', form=form, title='Add Contact', client=client)

@clients.route('/contacts/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contact(id):
    # Permissions
    if not current_user.is_admin() and not current_user.can_edit():
        flash('You do not have permission to edit contacts.', 'danger')
        return redirect(url_for('clients.contacts', client_id=id))

    contact = ContactPerson.query.get_or_404(id)
    client = Client.query.get_or_404(contact.client_id)
    form = ContactPersonForm(obj=contact)
    form.client_id.data = client.id

    if request.method == 'GET':
        # Clear and re-populate dynamic fields
        form.emails.entries.clear()
        form.phones.entries.clear()
        form.mobiles.entries.clear()

        for email in contact.emails:
            form.emails.append_entry({'email': email.email})
        for phone in contact.phones:
            form.phones.append_entry({'phone': phone.phone})
        for mobile in contact.mobiles:
            form.mobiles.append_entry({'mobile': mobile.mobile})

        # Add empty entries if needed
        if not form.emails:
            form.emails.append_entry()
        if not form.phones:
            form.phones.append_entry()
        if not form.mobiles:
            form.mobiles.append_entry()

        return render_template('clients/contact_form.html', form=form, title='Edit Contact', client=client)

    if request.method == 'POST':
        if 'add_email' in request.form:
            form.emails.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Edit Contact', client=client)

        if 'add_phone' in request.form:
            form.phones.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Edit Contact', client=client)

        if 'add_mobile' in request.form:
            form.mobiles.append_entry()
            return render_template('clients/contact_form.html', form=form, title='Edit Contact', client=client)

        if form.validate_on_submit():
            # Save changes
            contact.name = form.name.data
            contact.position = form.position.data

            for email in contact.emails:
                db.session.delete(email)

            for phone in contact.phones:
                db.session.delete(phone)

            for mobile in contact.mobiles:
                db.session.delete(mobile)

            for email in form.emails:
                if email.email.data:
                    contact.emails.append(ContactEmail(email=email.email.data))

            for phone in form.phones:
                if phone.phone.data:
                    contact.phones.append(ContactPhone(phone=phone.phone.data))

            for mobile in form.mobiles:
                if mobile.mobile.data:
                    contact.mobiles.append(ContactMobile(mobile=mobile.mobile.data))

            db.session.commit()
            flash('Contact updated successfully.', 'success')
            return redirect(url_for('clients.contacts', client_id=client.id))

        # ✅ Form submitted but invalid: show form again with errors
        return render_template('clients/contact_form.html', form=form, title='Edit Contact', client=client)


@clients.route('/contacts/delete/<int:id>', methods=['POST'])
@login_required
def delete_contact(id):
    # Check if user has permission to delete
    if not current_user.is_admin():
        flash('You do not have permission to delete contacts.', 'danger')
        return redirect(url_for('clients.contacts', client_id=id))

    contact = ContactPerson.query.get_or_404(id)
    client_id = contact.client_id

    try:
        db.session.delete(contact)
        db.session.commit()
        flash('Contact deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting contact: {str(e)}', 'danger')

    return redirect(url_for('clients.contacts', client_id=client_id))


# Routes for managing contact details (emails, phones, mobiles)
@clients.route('/contacts/emails/add/<int:contact_id>', methods=['GET', 'POST'])
@login_required
def add_email(contact_id):
    # Check if user has permission to add
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add email addresses.', 'danger')
        return redirect(url_for('clients.view_contact', id=contact_id))

    contact = ContactPerson.query.get_or_404(contact_id)
    form = ContactEmailForm()
    form.contact_id.data = contact_id

    if form.validate_on_submit():
        try:
            email = ContactEmail(
                contact_id=contact_id,
                email=form.email.data
            )
            db.session.add(email)
            db.session.commit()
            flash('Email added successfully.', 'success')
            return redirect(url_for('clients.contacts', client_id=contact.client_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding email: {str(e)}', 'danger')

    return render_template('clients/contact_email_form.html', form=form, contact=contact)


@clients.route('/contacts/emails/delete/<int:id>', methods=['POST'])
@login_required
def delete_email(id):
    # Check if user has permission to delete
    if not current_user.is_admin():
        flash('You do not have permission to delete email addresses.', 'danger')
        return redirect(url_for('clients.index'))

    email = ContactEmail.query.get_or_404(id)
    contact = ContactPerson.query.get_or_404(email.contact_id)

    try:
        db.session.delete(email)
        db.session.commit()
        flash('Email deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting email: {str(e)}', 'danger')

    return redirect(url_for('clients.contacts', client_id=contact.client_id))


@clients.route('/contacts/phones/add/<int:contact_id>', methods=['GET', 'POST'])
@login_required
def add_phone(contact_id):
    # Check if user has permission to add
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add phone numbers.', 'danger')
        return redirect(url_for('clients.view_contact', id=contact_id))

    contact = ContactPerson.query.get_or_404(contact_id)
    form = ContactPhoneForm()
    form.contact_id.data = contact_id

    if form.validate_on_submit():
        try:
            phone = ContactPhone(
                contact_id=contact_id,
                phone=form.phone.data
            )
            db.session.add(phone)
            db.session.commit()
            flash('Phone number added successfully.', 'success')
            return redirect(url_for('clients.contacts', client_id=contact.client_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding phone number: {str(e)}', 'danger')

    return render_template('clients/contact_phone_form.html', form=form, contact=contact)


@clients.route('/contacts/phones/delete/<int:id>', methods=['POST'])
@login_required
def delete_phone(id):
    # Check if user has permission to delete
    if not current_user.is_admin():
        flash('You do not have permission to delete phone numbers.', 'danger')
        return redirect(url_for('clients.index'))

    phone = ContactPhone.query.get_or_404(id)
    contact = ContactPerson.query.get_or_404(phone.contact_id)

    try:
        db.session.delete(phone)
        db.session.commit()
        flash('Phone number deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting phone number: {str(e)}', 'danger')

    return redirect(url_for('clients.contacts', client_id=contact.client_id))


@clients.route('/contacts/mobiles/add/<int:contact_id>', methods=['GET', 'POST'])
@login_required
def add_mobile(contact_id):
    # Check if user has permission to add
    if not current_user.is_admin() and not current_user.can_add():
        flash('You do not have permission to add mobile numbers.', 'danger')
        return redirect(url_for('clients.view_contact', id=contact_id))

    contact = ContactPerson.query.get_or_404(contact_id)
    form = ContactMobileForm()
    form.contact_id.data = contact_id

    if form.validate_on_submit():
        try:
            mobile = ContactMobile(
                contact_id=contact_id,
                mobile=form.mobile.data
            )
            db.session.add(mobile)
            db.session.commit()
            flash('Mobile number added successfully.', 'success')
            return redirect(url_for('clients.contacts', client_id=contact.client_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding mobile number: {str(e)}', 'danger')

    return render_template('clients/contact_mobile_form.html', form=form, contact=contact)


@clients.route('/contacts/mobiles/delete/<int:id>', methods=['POST'])
@login_required
def delete_mobile(id):
    # Check if user has permission to delete
    if not current_user.is_admin():
        flash('You do not have permission to delete mobile numbers.', 'danger')
        return redirect(url_for('clients.index'))

    mobile = ContactMobile.query.get_or_404(id)
    contact = ContactPerson.query.get_or_404(mobile.contact_id)

    try:
        db.session.delete(mobile)
        db.session.commit()
        flash('Mobile number deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting mobile number: {str(e)}', 'danger')

    return redirect(url_for('clients.contacts', client_id=contact.client_id))


@clients.route('/get-contacts/<int:client_id>')
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


@clients.route('/get-contact-details/<int:contact_id>')
@login_required
def get_contact_details(contact_id):
    """API endpoint to get details for a specific contact"""
    contact = ContactPerson.query.get_or_404(contact_id)

    # Get primary email, phone, and mobile if they exist
    primary_email = contact.primary_email()
    primary_phone = contact.primary_phone()
    primary_mobile = contact.primary_mobile()

    contact_details = {
        'id': contact.id,
        'full_name': contact.name,
        'position': contact.position or '',
        'email': primary_email.email if primary_email else '',
        'phone': primary_phone.phone if primary_phone else '',
        'mobile': primary_mobile.mobile if primary_mobile else ''
    }

    return jsonify(contact_details)


@clients.route('/check-duplicate-email', methods=['POST'])
@login_required
def check_duplicate_email():
    """API endpoint to check for duplicate emails"""
    email = request.form.get('email')
    client_id = request.form.get('client_id')
    contact_id = request.form.get('contact_id')

    if not email:
        return jsonify({'valid': True})

    # Check for duplicate emails within the same client
    query = ContactEmail.query.join(ContactPerson).filter(
        ContactEmail.email == email)

    if client_id:
        query = query.filter(ContactPerson.client_id == int(client_id))

    if contact_id:
        query = query.filter(ContactPerson.id != int(contact_id))

    existing = query.first()

    return jsonify({
        'valid': not existing,
        'message': f'Email {email} is already in use by another contact.' if existing else ''
    })


@clients.route('/update-status/<string:model_type>/<int:id>', methods=['POST'])
@login_required
def update_status(model_type, id):
    # Check if user has permission to update
    if not current_user.is_admin() and not current_user.can_update():
        flash('You do not have permission to update status.', 'danger')
        return redirect(request.referrer)

    new_status = request.form.get('status')
    if not new_status:
        flash('No status provided', 'danger')
        return redirect(request.referrer)

    try:
        if model_type == 'rfq':
            item = RFQ.query.get_or_404(id)
            item.proposal_status = new_status
        elif model_type == 'po':
            item = PurchaseOrder.query.get_or_404(id)
            item.status = new_status
        else:
            flash('Invalid model type', 'danger')
            return redirect(request.referrer)

        db.session.commit()
        flash(f'Status updated successfully to {new_status}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'danger')

    return redirect(request.referrer)
