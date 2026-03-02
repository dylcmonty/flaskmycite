from __future__ import annotations

from flask import Blueprint, render_template

paypal_demo_bp = Blueprint("paypal_demo", __name__)
TOOL_ID = "paypal_demo"
TOOL_TITLE = "PayPal Demo"
TOOL_HOME_PATH = "/portal/tools/paypal_demo/home"
TOOL_BLUEPRINT = paypal_demo_bp


@paypal_demo_bp.get("/portal/tools/paypal_demo/home")
def paypal_demo_home():
    return render_template("tools/paypal_demo_home.html")
