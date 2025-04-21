from flask import Blueprint

rfqs = Blueprint('rfqs', __name__)

from . import routes

