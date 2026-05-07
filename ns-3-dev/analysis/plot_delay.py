"""
plot_delay.py
-------------
Parses results/<tag>/flowmon.xml and produces delay, throughput,
and packet loss charts. Automatically detects the scenario from the
experiment tag and uses a matching analysis title and description.

Single experiment:
    python3 plot_delay.py --tag scenario1_lightLoad_stable

Compare all scenarios side by side:
    python3 plot_delay.py --compare

No arguments -> plots whichever subfolder(s) exist.
"""

import os
import re
import sys
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from lxml import etree

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")

# ── Scenario metadata ─────────────────────────
SCENARIO_META = {
    "scenario1_lightLoad_stable": {
        "title":    "Scenario 1: Light Load — Stable Queue (M/M/1 Under-utilised)",
        "subtitle": ("Arrival rate (900 Kbps total) < Service rate (2 Mbps bottleneck)\n"
                     "Expected: low delay across all flows, high throughput, zero packet loss"),
        "color":    "#0F6E56",
    },
    "scenario2_heavyLoad_congestion": {
        "title":    "Scenario 2: Heavy Congestion — Queue Saturation (M/M/1 Overloaded)",
        "subtitle": ("Arrival rate (6 Mbps total) >> Service rate (1 Mbps bottleneck)\n"
                     "Expected: high delay, throughput capped at bottleneck, significant packet loss"),
        "color":    "#A32D2D",
    },
    "scenario3_Prio": {
        "title":    "Scenario 3a: Queue Discipline — Priority Scheduling (PrioQueueDisc)",
        "subtitle": ("Arrival rate (3 Mbps total) vs Service rate (1 Mbps) — moderate load\n"
                     "Expected: Client 0 (512B small packets) gets lower delay due to priority"),
        "color":    "#534AB7",
    },
    "scenario3_FqCodel": {
        "title":    "Scenario 3b: Queue Discipline — Fair Queuing with AQM (FqCoDelQueueDisc)",
        "subtitle": ("Same load as Scenario 3a — compare delay and loss against Priority scheduling\n"
                     "Expected: fairer delay distribution across flows, reduced bufferbloat"),
        "color":    "#185FA5",
    },
}

DEFAULT_META = {
    "title":    "Per-Flow Statistics",
    "subtitle": "NS3 Queueing Simulation",
    "color":    "#4C72B0",
}


def get_meta(tag):
    return SCENARIO_META.get(tag, {
        **DEFAULT_META,
        "title":    f"Per-Flow Statistics — {tag}",
        "subtitle": "NS3 Queueing Simulation",
    })


# ── CLI ───────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--tag",     default="", help="Single experiment tag to plot")
parser.add_argument("--compare", action="store_true",
                    help="Compare all available experiments side by side")
args = parser.parse_args()


# ── Helper: NS3 time string → seconds ─────────
def parse_ns3_time(s):
    s = s.strip().lstrip('+')
    for unit, factor in [('ns', 1e-9), ('us', 1e-6), ('ms', 1e-3), ('s', 1.0)]:
        if s.endswith(unit):
            return float(s[:-len(unit)]) * factor
    return float(re.sub(r'[^0-9.eE\-]', '', s))


# ── Parse one flowmon.xml → list of flow dicts ─
def parse_flowmon(xml_path):
    tree  = etree.parse(xml_path)
    flows = []
    for flow in tree.xpath("//Flow"):
        rx_pkts = int(flow.get("rxPackets", "0"))
        tx_pkts = int(flow.get("txPackets", "0"))
        fid     = flow.get("flowId", "?")
        if rx_pkts == 0:
            print(f"  [SKIP] Flow {fid}: no received packets")
            continue
        delay_sum    = parse_ns3_time(flow.get("delaySum", "0ns"))
        avg_delay_ms = (delay_sum / rx_pkts) * 1e3
        rx_bytes     = int(flow.get("rxBytes", "0"))
        t_first_tx   = parse_ns3_time(flow.get("timeFirstTxPacket", "0ns"))
        t_last_rx    = parse_ns3_time(flow.get("timeLastRxPacket",  "0ns"))
        duration     = t_last_rx - t_first_tx
        tput_kbps    = (rx_bytes * 8) / duration / 1e3 if duration > 0 else 0.0
        loss_pct     = ((tx_pkts - rx_pkts) / tx_pkts * 100) if tx_pkts > 0 else 0.0
        flows.append({
            "id":    fid,
            "delay": avg_delay_ms,
            "tput":  tput_kbps,
            "loss":  loss_pct,
        })
    return flows


# ── Find experiment folders ───────────────────
def find_experiments():
    exps = []
    if not os.path.isdir(RESULTS_DIR):
        return exps
    for entry in sorted(os.listdir(RESULTS_DIR)):
        subdir = os.path.join(RESULTS_DIR, entry)
        xml    = os.path.join(subdir, "flowmon.xml")
        if os.path.isdir(subdir) and os.path.isfile(xml):
            exps.append((entry, xml))
    return exps


experiments = find_experiments()
if not experiments:
    sys.exit(f"[ERROR] No experiment subfolders with flowmon.xml found in {RESULTS_DIR}\n"
             "Run the NS3 simulation first.")

if args.tag:
    experiments = [(t, p) for t, p in experiments if t == args.tag]
    if not experiments:
        sys.exit(f"[ERROR] Tag '{args.tag}' not found in {RESULTS_DIR}")

print(f"[INFO] Found {len(experiments)} experiment(s): {[t for t,_ in experiments]}")

COLORS = ["#0F6E56", "#A32D2D", "#534AB7", "#185FA5", "#D97706", "#0891B2"]


# ══════════════════════════════════════════════
# COMPARE MODE — grouped bars across all scenarios
# ══════════════════════════════════════════════
if args.compare or len(experiments) > 1:

    all_data = {}
    for tag, xml_path in experiments:
        print(f"[INFO] Parsing: {xml_path}")
        flows = parse_flowmon(xml_path)
        if flows:
            all_data[tag] = flows

    if not all_data:
        sys.exit("[ERROR] No flows with received packets found in any experiment.")

    base_flows  = all_data[list(all_data.keys())[0]]
    flow_labels = [f"Flow {f['id']}" for f in base_flows]
    x           = np.arange(len(flow_labels))
    n           = len(all_data)
    width       = 0.7 / n

    fig, axes = plt.subplots(1, 3, figsize=(17, 6))
    fig.suptitle(
        "Per-Flow Statistics — All Scenarios Compared\n"
        "Scenario 1: light load  |  Scenario 2: congestion  |  "
        "Scenario 3a: Priority  |  Scenario 3b: FqCoDel",
        fontsize=11, fontweight='bold')

    metrics = [
        ("delay", "Avg Delay (ms)",    axes[0], "Average End-to-End Delay"),
        ("tput",  "Throughput (kbps)", axes[1], "Throughput per Flow"),
        ("loss",  "Packet Loss (%)",   axes[2], "Packet Loss per Flow"),
    ]

    for key, ylabel, ax, title in metrics:
        for i, (tag, _) in enumerate(all_data.items()):
            flows  = all_data[tag]
            values = [f[key] for f in flows]
            offset = (i - n / 2 + 0.5) * width
            ax.bar(x + offset, values, width,
                   label=tag,
                   color=COLORS[i % len(COLORS)],
                   edgecolor='white', linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(flow_labels, rotation=15, ha='right')
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.grid(axis='y', linestyle='--', alpha=0.4)

    axes[0].legend(fontsize=7, loc='upper left')
    plt.tight_layout()
    out_png = os.path.join(RESULTS_DIR, "plot_delay_comparison.png")
    plt.savefig(out_png, dpi=150, bbox_inches='tight')
    print(f"[INFO] Saved: {out_png}")


# ══════════════════════════════════════════════
# SINGLE MODE — detailed 4-panel chart
# ══════════════════════════════════════════════
else:
    tag, xml_path = experiments[0]
    meta  = get_meta(tag)
    print(f"[INFO] Parsing: {xml_path}")
    flows = parse_flowmon(xml_path)

    if not flows:
        sys.exit("[ERROR] No flows with received packets found in flowmon.xml.")

    flow_ids    = [f["id"]    for f in flows]
    avg_delays  = [f["delay"] for f in flows]
    throughputs = [f["tput"]  for f in flows]
    loss_ratios = [f["loss"]  for f in flows]
    x_labels    = [f"Flow {fid}" for fid in flow_ids]
    x_pos       = range(len(flow_ids))
    color       = meta["color"]

    print(f"[INFO] {len(flows)} active flows  |  "
          f"max delay = {max(avg_delays):.2f} ms  |  "
          f"max loss = {max(loss_ratios):.1f}%")

    def bar_chart(ax, values, bar_color, ylabel, title, fmt="{:.2f}"):
        bars = ax.bar(x_pos, values, color=bar_color,
                      edgecolor='white', linewidth=0.7)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(x_labels, rotation=15, ha='right')
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        offset = max(values) * 0.025 if max(values) > 0 else 0.1
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + offset,
                    fmt.format(val),
                    ha='center', va='bottom', fontsize=8)

    # Slightly lighter shade for variety across the 3 bar charts
    colors_panels = [color, "#55A868", "#DD8452"]

    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(meta["title"] + "\n" + meta["subtitle"],
                 fontsize=11, fontweight='bold', y=1.01)

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.52, wspace=0.38)

    # Panel 1 — Average delay
    bar_chart(fig.add_subplot(gs[0, 0]),
              avg_delays, colors_panels[0],
              "Avg Delay (ms)", "Average End-to-End Delay per Flow")

    # Panel 2 — Throughput
    bar_chart(fig.add_subplot(gs[0, 1]),
              throughputs, colors_panels[1],
              "Throughput (kbps)", "Throughput per Flow",
              fmt="{:.1f}")

    # Panel 3 — Packet loss
    bar_chart(fig.add_subplot(gs[1, 0]),
              loss_ratios, colors_panels[2],
              "Packet Loss (%)", "Packet Loss per Flow",
              fmt="{:.1f}%")

    # Panel 4 — Summary table
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')
    table_data = [
        [f"Flow {fid}",
         f"{d:.2f} ms",
         f"{t:.1f} kbps",
         f"{l:.1f}%"]
        for fid, d, t, l in zip(flow_ids, avg_delays, throughputs, loss_ratios)
    ]
    tbl = ax4.table(
        cellText=table_data,
        colLabels=["Flow", "Avg Delay", "Throughput", "Loss"],
        loc='center',
        cellLoc='center'
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.1, 1.7)

    # Colour the header row to match the scenario colour
    for col in range(4):
        tbl[(0, col)].set_facecolor(color)
        tbl[(0, col)].set_text_props(color='white', fontweight='bold')

    ax4.set_title("Summary Table", fontsize=10, fontweight='bold', pad=12)

    plt.tight_layout()
    out_png = os.path.join(RESULTS_DIR, tag, "delay_analysis.png")
    plt.savefig(out_png, dpi=150, bbox_inches='tight')
    print(f"[INFO] Saved: {out_png}")
