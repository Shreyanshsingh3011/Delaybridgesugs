"""NIT-76 Operations demo dataset — 79 rows with realistic delay reasons and dependencies."""
from typing import List, Dict, Any
from datetime import date, timedelta
import random

random.seed(7)


def _date(offset: int) -> str:
    base = date(2024, 1, 2)
    return (base + timedelta(days=offset)).isoformat()


_PEOPLE = [
    ("Rahul Sharma", "rahul.sharma@nit76.in", "+91-98100-11221"),
    ("Priya Mehta", "priya.mehta@nit76.in", "+91-98100-11222"),
    ("Deepak Verma", "deepak.verma@nit76.in", "+91-98100-11223"),
    ("Sonia Kapoor", "sonia.kapoor@nit76.in", "+91-98100-11224"),
    ("Arjun Reddy", "arjun.reddy@nit76.in", "+91-98100-11225"),
    ("Neha Iyer", "neha.iyer@nit76.in", "+91-98100-11226"),
    ("Vikram Singh", "vikram.singh@nit76.in", "+91-98100-11227"),
    ("Anita Joshi", "anita.joshi@nit76.in", "+91-98100-11228"),
    ("Karan Patel", "karan.patel@nit76.in", "+91-98100-11229"),
    ("Meera Nair", "meera.nair@nit76.in", "+91-98100-11230"),
    ("Sandeep Rao", "sandeep.rao@nit76.in", "+91-98100-11231"),
    ("Pooja Bansal", "pooja.bansal@nit76.in", "+91-98100-11232"),
    ("Rajeev Khanna", "rajeev.khanna@nit76.in", "+91-98100-11233"),
    ("Lakshmi Pillai", "lakshmi.pillai@nit76.in", "+91-98100-11234"),
    ("Imran Ahmed", "imran.ahmed@nit76.in", "+91-98100-11235"),
]

# (stage, activity, criticality, tat, actual, status, reason, deps)
_BASE = [
    ("Initiation", "Project Charter Sign-off", "Critical", 5, 7, "Completed", "Approval pending from sponsor", []),
    ("Initiation", "Stakeholder Register", "Normal", 3, 3, "Completed", "", ["Project Charter Sign-off"]),
    ("Initiation", "Communication Plan", "Normal", 4, 5, "Completed", "Document templates were missing", ["Stakeholder Register"]),
    ("Planning", "WBS Creation", "Critical", 6, 6, "Completed", "", ["Project Charter Sign-off"]),
    ("Planning", "Resource Plan", "Critical", 5, 9, "Delayed", "Resource unavailable from HR", ["WBS Creation"]),
    ("Planning", "Risk Register", "Normal", 4, 4, "Completed", "", ["WBS Creation"]),
    ("Planning", "Quality Plan", "Normal", 3, 4, "Completed", "Documentation missing from QA team", ["WBS Creation"]),
    ("Finance", "Budget Estimation", "Critical", 7, 11, "Delayed", "Vendor quotations pending approval", ["WBS Creation"]),
    ("Finance", "Cost Baseline Approval", "Critical", 4, 8, "Delayed", "Approval pending from CFO office", ["Budget Estimation"]),
    ("Finance", "Vendor Invoice Approval", "Critical", 2, 5, "Delayed", "Approval pending from Finance Head", ["Cost Baseline Approval"]),
    ("Procurement", "Equipment PO", "Critical", 6, 9, "Delayed", "Dependency not cleared — Vendor Invoice Approval", ["Vendor Invoice Approval"]),
    ("Procurement", "Spares Procurement", "Normal", 8, 8, "In Progress", "", ["Equipment PO"]),
    ("Procurement", "Logistics Contract", "Normal", 5, 5, "Completed", "", ["Equipment PO"]),
    ("Site", "Site Survey Report", "Critical", 4, 7, "Delayed", "Blocked by Equipment PO approval", ["Vendor Invoice Approval"]),
    ("Site", "Soil Testing", "Normal", 3, 3, "Completed", "", ["Site Survey Report"]),
    ("Site", "Site Mobilisation", "Critical", 5, 6, "In Progress", "Weather affected mobilisation", ["Soil Testing", "Equipment PO"]),
    ("Site", "Boundary Wall Construction", "Normal", 10, 10, "In Progress", "", ["Site Mobilisation"]),
    ("Engineering", "Design Drawing v1", "Critical", 7, 7, "Completed", "", ["WBS Creation"]),
    ("Engineering", "Design Review", "Critical", 4, 6, "Delayed", "Design change requested by client", ["Design Drawing v1"]),
    ("Engineering", "Final Design Sign-off", "Critical", 3, 4, "Delayed", "Approval pending from technical authority", ["Design Review"]),
    ("Engineering", "BOQ Preparation", "Normal", 5, 6, "Completed", "Documentation missing — vendor specs", ["Final Design Sign-off"]),
    ("Engineering", "Drawing Issued for Construction", "Critical", 2, 3, "In Progress", "Awaiting approval from PMO", ["Final Design Sign-off"]),
    ("Civil", "Foundation Excavation", "Normal", 8, 9, "In Progress", "Monsoon rain delayed excavation", ["Site Mobilisation"]),
    ("Civil", "PCC Laying", "Normal", 3, 3, "Yet to Start", "", ["Foundation Excavation"]),
    ("Civil", "Footing Reinforcement", "Critical", 5, 5, "Yet to Start", "", ["PCC Laying"]),
    ("Civil", "Plinth Beam Casting", "Critical", 4, 4, "Yet to Start", "", ["Footing Reinforcement"]),
    ("Civil", "Brickwork Ground Floor", "Normal", 12, 12, "Yet to Start", "", ["Plinth Beam Casting"]),
    ("Civil", "Slab Casting GF", "Critical", 5, 5, "Yet to Start", "", ["Brickwork Ground Floor"]),
    ("Electrical", "Cable Tray Layout", "Normal", 4, 5, "In Progress", "Design change in routing", ["Drawing Issued for Construction"]),
    ("Electrical", "Conduit Installation", "Normal", 6, 6, "Yet to Start", "", ["Cable Tray Layout"]),
    ("Electrical", "Switchgear Procurement", "Critical", 8, 12, "Delayed", "Vendor delivery delayed — external factor", ["Equipment PO"]),
    ("Electrical", "Switchgear Installation", "Critical", 5, 5, "Yet to Start", "", ["Switchgear Procurement", "Conduit Installation"]),
    ("Electrical", "Earthing Pit Construction", "Normal", 3, 4, "In Progress", "Resource unavailable — earthing contractor", ["Foundation Excavation"]),
    ("Mechanical", "HVAC Vendor Finalisation", "Normal", 5, 7, "Delayed", "Approval pending from procurement head", ["Equipment PO"]),
    ("Mechanical", "Chiller PO", "Critical", 4, 4, "Yet to Start", "", ["HVAC Vendor Finalisation"]),
    ("Mechanical", "Ducting Installation", "Normal", 7, 7, "Yet to Start", "", ["Chiller PO"]),
    ("Mechanical", "Fire Pump Installation", "Critical", 5, 5, "Yet to Start", "", ["Chiller PO"]),
    ("Safety", "HSE Plan", "Critical", 3, 3, "Completed", "", ["WBS Creation"]),
    ("Safety", "Toolbox Training", "Normal", 2, 2, "In Progress", "", ["HSE Plan"]),
    ("Safety", "PPE Procurement", "Normal", 4, 5, "Completed", "Documentation missing — MSDS pending", ["Equipment PO"]),
    ("Safety", "Site Safety Audit", "Critical", 2, 3, "In Progress", "Resource unavailable — safety officer on leave", ["Toolbox Training"]),
    ("Quality", "Material Test Reports", "Critical", 3, 4, "In Progress", "Documentation missing from supplier", ["Spares Procurement"]),
    ("Quality", "Calibration Records", "Normal", 2, 2, "Completed", "", ["Material Test Reports"]),
    ("Quality", "Welder Qualification", "Normal", 4, 4, "In Progress", "", ["Calibration Records"]),
    ("Regulatory", "Pollution NOC", "Critical", 10, 14, "Delayed", "Government clearance pending", ["Project Charter Sign-off"]),
    ("Regulatory", "Fire NOC", "Critical", 8, 11, "Delayed", "Government inspection deferred", ["Pollution NOC"]),
    ("Regulatory", "Grid Connection Agreement", "Critical", 12, 18, "Delayed", "Vendor and DISCOM approval pending", ["Pollution NOC"]),
    ("Regulatory", "Electrical Inspector Approval", "Critical", 5, 5, "Yet to Start", "", ["Grid Connection Agreement"]),
    ("IT", "Network Cabling Plan", "Normal", 4, 4, "Completed", "", ["Design Drawing v1"]),
    ("IT", "Server Room Setup", "Normal", 6, 7, "In Progress", "Design change in cooling spec", ["Network Cabling Plan"]),
    ("IT", "CCTV Procurement", "Normal", 5, 5, "In Progress", "", ["Equipment PO"]),
    ("IT", "Access Control Install", "Normal", 4, 4, "Yet to Start", "", ["CCTV Procurement"]),
    ("HR", "Manpower Mobilisation", "Critical", 5, 8, "Delayed", "Resource unavailable — labour shortage", ["Resource Plan"]),
    ("HR", "Staff Induction", "Normal", 2, 3, "In Progress", "Documentation missing — joining forms", ["Manpower Mobilisation"]),
    ("HR", "Skill Mapping", "Normal", 3, 3, "Completed", "", ["Staff Induction"]),
    ("Logistics", "Crane Hire", "Critical", 4, 6, "Delayed", "Vendor delivery delayed", ["Logistics Contract"]),
    ("Logistics", "Site Storage Setup", "Normal", 5, 5, "Completed", "", ["Site Mobilisation"]),
    ("Logistics", "Material Inwarding", "Normal", 3, 3, "In Progress", "", ["Crane Hire"]),
    ("Commissioning", "Pre-commissioning Checklist", "Critical", 4, 4, "Yet to Start", "", ["Switchgear Installation"]),
    ("Commissioning", "Trial Run", "Critical", 6, 6, "Yet to Start", "", ["Pre-commissioning Checklist"]),
    ("Commissioning", "Performance Guarantee Test", "Critical", 5, 5, "Yet to Start", "", ["Trial Run"]),
    ("Closure", "Punch List Closure", "Normal", 6, 6, "Yet to Start", "", ["Performance Guarantee Test"]),
    ("Closure", "Handover Documentation", "Critical", 5, 5, "Yet to Start", "", ["Punch List Closure"]),
    ("Closure", "Final Client Sign-off", "Critical", 3, 3, "Yet to Start", "", ["Handover Documentation"]),
    ("Closure", "Project Closure Report", "Normal", 4, 4, "Yet to Start", "", ["Final Client Sign-off"]),
    ("Audit", "Internal Audit", "Normal", 5, 5, "Yet to Start", "", ["Performance Guarantee Test"]),
    ("Audit", "External Audit Coordination", "Normal", 4, 4, "Yet to Start", "", ["Internal Audit"]),
    ("Training", "Operator Training", "Normal", 5, 5, "Yet to Start", "", ["Trial Run"]),
    ("Training", "Maintenance Training", "Normal", 4, 4, "Yet to Start", "", ["Operator Training"]),
    ("Training", "Spare Parts Familiarisation", "Normal", 3, 3, "Yet to Start", "", ["Maintenance Training"]),
    ("Stores", "Inventory Receipt", "Normal", 3, 3, "In Progress", "", ["Material Inwarding"]),
    ("Stores", "Bin Card Update", "Normal", 1, 1, "In Progress", "", ["Inventory Receipt"]),
    ("Stores", "Reorder Level Setting", "Normal", 2, 2, "Yet to Start", "", ["Bin Card Update"]),
    ("Site", "Drainage Network", "Normal", 7, 8, "In Progress", "Weather delayed work", ["Boundary Wall Construction"]),
    ("Site", "Internal Roads", "Normal", 9, 9, "Yet to Start", "", ["Drainage Network"]),
    ("Site", "Landscaping", "Normal", 6, 6, "Yet to Start", "", ["Internal Roads"]),
    ("Finance", "Insurance Renewal", "Normal", 3, 4, "Completed", "Approval pending from CFO", ["Project Charter Sign-off"]),
    ("Finance", "Bank Guarantee Issue", "Critical", 5, 7, "Delayed", "Documentation missing — collateral papers", ["Insurance Renewal"]),
    ("Audit", "Statutory Compliance Review", "Critical", 6, 9, "Delayed", "Government audit deferred", ["External Audit Coordination"]),
]


def get_demo_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sr, (stage, activity, criticality, tat, actual, status, reason, deps) in enumerate(_BASE, start=1):
        person = _PEOPLE[(sr - 1) % len(_PEOPLE)]
        rows.append({
            "Sr. No.": sr,
            "Stage of Process": stage,
            "Criticality": criticality,
            "Process Description": activity,
            "Responsible Person": person[0],
            "Responsible Person Email": person[1],
            "Responsible Person Phone": person[2],
            "Start Date": _date(sr * 2),
            "TAT": tat,
            "Days Taken": actual,
            "Status": status,
            "Reason for Delay": reason,
            "Project Dependency": ", ".join(deps),
        })
    return rows


def get_demo_rows_variant_b() -> List[Dict[str, Any]]:
    """A second snapshot of the same dataset with slightly different TAT/days (for variance demo)."""
    rows = get_demo_rows()
    out = []
    for r in rows:
        r2 = dict(r)
        # introduce variance in TAT and Days Taken for some rows
        r2["TAT"] = max(1, int(r["TAT"] * (1.0 + 0.25 * ((r["Sr. No."] % 5) - 2) / 2)))
        r2["Days Taken"] = max(1, int(r["Days Taken"] * (1.0 + 0.20 * ((r["Sr. No."] % 4) - 1) / 2)))
        # flip a few statuses to create conflicts
        if r["Sr. No."] in (5, 9, 10, 19, 31, 44):
            r2["Status"] = "In Progress" if r["Status"] == "Delayed" else r["Status"]
        out.append(r2)
    return out
