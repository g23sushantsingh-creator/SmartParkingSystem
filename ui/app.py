"""
Smart Parking Management System & DSA Visualizer.
Streamlit Web Application for MCA Mini Project Demonstration.

Architectural Role:
- Serves as the interactive graphical user interface and DSA inspection tool.
- Coordinates domain models (Vehicle, ParkingSlot) and custom Data Structures
  (ParkingHashMap, BookingQueue, ParkingStack) via ParkingManager.
- Reuses a single ParkingManager instance stored in Streamlit session_state.
- Dual-role interface:
  1. Customer Portal: View available slots, register, park, checkout, and check status.
  2. Administrator Dashboard: Password-protected (ADMIN_PASSWORD env var), full slot &
     vehicle management, permanent vehicle registry cleanup, historical activity logs,
     custom DSA visualizers (Hash Map, Booking Queue, Parking Stack with POP TOP), and Viva Guide.
- Visualizes actual internal bucket chains, queue nodes, and stack frames
  without hardcoded or simulated values.
"""

import sys
import os
import html
from datetime import datetime
from urllib.parse import quote
from typing import Optional, List, Dict, Any

# Ensure project root is on sys.path for direct module imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot
from database.repository import ParkingRepository
from services.parking_manager import ParkingManager

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Parking System | Customer & Admin Portal",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Constants & Navigation Configuration
# -----------------------------------------------------------------------------
VEHICLE_TYPES = ["Car", "Bike", "Truck", "EV"]
CURRENCY = "$"

CUSTOMER_NAV_ITEMS = [
    ("cust_slots", "Available Slots", "grid_view"),
    ("cust_park", "Park Vehicle", "directions_car"),
    ("cust_checkout", "Checkout & Billing", "receipt"),
    ("cust_register", "Register Vehicle", "app_registration"),
    ("cust_status", "My Parking Status", "search"),
]

ADMIN_NAV_ITEMS = [
    ("admin_dashboard", "Dashboard Overview", "dashboard"),
    ("admin_slots", "Slot Management", "grid_view"),
    ("admin_vehicles", "Vehicle Registry & Cleanup", "directions_car"),
    ("admin_history", "Parking History", "history"),
    None,  # visual divider
    ("admin_queue", "Booking Queue", "hourglass_top"),
    ("admin_stack", "Parking Stack", "layers"),
    ("admin_hashmap", "Hash Map Visualizer", "account_tree"),
]

PAGE_META = {
    # Customer Portal
    "cust_slots": ("Available Parking Slots", "Live vacancy overview for drivers and incoming visitors", "grid"),
    "cust_park": ("Park Vehicle", "Check in your vehicle with automatic best-fit or manual slot selection", "car"),
    "cust_checkout": ("Vehicle Departure & Billing", "Review duration, calculate fees and complete your checkout", "receipt"),
    "cust_register": ("Register Vehicle", "Pre-register your vehicle and contact details in the registry", "user"),
    "cust_status": ("My Parking Status", "Check active parking session, duration, fee or waitlist queue standing", "search"),
    # Administrator Dashboard
    "admin_dashboard": ("Administrator Dashboard", "Real-time facility status, key performance metrics and live insights", "grid"),
    "admin_slots": ("Slot Management", "Add new physical parking stalls and audit facility inventory", "grid"),
    "admin_vehicles": ("Vehicle Registry & Cleanup", "Manage registered vehicles, lookup owners and permanently delete records", "car"),
    "admin_history": ("Parking Activity & Audit History", "Complete chronological historical log preserved in MongoDB", "history"),
    "admin_queue": ("Booking Queue (FIFO)", "", "hourglass"),
    "admin_stack": ("Parking Stack (LIFO)", "", "layers"),
    "admin_hashmap": ("Hash Map Visualizer", "Live bucket arrays, load factors and separate chaining collision lists", "hash"),
}

HASHMAP_VIEWS = {
    "slots_hashmap": ("slots_map", "Slot ID → ParkingSlot"),
    "vehicles_hashmap": ("vehicles_map", "License Plate → Vehicle"),
    "vehicle_to_slot_hashmap": ("vehicle_to_slot_map", "License Plate → Slot ID"),
}

ACTION_META = {
    "PARK": ("Vehicle Parked", "Parked", "green"),
    "CHECK_OUT": ("Vehicle Checked Out", "Departed", "blue"),
    "ADD_SLOT": ("Parking Slot Added", "Slot Added", "violet"),
    "WAITLIST_ENQUEUE": ("Vehicle Added to Waiting Queue", "Queued", "amber"),
    "AUTOMATIC_ALLOCATION": ("Automatic Slot Allocation", "Allocated", "cyan"),
    "WAITLIST_ALLOCATION_ROLLBACK": ("Parking Allocation Reversed", "Rolled Back", "red"),
    "DELETE_VEHICLE": ("Vehicle Deleted", "Deleted", "red"),
    "DELETE_SLOT": ("Parking Slot Deleted", "Slot Deleted", "red"),
    "REGISTER_VEHICLE": ("Vehicle Registered", "Registered", "cyan"),
    # Backward compatibility aliases for legacy history/stack records
    "CHECK_IN": ("Vehicle Checked In", "Checked In", "green"),
    "WAITLIST_ALLOCATE": ("Automatic Slot Allocation", "Allocated", "cyan"),
    "WAITLIST_ALLOCATION": ("Automatic Slot Allocation", "Allocated", "cyan"),
}

STACK_ACTION_TYPES = [
    "PARK",
    "CHECK_OUT",
    "ADD_SLOT",
    "WAITLIST_ENQUEUE",
    "AUTOMATIC_ALLOCATION",
    "WAITLIST_ALLOCATION_ROLLBACK",
    "DELETE_VEHICLE",
    "DELETE_SLOT",
    "REGISTER_VEHICLE",
]

ACTION_ICONS = {
    "PARK": "car",
    "CHECK_IN": "car",
    "CHECK_OUT": "receipt",
    "REGISTER_VEHICLE": "user",
    "WAITLIST_ENQUEUE": "hourglass",
    "WAITLIST_ALLOCATE": "check-circle",
    "AUTOMATIC_ALLOCATION": "check-circle",
    "WAITLIST_ALLOCATION_ROLLBACK": "alert",
    "ADD_SLOT": "grid",
    "DELETE_SLOT": "trash",
    "DELETE_VEHICLE": "trash",
    "WAITLIST_ALLOCATION": "check-circle",
}

# -----------------------------------------------------------------------------
# Dark Theme Stylesheet
# -----------------------------------------------------------------------------
APP_CSS = """
:root{
  --bg:#070C18;--panel:#0B142B;--panel-h:#0F1C3D;--panel-sub:#080F22;
  --field:#081026;--line:#15244A;--line2:#1D3265;
  --tx:#EAF0FF;--mut:#95A7CF;--dim:#5E729E;
  --blue:#3B82F6;--cyan:#06B6D4;--green:#22C55E;--red:#F4506B;--amber:#F5A524;--violet:#8B7CF6;
  --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
}
html, body, [data-testid="stAppViewContainer"]{background-color:var(--bg)!important;color:var(--tx)!important;}
[data-testid="stSidebar"]{background-color:#080F22!important;border-right:1px solid var(--line)!important;}
[data-testid="stHeader"]{background:transparent!important;}
[data-testid="stVerticalBlock"]{gap:1rem;}
.block-container{padding-top:1.6rem;padding-bottom:2rem;max-width:1420px;}

.brand{display:flex;align-items:center;gap:.75rem;padding:.4rem .2rem .9rem;border-bottom:1px solid var(--line);margin-bottom:.9rem;}
.brand .logo{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#3B82F6,#1D4ED8);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:1.25rem;box-shadow:0 6px 18px rgba(37,99,235,.35);flex:none;}
.brand .name{font-weight:800;font-size:1.02rem;line-height:1.25;color:#fff;letter-spacing:-.01em;}
.side-h{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-weight:700;margin:.9rem 0 .4rem .3rem;}
.side-rule{height:1px;background:var(--line);margin:.65rem 0;}
.msr{display:flex;justify-content:space-between;align-items:center;padding:.32rem .4rem;font-size:.82rem;color:var(--mut);border-radius:6px;}
.msr b{font-family:var(--mono);color:var(--tx);font-weight:600;}
.sys{display:flex;align-items:center;gap:.6rem;padding:.55rem .7rem;border-radius:10px;border:1px solid var(--line);background:var(--panel-sub);margin-top:.4rem;font-size:.8rem;}
.sys i{width:8px;height:8px;border-radius:999px;flex:none;}
.sys.on i{background:var(--green);box-shadow:0 0 8px var(--green);}
.sys.off i{background:var(--amber);box-shadow:0 0 8px var(--amber);}
.sys div{display:flex;flex-direction:column;line-height:1.2;min-width:0;}
.sys div b{color:#fff;font-size:.8rem;}
.sys div span{font-size:.72rem;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}

.topbar{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1.25rem;border-radius:14px;background:linear-gradient(180deg,#0B142B 0%,#080F22 100%);border:1.5px solid var(--line);box-shadow:0 8px 24px rgba(0,0,0,.35);margin-bottom:1.15rem;gap:1rem;}
.topbar .tb-l{display:flex;align-items:center;gap:.85rem;min-width:0;}
.topbar .tb-logo{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,rgba(59,130,246,.25),rgba(6,182,212,.15));border:1.5px solid rgba(59,130,246,.45);display:flex;align-items:center;justify-content:center;color:#60A5FA;box-shadow:0 2px 10px rgba(37,99,235,.25);flex:none;}
.topbar .tb-title-wrap{display:flex;flex-direction:column;justify-content:center;}
.topbar .tb-title{color:#FFFFFF;font-weight:800;font-size:1.12rem;letter-spacing:-.015em;line-height:1.2;white-space:nowrap;}
.topbar .tb-accent{color:#38BDF8;font-weight:700;}
.topbar .tb-r{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap;justify-content:flex-end;}
.topbar .t{font-family:var(--mono);font-size:.83rem;color:var(--mut);display:inline-flex;align-items:center;gap:.4rem;}
.pill{display:inline-flex;align-items:center;gap:.45rem;border-radius:999px;padding:.24rem .7rem;font-size:.75rem;font-weight:600;border:1px solid;}
.pill.green{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.4);color:#68E49A;}
.pill.green i{width:6px;height:6px;border-radius:999px;background:#22C55E;}
.pill.amber{background:rgba(245,165,36,.12);border-color:rgba(245,165,36,.4);color:#FFBA52;}
.pill.amber i{width:6px;height:6px;border-radius:999px;background:#F5A524;}
.pill.blue{background:rgba(59,130,246,.12);border-color:rgba(59,130,246,.4);color:#88B7FF;}
.pill.blue i{width:6px;height:6px;border-radius:999px;background:#3B82F6;}

.ph{display:flex;align-items:center;gap:1rem;padding:.4rem 0 1.2rem;border-bottom:1.5px solid var(--line);margin-bottom:1.25rem;}
.ph-ic{width:46px;height:46px;border-radius:12px;background:linear-gradient(135deg,rgba(59,130,246,.22),rgba(6,182,212,.14));
  border:1.5px solid rgba(59,130,246,.45);display:flex;align-items:center;justify-content:center;color:#60A5FA;box-shadow:0 4px 14px rgba(37,99,235,.2);flex:none;}
.ph h1{font-size:1.48rem;font-weight:800;color:#FFFFFF;margin:0 0 3px;letter-spacing:-.02em;line-height:1.2;}
.ph p{font-size:.86rem;color:var(--mut);margin:0;font-weight:500;}

.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem;margin-bottom:1.1rem;}
.kpis.k5{grid-template-columns:repeat(5,minmax(0,1fr));}
.kpis.k3{grid-template-columns:repeat(3,minmax(0,1fr));}
.kpis.k2{grid-template-columns:repeat(2,minmax(0,1fr));}
.kpi{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.95rem 1.05rem;display:flex;align-items:center;gap:.95rem;overflow:hidden;}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;}
.kpi.blue::before{background:var(--blue);} .kpi.green::before{background:var(--green);}
.kpi.red::before{background:var(--red);} .kpi.amber::before{background:var(--amber);}
.kpi.violet::before{background:var(--violet);}
.kpi .ic{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex:none;}
.kpi.blue .ic{background:rgba(59,130,246,.15);color:#7FB5FF;}
.kpi.green .ic{background:rgba(34,197,94,.15);color:#52E08F;}
.kpi.red .ic{background:rgba(244,80,107,.15);color:#FF8DA0;}
.kpi.amber .ic{background:rgba(245,165,36,.15);color:#FFC766;}
.kpi.violet .ic{background:rgba(139,124,246,.15);color:#BDB3FF;}
.kpi .l{font-size:.78rem;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;}
.kpi .v{font-size:1.6rem;font-weight:800;color:#fff;line-height:1.1;margin:2px 0 3px;font-family:var(--mono);}
.kpi .v.sm{font-size:1.05rem;word-break:break-all;}
.kpi .s{font-size:.76rem;color:var(--dim);}

.ch{display:flex;align-items:center;gap:.6rem;font-weight:700;font-size:1rem;color:#fff;margin-bottom:.75rem;}
.ch-s{font-size:.82rem;color:var(--mut);margin:-.45rem 0 .85rem;}

.flash{display:flex;align-items:center;gap:.8rem;padding:.75rem 1rem;border-radius:12px;margin-bottom:1rem;font-size:.88rem;border:1px solid;}
.flash.success{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.45);color:#78EDA8;}
.flash.error{background:rgba(244,80,107,.13);border-color:rgba(244,80,107,.5);color:#FFAAB8;}
.flash.warn{background:rgba(245,165,36,.12);border-color:rgba(245,165,36,.45);color:#FFCF7A;}
.flash.info{background:rgba(59,130,246,.12);border-color:rgba(59,130,246,.45);color:#9CC4FF;}
.flash svg{flex:none;}

.empty{border:1px dashed var(--line2);border-radius:14px;padding:2.2rem 1.5rem;text-align:center;color:var(--mut);font-size:.9rem;background:rgba(11,20,43,.4);}
.empty b{color:#fff;display:block;margin-bottom:.3rem;font-size:.98rem;}

.meter{height:8px;border-radius:999px;background:#101F44;overflow:hidden;margin:.35rem 0 1rem;}
.meter i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#3B82F6,#06B6D4,#22C55E);transition:width .3s;}

/* 2x2 KPI Quad Container - Synchronized Heights & Zero Text Wrapping */
.kpi-quad{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:.85rem;}
.kpi-quad .kpi{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem .95rem;display:flex;align-items:center;gap:.8rem;min-height:84px;overflow:hidden;}
.kpi-quad .kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;}
.kpi-quad .kpi.blue::before{background:var(--blue);}
.kpi-quad .kpi.green::before{background:var(--green);}
.kpi-quad .kpi.red::before{background:var(--red);}
.kpi-quad .kpi.violet::before{background:var(--violet);}
.kpi-quad .kpi .ic{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none;}
.kpi-quad .kpi .l{font-size:.72rem;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kpi-quad .kpi .v{font-size:1.55rem;font-weight:800;color:#fff;line-height:1.1;margin:1px 0 2px;font-family:var(--mono);}
.kpi-quad .kpi .s{font-size:.72rem;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

/* Parking Lot Layout & Facility Scrollbar (Modern dark navy with subtle blue glow) */
.lot-scroll{
  max-height:680px;
  overflow-y:auto;
  overflow-x:hidden;
  padding-right:.45rem;
  scroll-behavior:smooth;
  scrollbar-width:thin;
  scrollbar-color:#3B82F6 #081026;
}
.lot-scroll::-webkit-scrollbar{
  width:9px;
  height:9px;
}
.lot-scroll::-webkit-scrollbar-track{
  background:#081026;
  border-radius:6px;
  border:1px solid rgba(21,36,74,.6);
  box-shadow:inset 0 0 6px rgba(0,0,0,.6);
}
.lot-scroll::-webkit-scrollbar-thumb{
  background:linear-gradient(180deg,#3B82F6,#1D4ED8);
  border-radius:6px;
  border:1.5px solid #081026;
  box-shadow:0 0 8px rgba(59,130,246,.45);
  transition:background .2s ease,box-shadow .2s ease;
}
.lot-scroll::-webkit-scrollbar-thumb:hover{
  background:linear-gradient(180deg,#60A5FA,#2563EB);
  box-shadow:0 0 12px rgba(59,130,246,.75);
}
.lot-scroll::-webkit-scrollbar-thumb:active{
  background:linear-gradient(180deg,#93C5FD,#3B82F6);
  box-shadow:0 0 14px rgba(147,197,253,.9);
}
.lot-legend{display:flex;align-items:center;gap:1.4rem;flex-wrap:wrap;padding:.6rem .95rem;background:#08132B;border:1px solid var(--line2);border-radius:11px;margin-bottom:.85rem;font-size:.78rem;color:var(--mut);}
.lot-legend-item{display:inline-flex;align-items:center;gap:.5rem;font-weight:600;}
.lot-legend-dot{width:12px;height:12px;border-radius:3px;border:1.5px solid;flex:none;}
.lot-legend-dot.vac{background:rgba(34,197,94,.28);border-color:#22C55E;box-shadow:0 0 8px rgba(34,197,94,.4);}
.lot-legend-dot.occ{background:rgba(244,80,107,.28);border-color:#F4506B;box-shadow:0 0 8px rgba(244,80,107,.4);}

.live-bar{display:flex;align-items:center;justify-content:space-between;padding:.5rem .95rem;background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.28);border-radius:10px;margin-bottom:.85rem;font-size:.8rem;color:var(--mut);}
.live-badge{display:inline-flex;align-items:center;gap:.5rem;font-weight:700;color:#68E49A;font-size:.76rem;letter-spacing:.02em;}
.live-pulse{width:8px;height:8px;border-radius:50%;background:#22C55E;box-shadow:0 0 10px #22C55E;animation:pulseLive 2s infinite ease-in-out;}
@keyframes pulseLive{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.85);}}

.floor{margin-bottom:1.4rem;background:#060C1B;border:1.5px solid var(--line);border-radius:14px;padding:1rem 1.15rem;position:relative;box-shadow:0 8px 24px rgba(0,0,0,.35);}
.floor::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--blue),var(--cyan),transparent);border-radius:14px 14px 0 0;}
.floor-h{font-size:.88rem;font-weight:800;color:#fff;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.9rem;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:.55rem;}
.floor-h span{font-size:.76rem;color:var(--mut);text-transform:none;letter-spacing:normal;font-weight:600;}

/* Real-World Aerial Top-Down Parking Apron Canvas */
.asphalt-apron{position:relative;background:radial-gradient(ellipse at 50% 50%,#0e1830 0%,#081024 65%,#050a17 100%);border:2px solid #1a294d;border-radius:12px;padding:1.1rem 1.25rem;box-shadow:inset 0 0 30px rgba(0,0,0,.7),0 12px 30px rgba(0,0,0,.5);overflow:hidden;}
.asphalt-apron::before{content:"";position:absolute;top:0;left:0;right:0;bottom:0;background-image:radial-gradient(rgba(255,255,255,.035) 1px,transparent 0);background-size:16px 16px;pointer-events:none;opacity:.65;}

.apron-curb{height:8px;background:repeating-linear-gradient(90deg,#1e293b 0px,#1e293b 24px,#eab308 24px,#eab308 48px);border-radius:3px;opacity:.9;box-shadow:0 1px 3px rgba(0,0,0,.7);}
.apron-curb.top-curb{margin-bottom:.9rem;}
.apron-curb.bottom-curb{margin-top:.9rem;}

.stalls-row{display:flex;justify-content:center;align-items:stretch;gap:0;margin:0 auto;flex-wrap:wrap;}

/* Unified Top-Down SVG Parking Facility Canvas */
.facility-canvas-svg{display:block;width:100%;height:auto;max-width:100%;margin:0 auto;border-radius:10px;filter:drop-shadow(0 14px 34px rgba(0,0,0,.6));}
.facility-canvas-svg .svg-bay-link{cursor:pointer;outline:none;text-decoration:none;}
.facility-canvas-svg .svg-bay-link:focus{outline:none;}
.facility-canvas-svg .bay{transition:transform .18s ease, filter .18s ease;cursor:pointer;}
.facility-canvas-svg .bay:hover .bay-boundary{stroke-width:3.2px;filter:brightness(1.18);}
.facility-canvas-svg .bay.selected .bay-boundary{stroke:#38BDF8!important;stroke-width:3.5px!important;}

/* Clean Bay Information Panel */
.slot-inspector-panel{margin-top:.85rem;background:#0A1224;border:1.5px solid #1E293B;border-radius:12px;padding:1rem 1.15rem;box-shadow:0 8px 24px rgba(0,0,0,.45);animation:fadeIn .2s ease;}
.slot-inspector-panel.occ{border-color:rgba(239,68,68,.35);}
.slot-inspector-panel.vac{border-color:rgba(34,197,94,.35);}
.sip-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.85rem;padding-bottom:.65rem;border-bottom:1px solid rgba(255,255,255,.08);}
.sip-title{display:flex;align-items:center;gap:.6rem;}
.sip-badge-slot{font-family:var(--mono);font-size:1.05rem;font-weight:900;color:#fff;background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.18);border-radius:6px;padding:2px 8px;}
.sip-deck{font-size:.82rem;font-weight:700;color:var(--mut);}
.sip-status-tag{display:inline-flex;align-items:center;gap:6px;font-size:.74rem;font-weight:800;letter-spacing:.05em;border-radius:999px;padding:3px 10px;text-transform:uppercase;}
.sip-dot{width:7px;height:7px;border-radius:50%;}
.sip-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:.65rem;}
.sip-cell{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:.5rem .7rem;}
.sip-cell.span-2{grid-column:span 2;}
.sip-lbl{display:block;font-size:.67rem;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px;}
.sip-val{font-size:.85rem;font-weight:700;color:#fff;display:inline-flex;align-items:center;gap:.35rem;}
.sip-val.mono{font-family:var(--mono);}
.sip-val.plate{font-family:var(--mono);color:#67E8F9;letter-spacing:.04em;font-size:.9rem;}
.live-pill{display:inline-flex;align-items:center;gap:6px;font-size:.72rem;font-weight:800;color:#22C55E;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.35);padding:3px 9px;border-radius:999px;}
.live-dot{width:7px;height:7px;border-radius:50%;background:#22C55E;box-shadow:0 0 8px #22C55E;}

/* Realistic Painted Parking Stall on Asphalt */
.bay{position:relative;flex:0 0 124px;width:124px;max-width:130px;min-height:205px;box-sizing:border-box;padding:.7rem .65rem;display:flex;flex-direction:column;justify-content:space-between;background:transparent;border-left:2.5px solid rgba(255,255,255,.55);border-right:2.5px solid rgba(255,255,255,.55);transition:transform .18s ease;cursor:default;}
.bay:hover{transform:scale(1.02);z-index:5;}
.bay.north{border-top:2.5px solid rgba(255,255,255,.55);border-bottom:2px dashed rgba(255,255,255,.32);}
.bay.south{border-top:2px dashed rgba(255,255,255,.32);border-bottom:2.5px solid rgba(255,255,255,.55);}

.bay.vac{border-left-color:rgba(34,197,94,.7);border-right-color:rgba(34,197,94,.7);background:radial-gradient(circle at 50% 50%,rgba(34,197,94,.08) 0%,transparent 70%);}
.bay.vac:hover{border-left-color:#22C55E;border-right-color:#22C55E;}
.bay.occ{border-left-color:rgba(244,80,107,.7);border-right-color:rgba(244,80,107,.7);background:radial-gradient(circle at 50% 50%,rgba(244,80,107,.09) 0%,transparent 70%);}
.bay.occ:hover{border-left-color:#F4506B;border-right-color:#F4506B;}

.bay-stopper{display:flex;align-items:center;justify-content:space-between;gap:5px;margin-bottom:5px;padding:0 2px;}
.bay-stopper .stopper-block{height:6px;flex:1;background:linear-gradient(180deg,#1F2E52,#131E38);border:1px solid rgba(255,255,255,.18);border-radius:3px;box-shadow:inset 0 1px 2px rgba(255,255,255,.1);}
.bay-stopper .bay-curb{width:7px;height:7px;border-radius:50%;flex:none;}
.bay.vac .bay-curb{background:#22C55E;box-shadow:0 0 8px #22C55E;}
.bay.occ .bay-curb{background:#F4506B;box-shadow:0 0 8px #F4506B;}

.bay-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;}
.bay-id{font-family:var(--mono);font-size:.88rem;font-weight:800;letter-spacing:.02em;color:#fff;}
.bay-tag{display:inline-flex;align-items:center;gap:3px;font-size:.65rem;font-weight:700;color:var(--mut);background:rgba(255,255,255,.08);padding:1px 5px;border-radius:3px;border:1px solid rgba(255,255,255,.1);}

/* Stenciled P symbol in Vacant stalls */
.bay-vac-center{display:flex;flex-direction:column;align-items:center;justify-content:center;margin:auto 0;padding:.3rem 0;}
.bay-p-symbol{width:52px;height:52px;border-radius:50%;border:2.5px solid #22C55E;background:rgba(34,197,94,.14);display:flex;align-items:center;justify-content:center;box-shadow:0 0 16px rgba(34,197,94,.28);margin-bottom:.4rem;}
.bay-p-letter{font-family:var(--mono);font-size:2.1rem;font-weight:900;color:#22C55E;line-height:1;}
.bay-vac-lbl{font-size:.72rem;font-weight:800;color:#52E08F;letter-spacing:.06em;text-transform:uppercase;}

/* Realistic Top-down Vehicle on Asphalt */
.bay-occ-center{display:flex;flex-direction:column;align-items:center;justify-content:center;margin:auto 0;position:relative;z-index:2;}
.bay-topdown-wrap{position:relative;display:flex;justify-content:center;align-items:center;}
.bay-car-svg{filter:drop-shadow(0 6px 14px rgba(0,0,0,.75));transition:transform .2s;}
.bay:hover .bay-car-svg{transform:scale(1.03);}
.bay-plate-badge{display:inline-flex;align-items:center;justify-content:center;background:#050B18;border:1.5px solid #334155;border-radius:5px;padding:2px 8px;margin-top:4px;box-shadow:0 3px 8px rgba(0,0,0,.6);}
.bay-plate-flag{font-size:.6rem;font-weight:900;color:#FFBA52;letter-spacing:.04em;}
.bay-plate{font-family:var(--mono);font-weight:800;font-size:.78rem;color:#fff;letter-spacing:.03em;white-space:nowrap;}
.bay-owner{font-size:.68rem;color:var(--mut);margin-top:2px;max-width:116px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center;}
text.bay-owner{font-family:'Inter',sans-serif;font-size:9px;font-weight:600;fill:#94A3B8;}
text.bay-type-lbl{font-family:'Inter',sans-serif;font-size:9px;font-weight:700;letter-spacing:.5px;fill:#64748B;}

.bay-foot{display:flex;justify-content:space-between;align-items:center;margin-top:auto;padding-top:4px;border-top:1px dashed rgba(255,255,255,.14);font-size:.7rem;font-weight:700;}
.bay.vac .bay-status{color:#52E08F;display:inline-flex;align-items:center;gap:4px;}
.bay.occ .bay-status{color:#FF8DA0;display:inline-flex;align-items:center;gap:4px;}
.bay-type-lbl{color:var(--dim);font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;}

/* Central Driving Roadway between North and South bay rows */
.driving-aisle{position:relative;background:linear-gradient(180deg,rgba(8,15,32,.95),rgba(4,8,18,.98));border-top:2px solid rgba(255,255,255,.24);border-bottom:2px solid rgba(255,255,255,.24);margin:.9rem 0;padding:.85rem 1.2rem;box-shadow:inset 0 2px 10px rgba(0,0,0,.8);overflow:hidden;}
.aisle-lane-markings{height:2px;border-top:2px dashed rgba(255,255,255,.32);margin:0;}
.aisle-roadway-content{display:flex;align-items:center;justify-content:space-between;font-size:.72rem;font-weight:800;letter-spacing:.1em;color:rgba(255,255,255,.45);text-transform:uppercase;padding:.5rem 0;}
.aisle-arrows{display:inline-flex;gap:.6rem;color:var(--blue);font-weight:900;font-size:.9rem;text-shadow:0 0 10px rgba(59,130,246,.6);}
.aisle-label{font-family:var(--mono);}

.badge{font-size:.74rem;font-weight:700;border-radius:999px;padding:.22rem .65rem;border:1px solid;white-space:nowrap;}
.t-green{color:#52E08F;background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.45);}
.t-blue{color:#7FB5FF;background:rgba(59,130,246,.14);border-color:rgba(59,130,246,.5);}
.t-cyan{color:#67E8F9;background:rgba(6,182,212,.14);border-color:rgba(6,182,212,.5);}
.t-violet{color:#BDB3FF;background:rgba(139,124,246,.14);border-color:rgba(139,124,246,.5);}
.t-amber{color:#FFC766;background:rgba(245,165,36,.13);border-color:rgba(245,165,36,.5);}
.t-red{color:#FF8DA0;background:rgba(244,80,107,.13);border-color:rgba(244,80,107,.5);}
.d-green{background:var(--green);} .d-blue{background:var(--blue);} .d-cyan{background:var(--cyan);} .d-violet{background:var(--violet);} .d-amber{background:var(--amber);} .d-red{background:var(--red);}

/* Compact Activity Timeline Component */
.timeline{display:flex;flex-direction:column;position:relative;padding-left:1.35rem;margin:.3rem 0;min-width:0;box-sizing:border-box;}
.timeline::before{content:"";position:absolute;left:.5rem;top:6px;bottom:6px;width:2px;background:var(--line);}
.t-node{position:relative;padding-bottom:.65rem;min-width:0;box-sizing:border-box;}
.t-node:last-child{padding-bottom:0;}
.t-dot{position:absolute;left:-1.35rem;top:8px;width:10px;height:10px;border-radius:50%;border:2px solid var(--bg);z-index:2;}
.t-dot.d-green{background:#22C55E;box-shadow:0 0 6px rgba(34,197,94,.6);}
.t-dot.d-blue{background:#3B82F6;box-shadow:0 0 6px rgba(59,130,246,.6);}
.t-dot.d-cyan{background:#06B6D4;box-shadow:0 0 6px rgba(6,182,212,.6);}
.t-dot.d-violet{background:#8B7CF6;box-shadow:0 0 6px rgba(139,124,246,.6);}
.t-dot.d-amber{background:#F5A524;box-shadow:0 0 6px rgba(245,165,36,.6);}
.t-dot.d-red{background:#F4506B;box-shadow:0 0 6px rgba(244,80,107,.6);}
.t-body{background:var(--panel-sub);border:1px solid var(--line);border-radius:9px;padding:.5rem .75rem;transition:border-color .15s, background .15s;overflow:hidden;box-sizing:border-box;min-width:0;}
.t-body:hover{border-color:var(--line2);background:#0A1636;}
.t-header{display:flex;align-items:flex-start;justify-content:space-between;gap:.4rem .65rem;flex-wrap:wrap;min-width:0;}
.t-title{font-size:.82rem;font-weight:700;color:#FFFFFF;display:inline-flex;align-items:center;gap:.4rem;min-width:0;flex:1 1 180px;line-height:1.3;word-break:break-word;overflow-wrap:anywhere;}
.t-title svg{flex:none;color:var(--blue);margin-top:1px;}
.t-title span{word-break:break-word;overflow-wrap:anywhere;}
.t-meta{display:inline-flex;align-items:center;gap:.45rem;flex-shrink:0;margin-left:auto;}
.t-time{font-size:.7rem;color:var(--dim);font-family:var(--mono);white-space:nowrap;}
.t-meta .badge{font-size:.7rem;padding:.15rem .55rem;flex-shrink:0;}
.t-props{display:flex;align-items:center;flex-wrap:wrap;gap:.3rem .75rem;font-size:.73rem;margin-top:.45rem;border-top:1px solid rgba(255,255,255,.05);padding-top:.4rem;min-width:0;}
.t-prop{display:inline-flex;align-items:center;gap:4px;min-width:0;max-width:100%;}
.t-prop-k{color:var(--dim);font-weight:600;flex-shrink:0;}
.t-prop-v{color:var(--tx);word-break:break-all;overflow-wrap:anywhere;}
.t-prop-v.plate-text{font-family:var(--mono);font-weight:700;color:#FFFFFF;}
.t-prop-v.slot-text{font-family:var(--mono);font-weight:700;color:#7FB5FF;}
.t-prop-v.fee-text{font-family:var(--mono);font-weight:700;color:#52E08F;}

.pipe{display:flex;align-items:stretch;gap:.4rem;overflow-x:auto;padding:1.8rem .2rem .7rem;}
.pnode{position:relative;flex:none;min-width:190px;background:#0B1A3B;border:1px solid var(--line2);border-radius:13px;padding:.75rem .9rem;}
.pnode.front{border-color:rgba(59,130,246,.9);box-shadow:0 0 0 1px rgba(59,130,246,.35),0 10px 26px rgba(37,99,235,.22);}
.pnode.rear{border-color:rgba(139,124,246,.9);}
.pnode.front.rear{border-color:rgba(59,130,246,.9);}
.ptag{position:absolute;top:-1.55rem;left:.2rem;display:flex;gap:.3rem;}
.ptag span{font-size:.7rem;font-weight:700;padding:.1rem .5rem;border-radius:6px;}
.ptag .f{background:rgba(59,130,246,.22);color:#9CC4FF;border:1px solid rgba(59,130,246,.55);}
.ptag .r{background:rgba(139,124,246,.22);color:#C9C1FF;border:1px solid rgba(139,124,246,.55);}
.pnode .pl{font-family:var(--mono);font-weight:600;font-size:1.02rem;}
.pnode .pm{display:flex;align-items:center;gap:.4rem;color:var(--mut);font-size:.8rem;margin-top:.25rem;}
.pnode .pk{font-size:.74rem;color:var(--dim);margin-top:.5rem;font-family:var(--mono);word-break:break-all;line-height:1.35;}
.parrow{display:flex;align-items:center;color:var(--blue);flex:none;}
.pnull{flex:none;align-self:center;font-family:var(--mono);font-size:.78rem;color:var(--dim);border:1px dashed var(--line2);border-radius:8px;padding:.35rem .6rem;}

.stk{display:flex;flex-direction:column;gap:.15rem;}
.sframe{position:relative;border:1px solid var(--line2);border-left-width:5px;border-radius:12px;padding:.75rem .95rem;background:#0B1A3B;}
.sframe.top{box-shadow:0 0 0 1px rgba(59,130,246,.35),0 10px 26px rgba(37,99,235,.2);}
.sframe .sh{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;}
.sframe .sh .pos{font-size:.74rem;color:var(--mut);font-weight:700;}
.sframe .sh .pos.top{color:#9CC4FF;}
.sframe .sh .sf-desc{color:var(--mut);font-size:.76rem;font-weight:500;}
.sframe .sh .badge{margin-left:auto;}
.sframe .kv{display:flex;flex-wrap:wrap;gap:.35rem 1.1rem;margin-top:.5rem;font-size:.8rem;color:var(--mut);}
.sframe .kv span b{color:var(--dim);font-weight:600;margin-right:.35rem;}
.sframe .kv span{font-family:var(--mono);font-size:.78rem;color:var(--tx);}
.sarrow{display:flex;justify-content:center;color:var(--dim);height:18px;}

/* Stack Visualizer Action Types Legend */
.act-list{display:flex;flex-direction:column;gap:.55rem;}
.act{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.65rem .85rem;background:#081226;border:1px solid var(--line);border-radius:10px;transition:border-color .18s ease, background .18s ease;}
.act:hover{background:#0C1733;border-color:var(--line2);}
.act-left{display:flex;align-items:center;gap:.75rem;min-width:0;flex:1;}
.act .dot{width:9px;height:9px;border-radius:50%;flex:none;}
.act-text, .act .tx{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1;}
.act-name, .act .tx b{font-family:var(--mono);font-size:.82rem;font-weight:700;color:#FFFFFF;letter-spacing:.02em;line-height:1.2;display:block;}
.act-desc, .act .tx span{font-family:'Inter',sans-serif;font-size:.76rem;color:#94A3B8;font-weight:400;line-height:1.25;display:block;}
.act .badge{flex:none;font-size:.74rem;font-weight:700;white-space:nowrap;}
.fact{display:flex;align-items:flex-start;gap:.6rem;font-size:.82rem;color:var(--mut);margin-bottom:.45rem;line-height:1.4;}
.fact svg{flex:none;color:var(--green);margin-top:2px;}

.brow{display:grid;grid-template-columns:64px 1fr 150px;gap:.8rem;align-items:center;padding:.6rem .8rem;border:1px solid var(--line);border-left-width:4px;border-radius:11px;background:#091330;margin-bottom:.4rem;}
.brow.e{opacity:.62;border-left-color:var(--line2);}
.brow.n{border-left-color:var(--blue);}
.brow.c{border-left-color:var(--red);background:rgba(244,80,107,.06);}
.bidx{font-family:var(--mono);font-weight:600;color:var(--mut);font-size:.88rem;}
.bchain{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;min-width:0;}
.bnode{display:inline-flex;align-items:center;gap:.5rem;background:#10224C;border:1px solid var(--line2);border-radius:8px;padding:.3rem .6rem;font-size:.8rem;max-width:100%;}
.bnode b{font-family:var(--mono);font-weight:600;color:#BFD5FF;}
.bnode em{font-style:normal;color:var(--mut);}
.bnull{font-family:var(--mono);font-size:.74rem;color:var(--dim);}
.blen{font-size:.78rem;color:var(--mut);text-align:right;}
.blen.c{color:#FF8DA0;font-weight:700;}

.rcpt{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem 1.4rem;margin-top:.2rem;}
.rcpt div{display:flex;justify-content:space-between;gap:.8rem;font-size:.88rem;border-bottom:1px dashed var(--line);padding:.35rem 0;color:var(--mut);}
.rcpt div b{color:var(--tx);font-family:var(--mono);font-weight:600;text-align:right;}
.rcpt-total{display:flex;justify-content:space-between;align-items:center;margin-top:.8rem;padding:.8rem 1rem;border-radius:12px;background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.5);}
.rcpt-total span{color:var(--mut);font-weight:600;}
.rcpt-total b{font-size:1.5rem;font-family:var(--mono);}
.kvlist .row{display:flex;justify-content:space-between;gap:1rem;padding:.45rem 0;border-bottom:1px dashed var(--line);font-size:.9rem;color:var(--mut);}
.kvlist .row b{color:var(--tx);font-family:var(--mono);font-weight:600;text-align:right;}

.chips{display:flex;flex-wrap:wrap;gap:.5rem;}
.chip{display:inline-flex;align-items:center;gap:.45rem;border:1px solid rgba(59,130,246,.5);background:rgba(59,130,246,.08);color:#CFE0FF;border-radius:10px;padding:.38rem .7rem;font-family:var(--mono);font-size:.8rem;}
.sub-h{font-size:.84rem;color:var(--mut);margin:.5rem 0 .5rem;font-weight:600;}
.hint{font-size:.76rem;color:var(--dim);}

.note{display:flex;align-items:flex-start;gap:.75rem;padding:.75rem .95rem;border-radius:12px;background:rgba(245,165,36,.09);border:1px solid rgba(245,165,36,.4);color:#FFCF7A;font-size:.86rem;margin-top:.8rem;}
.note.info{background:rgba(59,130,246,.09);border-color:rgba(59,130,246,.4);color:#9CC4FF;}
.note.danger{background:rgba(244,80,107,.09);border-color:rgba(244,80,107,.4);color:#FFAAB8;}
.note svg{flex:none;margin-top:2px;}

/* Modern Sidebar Collapse & Expand Controls */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="collapsedControl"] button,
[data-testid="stExpandSidebarButton"] button,
[data-testid="stSidebarHeader"] button {
  background: #0B1633 !important;
  border: 1.5px solid rgba(59, 130, 246, 0.45) !important;
  border-radius: 9px !important;
  color: #93C5FD !important;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4), inset 0 0 6px rgba(59, 130, 246, 0.15) !important;
  transition: all 0.2s ease-in-out !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 34px !important;
  height: 34px !important;
  min-width: 34px !important;
  min-height: 34px !important;
  padding: 0 !important;
}

[data-testid="stSidebarCollapseButton"] button svg,
[data-testid="collapsedControl"] button svg,
[data-testid="stExpandSidebarButton"] button svg,
[data-testid="stSidebarHeader"] button svg {
  color: #60A5FA !important;
  fill: #60A5FA !important;
  width: 18px !important;
  height: 18px !important;
  transition: transform 0.2s ease, color 0.2s ease !important;
}

[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="collapsedControl"] button:hover,
[data-testid="stExpandSidebarButton"] button:hover,
[data-testid="stSidebarHeader"] button:hover {
  background: #142758 !important;
  border-color: #38BDF8 !important;
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.45), 0 4px 12px rgba(0, 0, 0, 0.5) !important;
  transform: translateY(-1px) !important;
}

[data-testid="stSidebarCollapseButton"] button:hover svg,
[data-testid="collapsedControl"] button:hover svg,
[data-testid="stExpandSidebarButton"] button:hover svg,
[data-testid="stSidebarHeader"] button:hover svg {
  color: #FFFFFF !important;
  fill: #FFFFFF !important;
  transform: scale(1.1) !important;
}

/* Streamlit widget skinning */
[data-testid="stHtml"], .stHtml{color:var(--tx);}
[data-testid="stAppDeployButton"]{display:none!important;}
[data-testid="stMainMenuButton"] svg{color:var(--mut)!important;fill:var(--mut)!important;}
[data-testid="stCaptionContainer"] p{color:var(--mut)!important;}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{color:var(--mut)!important;font-size:.82rem!important;font-weight:600!important;}
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], .stSelectbox [role="group"]{
  background:var(--field)!important;border:1px solid var(--line2)!important;border-radius:10px!important;box-shadow:none!important;}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within, .stSelectbox [role="group"]:focus-within{
  border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(59,130,246,.25)!important;}
input, textarea{color:var(--tx)!important;-webkit-text-fill-color:var(--tx)!important;caret-color:var(--cyan);background:transparent!important;}
input::placeholder, textarea::placeholder{color:var(--dim)!important;-webkit-text-fill-color:var(--dim)!important;opacity:1;}
.stSelectbox button{background:transparent!important;color:var(--mut)!important;}
.stSelectbox button svg, [data-testid="stNumberInput"] svg{color:var(--mut)!important;fill:var(--mut)!important;}
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"]{background:#0C1838!important;color:var(--tx)!important;border-color:var(--line2)!important;}
[data-testid="stNumberInputStepUp"] svg, [data-testid="stNumberInputStepDown"] svg{fill:var(--tx)!important;color:var(--tx)!important;}
[data-testid="stSelectboxVirtualDropdown"], [role="listbox"]{background:#0C1838!important;color:var(--tx)!important;border:1px solid var(--line2)!important;border-radius:10px!important;}
[role="listbox"] [role="option"], [data-testid="stSelectboxVirtualDropdown"] li{color:var(--tx)!important;background:transparent!important;}
[role="listbox"] [role="option"]:hover, [role="listbox"] [role="option"][data-focused="true"], [role="listbox"] [role="option"][aria-selected="true"]{background:#16295A!important;}
[data-testid="stRadioOption"] p{color:var(--tx)!important;font-size:.9rem!important;font-weight:500!important;}
[data-testid="stRadioGroup"]{gap:1.4rem!important;}
[data-testid="stRadioOption"]>div>div:first-child{background:var(--field)!important;border:1.5px solid var(--line2)!important;box-shadow:none!important;}
[data-testid="stRadioOption"][data-selected="true"]>div>div:first-child{background:var(--blue)!important;border-color:var(--blue)!important;}
[data-testid="stRadioOption"]>div>div:first-child>div{background:#fff!important;}

.stButton>button[data-testid="stBaseButton-secondary"]{border-radius:10px;font-weight:700;border:1px solid var(--line2);background:#0F1D44;color:var(--tx);min-height:2.6rem;}
.stButton>button[data-testid="stBaseButton-secondary"]:hover{background:#15285C;border-color:var(--blue);color:#fff;}
.stButton>button[data-testid="stBaseButton-primary"]{border-radius:10px;font-weight:700;min-height:2.6rem;background:linear-gradient(135deg,#3B82F6,#2563EB);border:1px solid transparent;color:#fff;box-shadow:0 8px 22px rgba(37,99,235,.35);}
.stButton>button[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.1);color:#fff;}
[class*="st-key-nav_"] .stButton>button{justify-content:flex-start;gap:.65rem;border-radius:11px;padding:.62rem .85rem;min-height:2.7rem;width:100%;
  background:transparent;border:1px solid transparent;color:var(--mut);box-shadow:none;}
[class*="st-key-nav_"] .stButton>button p{color:inherit!important;font-weight:600;font-size:.93rem;}
[class*="st-key-nav_"] .stButton>button:hover{background:rgba(59,130,246,.12);color:var(--tx);border-color:transparent;filter:none;}
[class*="st-key-nav_"] .stButton>button[data-testid="stBaseButton-primary"]{background:linear-gradient(135deg,#3B82F6,#2563EB);color:#fff;box-shadow:0 8px 22px rgba(37,99,235,.38);}

[data-testid="stButtonGroup"] [role="radiogroup"]{gap:.5rem!important;display:flex;flex-wrap:wrap;}
button[data-variant="segmented_control"]{border-radius:10px!important;border:1px solid var(--line2)!important;background:#0B1736!important;color:var(--mut)!important;font-weight:700;padding:.5rem 1rem!important;}
button[data-variant="segmented_control"]:hover{border-color:var(--blue)!important;color:var(--tx)!important;}
button[data-variant="segmented_control"][aria-checked="true"]{background:linear-gradient(135deg,#3B82F6,#2563EB)!important;border-color:transparent!important;color:#fff!important;box-shadow:0 6px 18px rgba(37,99,235,.35)!important;}

[data-testid="stExpander"], [data-testid="stExpander"] details{border:1px solid var(--line)!important;border-radius:14px!important;background:var(--panel)!important;}
[data-testid="stExpander"] details{border:0!important;}
[data-testid="stExpander"] summary{color:var(--tx)!important;}
[data-testid="stExpander"] summary p{color:var(--tx)!important;font-weight:700;}
[data-testid="stExpander"] summary:hover{background:rgba(59,130,246,.06);}

@media (max-width:1100px){
  .kpis, .kpis.k5, .kpis.k4{grid-template-columns:repeat(2,minmax(0,1fr));}
  .rcpt{grid-template-columns:1fr;}
  .brow{grid-template-columns:48px 1fr;} .blen{display:none;}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;}}
"""

# -----------------------------------------------------------------------------
# SVG Icons via CSS Mask
# -----------------------------------------------------------------------------
_ICON_PATHS = {
    "car": '<path d="M4.5 12l1.7-4.6A2 2 0 0 1 8.1 6h7.8a2 2 0 0 1 1.9 1.4L19.5 12"/><rect x="3" y="12" width="18" height="5.5" rx="1.8"/><circle cx="7.5" cy="17.5" r="1.6"/><circle cx="16.5" cy="17.5" r="1.6"/>',
    "bike": '<circle cx="5.5" cy="16.5" r="3"/><circle cx="18.5" cy="16.5" r="3"/><path d="M5.5 16.5L9 9h4l2.5 7.5M13 9l1.6-2.5h2.4M9 9H7M10.5 13.5h6"/>',
    "truck": '<rect x="2" y="7" width="12" height="9" rx="1.5"/><path d="M14 10h4l3 3.2V16h-7z"/><circle cx="7" cy="17.5" r="1.7"/><circle cx="17.5" cy="17.5" r="1.7"/>',
    "ev": '<path d="M13 2.5L5 13.5h6l-1 8 8-11h-6z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "hourglass": '<path d="M7 3h10M7 21h10M8 3v3.5a4 4 0 0 0 1.6 3.2L12 12l2.4-2.3A4 4 0 0 0 16 6.5V3M8 21v-3.5a4 4 0 0 1 1.6-3.2L12 12l2.4 2.3A4 4 0 0 1 16 17.5V21"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.1"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.1"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "hash": '<path d="M5 9h14M5 15h14M9 4L8 20M16 4l-1 16"/>',
    "book": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H12v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H12v16h5.5a2.5 2.5 0 0 1 2.5 2.5z"/>',
    "arrow": '<path d="M4 12h15M13 6l6 6-6 6"/>',
    "arrow-down": '<path d="M12 4v15M6 13l6 6 6-6"/>',
    "log-in": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 8l-4 4 4 4M6 12h11" transform="rotate(180 12 12)"/>',
    "receipt": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    "user": '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.4 7-5.4s6.2 1.8 7 5.4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14zM10 11v6M14 11v6"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5M12 7v5l4 2"/>',
}
_TYPE_ICON = {"Car": "car", "Bike": "bike", "Truck": "truck", "EV": "ev"}


def _build_icon_css() -> str:
    rules = [
        ".ic-s{display:inline-block;flex:none;vertical-align:middle;background-color:currentColor;"
        "-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;-webkit-mask-position:center;mask-position:center;"
        "-webkit-mask-size:contain;mask-size:contain;}"
    ]
    for name, body in _ICON_PATHS.items():
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>"
        )
        url = "data:image/svg+xml;utf8," + quote(svg, safe="")
        rules.append(f'.i-{name}{{-webkit-mask-image:url("{url}");mask-image:url("{url}");}}')
    return "\n".join(rules)


def icon(name: str, size: int = 18) -> str:
    if name not in _ICON_PATHS:
        name = "info"
    return f'<i class="ic-s i-{name}" style="width:{size}px;height:{size}px" aria-hidden="true"></i>'


st.markdown(f"<style>{APP_CSS}\n{_build_icon_css()}</style>", unsafe_allow_html=True)


def type_icon(slot_type: str, size: int = 16) -> str:
    return icon(_TYPE_ICON.get(slot_type, "car"), size)


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def b(value: Any) -> str:
    return f"<b>{e(value)}</b>"


def render(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def fmt_dt(value: Any, with_date: bool = False) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %I:%M %p") if with_date else value.strftime("%I:%M %p")
    return "—" if value is None else str(value)


def flash(kind: str, message_html: str) -> None:
    st.session_state["flash"] = (kind, message_html)


def render_flash() -> None:
    item = st.session_state.pop("flash", None)
    if not item:
        return
    kind, message_html = item
    ic = {"success": "check-circle", "error": "x-circle", "warn": "alert", "info": "info"}.get(kind, "info")
    render(f'<div class="flash {kind}" role="status">{icon(ic, 20)}<div>{message_html}</div></div>')


def empty_state(title: str, body: str) -> None:
    render(f'<div class="empty"><b>{e(title)}</b>{e(body)}</div>')


def card_header(title: str, subtitle: str = "", icon_name: str = "grid") -> None:
    sub = f'<div class="ch-s">{e(subtitle)}</div>' if subtitle else ""
    render(f'<div class="ch">{icon(icon_name, 20)}<span class="t">{e(title)}</span></div>{sub}')


def kpi(label: str, value: Any, sub: str, tone: str, icon_name: str, small: bool = False) -> str:
    vcls = "v sm" if small else "v"
    return (
        f'<div class="kpi {tone}"><div class="ic">{icon(icon_name, 24)}</div>'
        f'<div style="min-width:0"><div class="l">{e(label)}</div><div class="{vcls}">{e(value)}</div>'
        f'<div class="s">{e(sub)}</div></div></div>'
    )


def kpi_row(items: List[str], cols: int) -> None:
    render(f'<div class="kpis k{cols}">{"".join(items)}</div>')


def go(page: str) -> None:
    st.session_state["nav"] = page
    st.session_state.pop("park_full", None)


def slot_stats(slots: List[ParkingSlot]) -> Dict[str, Any]:
    occupied = [s for s in slots if s.is_occupied]
    total = len(slots)
    return {
        "total": total,
        "occupied": len(occupied),
        "available": total - len(occupied),
        "pct": (len(occupied) / total * 100.0) if total else 0.0,
    }


def describe_value(v: Any) -> str:
    if isinstance(v, ParkingSlot):
        state = "occupied" if v.is_occupied else "vacant"
        return f"Slot {v.slot_id} · {v.slot_type} · Floor {v.floor} · {state}"
    if isinstance(v, Vehicle):
        return f"Vehicle {v.license_plate} · {v.vehicle_type} · {v.owner_name or 'no owner'}"
    text = str(v)
    return text if len(text) <= 60 else text[:57] + "…"


def action_details(act: Dict[str, Any]) -> str:
    parts = []
    # Pretty label mapping
    label_map = {
        "license_plate": "Plate",
        "slot_id": "Slot",
        "floor": "Floor",
        "type": "Type",
        "vehicle_type": "Type",
        "owner_name": "Owner",
        "booking_id": "Booking",
        "timestamp": "Time",
        "fee": "Fee",
        "duration_hours": "Duration",
    }
    for k, v in act.items():
        if k == "action":
            continue
        display_label = label_map.get(k, k.replace("_", " ").title())
        if isinstance(v, datetime):
            v_str = fmt_dt(v, with_date=False)
        elif k == "fee" and isinstance(v, (int, float)):
            v_str = f"{CURRENCY}{v:.2f}"
        elif k == "duration_hours" and isinstance(v, (int, float)):
            v_str = f"{v:.2f}h"
        else:
            v_str = str(v)
        parts.append(
            f'<span class="act-prop"><b class="act-prop-lbl">{e(display_label)}:</b> <span class="act-prop-val">{e(v_str)}</span></span>'
        )
    return "".join(parts)


def activity_timeline_html(actions: List[Dict[str, Any]]) -> str:
    """Renders recent actions in a compact, modern vertical timeline layout."""
    if not actions:
        return ""
    items = []
    for act in actions:
        name = act.get("action", "ACTION")
        hl, badge, tone = ACTION_META.get(name, (name.replace("_", " ").title(), name, "blue"))
        ic_name = ACTION_ICONS.get(name, "clock")
        
        # Display timestamp with seconds precision to distinguish rapid/batch events
        ts = act.get("timestamp")
        if isinstance(ts, datetime):
            ts_str = ts.strftime("%I:%M:%S %p")
        elif ts:
            ts_str = str(ts)
        else:
            ts_str = "Just now"

        tags = []
        if act.get("license_plate"):
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Plate:</span> <b class="t-prop-v plate-text">{e(act["license_plate"])}</b></span>')
        if act.get("slot_id"):
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Slot:</span> <b class="t-prop-v slot-text">{e(act["slot_id"])}</b></span>')
        if act.get("floor"):
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Floor:</span> <span class="t-prop-v">{e(str(act["floor"]))}</span></span>')
        if act.get("type"):
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Type:</span> <span class="t-prop-v">{e(str(act["type"]))}</span></span>')
        if act.get("fee") is not None:
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Fee:</span> <b class="t-prop-v fee-text">{CURRENCY}{float(act["fee"]):.2f}</b></span>')
        if act.get("booking_id"):
            tags.append(f'<span class="t-prop"><span class="t-prop-k">Booking:</span> <span class="t-prop-v">{e(act["booking_id"])}</span></span>')

        items.append(
            f'<div class="t-node">'
            f'<i class="t-dot d-{tone}"></i>'
            f'<div class="t-body">'
            f'<div class="t-header">'
            f'<div class="t-title">{icon(ic_name, 14)}<span>{e(hl)}</span></div>'
            f'<div class="t-meta">'
            f'<span class="t-time">{e(ts_str)}</span>'
            f'<span class="badge t-{tone}">{e(badge)}</span>'
            f'</div>'
            f'</div>'
            f'<div class="t-props">{"".join(tags)}</div>'
            f'</div></div>'
        )
    return f'<div class="timeline">{"".join(items)}</div>'


def queue_pipeline_html(q_state: List[Dict[str, Any]], limit: Optional[int] = None) -> str:
    mini = limit is not None
    shown = q_state[:limit] if mini else q_state
    n = len(q_state)
    out = []
    for idx, item in enumerate(shown):
        tags = ""
        cls = "pnode"
        if idx == 0:
            cls += " front"
            tags += '<span class="f">Front</span>'
        if idx == n - 1:
            cls += " rear"
            tags += '<span class="r">Rear</span>'
        vt = item.get("vehicle_type", "Car")
        body = (
            f'<div class="{cls}"><div class="ptag">{tags}</div>'
            f'<div class="pl">{e(item.get("license_plate", "N/A"))}</div>'
            f'<div class="pm">{type_icon(vt, 15)}<span>{e(vt)}</span></div>'
        )
        if not mini:
            body += (
                f'<div class="pm">{icon("user", 15)}<span>{e(item.get("owner_name") or "No owner name")}</span></div>'
                f'<div class="pm">{icon("clock", 15)}<span>{e(fmt_dt(item.get("created_at"), with_date=True))}</span></div>'
                f'<div class="pk">{e(item.get("booking_id", "N/A"))}</div>'
            )
        body += "</div>"
        out.append(body)
        out.append(f'<div class="parrow">{icon("arrow", 20)}</div>')
    if mini and n > len(shown):
        out.append(f'<div class="pnull">+{n - len(shown)} more</div>')
    else:
        out.append('<div class="pnull">NULL</div>')
    return f'<div class="pipe{" mini" if mini else ""}">{"".join(out)}</div>'


def stack_frames_html(stack_state: List[Dict[str, Any]], limit: Optional[int] = None) -> str:
    mini = limit is not None
    shown = stack_state[:limit] if mini else stack_state
    tone_color = {"green": "#22C55E", "blue": "#3B82F6", "violet": "#8B7CF6", "amber": "#F5A524", "red": "#F4506B"}
    out = []
    for idx, act in enumerate(shown):
        name = act.get("action", "N/A")
        headline, badge, tone = ACTION_META.get(name, (name, name, "blue"))
        pos = '<span class="pos top">Top of stack</span>' if idx == 0 else f'<span class="pos">Frame {idx}</span>'
        details = "" if mini else f'<div class="kv">{action_details(act)}</div>'
        out.append(
            f'<div class="sframe{" top" if idx == 0 else ""}" style="border-left-color:{tone_color.get(tone, "#3B82F6")}">'
            f'<div class="sh" title="{e(name)}: {e(headline)}">{pos}<b>{e(name)}</b><span class="sf-desc">{e(headline)}</span><span class="badge t-{tone}">{e(badge)}</span></div>{details}</div>'
        )
        if idx < len(shown) - 1:
            out.append(f'<div class="sarrow">{icon("arrow-down", 16)}</div>')
    if mini and len(stack_state) > len(shown):
        out.append(f'<div class="hint" style="margin-top:.4rem">+{len(stack_state) - len(shown)} more frames below</div>')
    return f'<div class="stk{" mini" if mini else ""}">{"".join(out)}</div>'


def topdown_vehicle_svg(vehicle_type: str) -> str:
    """Renders a realistic top-down 2D vehicle SVG illustration for parking spaces."""
    vtype = (vehicle_type or "Car").lower()
    if "bike" in vtype or "motor" in vtype:
        return (
            '<svg class="bay-car-svg" viewBox="0 0 54 96" width="54" height="96" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '<filter id="bikeShadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2" result="blur"/></filter>'
            '</defs>'
            '<ellipse cx="27" cy="48" rx="14" ry="40" fill="rgba(0,0,0,0.55)" filter="url(#bikeShadow)"/>'
            '<rect x="24" y="6" width="6" height="20" rx="3" fill="#0A1122" stroke="#475569" stroke-width="1.2"/>'
            '<line x1="12" y1="24" x2="42" y2="24" stroke="#94A3B8" stroke-width="3" stroke-linecap="round"/>'
            '<circle cx="10" cy="24" r="2.5" fill="#334155" stroke="#94A3B8" stroke-width="0.8"/>'
            '<circle cx="44" cy="24" r="2.5" fill="#334155" stroke="#94A3B8" stroke-width="0.8"/>'
            '<path d="M 21 28 C 21 24, 33 24, 33 28 L 32 52 C 32 58, 22 58, 22 52 Z" fill="#F4506B" stroke="#B91C1C" stroke-width="1.2"/>'
            '<rect x="22" y="52" width="10" height="20" rx="3" fill="#1E293B" stroke="#0F172A"/>'
            '<rect x="24" y="70" width="6" height="20" rx="3" fill="#0A1122" stroke="#475569" stroke-width="1.2"/>'
            '<circle cx="27" cy="8" r="2.5" fill="#FEF08A"/>'
            '<rect x="24" y="88" width="6" height="2" rx="1" fill="#EF4444"/>'
            '</svg>'
        )
    elif "truck" in vtype or "heavy" in vtype:
        return (
            '<svg class="bay-car-svg" viewBox="0 0 78 128" width="76" height="128" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '<filter id="truckShadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="blur"/></filter>'
            '<linearGradient id="truckCabGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
            '<stop offset="0%" stop-color="#1E293B"/><stop offset="50%" stop-color="#334155"/><stop offset="100%" stop-color="#1E293B"/>'
            '</linearGradient>'
            '</defs>'
            '<rect x="8" y="10" width="62" height="110" rx="8" fill="rgba(0,0,0,0.55)" filter="url(#truckShadow)"/>'
            '<rect x="3" y="18" width="7" height="18" rx="2" fill="#070E1C"/><rect x="68" y="18" width="7" height="18" rx="2" fill="#070E1C"/>'
            '<rect x="2" y="80" width="8" height="18" rx="2" fill="#070E1C"/><rect x="68" y="80" width="8" height="18" rx="2" fill="#070E1C"/>'
            '<rect x="2" y="100" width="8" height="18" rx="2" fill="#070E1C"/><rect x="68" y="100" width="8" height="18" rx="2" fill="#070E1C"/>'
            '<rect x="10" y="8" width="58" height="34" rx="6" fill="url(#truckCabGrad)" stroke="#475569" stroke-width="1.2"/>'
            '<path d="M 16 12 Q 39 9 62 12 L 60 22 Q 39 19 18 22 Z" fill="#080F1E" stroke="#38BDF8" stroke-width="1"/>'
            '<rect x="3" y="20" width="8" height="4" rx="1.5" fill="#475569"/><rect x="67" y="20" width="8" height="4" rx="1.5" fill="#475569"/>'
            '<rect x="10" y="44" width="58" height="74" rx="3" fill="#0F172A" stroke="#475569" stroke-width="1.5"/>'
            '<line x1="10" y1="62" x2="68" y2="62" stroke="#1E293B" stroke-dasharray="3 3"/>'
            '<line x1="10" y1="82" x2="68" y2="82" stroke="#1E293B" stroke-dasharray="3 3"/>'
            '<line x1="10" y1="102" x2="68" y2="102" stroke="#1E293B" stroke-dasharray="3 3"/>'
            '<circle cx="18" cy="10" r="2.5" fill="#FEF08A"/><circle cx="60" cy="10" r="2.5" fill="#FEF08A"/>'
            '<circle cx="34" cy="9" r="1.5" fill="#F59E0B"/><circle cx="39" cy="9" r="1.5" fill="#F59E0B"/><circle cx="44" cy="9" r="1.5" fill="#F59E0B"/>'
            '<rect x="15" y="117" width="10" height="3" rx="1.5" fill="#EF4444"/><rect x="53" y="117" width="10" height="3" rx="1.5" fill="#EF4444"/>'
            '</svg>'
        )
    elif "ev" in vtype or "electric" in vtype:
        return (
            '<svg class="bay-car-svg" viewBox="0 0 74 120" width="72" height="120" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '<filter id="evShadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="blur"/></filter>'
            '<linearGradient id="evBodyGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
            '<stop offset="0%" stop-color="#0E1E38"/><stop offset="50%" stop-color="#1E3A8A"/><stop offset="100%" stop-color="#0E1E38"/>'
            '</linearGradient>'
            '</defs>'
            '<rect x="8" y="10" width="58" height="102" rx="16" fill="rgba(0,0,0,0.55)" filter="url(#evShadow)"/>'
            '<rect x="3" y="24" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#06B6D4" stroke-width="0.8"/>'
            '<rect x="64" y="24" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#06B6D4" stroke-width="0.8"/>'
            '<rect x="3" y="80" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#06B6D4" stroke-width="0.8"/>'
            '<rect x="64" y="80" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#06B6D4" stroke-width="0.8"/>'
            '<path d="M 12 28 C 12 12, 22 6, 37 6 C 52 6, 62 12, 62 28 L 63 94 C 63 108, 54 114, 37 114 C 20 114, 11 108, 11 94 Z" fill="url(#evBodyGrad)" stroke="#06B6D4" stroke-width="1.5"/>'
            '<path d="M 18 36 C 24 32, 50 32, 56 36 L 54 50 C 44 47, 30 47, 20 50 Z" fill="#080F1E" stroke="#38BDF8" stroke-width="1"/>'
            '<path d="M 11 38 C 7 38, 5 42, 8 46 L 13 44 Z" fill="#06B6D4"/>'
            '<path d="M 63 38 C 67 38, 69 42, 66 46 L 61 44 Z" fill="#06B6D4"/>'
            '<rect x="22" y="52" width="30" height="26" rx="4" fill="#091424" stroke="#06B6D4" stroke-width="0.8"/>'
            '<path d="M 38 56 L 34 65 L 38 65 L 36 74 L 42 63 L 38 63 Z" fill="#06B6D4"/>'
            '<path d="M 20 81 C 28 78, 46 78, 54 81 L 56 94 C 47 91, 27 91, 18 94 Z" fill="#080F1E" stroke="#38BDF8" stroke-width="1"/>'
            '<ellipse cx="18" cy="11" rx="4" ry="2.5" fill="#67E8F9"/><ellipse cx="56" cy="11" rx="4" ry="2.5" fill="#67E8F9"/>'
            '<line x1="22" y1="11" x2="52" y2="11" stroke="#67E8F9" stroke-width="1.5"/>'
            '<rect x="15" y="110" width="44" height="3" rx="1.5" fill="#EF4444"/>'
            '</svg>'
        )
    else:
        # Standard Car / Sedan top-down (White Sedan matching reference image S1)
        return (
            '<svg class="bay-car-svg" viewBox="0 0 74 120" width="72" height="120" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '<filter id="carShadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="blur"/></filter>'
            '<linearGradient id="carBodyGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
            '<stop offset="0%" stop-color="#E2E8F0"/><stop offset="15%" stop-color="#FFFFFF"/><stop offset="85%" stop-color="#FFFFFF"/><stop offset="100%" stop-color="#CBD5E1"/>'
            '</linearGradient>'
            '<linearGradient id="glassGrad" x1="0%" y1="0%" x2="0%" y2="100%">'
            '<stop offset="0%" stop-color="#0F172A"/><stop offset="100%" stop-color="#1E293B"/>'
            '</linearGradient>'
            '</defs>'
            '<rect x="8" y="10" width="58" height="102" rx="16" fill="rgba(0,0,0,0.55)" filter="url(#carShadow)"/>'
            '<rect x="3" y="24" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#334155" stroke-width="1"/>'
            '<rect x="64" y="24" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#334155" stroke-width="1"/>'
            '<rect x="3" y="80" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#334155" stroke-width="1"/>'
            '<rect x="64" y="80" width="7" height="18" rx="2.5" fill="#0A0F1D" stroke="#334155" stroke-width="1"/>'
            '<path d="M 12 28 C 12 12, 22 6, 37 6 C 52 6, 62 12, 62 28 L 63 94 C 63 108, 54 114, 37 114 C 20 114, 11 108, 11 94 Z" fill="url(#carBodyGrad)" stroke="#94A3B8" stroke-width="1.2"/>'
            '<path d="M 23 10 L 25 32 M 51 10 L 49 32" stroke="#CBD5E1" stroke-width="1" stroke-linecap="round"/>'
            '<path d="M 18 36 C 24 32, 50 32, 56 36 L 54 50 C 44 47, 30 47, 20 50 Z" fill="url(#glassGrad)" stroke="#38BDF8" stroke-width="0.8"/>'
            '<path d="M 24 36 L 22 48" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round"/>'
            '<path d="M 11 38 C 7 38, 5 42, 8 46 L 13 44 Z" fill="#F8FAFC" stroke="#64748B" stroke-width="0.8"/>'
            '<path d="M 63 38 C 67 38, 69 42, 66 46 L 61 44 Z" fill="#F8FAFC" stroke="#64748B" stroke-width="0.8"/>'
            '<rect x="22" y="52" width="30" height="26" rx="4" fill="#0B1329" stroke="#1E293B" stroke-width="1"/>'
            '<line x1="22" y1="65" x2="52" y2="65" stroke="rgba(255,255,255,0.08)"/>'
            '<path d="M 20 81 C 28 78, 46 78, 54 81 L 56 94 C 47 91, 27 91, 18 94 Z" fill="url(#glassGrad)" stroke="#38BDF8" stroke-width="0.8"/>'
            '<path d="M 23 83 L 21 92" stroke="rgba(255,255,255,0.3)" stroke-width="1.2" stroke-linecap="round"/>'
            '<path d="M 22 102 C 30 100, 44 100, 52 102" stroke="#94A3B8" stroke-width="1" fill="none"/>'
            '<ellipse cx="18" cy="11" rx="4" ry="2.5" fill="#FEF08A"/>'
            '<ellipse cx="56" cy="11" rx="4" ry="2.5" fill="#FEF08A"/>'
            '<rect x="15" y="110" width="10" height="3" rx="1.5" fill="#EF4444"/>'
            '<rect x="49" y="110" width="10" height="3" rx="1.5" fill="#EF4444"/>'
            '</svg>'
        )


def render_svg_bay(slot: ParkingSlot, orientation: str = "north", is_selected: bool = False, clickable: bool = True, is_admin: Optional[bool] = None) -> str:
    """Renders a single parking bay SVG element within the unified facility."""
    if is_admin is None:
        is_admin = clickable

    is_occ = slot.is_occupied and slot.vehicle is not None
    is_south = orientation == "south"
    orient_cls = "south" if is_south else "north"
    status_cls = "occ" if is_occ else "vac"

    stopper_y = 206 if is_south else 8
    curb_color = "#EF4444" if is_occ else "#22C55E"
    stopper_svg = (
        f'<g class="bay-stopper">'
        f'<rect class="stopper-block" x="25" y="{stopper_y}" width="100" height="6" rx="2" fill="#1E293B" stroke="rgba(255,255,255,0.2)"/>'
        f'<circle class="bay-curb" cx="28" cy="{stopper_y + 3}" r="2.5" fill="{curb_color}"/>'
        f'<circle class="bay-curb" cx="122" cy="{stopper_y + 3}" r="2.5" fill="{curb_color}"/>'
        f'</g>'
    )

    head_y_id = 32 if not is_south else 34
    head_y_st = 48 if not is_south else 50
    st_color = "#EF4444" if is_occ else "#22C55E"
    st_text = "OCCUPIED" if is_occ else "AVAILABLE"
    
    header_svg = (
        f'<g class="bay-head">'
        f'<text class="bay-id" x="75" y="{head_y_id}" text-anchor="middle" font-family="\'JetBrains Mono\', monospace" font-size="15" font-weight="800" fill="#FFFFFF">{e(slot.slot_id)}</text>'
        f'<text class="bay-status" x="75" y="{head_y_st}" text-anchor="middle" font-family="\'Inter\', sans-serif" font-size="10.5" font-weight="800" letter-spacing="1.5" fill="{st_color}">{st_text}</text>'
        f'</g>'
    )

    selected_overlay = ""
    if is_selected:
        selected_overlay = (
            f'<g class="bay-selected-ring">'
            f'<rect x="-3" y="-3" width="156" height="226" rx="10" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-dasharray="6 3"/>'
            f'<rect x="36" y="-11" width="78" height="18" rx="4" fill="#0284C7"/>'
            f'<text x="75" y="2" text-anchor="middle" font-family="\'Inter\', sans-serif" font-size="9" font-weight="800" fill="#FFFFFF" letter-spacing="0.5">INSPECTING</text>'
            f'</g>'
        )

    if is_occ:
        v = slot.vehicle
        if is_admin:
            owner_name = (v.owner_name or "").strip()
            if owner_name:
                disp_text = owner_name if len(owner_name) <= 16 else owner_name[:15].rstrip() + "…"
                owner_svg = (
                    f'<text class="bay-owner" x="75" y="208" text-anchor="middle" dominant-baseline="central" '
                    f'font-family="\'Inter\', sans-serif" font-size="9" font-weight="600" fill="#94A3B8">'
                    f'<title>{e(owner_name)}</title>{e(disp_text)}</text>'
                )
            else:
                type_lbl = v.vehicle_type or "Car"
                owner_svg = (
                    f'<text class="bay-type-lbl" x="75" y="208" text-anchor="middle" dominant-baseline="central" '
                    f'font-family="\'Inter\', sans-serif" font-size="9" font-weight="700" letter-spacing="0.5" fill="#64748B">'
                    f'{e(type_lbl)}</text>'
                )

            plate_y = 177
            plate_h = 20
            plate_w = 114
            plate_x = 18
            plate_font = "11"

            vtype = (v.vehicle_type or "Car").lower()
            if "bike" in vtype or "motor" in vtype:
                car_x = 48
                car_y = 58
            elif "truck" in vtype or "heavy" in vtype:
                car_x = 36
                car_y = 46
            else:
                car_x = 38
                car_y = 50
        else:
            owner_svg = ""
            plate_y = 186
            plate_h = 22
            plate_w = 118
            plate_x = 16
            plate_font = "11.5"

            vtype = (v.vehicle_type or "Car").lower()
            if "bike" in vtype or "motor" in vtype:
                car_x = 48
                car_y = 66
            elif "truck" in vtype or "heavy" in vtype:
                car_x = 36
                car_y = 52
            else:
                car_x = 38
                car_y = 56
        
        car_svg = topdown_vehicle_svg(v.vehicle_type)
        
        plate_badge = (
            f'<g class="bay-plate-badge">'
            f'<rect x="{plate_x}" y="{plate_y}" width="{plate_w}" height="{plate_h}" rx="4" fill="#070D1B" stroke="#334155" stroke-width="1.3"/>'
            f'<text class="bay-plate" x="75" y="{plate_y + plate_h // 2}" text-anchor="middle" dominant-baseline="central" font-family="\'JetBrains Mono\', monospace" font-size="{plate_font}" font-weight="800" fill="#FFFFFF" letter-spacing="0.5">{e(v.license_plate)}</text>'
            f'</g>'
        )

        bdr_color = "#38BDF8" if is_selected else "#EF4444"
        bdr_fill = "rgba(56, 189, 248, 0.12)" if is_selected else "rgba(239, 68, 68, 0.08)"
        bdr_w = "3.2" if is_selected else "2.5"

        bay_markup = (
            f'<g class="bay {status_cls} {orient_cls}{" selected" if is_selected else ""}" id="bay-{e(slot.slot_id)}">'
            f'<rect class="bay-boundary" x="0" y="0" width="150" height="220" rx="8" fill="{bdr_fill}" stroke="{bdr_color}" stroke-width="{bdr_w}"/>'
            f'{selected_overlay}'
            f'{stopper_svg}'
            f'{header_svg}'
            f'<g class="bay-occ-center">'
            f'<g transform="translate({car_x}, {car_y})">'
            f'{car_svg}'
            f'</g>'
            f'{plate_badge}'
            f'{owner_svg}'
            f'</g>'
            f'<text style="display:none;" class="bay-status">Occupied</text>'
            f'</g>'
        )
        if clickable:
            return f'<a href="?selected_slot={quote(slot.slot_id)}" target="_self" class="svg-bay-link">{bay_markup}</a>'
        return bay_markup

    # VACANT / AVAILABLE BAY
    p_symbol_svg = (
        f'<g class="bay-p-symbol">'
        f'<rect x="49" y="80" width="52" height="52" rx="12" fill="rgba(34, 197, 94, 0.1)" stroke="rgba(34, 197, 94, 0.45)" stroke-width="2"/>'
        f'<text class="bay-p-letter" x="75" y="117" text-anchor="middle" font-family="\'JetBrains Mono\', monospace" font-size="34" font-weight="900" fill="#22C55E">P</text>'
        f'</g>'
    )
    avail_indicator = (
        f'<g class="bay-status-avail">'
        f'<circle cx="48" cy="154" r="3.5" fill="#22C55E"/>'
        f'<text class="bay-vac-lbl" x="58" y="158" font-family="\'Inter\', sans-serif" font-size="10.5" font-weight="700" fill="#22C55E">Available</text>'
        f'</g>'
    )
    type_badge = (
        f'<g class="bay-type-badge">'
        f'<rect x="45" y="174" width="60" height="20" rx="4" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>'
        f'<text class="bay-type-lbl" x="75" y="188" text-anchor="middle" font-family="\'Inter\', sans-serif" font-size="10" font-weight="700" fill="#94A3B8">{e(slot.slot_type)}</text>'
        f'</g>'
    )

    bdr_color = "#38BDF8" if is_selected else "#22C55E"
    bdr_fill = "rgba(56, 189, 248, 0.12)" if is_selected else "rgba(34, 197, 94, 0.05)"
    bdr_w = "3.2" if is_selected else "2.5"

    bay_markup = (
        f'<g class="bay {status_cls} {orient_cls}{" selected" if is_selected else ""}" id="bay-{e(slot.slot_id)}">'
        f'<rect class="bay-boundary" x="0" y="0" width="150" height="220" rx="8" fill="{bdr_fill}" stroke="{bdr_color}" stroke-width="{bdr_w}"/>'
        f'{selected_overlay}'
        f'{stopper_svg}'
        f'{header_svg}'
        f'<g class="bay-vac-center">'
        f'{p_symbol_svg}'
        f'{avail_indicator}'
        f'{type_badge}'
        f'</g>'
        f'<text style="display:none;" class="bay-status">Available Vacant</text>'
        f'</g>'
    )
    if clickable:
        return f'<a href="?selected_slot={quote(slot.slot_id)}" target="_self" class="svg-bay-link">{bay_markup}</a>'
    return bay_markup


def stall_html(slot: ParkingSlot, compact: bool = False, orientation: str = "north") -> str:
    stopper = '<div class="bay-stopper"><span class="stopper-block"></span><i class="bay-curb"></i></div>'
    top = (
        f'<div class="bay-head">'
        f'<span class="bay-id">{e(slot.slot_id)}</span>'
        f'<span class="bay-tag" title="{e(slot.slot_type)} slot">{type_icon(slot.slot_type, 13)} {e(slot.slot_type)}</span>'
        f'</div>'
    )
    is_south = orientation == "south"
    orient_cls = "south" if is_south else "north"

    if slot.is_occupied and slot.vehicle:
        v = slot.vehicle
        owner_name = (v.owner_name or "").strip()
        owner_html = f'<div class="bay-owner" title="Driver: {e(owner_name)}">{e(owner_name)}</div>' if owner_name else ""
        car_svg = topdown_vehicle_svg(v.vehicle_type)
        header_part = f'{stopper}{top}' if not is_south else f'{top}'
        footer_part = f'{stopper}' if is_south else ''
        return (
            f'<div class="bay occ {orient_cls}" title="Slot {e(slot.slot_id)}: Occupied by {e(v.license_plate)}">'
            f'{header_part}'
            f'<div class="bay-occ-center">'
            f'<div class="bay-topdown-wrap">{car_svg}</div>'
            f'<div class="bay-plate-badge"><b class="bay-plate">{e(v.license_plate)}</b></div>'
            f'{owner_html}'
            f'</div>'
            f'<div class="bay-foot">'
            f'<span class="bay-status"><i class="bay-curb"></i>Occupied</span>'
            f'<span class="bay-type-lbl">{e(v.vehicle_type)}</span>'
            f'</div>'
            f'{footer_part}'
            f'</div>'
        )
    header_part = f'{stopper}{top}' if not is_south else f'{top}'
    footer_part = f'{stopper}' if is_south else ''
    return (
        f'<div class="bay vac {orient_cls}" title="Slot {e(slot.slot_id)}: Available for {e(slot.slot_type)}">'
        f'{header_part}'
        f'<div class="bay-vac-center">'
        f'<div class="bay-p-symbol"><span class="bay-p-letter">P</span></div>'
        f'<div class="bay-vac-lbl">Available</div>'
        f'</div>'
        f'<div class="bay-foot">'
        f'<span class="bay-status"><i class="bay-curb"></i>Vacant</span>'
        f'<span class="bay-type-lbl">{e(slot.slot_type)}</span>'
        f'</div>'
        f'{footer_part}'
        f'</div>'
    )


def lot_legend_html() -> str:
    return (
        '<div class="lot-legend">'
        '<span style="font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:.05em;font-size:.72rem;">Legend:</span>'
        '<span class="lot-legend-item"><i class="lot-legend-dot vac"></i>Available (Green)</span>'
        '<span class="lot-legend-item"><i class="lot-legend-dot occ"></i>Occupied (Red)</span>'
        '<span style="margin-left:auto;color:var(--dim);font-size:.72rem;">Top-Down Facility View • Real-Time Synchronized</span>'
        '</div>'
    )


def slot_inspector_panel_html(slot: ParkingSlot) -> str:
    """Renders a clean, modern information panel for an inspected parking bay."""
    is_occ = slot.is_occupied and slot.vehicle is not None
    v = slot.vehicle if is_occ else None
    status_label = "OCCUPIED" if is_occ else "AVAILABLE"
    status_cls = "occ" if is_occ else "vac"
    status_color = "#EF4444" if is_occ else "#22C55E"
    plate_text = v.license_plate if v else "None (Slot is vacant)"
    owner_text = (v.owner_name or "—") if v else "—"
    time_text = fmt_dt(v.entry_time, with_date=True) if v else "—"

    extra_cells = ""
    if is_occ and v:
        duration_hrs = round((datetime.now() - v.entry_time).total_seconds() / 3600.0, 2)
        extra_cells = (
            f'<div class="sip-cell"><span class="sip-lbl">Driver / Owner</span><b class="sip-val">{e(owner_text)}</b></div>'
            f'<div class="sip-cell"><span class="sip-lbl">Entry Time</span><b class="sip-val">{e(time_text)} (~{duration_hrs:.2f} hrs)</b></div>'
        )

    return (
        f'<div class="slot-inspector-panel {status_cls}">'
        f'<div class="sip-top">'
        f'<div class="sip-title">'
        f'<span class="sip-badge-slot">{e(slot.slot_id)}</span>'
        f'<span class="sip-deck">Floor {e(slot.floor)} · {e(slot.slot_type)} Bay</span>'
        f'</div>'
        f'<div class="sip-status-tag" style="background:{status_color}22;color:{status_color};border:1.5px solid {status_color}66;">'
        f'<i class="sip-dot" style="background:{status_color};"></i>{status_label}'
        f'</div>'
        f'</div>'
        f'<div class="sip-grid">'
        f'<div class="sip-cell"><span class="sip-lbl">Slot ID</span><b class="sip-val mono">{e(slot.slot_id)}</b></div>'
        f'<div class="sip-cell"><span class="sip-lbl">Floor Level</span><b class="sip-val">Floor {e(slot.floor)}</b></div>'
        f'<div class="sip-cell"><span class="sip-lbl">Vehicle Type</span><b class="sip-val">{type_icon(slot.slot_type, 15)} {e(slot.slot_type)}</b></div>'
        f'<div class="sip-cell"><span class="sip-lbl">Availability Status</span><b class="sip-val" style="color:{status_color}">{status_label}</b></div>'
        f'<div class="sip-cell span-2"><span class="sip-lbl">Registration Number</span><b class="sip-val plate">{e(plate_text)}</b></div>'
        f'{extra_cells}'
        f'</div>'
        f'</div>'
    )


def lot_html(slots: List[ParkingSlot], show_legend: bool = True, compact: bool = False, selected_slot_id: Optional[str] = None, clickable: bool = True, is_admin: Optional[bool] = None) -> str:
    if is_admin is None:
        is_admin = clickable
    floors: Dict[int, List[ParkingSlot]] = {}
    for s in slots:
        floors.setdefault(s.floor, []).append(s)
    out = []
    if show_legend:
        out.append(lot_legend_html())
    
    for fl in sorted(floors):
        group = floors[fl]
        vac = sum(1 for s in group if not s.is_occupied)
        tot = len(group)
        pct_occ = ((tot - vac) / tot * 100.0) if tot else 0.0

        # Dynamic balanced partitioning:
        # If <= 3 slots: 1 row facing the driving aisle
        # If >= 4 slots: balanced evenly into North and South facing rows
        if len(group) <= 3:
            north_slots = group
            south_slots = []
        else:
            mid = (len(group) + 1) // 2
            north_slots = group[:mid]
            south_slots = group[mid:]

        w_bay = 150
        h_bay = 220
        gap = 14
        cols = max(len(north_slots), len(south_slots) if south_slots else 0)
        
        # Dimensions
        side_margin = 85
        content_w = cols * w_bay + (cols - 1) * gap
        total_w = max(content_w + 2 * side_margin, 660)
        
        y_top_margin = 25
        y_north = y_top_margin + 10
        y_aisle = y_north + h_bay + 12
        h_aisle = 85
        y_south = y_aisle + h_aisle + 12
        y_bot_margin = 25
        
        if south_slots:
            total_h = y_south + h_bay + y_bot_margin
        else:
            total_h = y_aisle + h_aisle + y_bot_margin

        # Render North row bays with horizontal centering
        w_north = len(north_slots) * w_bay + (len(north_slots) - 1) * gap
        start_x_north = (total_w - w_north) / 2
        north_bays_svg = []
        for i, s in enumerate(north_slots):
            bx = start_x_north + i * (w_bay + gap)
            by = y_north
            is_sel = (s.slot_id == selected_slot_id)
            bay_content = render_svg_bay(s, orientation="north", is_selected=is_sel, clickable=clickable, is_admin=is_admin)
            north_bays_svg.append(f'<g transform="translate({bx}, {by})">{bay_content}</g>')

        # Render South row bays if present
        south_bays_svg = []
        if south_slots:
            w_south = len(south_slots) * w_bay + (len(south_slots) - 1) * gap
            start_x_south = (total_w - w_south) / 2
            for j, s in enumerate(south_slots):
                bx = start_x_south + j * (w_bay + gap)
                by = y_south
                is_sel = (s.slot_id == selected_slot_id)
                bay_content = render_svg_bay(s, orientation="south", is_selected=is_sel, clickable=clickable, is_admin=is_admin)
                south_bays_svg.append(f'<g transform="translate({bx}, {by})">{bay_content}</g>')

        # Realistic Landscaping Hedge Strips on Left and Right borders (matching reference image)
        trees_svg = []
        # Left hedge planter
        trees_svg.append(
            f'<g class="landscaping-left">'
            f'<rect x="14" y="20" width="38" height="{total_h - 40}" rx="8" fill="#042F24" stroke="#064E3B" stroke-width="1.5"/>'
            f'<rect x="18" y="24" width="30" height="{total_h - 48}" rx="6" fill="#064E3B"/>'
        )
        for hy in range(36, total_h - 45, 42):
            trees_svg.append(
                f'<ellipse cx="33" cy="{hy}" rx="14" ry="17" fill="#15803D" opacity="0.9"/>'
                f'<ellipse cx="32" cy="{hy - 2}" rx="10" ry="12" fill="#22C55E" opacity="0.65"/>'
            )
        trees_svg.append('</g>')

        # Right hedge planter
        trees_svg.append(
            f'<g class="landscaping-right">'
            f'<rect x="{total_w - 52}" y="20" width="38" height="{total_h - 40}" rx="8" fill="#042F24" stroke="#064E3B" stroke-width="1.5"/>'
            f'<rect x="{total_w - 48}" y="24" width="30" height="{total_h - 48}" rx="6" fill="#064E3B"/>'
        )
        for hy in range(36, total_h - 45, 42):
            trees_svg.append(
                f'<ellipse cx="{total_w - 33}" cy="{hy}" rx="14" ry="17" fill="#15803D" opacity="0.9"/>'
                f'<ellipse cx="{total_w - 32}" cy="{hy - 2}" rx="10" ry="12" fill="#22C55E" opacity="0.65"/>'
            )
        trees_svg.append('</g>')

        # Driving Aisle SVG
        arrow_y = y_aisle + h_aisle / 2
        aisle_arrows_svg = []
        for ax in [total_w * 0.28, total_w * 0.5, total_w * 0.72]:
            aisle_arrows_svg.append(
                f'<path d="M {ax - 12} {arrow_y - 8} L {ax + 8} {arrow_y} L {ax - 12} {arrow_y + 8} L {ax - 6} {arrow_y} Z" fill="#EAB308"/>'
            )

        driving_aisle_svg = (
            f'<g class="driving-aisle">'
            f'<rect x="62" y="{y_aisle}" width="{total_w - 124}" height="{h_aisle}" fill="#080F1E" rx="4"/>'
            f'<line x1="66" y1="{y_aisle}" x2="{total_w - 66}" y2="{y_aisle}" stroke="rgba(255,255,255,0.4)" stroke-width="2.2"/>'
            f'<line x1="66" y1="{y_aisle + h_aisle}" x2="{total_w - 66}" y2="{y_aisle + h_aisle}" stroke="rgba(255,255,255,0.4)" stroke-width="2.2"/>'
            f'<line x1="74" y1="{arrow_y}" x2="{total_w - 74}" y2="{arrow_y}" stroke="rgba(255,255,255,0.38)" stroke-width="2" stroke-dasharray="14 10"/>'
            f'{"".join(aisle_arrows_svg)}'
            f'<text x="{total_w / 2}" y="{arrow_y - 14}" text-anchor="middle" font-family="\'JetBrains Mono\', monospace" font-size="10.5" font-weight="800" letter-spacing="2.5" fill="rgba(255,255,255,0.45)">DRIVING AISLE • ONE WAY TRAFFIC</text>'
            f'</g>'
        )

        facility_svg = (
            f'<svg class="facility-canvas-svg" viewBox="0 0 {total_w} {total_h}" width="100%" height="auto" style="width:100%;height:auto;aspect-ratio:{total_w}/{total_h};display:block;" xmlns="http://www.w3.org/2000/svg">'
            f'<defs>'
            f'<linearGradient id="asphaltGround" x1="0%" y1="0%" x2="0%" y2="100%">'
            f'<stop offset="0%" stop-color="#0E172E"/><stop offset="50%" stop-color="#090F20"/><stop offset="100%" stop-color="#060A17"/>'
            f'</linearGradient>'
            f'</defs>'
            f'<!-- Asphalt Base Ground -->'
            f'<rect x="0" y="0" width="{total_w}" height="{total_h}" rx="10" fill="url(#asphaltGround)"/>'
            f'<!-- Concrete Curbs along margins -->'
            f'<rect x="58" y="16" width="5" height="{total_h - 32}" rx="2" fill="#334155"/>'
            f'<rect x="{total_w - 63}" y="16" width="5" height="{total_h - 32}" rx="2" fill="#334155"/>'
            f'<!-- Landscaping Trees/Hedges -->'
            f'{"".join(trees_svg)}'
            f'<!-- North Bay Row -->'
            f'<g class="stalls-row north-row">{"".join(north_bays_svg)}</g>'
            f'<!-- Central Roadway -->'
            f'{driving_aisle_svg}'
            f'<!-- South Bay Row -->'
            f'{"<g class=\"stalls-row south-row\">" + "".join(south_bays_svg) + "</g>" if south_slots else ""}'
            f'</svg>'
        )

        out.append(
            f'<div class="floor aerial-facility">'
            f'<div class="floor-h">'
            f'<span>FLOOR {fl} · DECK LEVEL</span>'
            f'<span><b>{vac}</b> of <b>{tot}</b> Available ({pct_occ:.0f}% Occupied)</span>'
            f'</div>'
            f'<div class="asphalt-apron">'
            f'<div class="apron-curb top-curb"></div>'
            f'{facility_svg}'
            f'<div class="apron-curb bottom-curb"></div>'
            f'</div>'
            f'</div>'
        )

    return f'<div class="lot-scroll">{"".join(out)}</div>'


def table_html(headers: List[str], rows: List[List[str]], mono_cols: Optional[List[int]] = None, cls: str = "") -> str:
    mono_cols = mono_cols or []
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(
            f'<td class="{"m" if i in mono_cols else ""}">{c}</td>' for i, c in enumerate(r)
        ) + "</tr>"
    return f'<div class="tbl-wrap"><table class="tbl {cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


# -----------------------------------------------------------------------------
# Session State & Manager Initialization
# -----------------------------------------------------------------------------
def initialize_system() -> None:
    if "manager" not in st.session_state:
        try:
            repo = ParkingRepository()
            st.session_state.manager = ParkingManager(repository=repo)
            st.session_state.storage_backend = "MongoDB Atlas (Live Database)"
            st.session_state.connection_status = "Online"
        except Exception as exc:
            from tests.test_repository import MockDatabase
            mock_repo = ParkingRepository(database=MockDatabase())
            st.session_state.manager = ParkingManager(repository=mock_repo)
            st.session_state.storage_backend = "In-Memory Simulation (Offline Demo Mode)"
            st.session_state.connection_status = "Offline"
            st.session_state.init_error = str(exc)
            _seed_demo_slots(st.session_state.manager)


def _seed_demo_slots(manager: ParkingManager) -> int:
    existing_slots = manager.get_all_slots()
    if existing_slots:
        return 0

    demo_slots = [
        ParkingSlot("F1-C01", floor=1, slot_type="Car"),
        ParkingSlot("F1-C02", floor=1, slot_type="Car"),
        ParkingSlot("F1-B01", floor=1, slot_type="Bike"),
        ParkingSlot("F1-E01", floor=1, slot_type="EV"),
        ParkingSlot("F2-C03", floor=2, slot_type="Car"),
        ParkingSlot("F2-T01", floor=2, slot_type="Truck"),
    ]
    added = 0
    for s in demo_slots:
        try:
            manager.add_parking_slot(s)
            added += 1
        except Exception:
            pass
    return added


def get_manager() -> ParkingManager:
    return st.session_state.manager


# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------
def cb_seed_demo() -> None:
    count = _seed_demo_slots(get_manager())
    if count > 0:
        flash("success", f"Added {b(count)} demo slots.")
    else:
        flash("info", "Slots already exist, so nothing was seeded.")


def cb_reconnect() -> None:
    if "manager" in st.session_state:
        del st.session_state["manager"]
    st.session_state.pop("park_full", None)


def cb_switch_role(role: str) -> None:
    st.session_state["portal_role"] = role
    if role == "customer":
        st.session_state["nav"] = "cust_slots"
    else:
        st.session_state["nav"] = "admin_dashboard"


def cb_admin_login() -> None:
    entered = (st.session_state.get("admin_pwd_input") or "").strip()
    configured_pwd = os.getenv("ADMIN_PASSWORD")
    if not configured_pwd:
        configured_pwd = "admin"
    if entered == configured_pwd:
        st.session_state["admin_authenticated"] = True
        st.session_state["admin_pwd_input"] = ""
        st.session_state["nav"] = "admin_dashboard"
        flash("success", "Administrator authenticated successfully.")
    else:
        flash("error", "Incorrect administrator password.")


def cb_admin_logout() -> None:
    st.session_state["admin_authenticated"] = False
    st.session_state["portal_role"] = "customer"
    st.session_state["nav"] = "cust_slots"
    flash("info", "Signed out of Administrator Dashboard.")


def _park_inputs() -> Dict[str, Any]:
    mode_manual = st.session_state.get("park_mode", "Automatic Allocation (Best Fit)") == "Manual Slot Selection"
    return {
        "plate": (st.session_state.get("park_plate") or "").strip(),
        "type": st.session_state.get("park_type", "Car"),
        "owner": (st.session_state.get("park_owner") or "").strip(),
        "phone": (st.session_state.get("park_phone") or "").strip(),
        "slot_id": st.session_state.get("park_slot") if mode_manual else None,
    }


def cb_park_vehicle() -> None:
    f = _park_inputs()
    st.session_state.pop("park_full", None)
    if not f["plate"]:
        flash("error", "License plate is required.")
        return
    try:
        slot_result = get_manager().park_vehicle(
            license_plate=f["plate"],
            vehicle_type=f["type"],
            owner_name=f["owner"],
            owner_phone=f["phone"],
            slot_id=f["slot_id"],
        )
        flash("success", f"Vehicle {b(f['plate'].upper())} successfully parked in Slot {b(slot_result.slot_id)}!")
        for k in ("park_plate", "park_owner", "park_phone"):
            st.session_state[k] = ""
    except ValueError as val_err:
        flash("error", f"Validation error: {e(val_err)}")
        if "No available compatible" in str(val_err):
            st.session_state["park_full"] = dict(f)
    except RuntimeError as run_err:
        flash("error", f"Persistence error: {e(run_err)}")
    except Exception as err:
        flash("error", f"Parking failed: {e(err)}")


def cb_park_to_waitlist() -> None:
    f = st.session_state.pop("park_full", None)
    if not f:
        return
    try:
        rec = get_manager().add_booking_to_waitlist(f["plate"], f["type"], f["owner"], f["phone"])
        flash("success", f"Booking {b(rec['booking_id'])} added to the waiting queue for {b(f['plate'].upper())}.")
    except ValueError as ve:
        flash("warn", f"Waitlist policy: {e(ve)}")
    except Exception as err:
        flash("error", f"Enqueue error: {e(err)}")


def cb_checkout() -> None:
    plate = st.session_state.get("co_plate")
    rate = float(ParkingManager.DEFAULT_HOURLY_RATE)
    if not plate:
        flash("error", "Please select or specify a parked vehicle.")
        return
    try:
        receipt = get_manager().checkout_vehicle(license_plate=plate, hourly_rate=rate)
        st.session_state["last_receipt"] = receipt
        flash("success", f"Checkout completed for vehicle {b(plate)}.")
        st.session_state.pop("co_plate", None)
    except Exception as err:
        st.session_state.pop("last_receipt", None)
        flash("error", f"Checkout failed: {e(err)}")


def cb_dismiss_receipt() -> None:
    st.session_state.pop("last_receipt", None)


def cb_register_vehicle() -> None:
    plate = (st.session_state.get("reg_plate") or "").strip()
    if not plate:
        flash("error", "License plate is required.")
        return
    try:
        mgr = get_manager()
        new_v = Vehicle(
            plate,
            st.session_state.get("reg_type", "Car"),
            owner_name=(st.session_state.get("reg_owner") or "").strip(),
            owner_phone=(st.session_state.get("reg_phone") or "").strip(),
        )
        already = mgr.get_vehicle_by_plate(new_v.license_plate) is not None
        ret_plate = mgr.register_vehicle(new_v)
        if already:
            flash("info", f"Vehicle {b(ret_plate)} was already registered; canonical record preserved.")
        else:
            flash("success", f"Vehicle {b(ret_plate)} registered in database and vehicles hash map.")
        for k in ("reg_plate", "reg_owner", "reg_phone"):
            st.session_state[k] = ""
    except Exception as err:
        flash("error", f"Registration error: {e(err)}")


def cb_add_slot() -> None:
    slot_id = (st.session_state.get("slot_new_id") or "").strip()
    if not slot_id:
        flash("error", "Slot ID cannot be empty.")
        return
    try:
        created = ParkingSlot(
            slot_id=slot_id,
            floor=int(st.session_state.get("slot_new_floor", 1)),
            slot_type=st.session_state.get("slot_new_type", "Car"),
        )
        res_id = get_manager().add_parking_slot(created)
        flash("success", f"Slot {b(res_id)} added to database and slots hash map.")
        st.session_state["slot_new_id"] = ""
    except Exception as err:
        flash("error", f"Could not add slot: {e(err)}")


def cb_delete_slot() -> None:
    target_slot = st.session_state.get("slot_del_target")
    if not target_slot:
        flash("error", "Please select a parking slot to delete.")
        return
    mgr = get_manager()
    try:
        mgr.delete_parking_slot(target_slot)
        flash("success", f"Parking Slot {b(target_slot)} permanently deleted from MongoDB and slots_map. Parking history preserved.")
        st.session_state.pop("slot_del_target", None)
    except ValueError as ve:
        flash("error", f"Cannot delete slot: {e(ve)}")
    except Exception as err:
        flash("error", f"Slot deletion error: {e(err)}")


def cb_delete_vehicle_admin() -> None:
    target_plate = st.session_state.get("adm_del_plate")
    if not target_plate:
        flash("error", "Please select a vehicle to permanently delete.")
        return
    mgr = get_manager()
    try:
        mgr.delete_registered_vehicle(target_plate)
        flash("success", f"Vehicle {b(target_plate)} permanently deleted from MongoDB and vehicles_map. History preserved.")
        st.session_state.pop("adm_del_plate", None)
    except ValueError as ve:
        flash("error", f"Cannot delete vehicle: {e(ve)}")
    except Exception as err:
        flash("error", f"Deletion error: {e(err)}")


def cb_pop_top() -> None:
    mgr = get_manager()
    popped = mgr.pop_action_stack()
    if popped:
        action_name = popped.get("action", "ACTION")
        plate = popped.get("license_plate", "")
        flash("success", f"Popped top frame {b(action_name)} {b(plate)} from ParkingStack.")
    else:
        flash("warn", "Cannot pop from an empty ParkingStack (depth is 0).")


def cb_enqueue() -> None:
    plate = (st.session_state.get("wq_plate") or "").strip()
    if not plate:
        flash("error", "License plate is required.")
        return
    try:
        rec = get_manager().add_booking_to_waitlist(
            plate,
            st.session_state.get("wq_type", "Car"),
            (st.session_state.get("wq_owner") or "").strip(),
            (st.session_state.get("wq_phone") or "").strip(),
        )
        flash("success", f"Booking {b(rec['booking_id'])} enqueued at the rear for {b(plate.upper())}.")
        for k in ("wq_plate", "wq_owner", "wq_phone"):
            st.session_state[k] = ""
    except ValueError as ve:
        flash("warn", f"Waitlist policy: {e(ve)}")
    except Exception as err:
        flash("error", f"Enqueue error: {e(err)}")


def cb_process_next() -> None:
    try:
        res = get_manager().process_next_waiting_booking()
        if res:
            flash("success", f"Allocated booking {b(res['booking_id'])} ({b(res['license_plate'])}) to Slot {b(res['slot_id'])}.")
        else:
            flash("info", "No compatible booking could be allocated: queue is empty or no compatible slot is vacant.")
    except Exception as err:
        flash("error", f"Allocation error: {e(err)}")


def cb_cust_search_status() -> None:
    plate = (st.session_state.get("cust_status_input") or "").strip()
    if not plate:
        flash("warn", "Please enter your license plate.")
        st.session_state.pop("cust_status_result", None)
        return
    st.session_state["cust_status_result"] = plate.upper()


# -----------------------------------------------------------------------------
# Sidebar & Header Navigation
# -----------------------------------------------------------------------------
def render_sidebar() -> None:
    mgr = get_manager()
    st.session_state.setdefault("portal_role", "customer")
    role = st.session_state["portal_role"]
    is_admin_auth = st.session_state.get("admin_authenticated", False)

    with st.sidebar:
        render(
            '<div class="brand"><div class="logo">P</div>'
            '<div class="name">Smart Parking<br>Management System</div></div>'
        )

        # Role Selector Switch
        render('<div class="side-h">Application Role</div>')
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            st.button(
                "Customer",
                key="btn_role_cust",
                type="primary" if role == "customer" else "secondary",
                use_container_width=True,
                on_click=cb_switch_role,
                args=("customer",),
            )
        with c_r2:
            st.button(
                "Admin",
                key="btn_role_admin",
                type="primary" if role == "admin" else "secondary",
                use_container_width=True,
                on_click=cb_switch_role,
                args=("admin",),
            )

        render('<div class="side-rule"></div>')

        # Role Specific Navigation Items
        current = st.session_state.get("nav", "cust_slots" if role == "customer" else "admin_dashboard")
        nav_items = CUSTOMER_NAV_ITEMS if role == "customer" else ADMIN_NAV_ITEMS

        render(f'<div class="side-h">{"Customer Services" if role == "customer" else "Admin Navigation"}</div>')
        for item in nav_items:
            if item is None:
                render('<div class="side-rule"></div>')
                continue
            key, label, mat_icon = item
            st.button(
                label,
                key=f"nav_{key}",
                icon=f":material/{mat_icon}:",
                type="primary" if current == key else "tertiary",
                use_container_width=True,
                on_click=go,
                args=(key,),
            )

        if role == "admin" and is_admin_auth:
            render('<div class="side-rule"></div>')
            st.button("Log Out of Admin", key="btn_logout_sidebar", use_container_width=True, on_click=cb_admin_logout)

        if role == "admin":
            metrics = mgr.get_dsa_metrics()
            render(
                '<div class="side-h">Live DSA Metrics</div>'
                f'<div class="msr">Slots Map<b>{metrics["slots_map_size"]} / {metrics["slots_map_capacity"]}</b></div>'
                f'<div class="msr">Vehicles Map<b>{metrics["vehicles_map_size"]} / {metrics["vehicles_map_capacity"]}</b></div>'
                f'<div class="msr">Vehicle → Slot Map<b>{metrics["vehicle_to_slot_map_size"]} / {metrics["vehicle_to_slot_map_capacity"]}</b></div>'
                f'<div class="msr">Waitlist Queue<b>{metrics["waitlist_queue_size"]}</b></div>'
                f'<div class="msr">Action Stack<b>{metrics["action_stack_size"]}</b></div>'
            )

        online = st.session_state.connection_status == "Online"
        render(
            '<div class="side-h">Database Status</div>'
            f'<div class="sys {"on" if online else "off"}"><i></i><div>'
            f'<b>{"Connected to MongoDB Atlas" if online else "Offline Demo Mode"}</b>'
            f'<span>{e(st.session_state.storage_backend)}</span></div></div>'
        )
        if not online:
            with st.expander("Offline Notice & Retry"):
                st.caption("MongoDB Atlas was unreachable at startup. Running with isolated in-memory storage.")
                st.button("Reconnect to Atlas", key="act_reconnect", on_click=cb_reconnect, use_container_width=True)


def render_topbar() -> None:
    online = st.session_state.connection_status == "Online"
    now = datetime.now().strftime("%a, %b %d, %Y • %I:%M %p")
    role = st.session_state.get("portal_role", "customer")
    is_admin = role == "admin" and st.session_state.get("admin_authenticated", False)

    role_pill = (
        '<span class="pill blue"><i></i>Admin Mode</span>' if is_admin
        else '<span class="pill green"><i></i>Customer Portal</span>'
    )
    db_pill = (
        '<span class="pill green"><i></i>Atlas Live</span>' if online
        else '<span class="pill amber"><i></i>Demo Mode</span>'
    )
    render(
        f'<div class="topbar">'
        f'<div class="tb-l">'
        f'<div class="tb-logo">{icon("car", 20)}</div>'
        f'<div class="tb-title-wrap">'
        f'<span class="tb-title">Smart Parking <span class="tb-accent">Management System</span></span>'
        f'</div>'
        f'</div>'
        f'<div class="tb-r"><span class="t">{icon("clock", 16)}{e(now)}</span>{role_pill}{db_pill}</div>'
        f'</div>'
    )


def page_header(page: str) -> None:
    title, subtitle, ic = PAGE_META.get(page, ("Dashboard", "Parking Management", "grid"))
    sub_html = f"<p>{e(subtitle)}</p>" if subtitle else ""
    render(
        f'<div class="ph"><div class="ph-ic">{icon(ic, 26)}</div>'
        f'<div><h1>{e(title)}</h1>{sub_html}</div></div>'
    )


# =============================================================================
# 1. CUSTOMER PORTAL PAGES
# =============================================================================
def page_cust_slots() -> None:
    mgr = get_manager()
    all_slots = mgr.get_all_slots()

    st.session_state.setdefault("cust_fl_type", "All Types")
    st.session_state.setdefault("cust_fl_num", "All Floors")

    f1, f2 = st.columns([1, 1])
    with f1:
        type_f = st.selectbox("Vehicle Type Filter", ["All Types"] + VEHICLE_TYPES, key="cust_fl_type")
    with f2:
        floors = sorted(list({s.floor for s in all_slots})) if all_slots else [1]
        floor_f = st.selectbox("Floor Level Filter", ["All Floors"] + [f"Floor {fl}" for fl in floors], key="cust_fl_num")

    filtered = all_slots
    if type_f != "All Types":
        filtered = [s for s in filtered if s.slot_type == type_f]
    if floor_f != "All Floors":
        fl_val = int(floor_f.replace("Floor ", ""))
        filtered = [s for s in filtered if s.floor == fl_val]

    stats = slot_stats(filtered)

    kpi_row([
        kpi("Available Slots", stats["available"], "Ready for parking", "green", "check-circle"),
        kpi("Occupied Slots", stats["occupied"], f"{stats['pct']:.1f}% occupied", "red", "car"),
        kpi("Total Capacity", stats["total"], "Physical spaces matching filter", "blue", "grid"),
    ], 3)

    st.write("")

    @st.fragment(run_every=7)
    def render_live_cust_lot() -> None:
        mgr = get_manager()
        fresh_slots = mgr.get_all_slots()

        # Apply current filters strictly
        filt = fresh_slots
        if type_f != "All Types":
            filt = [s for s in filt if s.slot_type == type_f]
        if floor_f != "All Floors":
            fl_val = int(floor_f.replace("Floor ", ""))
            filt = [s for s in filt if s.floor == fl_val]

        with st.container(key="card_cust_stalls"):
            render(f'<div class="card-h" style="display:flex;align-items:center;gap:.6rem;margin-bottom:.75rem;">'
                   f'<span style="font-size:1.05rem;font-weight:800;color:#fff;">Available Parking Stalls</span>'
                   f'<span class="live-pill"><i class="live-dot"></i>Live</span>'
                   f'</div>')

            if not filt:
                empty_state("No parking slots match the selected filter", "Try changing the filter criteria above.")
            else:
                render(lot_html(filt, show_legend=True, compact=False, clickable=False, is_admin=False))

    render_live_cust_lot()


def page_cust_park() -> None:
    mgr = get_manager()
    all_slots = mgr.get_all_slots()

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        with st.container(key="card_cust_park"):
            card_header("Park Your Vehicle", "Automatic or manual bay allocation", "car")
            st.text_input("License Plate *", placeholder="e.g. DL01AB1234", key="park_plate")
            c1, c2 = st.columns(2)
            with c1:
                p_type = st.selectbox("Vehicle Type *", VEHICLE_TYPES, key="park_type")
            with c2:
                st.text_input("Owner Phone", placeholder="e.g. 9811223344", key="park_phone")
            st.text_input("Owner Name", placeholder="e.g. Jane Doe", key="park_owner")

            mode = st.radio(
                "Slot Selection Mode",
                ["Automatic Allocation (Best Fit)", "Manual Slot Selection"],
                key="park_mode",
                horizontal=True,
            )

            if mode == "Manual Slot Selection":
                vacant_for_type = [
                    s.slot_id for s in all_slots
                    if not s.is_occupied and (s.slot_type == p_type or (p_type == "EV" and s.slot_type == "Car"))
                ]
                if vacant_for_type:
                    st.selectbox("Choose Vacant Compatible Slot", vacant_for_type, key="park_slot")
                else:
                    st.warning(f"No vacant slots currently available for type '{p_type}'.")

            st.button("Confirm Check-In & Park", key="park_go", type="primary", use_container_width=True, on_click=cb_park_vehicle)

            if st.session_state.get("park_full"):
                pf = st.session_state["park_full"]
                render(
                    f'<div class="note danger">{icon("alert", 20)}<div><b>Parking facility is currently full</b> for vehicle type '
                    f'<b>{e(pf["type"])}</b>. Would you like to enter the FIFO waiting queue?</div></div>'
                )
                st.button("Join Waiting Queue Now", key="park_join_wq", type="primary", use_container_width=True, on_click=cb_park_to_waitlist)

    with right:
        with st.container(key="card_cust_info"):
            card_header("Parking Guidance", "Rules & policies for parking", "info")
            render(
                f'<div class="fact">{icon("check", 16)}<span><b>EV Parking:</b> EVs can occupy dedicated EV stalls or Car stalls.</span></div>'
                f'<div class="fact">{icon("check", 16)}<span><b>FIFO Queue:</b> If all compatible slots are occupied, you may join the waiting queue.</span></div>'
                f'<div class="fact">{icon("check", 16)}<span><b>Rate:</b> Standard parking fee is {CURRENCY}{ParkingManager.DEFAULT_HOURLY_RATE:.2f}/hr (min 1.0 hr).</span></div>'
            )


def page_cust_checkout() -> None:
    mgr = get_manager()
    all_slots = mgr.get_all_slots()

    with st.container(key="card_cust_checkout"):
        card_header("Checkout & Billing", "Depart from facility and calculate parking fee", "receipt")
        parked = {s.vehicle.license_plate: s.slot_id for s in all_slots if s.is_occupied and s.vehicle}
        if not parked:
            empty_state("No vehicles currently parked", "There are no vehicles parked in the facility at this moment.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox(
                    "Select Your Parked Vehicle *",
                    list(parked.keys()),
                    index=None,
                    placeholder="Select a vehicle...",
                    key="co_plate",
                    format_func=lambda p: f"{p}  (Slot {parked[p]})" if p else "",
                )
            with c2:
                st.text_input(
                    f"Hourly Rate ({CURRENCY}/hr)",
                    value=f"{CURRENCY}{ParkingManager.DEFAULT_HOURLY_RATE:.2f}/hr (Fixed)",
                    disabled=True,
                    key="co_rate_fixed",
                )
            st.button("Complete Departure & Pay Fee", key="co_go", type="primary", use_container_width=True, on_click=cb_checkout)

        receipt = st.session_state.get("last_receipt")
        if receipt:
            render(
                f'<div class="sub-h">Departure Receipt</div>'
                f'<div class="rcpt">'
                f'<div>License plate<b>{e(receipt["license_plate"])}</b></div>'
                f'<div>Elapsed duration<b>{e(receipt["duration_hours"])} hrs</b></div>'
                f'<div>Vacated slot<b>{e(receipt["slot_id"])}</b></div>'
                f'<div>Billable hours<b>{e(receipt["billable_hours"])} hrs</b></div>'
                f'<div>Entry time<b>{e(fmt_dt(receipt["entry_time"], with_date=True))}</b></div>'
                f'<div>Rate applied<b>{CURRENCY}{receipt["hourly_rate"]:.2f}/hr</b></div>'
                f'<div>Exit time<b>{e(fmt_dt(receipt["exit_time"], with_date=True))}</b></div>'
                f'<div>History ID<b>{e(receipt.get("history_id", "—"))}</b></div>'
                f'</div>'
                f'<div class="rcpt-total"><span>Total fee</span><b>{CURRENCY}{receipt["fee"]:.2f}</b></div>'
            )
            st.button("Dismiss Receipt", key="co_dismiss", on_click=cb_dismiss_receipt)


def page_cust_register() -> None:
    with st.container(key="card_cust_reg"):
        card_header("Register Vehicle", "Pre-register your vehicle and contact details", "user")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("License Plate *", placeholder="e.g. MH12AB5678", key="reg_plate")
        with c2:
            st.text_input("Owner Full Name", placeholder="e.g. Alice Smith", key="reg_owner")
        c3, c4 = st.columns(2)
        with c3:
            st.selectbox("Vehicle Type *", VEHICLE_TYPES, key="reg_type")
        with c4:
            st.text_input("Owner Phone", placeholder="e.g. 9811223344", key="reg_phone")

        st.button("Register Vehicle", key="reg_go", type="primary", use_container_width=True, on_click=cb_register_vehicle)


def page_cust_status() -> None:
    mgr = get_manager()
    with st.container(key="card_cust_status"):
        card_header("Check Parking Status", "View active stall, parked time or waitlist position", "search")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.text_input("Enter License Plate", placeholder="e.g. DL01AB1234", key="cust_status_input")
        with c2:
            st.write("")
            st.button("Look Up My Vehicle", key="cust_status_btn", type="primary", use_container_width=True, on_click=cb_cust_search_status)

        target = st.session_state.get("cust_status_result")
        if target:
            norm_target = target.strip().upper().replace(" ", "").replace("-", "")
            found_v = mgr.get_vehicle_by_plate(norm_target)
            found_slot = mgr.get_slot_by_vehicle(norm_target)

            # Check if vehicle is in waiting queue
            wq_state = mgr.get_queue_state()
            queue_pos = -1
            queue_booking = None
            for idx, b_item in enumerate(wq_state):
                if b_item.get("license_plate") == norm_target:
                    queue_pos = idx + 1
                    queue_booking = b_item
                    break

            if found_slot and found_slot.vehicle:
                v = found_slot.vehicle
                duration_hrs = round((datetime.now() - v.entry_time).total_seconds() / 3600.0, 2)
                fee_est = round(max(1.0, duration_hrs) * ParkingManager.DEFAULT_HOURLY_RATE, 2)

                render(
                    f'<div class="note info" style="margin-top:1.2rem">{icon("check-circle", 24)}'
                    f'<div><b>Active Parking Session:</b> Vehicle <b>{e(norm_target)}</b> is parked in Slot <b>{e(found_slot.slot_id)}</b> (Floor {e(found_slot.floor)}).</div></div>'
                )
                render(
                    f'<div class="rcpt" style="margin-top:1rem;">'
                    f'<div>Slot ID<b>{e(found_slot.slot_id)} (Floor {found_slot.floor})</b></div>'
                    f'<div>Vehicle Type<b>{e(v.vehicle_type)}</b></div>'
                    f'<div>Owner<b>{e(v.owner_name or "—")}</b></div>'
                    f'<div>Entry Time<b>{e(fmt_dt(v.entry_time, with_date=True))}</b></div>'
                    f'<div>Elapsed Time<b>~{duration_hrs:.2f} hrs</b></div>'
                    f'<div>Estimated Fee<b>{CURRENCY}{fee_est:.2f}</b></div>'
                    f'</div>'
                )
            elif queue_pos > 0:
                render(
                    f'<div class="note warn" style="margin-top:1.2rem">{icon("hourglass", 24)}'
                    f'<div><b>On Waiting List:</b> Vehicle <b>{e(norm_target)}</b> is currently in the waitlist queue at <b>Position #{queue_pos}</b> '
                    f'(Booking ID: <code>{e(queue_booking.get("booking_id"))}</code>). You will be allocated automatically when a compatible slot frees up.</div></div>'
                )
            elif found_v:
                render(
                    f'<div class="note" style="margin-top:1.2rem">{icon("info", 24)}'
                    f'<div>Vehicle <b>{e(norm_target)}</b> is registered in the system, but is <b>not currently parked</b> in any slot.</div></div>'
                )
            else:
                render(
                    f'<div class="note danger" style="margin-top:1.2rem">{icon("x-circle", 24)}'
                    f'<div>No active parking session or registration found for vehicle <b>{e(norm_target)}</b>. '
                    f'You can register your vehicle or check in at the Park Vehicle page.</div></div>'
                )


# =============================================================================
# 2. ADMINISTRATOR DASHBOARD & LOGIN
# =============================================================================
def page_admin_login() -> None:
    with st.container(key="card_admin_login"):
        card_header("Administrator Authentication", "Access restricted to authorized facility administrators", "lock")
        st.markdown(
            '<div class="hint" style="margin-bottom:1.1rem">Enter the administrator password to manage parking inventory, '
            'clean up vehicle records, review audit logs, and access live custom DSA visualizers.</div>',
            unsafe_allow_html=True
        )

        c1, c2 = st.columns([1.5, 1])
        with c1:
            st.text_input("Administrator Password", type="password", key="admin_pwd_input", placeholder="Enter administrator password")
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                st.button("Unlock Dashboard", key="btn_login_admin", type="primary", use_container_width=True, on_click=cb_admin_login)
            with b_col2:
                st.button("Cancel & Return to Customer", key="btn_cancel_admin", use_container_width=True, on_click=lambda: cb_switch_role("customer"))


def page_dashboard() -> None:
    mgr = get_manager()
    all_slots = mgr.get_all_slots()
    stats = slot_stats(all_slots)
    waitlist_count = len(mgr.waiting_queue)

    # Balanced 2-column layout with Parking Facility View prominent (1 : 1.8)
    left, right = st.columns([1, 1.8], gap="large")
    with left:
        render(f'''
        <div class="kpi-quad">
            {kpi("Total Slots", stats["total"], "Managed inventory", "blue", "grid")}
            {kpi("Occupied Slots", stats["occupied"], f"{stats['pct']:.1f}% occupied", "red", "car")}
            {kpi("Available Slots", stats["available"], f"{100 - stats['pct']:.1f}% vacant" if stats["total"] else "No slots", "green", "check-circle")}
            {kpi("Waiting Queue", waitlist_count, "Vehicles waiting", "violet", "hourglass")}
        </div>
        ''')
        render(f'<div class="meter" title="Facility Occupancy: {stats["pct"]:.1f}%"><i style="width:{min(stats["pct"], 100):.0f}%"></i></div>')

        with st.container(key="card_activity"):
            h_col, nav_col = st.columns([2.05, 1.35])
            with h_col:
                card_header("Recent Activity", "Chronological audit trail from ParkingStack", "clock")
            with nav_col:
                if st.button("View Full History →", key="dash_view_all_history_btn", use_container_width=True):
                    go("admin_history")
            recent = mgr.get_recent_actions(6)
            if not recent:
                empty_state("No recent activity", "Park or check out a vehicle to record live audit events.")
            else:
                render(activity_timeline_html(recent))

    with right:
        @st.fragment(run_every=7)
        def render_live_admin_lot() -> None:
            mgr = get_manager()
            fresh_slots = mgr.get_all_slots()
            cur_stats = slot_stats(fresh_slots)
            now_str = datetime.now().strftime("%I:%M:%S %p")

            with st.container(key="card_lot"):
                render(f'<div class="card-h" style="display:flex;align-items:center;gap:.6rem;margin-bottom:.75rem;">'
                       f'<span style="font-size:1.05rem;font-weight:800;color:#fff;">Parking Lot View</span>'
                       f'<span class="live-pill"><i class="live-dot"></i>Live</span>'
                       f'</div>')

                if not fresh_slots:
                    empty_state("No parking slots registered", "Add parking slots in the Slot Management tab.")
                else:
                    floors = sorted(list({s.floor for s in fresh_slots}))
                    if len(floors) > 1:
                        deck_opts = ["All Floors"] + [f"Floor {fl}" for fl in floors]
                        chosen_deck = st.pills("Facility Deck", deck_opts, default=deck_opts[0], key="admin_deck_pill", label_visibility="collapsed")
                        if chosen_deck and chosen_deck != "All Floors":
                            fl_target = int(chosen_deck.replace("Floor ", ""))
                            display_slots = [s for s in fresh_slots if s.floor == fl_target]
                        else:
                            display_slots = fresh_slots
                    else:
                        display_slots = fresh_slots

                    active_slot_id = st.query_params.get("selected_slot") or st.session_state.get("admin_active_slot")
                    if active_slot_id and not any(s.slot_id == active_slot_id for s in display_slots):
                        active_slot_id = None
                        st.session_state.pop("admin_active_slot", None)
                        st.session_state.pop("admin_bay_inspect_pills", None)
                        if "selected_slot" in st.query_params:
                            try:
                                del st.query_params["selected_slot"]
                            except Exception:
                                st.query_params.pop("selected_slot", None)

                    render(lot_html(display_slots, show_legend=True, compact=False, selected_slot_id=active_slot_id, clickable=False, is_admin=True))

                    slot_ids = [s.slot_id for s in display_slots]
                    if slot_ids:
                        c_pills, c_btn = st.columns([3.2, 1.2])
                        with c_pills:
                            new_sel = st.pills(
                                "Select bay to inspect:",
                                slot_ids,
                                default=active_slot_id if active_slot_id in slot_ids else None,
                                key="admin_bay_inspect_pills",
                                label_visibility="collapsed",
                            )
                            if new_sel != active_slot_id:
                                if new_sel:
                                    st.query_params["selected_slot"] = new_sel
                                    st.session_state["admin_active_slot"] = new_sel
                                else:
                                    st.session_state.pop("admin_active_slot", None)
                                    st.session_state.pop("admin_bay_inspect_pills", None)
                                    if "selected_slot" in st.query_params:
                                        try:
                                            del st.query_params["selected_slot"]
                                        except Exception:
                                            st.query_params.pop("selected_slot", None)
                                st.rerun()
                        with c_btn:
                            if active_slot_id:
                                def cb_close_admin_details() -> None:
                                    st.session_state.pop("admin_active_slot", None)
                                    st.session_state.pop("admin_bay_inspect_pills", None)
                                    if "selected_slot" in st.query_params:
                                        try:
                                            del st.query_params["selected_slot"]
                                        except Exception:
                                            st.query_params.pop("selected_slot", None)

                                if st.button("✕ Close Details", key="admin_close_panel_btn", use_container_width=True, on_click=cb_close_admin_details):
                                    cb_close_admin_details()
                                    active_slot_id = None
                                    st.rerun()

                    if active_slot_id:
                        inspected_slot = next((s for s in display_slots if s.slot_id == active_slot_id), None)
                        if inspected_slot:
                            render(slot_inspector_panel_html(inspected_slot))

        render_live_admin_lot()


def page_slots() -> None:
    mgr = get_manager()
    all_slots = mgr.get_all_slots()
    stats = slot_stats(all_slots)

    kpi_row([
        kpi("Total Slots", stats["total"], "In the inventory", "blue", "grid"),
        kpi("Occupied", stats["occupied"], f"{stats['pct']:.1f}% occupancy", "red", "car"),
        kpi("Vacant", stats["available"], "Ready for check-in", "green", "check-circle"),
    ], 3)
    st.write("")

    left, right = st.columns([1, 1.7], gap="large")
    with left:
        with st.container(key="card_addslot"):
            card_header("Add Parking Slot", "Registers a physical slot in database and slots_map", "plus")
            st.text_input("Slot ID *", placeholder="e.g. F2-C05", key="slot_new_id")
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Floor Level *", min_value=1, max_value=50, value=1, step=1, key="slot_new_floor")
            with c2:
                st.selectbox("Slot Vehicle Type *", VEHICLE_TYPES, key="slot_new_type")
            st.button("Add Slot to System", key="slot_add_go", type="primary", use_container_width=True, on_click=cb_add_slot)

        st.write("")
        with st.container(key="card_delslot"):
            card_header("Delete Parking Slot", "Delete vacant slot from database and slots_map", "trash")
            render(
                f'<div class="note danger">{icon("alert", 20)}<div><b>Vacant Slots Only:</b> '
                f'Occupied slots cannot be deleted. Deleting a slot removes it permanently from MongoDB and <code>slots_map</code>. '
                f'Historical logs are preserved.</div></div>'
            )
            if not all_slots:
                empty_state("No slots available", "There are no slots to delete.")
            else:
                st.write("")
                st.selectbox(
                    "Select Parking Slot to Delete *",
                    [s.slot_id for s in all_slots],
                    index=None,
                    placeholder="Select a parking slot...",
                    key="slot_del_target",
                    format_func=lambda sid: f"{sid}  ({'OCCUPIED' if mgr.get_slot_by_id(sid) and mgr.get_slot_by_id(sid).is_occupied else 'Available (Vacant)'})" if sid else "",
                )
                sel_slot_id = st.session_state.get("slot_del_target")
                if sel_slot_id:
                    sel_slot = mgr.get_slot_by_id(sel_slot_id)
                    if sel_slot and sel_slot.is_occupied:
                        occ_plate = sel_slot.vehicle.license_plate if sel_slot.vehicle else "active vehicle"
                        st.error(f"Cannot delete '{sel_slot_id}': Slot is currently occupied by {occ_plate}.")
                    else:
                        st.button("Permanently Delete Slot", key="btn_del_slot_admin", type="primary", use_container_width=True, on_click=cb_delete_slot)
                else:
                    st.button("Permanently Delete Slot", key="btn_del_slot_admin", type="primary", use_container_width=True, on_click=cb_delete_slot)

    with right:
        with st.container(key="card_inventory"):
            card_header("Slot Inventory Directory", "All slots with current occupancy status", "layers")
            if not all_slots:
                empty_state("No slots available", "Add a parking slot using the form on the left to initialize inventory.")
            else:
                rows = []
                for s in all_slots:
                    occ = s.is_occupied and s.vehicle
                    status = '<span class="badge t-red">Occupied</span>' if s.is_occupied else '<span class="badge t-green">Vacant</span>'
                    rows.append([
                        e(s.slot_id),
                        e(s.floor),
                        f'<span style="display:inline-flex;align-items:center;gap:.4rem">{type_icon(s.slot_type, 15)}{e(s.slot_type)}</span>',
                        status,
                        e(s.vehicle.license_plate) if occ else '<span class="dim">None</span>',
                        e(s.vehicle.owner_name or "—") if occ else '<span class="dim">None</span>',
                        e(fmt_dt(s.vehicle.entry_time)) if occ else '<span class="dim">None</span>',
                    ])
                render(table_html(
                    ["Slot ID", "Floor", "Slot Type", "Status", "Parked Plate", "Owner", "Entry Time"],
                    rows, mono_cols=[0, 4],
                ))


def page_admin_vehicles() -> None:
    mgr = get_manager()
    all_vehicles = mgr.get_all_vehicles()
    parked_map = {s.vehicle.license_plate: s.slot_id for s in mgr.get_all_slots() if s.is_occupied and s.vehicle}

    kpi_row([
        kpi("Registered Vehicles", len(all_vehicles), "Total in vehicles_map", "blue", "car"),
        kpi("Currently Parked", len(parked_map), "Occupying stalls", "red", "car"),
        kpi("Not Parked", max(0, len(all_vehicles) - len(parked_map)), "Active in registry", "green", "check-circle"),
    ], 3)
    st.write("")

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with st.container(key="card_veh_list"):
            card_header("Registered Vehicles Directory", "All vehicle records maintained in MongoDB and vehicles_map", "user")
            if not all_vehicles:
                empty_state("No registered vehicles", "Vehicles are added upon registration or check-in.")
            else:
                rows = []
                for v in all_vehicles:
                    is_parked = v.license_plate in parked_map
                    slot_txt = f'<span class="badge t-red">Slot {e(parked_map[v.license_plate])}</span>' if is_parked else '<span class="badge t-green">Not Parked</span>'
                    rows.append([
                        e(v.license_plate),
                        f'<span style="display:inline-flex;align-items:center;gap:.4rem">{type_icon(v.vehicle_type, 14)}{e(v.vehicle_type)}</span>',
                        e(v.owner_name or "—"),
                        e(v.owner_phone or "—"),
                        slot_txt,
                    ])
                render(table_html(
                    ["License Plate", "Type", "Owner Name", "Phone", "Parking Status"],
                    rows, mono_cols=[0],
                ))

    with right:
        # 3. Administrator Vehicle Registry Cleanup
        with st.container(key="card_veh_cleanup"):
            card_header("Vehicle Registry Cleanup", "Permanent deletion with parked-vehicle protection", "trash")
            render(
                f'<div class="note danger">{icon("alert", 20)}<div><b>Permanent Removal:</b> '
                f'Deletes the vehicle from MongoDB and <code>vehicles_map</code>. '
                f'Vehicles currently parked in a stall cannot be deleted. Historical logs are preserved.</div></div>'
            )
            if not all_vehicles:
                empty_state("No vehicles to delete", "Vehicle list is empty.")
            else:
                st.write("")
                st.selectbox(
                    "Select Vehicle to Permanently Delete *",
                    [v.license_plate for v in all_vehicles],
                    index=None,
                    placeholder="Select a registered vehicle...",
                    key="adm_del_plate",
                    format_func=lambda p: f"{p}  ({'PARKED IN SLOT ' + parked_map[p] if p in parked_map else 'Eligible (Not Parked)'})" if p else "",
                )

                sel = st.session_state.get("adm_del_plate")
                if sel:
                    if sel in parked_map:
                        st.error(f"Cannot delete '{sel}': Currently parked in slot '{parked_map[sel]}'.")
                    else:
                        st.button("Permanently Delete Vehicle", key="btn_del_veh_admin", type="primary", use_container_width=True, on_click=cb_delete_vehicle_admin)
                else:
                    st.button("Permanently Delete Vehicle", key="btn_del_veh_admin", type="primary", use_container_width=True, on_click=cb_delete_vehicle_admin)


def page_admin_history() -> None:
    mgr = get_manager()
    history_records = mgr.get_parking_history(limit=100)

    total_events = len(history_records)
    checkins = sum(1 for h in history_records if h.get("action") == "CHECK_IN")
    checkouts = sum(1 for h in history_records if h.get("action") == "CHECK_OUT")
    total_revenue = sum(float(h.get("fee", 0.0)) for h in history_records if h.get("fee"))

    kpi_row([
        kpi("Audit Events", total_events, "Recorded in MongoDB", "blue", "history"),
        kpi("Check-Ins", checkins, "Vehicles parked", "green", "car"),
        kpi("Check-Outs", checkouts, "Vehicles departed", "violet", "receipt"),
        kpi("Revenue Collected", f"{CURRENCY}{total_revenue:.2f}", "Total fees billed", "amber", "receipt"),
    ], 4)
    st.write("")

    with st.container(key="card_history_tbl"):
        card_header("Parking Activity & Audit Trail", "Historical event log from MongoDB parking_history collection", "history")
        if not history_records:
            empty_state("No parking history found", "Complete check-ins and departures to generate history records.")
        else:
            rows = []
            for h in history_records:
                act = h.get("action", "EVENT")
                hl, badge, tone = ACTION_META.get(act, (act, act, "blue"))
                fee_val = f"{CURRENCY}{float(h.get('fee', 0.0)):.2f}" if h.get("fee") is not None else "—"
                dur = f"{h.get('duration_hours')} hrs" if h.get("duration_hours") is not None else "—"
                rows.append([
                    e(h.get("history_id", "—")),
                    f'<span class="badge t-{tone}">{e(badge)}</span>',
                    e(h.get("license_plate", "—")),
                    e(h.get("slot_id", "—")),
                    e(fmt_dt(h.get("timestamp"), with_date=True)),
                    e(dur),
                    e(fee_val),
                ])
            render(table_html(
                ["History ID", "Action", "Plate", "Slot ID", "Timestamp", "Duration", "Fee"],
                rows, mono_cols=[0, 2, 3],
            ))


def page_queue() -> None:
    mgr = get_manager()
    q_state = mgr.get_queue_state()
    q_len = len(mgr.waiting_queue)
    kpi_row([
        kpi("Queue Length", q_len, "Nodes in the linked list", "violet", "hourglass"),
        kpi("Front Pointer (Next)", q_state[0]["license_plate"] if q_state else "None (Empty)", "Served first", "blue", "arrow", small=True),
        kpi("Rear Pointer (Last)", q_state[-1]["license_plate"] if q_state else "None (Empty)", "Most recent arrival", "amber", "arrow", small=True),
    ], 3)
    st.write("")

    with st.container(key="card_pipeline"):
        card_header("Queue Visual Pipeline", "Front → Rear, one box per linked-list node", "hourglass")
        if not q_state:
            empty_state("The waiting queue is empty", "All arriving vehicles have been accommodated directly.")
        else:
            render(queue_pipeline_html(q_state))

    st.write("")
    a1, a2 = st.columns(2, gap="large")
    with a1:
        with st.container(key="card_enqueue"):
            card_header("Manual Waitlist Enqueue", "Enroll a vehicle when compatible slots are full", "plus")
            st.text_input("License Plate *", key="wq_plate")
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox("Vehicle Type *", VEHICLE_TYPES, key="wq_type")
            with c2:
                st.text_input("Owner Phone", key="wq_phone")
            st.text_input("Owner Name", key="wq_owner")
            st.button("Enqueue to Waitlist", key="wq_go", type="primary", use_container_width=True, on_click=cb_enqueue)
    with a2:
        with st.container(key="card_process"):
            card_header("Process Next Waiting Booking", "Finds earliest compatible booking and allocates slot", "arrow")
            render(
                f'<div class="fact">{icon("check", 16)}<span>Scans queue from front to rear for earliest vehicle matching available slot.</span></div>'
                f'<div class="fact">{icon("check", 16)}<span>EVs may use Car slots when no dedicated EV slot is vacant.</span></div>'
                f'<div class="fact">{icon("check", 16)}<span>If parking fails, booking is restored to exact original FIFO position.</span></div>'
            )
            st.button("Process & Allocate Next Booking", key="wq_process", type="primary", use_container_width=True, on_click=cb_process_next)


def page_stack() -> None:
    mgr = get_manager()
    stack_state = mgr.get_stack_state()
    depth = mgr.action_stack.size
    top_action = stack_state[0].get("action", "None") if stack_state else "Empty"
    kpi_row([
        kpi("Stack Depth (Size)", depth, "Frames in linked list", "violet", "layers"),
        kpi("Top of Stack Action", top_action, "Most recent operation", "blue", "arrow", small=True),
    ], 2)
    st.write("")

    left, right = st.columns([1.7, 1], gap="large")
    with left:
        with st.container(key="card_frames"):
            card_header("Stack Frame Inspection", "Top → Bottom, one box per linked-list node", "layers")
            if not stack_state:
                empty_state("No actions recorded yet", "Perform an operation (park, checkout, add slot) to push a frame.")
            else:
                render(stack_frames_html(stack_state))
    with right:
        with st.container(key="card_stack_ctrl"):
            card_header("Stack Operations", "Direct DSA manipulation (LIFO)", "layers")
            render(
                f'<div class="fact">{icon("check", 16)}<span><b>POP TOP</b> removes exactly one top node from memory via <code>ParkingStack.pop()</code>.</span></div>'
                f'<div class="fact">{icon("check", 16)}<span>Does NOT undo parking operations or alter MongoDB records.</span></div>'
            )
            st.write("")
            st.button(
                "POP TOP",
                key="btn_pop_top_action",
                type="primary",
                use_container_width=True,
                on_click=cb_pop_top
            )

        st.write("")
        with st.container(key="card_legend"):
            card_header("Action Types", "Colours used for stack frames", "info")
            legend = "".join(
                f'<div class="act">'
                f'<div class="act-left">'
                f'<span class="dot d-{tone}"></span>'
                f'<div class="act-text tx"><b class="act-name">{e(name)}</b><span class="act-desc">{e(headline)}</span></div>'
                f'</div>'
                f'<span class="badge t-{tone}">{e(badge)}</span>'
                f'</div>'
                for name, (headline, badge, tone) in [
                    (k, ACTION_META[k]) for k in STACK_ACTION_TYPES if k in ACTION_META
                ]
            )
            render(f'<div class="act-list">{legend}</div>')


def page_hashmap() -> None:
    mgr = get_manager()
    hm_states = mgr.get_hashmap_state()
    st.session_state.setdefault("hm_map", "slots_hashmap")
    map_key = st.segmented_control(
        "Hash map to inspect",
        list(HASHMAP_VIEWS.keys()),
        key="hm_map",
        required=True,
        format_func=lambda k: f"{HASHMAP_VIEWS[k][0]}  ({HASHMAP_VIEWS[k][1]})",
        label_visibility="collapsed",
    ) or "slots_hashmap"

    cur = hm_states[map_key]
    buckets = cur["buckets"]
    chains = [len(bk) for bk in buckets]
    collisions = sum(1 for c in chains if c > 1)
    longest = max(chains) if chains else 0

    st.write("")
    kpi_row([
        kpi("Keys Count (n)", cur["size"], "Stored entries", "blue", "hash"),
        kpi("Bucket Array Size (m)", cur["capacity"], "Array length", "violet", "grid"),
        kpi("Load Factor (n/m)", f"{cur['load_factor']:.3f}", "Resize threshold 0.75", "amber", "layers"),
        kpi("Collision Buckets", collisions, "Buckets with 2+ nodes", "red", "alert"),
        kpi("Longest Chain", longest, "Worst-case probe length", "green", "arrow"),
    ], 5)
    st.write("")

    with st.container(key="card_buckets"):
        card_header(f"Internal Bucket Array: {HASHMAP_VIEWS[map_key][0]}", HASHMAP_VIEWS[map_key][1], "hash")
        hide_empty = st.toggle("Hide empty buckets", value=False, key="hm_hide")
        rows = []
        for idx, chain in enumerate(buckets):
            if hide_empty and not chain:
                continue
            if not chain:
                rows.append(
                    f'<div class="brow e"><div class="bidx">[{idx:02d}]</div>'
                    f'<div class="bchain"><span class="bnull">EMPTY</span></div><div class="blen">0 nodes</div></div>'
                )
                continue
            nodes = []
            for k, v in chain:
                nodes.append(f'<span class="bnode"><b>{e(k)}</b><em>→</em>{e(describe_value(v))}</span>')
            joined = f'<span style="color:var(--blue);display:inline-flex">{icon("arrow", 16)}</span>'.join(nodes)
            is_col = len(chain) > 1
            rows.append(
                f'<div class="brow {"c" if is_col else "n"}"><div class="bidx">[{idx:02d}]</div>'
                f'<div class="bchain">{joined}<span class="bnull">→ NULL</span></div>'
                f'<div class="blen{" c" if is_col else ""}">{len(chain)} node(s){" · collision" if is_col else ""}</div></div>'
            )
        if rows:
            render("".join(rows))
        else:
            empty_state("Every bucket is empty", "Add a slot or register a vehicle to place the first node.")



# -----------------------------------------------------------------------------
# Main Application Dispatcher
# -----------------------------------------------------------------------------
initialize_system()
st.session_state.setdefault("portal_role", "customer")
st.session_state.setdefault("admin_authenticated", False)
st.session_state.setdefault("nav", "cust_slots")

render_sidebar()
render_topbar()
render_flash()

current_role = st.session_state["portal_role"]
current_page = st.session_state["nav"]

if current_role == "customer":
    if not current_page.startswith("cust_"):
        current_page = "cust_slots"
        st.session_state["nav"] = current_page

    page_header(current_page)
    {
        "cust_slots": page_cust_slots,
        "cust_park": page_cust_park,
        "cust_checkout": page_cust_checkout,
        "cust_register": page_cust_register,
        "cust_status": page_cust_status,
    }.get(current_page, page_cust_slots)()

else:  # Administrator Dashboard
    if not st.session_state.get("admin_authenticated"):
        page_header("admin_dashboard")
        page_admin_login()
    else:
        if not current_page.startswith("admin_"):
            current_page = "admin_dashboard"
            st.session_state["nav"] = current_page

        page_header(current_page)
        {
            "admin_dashboard": page_dashboard,
            "admin_slots": page_slots,
            "admin_vehicles": page_admin_vehicles,
            "admin_history": page_admin_history,
            "admin_queue": page_queue,
            "admin_stack": page_stack,
            "admin_hashmap": page_hashmap,
        }.get(current_page, page_dashboard)()