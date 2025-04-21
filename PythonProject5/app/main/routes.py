from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.main import main
from app.models import Client, RFQ, PurchaseOrder, ContactPerson, Role
from sqlalchemy import or_
from datetime import datetime, timedelta


@main.route('/')
@login_required
def index():
    # If not logged in, redirect to login page
    if not current_user.is_authenticated:
        flash('Please log in to access the dashboard.', 'info')
        return redirect(url_for('auth.login'))

    # Dashboard statistics
    clients_count = Client.query.count()
    rfqs_count = RFQ.query.count()
    pending_rfqs = RFQ.query.filter_by(proposal_status="Pending").count()
    purchase_orders_count = PurchaseOrder.query.count()

    # Recent RFQs and POs - filter based on permissions
    if current_user.is_admin():
        # Admins see all records
        recent_rfqs = RFQ.query.order_by(RFQ.last_updated.desc()).limit(5).all()
        recent_pos = PurchaseOrder.query.order_by(PurchaseOrder.last_updated.desc()).limit(5).all()
    else:
        # Regular users see only records they can access based on permissions
        if current_user.permissions and current_user.permissions.edit_scope == 'all':
            # User can see all records
            recent_rfqs = RFQ.query.order_by(RFQ.last_updated.desc()).limit(5).all()
            recent_pos = PurchaseOrder.query.order_by(PurchaseOrder.last_updated.desc()).limit(5).all()
        else:
            # User can only see their own records
            recent_rfqs = RFQ.query.filter_by(created_by_user_id=current_user.id).order_by(
                RFQ.last_updated.desc()).limit(5).all()
            recent_pos = PurchaseOrder.query.filter_by(created_by_user_id=current_user.id).order_by(
                PurchaseOrder.last_updated.desc()).limit(5).all()

    # Get upcoming deadlines (RFQs with bid closing date in the next 7 days)
    today = datetime.now().date()
    next_week = today + timedelta(days=7)

    # Filter upcoming deadlines based on permissions
    upcoming_deadlines_query = RFQ.query.filter(
        RFQ.bid_closing_date.isnot(None),
        RFQ.bid_closing_date >= today,
        RFQ.bid_closing_date <= next_week,
        RFQ.proposal_status == 'Pending'
    )

    if not current_user.is_admin() and current_user.permissions and current_user.permissions.edit_scope != 'all':
        upcoming_deadlines_query = upcoming_deadlines_query.filter(RFQ.created_by_user_id == current_user.id)

    upcoming_deadlines = upcoming_deadlines_query.order_by(RFQ.bid_closing_date.asc()).all()

    return render_template('main/index.html',
                           clients_count=clients_count,
                           rfqs_count=rfqs_count,
                           pending_rfqs=pending_rfqs,
                           purchase_orders_count=purchase_orders_count,
                           recent_rfqs=recent_rfqs,
                           recent_pos=recent_pos,
                           upcoming_deadlines=upcoming_deadlines)


@main.route('/api/search')
@login_required
def global_search():
    """API endpoint for global search across all entities"""
    search_term = request.args.get('term', '')
    if not search_term or len(search_term) < 2:
        return jsonify([])

    results = []
    search_pattern = f"%{search_term}%"

    # Search clients
    clients = Client.query.filter(Client.company_name.ilike(search_pattern)).limit(5).all()
    for client in clients:
        results.append({
            'type': 'client',
            'title': client.company_name,
            'description': f"Client ID: {client.id}",
            'url': url_for('clients.view', id=client.id)
        })

    # Search RFQs
    rfqs = RFQ.query.filter(
        or_(
            RFQ.item_description.ilike(search_pattern),
            RFQ.remarks.ilike(search_pattern)
        )
    ).limit(5).all()

    for rfq in rfqs:
        results.append({
            'type': 'rfq',
            'title': f"RFQ #{rfq.id}",
            'description': f"{rfq.client.company_name if rfq.client else 'Unknown Client'} - {rfq.item_description[:50]}...",
            'url': url_for('rfqs.view', id=rfq.id)
        })

    # Search Purchase Orders
    pos = PurchaseOrder.query.filter(
        or_(
            PurchaseOrder.items_ordered.ilike(search_pattern),
            PurchaseOrder.remarks.ilike(search_pattern)
        )
    ).limit(5).all()

    for po in pos:
        results.append({
            'type': 'po',
            'title': f"PO #{po.id}",
            'description': f"{po.client.company_name} - {po.items_ordered[:50]}...",
            'url': url_for('purchase_orders.view', id=po.id)
        })

    # Search contacts
    contacts = ContactPerson.query.filter(
        or_(
            ContactPerson.name.ilike(search_pattern),
            ContactPerson.position.ilike(search_pattern)
        )
    ).limit(5).all()

    for contact in contacts:
        results.append({
            'type': 'contact',
            'title': contact.name,
            'description': f"{contact.client.company_name} - {contact.position or 'No position'}",
            'url': url_for('clients.view', id=contact.client_id)
        })

    return jsonify(results)
