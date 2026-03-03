from __future__ import annotations

from flask import Blueprint, render_template


data_tool_bp = Blueprint("data_tool", __name__)

TOOL_ID = "data_tool"
TOOL_TITLE = "Data Tool"
TOOL_HOME_PATH = "/portal/tools/data_tool/home"
TOOL_BLUEPRINT = data_tool_bp


@data_tool_bp.get("/portal/tools/data_tool/home")
def data_tool_home():
    return render_template("tools/data_tool_home.html")
