from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services import dashboard

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", **dashboard.summary(current_user))
