"""PDF Report generator using fpdf2"""
from __future__ import annotations
from fpdf import FPDF
from typing import Dict, Any
import io, datetime


class TowerReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(30, 60, 100)
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, "TELECOM TOWER ENGINEERING REPORT", align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()} | AI-OTDIQ Tower Engineering Assistant", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(220, 230, 245)
        self.cell(0, 8, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def kv_row(self, key: str, value: str):
        self.set_x(self.l_margin)  # guard against x-drift after table rendering
        self.set_font("Helvetica", "B", 9)
        self.cell(70, 6, key + ":", new_x="RIGHT", new_y="TOP")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, str(value), new_x="LMARGIN", new_y="NEXT")


def generate_pdf_report(state_dict: Dict[str, Any]) -> bytes:
    pdf = TowerReportPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header info
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Session ID: {state_dict.get('session_id', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Tower summary
    pdf.section_title("1. TOWER SUMMARY")
    tower_type = state_dict.get("tower_type", "Not defined")
    pdf.kv_row("Tower Type", tower_type.upper() if tower_type else "N/A")
    pdf.kv_row("Geometry Version", str(state_dict.get("geometry_version", 0)))

    params = state_dict.get("params", {}) or {}
    pdf.kv_row("Height", f"{params.get('height', 'N/A')} m")
    if tower_type == "lattice":
        pdf.kv_row("Legs", str(params.get("num_legs", "N/A")))
        pdf.kv_row("Base Width", f"{params.get('base_width', 'N/A')} m")
        pdf.kv_row("Top Width", f"{params.get('top_width', 'N/A')} m")
        pdf.kv_row("Bracing", params.get("bracing_type", "N/A"))
    elif tower_type == "guyed":
        pdf.kv_row("Guy Wire Levels", str(params.get("guy_wire_levels", "N/A")))
        pdf.kv_row("Guy Directions", str(params.get("num_guy_directions", "N/A")))
    elif tower_type == "monopole":
        pdf.kv_row("Base Diameter", f"{params.get('base_diameter', 'N/A')} m")
        pdf.kv_row("Top Diameter", f"{params.get('top_diameter', 'N/A')} m")
    pdf.kv_row("Material", params.get("material", "N/A"))
    pdf.ln(4)

    # Mounted equipment
    pdf.section_title("2. MOUNTED EQUIPMENT INVENTORY")
    mounts = state_dict.get("mounts", [])
    if mounts:
        for m in mounts:
            pdf.kv_row(m.get("label", m.get("id", "?")), f"Type: {m.get('type')} | Height: {m.get('height')}m | Az: {m.get('azimuth')} deg")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, "  No equipment mounted.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Wind parameters
    pdf.section_title("3. WIND INPUT PARAMETERS")
    wp = state_dict.get("wind_params", {}) or {}
    pdf.kv_row("Structural Class", wp.get("structural_class", "II"))
    pdf.kv_row("Exposure Category", wp.get("exposure_category", "C"))
    pdf.kv_row("Service Wind Speed", f"{wp.get('service_wind_speed', 45)} m/s")
    pdf.kv_row("Max Wind Speed", f"{wp.get('max_wind_speed', 60)} m/s")
    pdf.kv_row("Ice Thickness", f"{wp.get('ice_thickness', 0)} mm")
    pdf.ln(4)

    # Wind analysis results
    wr = state_dict.get("wind_result")
    if wr:
        pdf.section_title("4. WIND ANALYSIS RESULTS")
        pdf.kv_row("Max Tip Deflection", f"{wr.get('max_deflection_m', 0):.3f} m")
        pdf.kv_row("Critical Direction", f"{wr.get('critical_direction', 0)} deg")
        pdf.kv_row("Stability Index", f"{wr.get('stability_index', 1):.3f}")
        pdf.ln(2)

        lcs = wr.get("load_cases", [])
        if lcs:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(200, 210, 230)
            cols = ["Dir (deg)", "V (m/s)", "Shear (kN)", "Moment (kNm)", "Defl (m)", "SR"]
            widths = [22, 22, 27, 32, 22, 22]
            for c, w in zip(cols, widths):
                pdf.cell(w, 7, c, border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 8)
            for lc in lcs:
                vals = [lc.get("direction"), lc.get("wind_speed"), lc.get("base_shear"),
                        lc.get("overturning_moment"), lc.get("tip_deflection"), lc.get("max_stress_ratio")]
                for v, w in zip(vals, widths):
                    pdf.cell(w, 6, str(v), border=1, align="C")
                pdf.ln()
        pdf.ln(4)

    # Engineering notes
    notes = state_dict.get("engineering_notes", [])
    if notes:
        pdf.section_title("5. ENGINEERING NOTES & ASSUMPTIONS")
        pdf.set_font("Helvetica", "", 9)
        for note in notes:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, f"- {note}")
        pdf.ln(4)

    pdf.section_title("DISCLAIMER")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5,
        "This report is generated by an AI-assisted engineering tool for preliminary assessment only. "
        "All structural calculations are simplified approximations. Full structural verification by a "
        "licensed professional engineer is required before any construction or modification.")

    return bytes(pdf.output())
