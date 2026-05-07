"""
plot_queue.py
-------------
Plots queue length over time. Automatically detects which scenario
the experiment belongs to and uses a matching analysis title.

Single experiment:
    python3 plot_queue.py --tag scenario1_lightLoad_stable

Compare all scenarios:
    python3 plot_queue.py --compare
"""

import os
import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")

# ── Scenario metadata ─────────────────────────
# Maps experiment tag → human title + description for the report heading
SCENARIO_META = {
    "scenario1_lightLoad_stable": {
        "title":    "Scenario 1: Light Load — Stable Queue (M/M/1 Under-utilised)",
        "subtitle": "Arrival rate (900 Kbps total) < Service rate (2 Mbps bottleneck)\n"
                    "Queueing theory predicts: short queue, low delay, zero loss",
        "color":    "#0F6E56",
    },
    "scenario2_heavyLoad_congestion": {
        "title":    "Scenario 2: Heavy Congestion — Queue Saturation (M/M/1 Overloaded)",
        "subtitle": "Arrival rate (6 Mbps total) >> Service rate (1 Mbps bottleneck)\n"
                    "Queueing theory predicts: queue fills to capacity, high delay, packet loss",
        "color":    "#A32D2D",
    },
    "scenario3_Prio": {
        "title":    "Scenario 3a: Queue Discipline — Priority Scheduling (PrioQueueDisc)",
        "subtitle": "Arrival rate (3 Mbps total) ≈ Service rate (1 Mbps bottleneck) — moderate load\n"
                    "Priority discipline: small packets served first regardless of arrival order",
        "color":    "#534AB7",
    },
    "scenario3_FqCodel": {
        "title":    "Scenario 3b: Queue Discipline — Fair Queuing with AQM (FqCoDelQueueDisc)",
        "subtitle": "Same load as 3a — compare queue depth and delay against Priority\n"
                    "FqCoDel: per-flow fair queuing + active queue management reduces bufferbloat",
        "color":    "#185FA5",
    },
}

DEFAULT_META = {
    "title":    "Queue Length Over Time",
    "subtitle": "NS3 Queueing Simulation",
    "color":    "#2563EB",
}


def get_meta(tag):
    return SCENARIO_META.get(tag, {**DEFAULT_META,
                                    "title": f"Queue Length — {tag}",
                                    "subtitle": "NS3 Queueing Simulation"})


# ── CLI ───────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--tag",     default="", help="Single experiment tag")
parser.add_argument("--compare", action="store_true", help="Overlay all experiments")
args = parser.parse_args()


def find_experiments():
    exps = []
    if not os.path.isdir(RESULTS_DIR):
        return exps
    for entry in sorted(os.listdir(RESULTS_DIR)):
        subdir = os.path.join(RESULTS_DIR, entry)
        trace  = os.path.join(subdir, "queue-size.tr")
        if os.path.isdir(subdir) and os.path.isfile(trace):
            exps.append((entry, trace))
    return exps


def load_trace(path):
    time, queue = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t, q = map(float, line.split())
            time.append(t)
            queue.append(q)
    return np.array(time), np.array(queue)


def smooth(time, queue, n=2000):
    t_u = np.linspace(time[0], time[-1], n)
    q_u = np.interp(t_u, time, queue)
    window = max(1, n // 100)
    q_s = np.convolve(q_u, np.ones(window)/window, mode='same')
    return t_u, q_s


experiments = find_experiments()
if not experiments:
    sys.exit(f"[ERROR] No experiment subfolders found in {RESULTS_DIR}")

if args.tag:
    experiments = [(t, p) for t, p in experiments if t == args.tag]
    if not experiments:
        sys.exit(f"[ERROR] Tag '{args.tag}' not found.")

print(f"[INFO] Plotting {len(experiments)} experiment(s): {[t for t,_ in experiments]}")

# ── COMPARE: all on one chart ─────────────────
if args.compare or len(experiments) > 1:
    fig, ax = plt.subplots(figsize=(13, 5))
    fig.suptitle(
        "Queue Length Comparison — Three Queueing Theory Scenarios\n"
        "Scenario 1: light load  |  Scenario 2: congestion  |  Scenario 3: discipline effect",
        fontsize=11, fontweight='bold')

    for tag, trace_path in experiments:
        meta = get_meta(tag)
        time, queue = load_trace(trace_path)
        t_u, q_s    = smooth(time, queue)
        ax.plot(t_u, q_s, color=meta["color"], linewidth=1.8, label=tag)
        ax.fill_between(t_u, q_s, alpha=0.07, color=meta["color"])

    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel("Queue Length (packets)", fontsize=10)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "plot_queue_comparison.png")
    plt.savefig(out, dpi=150, bbox_inches='tight')
    print(f"[INFO] Saved: {out}")

# ── SINGLE: detailed two-panel chart ──────────
else:
    tag, trace_path = experiments[0]
    meta = get_meta(tag)
    time, queue = load_trace(trace_path)
    t_u, q_s    = smooth(time, queue)

    print(f"[INFO] {tag}  |  {len(time)} events  |  peak = {int(queue.max())} pkts")

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(meta["title"] + "\n" + meta["subtitle"],
                 fontsize=11, fontweight='bold', y=1.01)

    color = meta["color"]

    ax = axes[0]
    ax.plot(t_u, q_s, color=color, linewidth=1.8, label="Queue length (smoothed)")
    ax.fill_between(t_u, q_s, alpha=0.18, color=color)

    peak_idx = int(np.argmax(q_s))
    peak_t, peak_q = t_u[peak_idx], q_s[peak_idx]
    ax.annotate(f"Peak: {peak_q:.1f} pkts @ {peak_t:.2f}s",
                xy=(peak_t, peak_q),
                xytext=(peak_t + (time[-1]-time[0])*0.05, peak_q * 0.82),
                arrowprops=dict(arrowstyle="->", color="#DC2626", lw=1.2),
                color="#DC2626", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#DC2626", alpha=0.85))

    for start, lbl in [(1,"C0 starts"),(2,"C1 starts"),(3,"C2 starts")]:
        ax.axvline(start, color="#9CA3AF", linewidth=1.0, linestyle="--")
        ax.text(start+0.1, ax.get_ylim()[1]*0.92, lbl, fontsize=7, color="#4B5563")

    ax.set_ylabel("Queue Length (packets)", fontsize=10)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.4)

    ax2 = axes[1]
    ax2.scatter(time, queue, s=4, color=color, alpha=0.45, linewidths=0,
                label="Raw trace events (each dot = one queue-change)")
    ax2.plot(t_u, q_s, color=color, linewidth=1.0, alpha=0.5)
    ax2.set_xlabel("Time (s)", fontsize=10)
    ax2.set_ylabel("Queue Length (packets)", fontsize=10)
    ax2.set_ylim(bottom=0)
    ax2.legend(fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.set_title("Raw trace events", fontsize=9)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, tag, "plot_queue.png")
    plt.savefig(out, dpi=150, bbox_inches='tight')
    print(f"[INFO] Saved: {out}")
