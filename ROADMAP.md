# OpenVision: Universal Schematic Viewer for Technology-Mapped Netlists
## Master Engineering Specification & Project Roadmap

---

## 1. Executive Summary & Vision

### 1.1 The Problem
In modern open-source digital VLSI design, engineers face a severe visualization gap:
* **Graphviz (`show` in Yosys):** Designed for generic directed graphs, not VLSI schematics. It produces unreadable, tangled spaghetti lines, cuts through gate bodies, and places pins haphazardly.
* **`netlistsvg`:** Relies on generic Yosys GTECH primitives (`$and`, `$dff`). When applied to a technology-mapped netlist (e.g. SkyWater 130nm, GF180, Nangate45), it collapses into generic rectangular black boxes with arbitrary pin orders.
* **Commercial Reference Standard:** Tools like **Synopsys Design Vision**, **Cadence Genus/Verdi**, and **Siemens Tessent** provide clean, readable schematics with:
  * Left-to-right topological logic flow.
  * Standard IEEE logic gate symbols for library cells.
  * Clean orthogonal (Manhattan 90°) wiring with solder-dot junctions.
  * Incremental logic cone exploration (fanin/fanout expansion).

### 1.2 Mission
Build an open-source, standalone, cross-platform schematic generator and interactive viewer that consumes **structural gate-level Verilog netlists (`.v`)** and **technology PDK Liberty files (`.lib`)** directly to produce **clean, publication-quality, interactive schematics** matching commercial EDA standards.

---

## 2. Core Architecture Overview

```
                                [ Synthesized Gate Netlist ]          [ Technology PDK ]
                                     (structural .v)                    (Liberty .lib)
                                            │                                 │
                                            └───────────────┬─────────────────┘
                                                            │
                                                            ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                  STAGE 1: INGESTION ENGINE                  │
                    │ - Structural Verilog Tokenizer (`netlist_parser.py`)        │
                    │ - Liberty (.lib) Parser (`liberty_parser.py`)               │
                    │ - Dynamic Boolean Function Classifier (`symbol_classifier`) │
                    └──────────────────────────────┬──────────────────────────────┘
                                                   │
                                                   ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                  STAGE 2: PLACEMENT ENGINE                  │
                    │ - Cycle Breaking (Feedback loops at DFF boundaries)         │
                    │ - Topological Layering (Sugiyama Left-to-Right Ranking)     │
                    │ - Crossing Minimization (Barycentric Heuristic)             │
                    │ - Coordinate & Channel Assignment                           │
                    └──────────────────────────────┬──────────────────────────────┘
                                                   │
                                                   ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                  STAGE 3: ORTHOGONAL ROUTER                 │
                    │ - Manhattan Wire Segment Generator (90° bends only)         │
                    │ - Junction Solder Dot (•) Insertion for Fanout > 1          │
                    │ - High-Fanout Net (HFN) Decoupling (clk/rst stubs)          │
                    └──────────────────────────────┬──────────────────────────────┘
                                                   │
                                                   ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                  STAGE 4: INTERACTIVE CANVAS                │
                    │ - Hardware-Accelerated 2D Vector Rendering (PyQt6)          │
                    │ - Infinite Pan / Cursor-Centered Zoom                       │
                    │ - Incremental Fanin / Fanout Cone Expansion                 │
                    │ - Interactive Net Highlighting & Search                     │
                    └─────────────────────────────────────────────────────────────┘
```

---

## 3. Direct Ingestion & Dynamic Symbol Classification

### 3.1 Structural Verilog Netlist (`.v`)
* Structural Verilog is an unambiguous, declarative format containing only:
  * Module and port definitions (`module my_design (clk, in1, out1);`)
  * Wire declarations (`wire n1, n2;`)
  * Gate/cell instantiations with named port connections (`sky130_fd_sc_hd__nand2_1 g1 (.A(in1), .B(in2), .Y(n1));`)
* Avoids dependence on intermediate JSON representations; universally compatible across netlists produced by Yosys, Synopsys Design Compiler, or Cadence Genus.

### 3.2 Liberty (`.lib`) Parsing & Dynamic IEEE Classification
Instead of hardcoding cell names, OpenVision parses the Boolean `function` in the `.lib` file to dynamically determine the gate symbol:
* `(!A & !B)` or `!(A | B)` $\rightarrow$ **IEEE NOR Gate**
* `(!A | !B)` or `!(A & B)` $\rightarrow$ **IEEE NAND Gate**
* `(A ^ B)` $\rightarrow$ **IEEE XOR Gate**
* `!A` $\rightarrow$ **IEEE Inverter (Triangle with bubble)**
* `(S ? B : A)` or `((A & !S) | (B & S))` $\rightarrow$ **2:1 Multiplexer**
* Cell contains `ff` block or clock pin $\rightarrow$ **D-Flip-Flop (Box with dynamic clock triangle)**
* Unrecognized or multi-output macros $\rightarrow$ **Structured rectangular block with West inputs & East outputs**

---

## 4. Placement & Orthogonal Routing Algorithms

### 4.1 Placement Engine (The Sugiyama Framework)
1. **Cycle Breaking:** Decouple sequential feedback loops at flip-flop boundaries (treating DFF Q as input and D as output).
2. **Topological Layering:** Assign gates to vertical columns (Rank 0: Primary Inputs & Register Qs; Intermediate Ranks: Combinational logic; Final Rank: Primary Outputs & Register Ds).
3. **Crossing Reduction:** Apply the Barycentric / Median heuristic with two-pass sweeps to sort gates vertically within each rank.

### 4.2 Manhattan Orthogonal Auto-Router
1. **Strict 90° Segments:** Wires are exclusively horizontal and vertical segments.
2. **Perpendicular Pin Exits:** Inputs enter from the West; outputs emerge to the East; clocks/resets enter from the South.
3. **Solder Dots (`•`):** Inserted at all wire branch points driving multiple fanout gates.
4. **High-Fanout Net (HFN) Decoupling:** Global signals (`clk`, `rst`, `scan_enable`) are decoupled into local net label stubs to prevent unreadable global spiderwebs.

---

## 5. Benchmark Suite: 10 RTL Designs & Automated Sky130 Synthesis

Located in `benchmarks/rtl/` and synthesized to `benchmarks/synth/*.v`:

1. **`full_adder.v`:** Basic combinational logic (XOR, AND, OR gates).
2. **`priority_encoder_8to3.v`:** Cascaded combinational priority logic.
3. **`mux4to1.v`:** Multiplexer tree and select-line decoding.
4. **`alu_4bit.v`:** Arithmetic logic unit (ADD, SUB, AND, OR, XOR with zero/carry flags).
5. **`dff_sync_reset.v`:** Sequential storage element with clock and reset.
6. **`up_down_counter_4bit.v`:** Sequential feedback loop (registers feeding back into adder/subtractor logic).
7. **`shift_register_8bit.v`:** Pure pipeline shift chain (tests horizontal register-to-register alignment).
8. **`fsm_traffic_light.v`:** Finite State Machine (state registers + next-state logic + output decoding).
9. **`barrel_shifter_8bit.v`:** Complex routing mesh with multi-stage multiplexers and high cross-wiring.
10. **`fibonacci_generator.v`:** Dual-register arithmetic loop with comparator and control logic.

**Synthesis Recipe:**
Automated via `synthesize_benchmarks.py` using **Yosys** targeting:
* `$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib`

---

## 6. Implementation Milestones

* **Milestone 1: Project Setup, 10 RTL Designs & Automated Synthesis**
  * Set up project structure & virtual environment in `/eda/OpenVision`.
  * Write the 10 Verilog RTL benchmark designs in `benchmarks/rtl/`.
  * Create the automated Yosys synthesis script to tech-map all 10 designs to Sky130 (`benchmarks/synth/*.v`).
  * Build `liberty_parser.py` and `symbol_classifier.py` (extracts cell pins, directions, and Boolean functions from `.lib`).
  * Build `netlist_parser.py` (parses structural Verilog gate instantiations).
  * Verify by parsing all 10 synthesized netlists and printing the recognized gate summary.

* **Milestone 2: Sugiyama Layered Placement Engine**
  * Cycle breaking, topological leveling, and Barycentric crossing minimization.

* **Milestone 3: Manhattan Orthogonal Auto-Router**
  * 100% horizontal/vertical wire routes, solder dots, and HFN decoupling.

* **Milestone 4: Interactive PyQt6 GUI Canvas**
  * Hardware-accelerated 2D vector canvas (`QGraphicsView`), pan, zoom, net highlighting.

* **Milestone 5: Incremental Logic Cone Tracing & CLI**
  * Fanin/Fanout expansion, search bar, and full regression testing across all 10 benchmark netlists.
