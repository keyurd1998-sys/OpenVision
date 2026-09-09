"""
Unit tests for the structural Verilog netlist parser and connectivity graph builder.
"""

import pytest
from openvision.ingestion.netlist_parser import parse_netlist_text
from openvision.ingestion.liberty_parser import parse_liberty_text

SAMPLE_VERILOG = """
module simple_adder(
    input  wire       clk,
    input  wire       reset,
    input  wire [1:0] a,
    input  wire [1:0] b,
    output wire [1:0] sum,
    output wire       cout
);
  wire [1:0] sum_int;
  wire c_mid;

  sky130_fd_sc_hd__fa_1 fa0 (
    .A(a[0]),
    .B(b[0]),
    .CIN(1'b0),
    .COUT(c_mid),
    .SUM(sum_int[0])
  );

  sky130_fd_sc_hd__fa_1 fa1 (
    .A(a[1]),
    .B(b[1]),
    .CIN(c_mid),
    .COUT(cout),
    .SUM(sum_int[1])
  );

  sky130_fd_sc_hd__dfxtp_1 dff0 (
    .CLK(clk),
    .D(sum_int[0]),
    .Q(sum[0])
  );

  sky130_fd_sc_hd__dfxtp_1 dff1 (
    .CLK(clk),
    .D(sum_int[1]),
    .Q(sum[1])
  );

endmodule
"""

SAMPLE_LIB = """
library ("mock_lib") {
  cell ("sky130_fd_sc_hd__fa_1") {
    pin ("A") { direction : "input"; }
    pin ("B") { direction : "input"; }
    pin ("CIN") { direction : "input"; }
    pin ("COUT") { direction : "output"; function : "(A&B) | (A&CIN) | (B&CIN)"; }
    pin ("SUM") { direction : "output"; function : "(A&!B&!CIN) | (!A&B&!CIN) | (!A&!B&CIN) | (A&B&CIN)"; }
  }
  cell ("sky130_fd_sc_hd__dfxtp_1") {
    ff ("IQ", "IQ_N") { clocked_on : "CLK"; next_state : "D"; }
    pin ("CLK") { direction : "input"; clock : "true"; }
    pin ("D") { direction : "input"; }
    pin ("Q") { direction : "output"; function : "IQ"; }
  }
}
"""

def test_parse_netlist_structure():
    netlist = parse_netlist_text(SAMPLE_VERILOG)
    assert len(netlist) == 1
    assert "simple_adder" in netlist

    mod = netlist["simple_adder"]
    assert len(mod.ports) == 6
    assert mod.ports["a"].width == 2
    assert mod.ports["b"].width == 2
    assert mod.ports["sum"].width == 2
    assert mod.ports["cout"].width == 1

    assert len(mod.instances) == 4
    assert "fa0" in mod.instances
    assert "fa1" in mod.instances
    assert "dff0" in mod.instances
    assert "dff1" in mod.instances

    # Check connection of fa0
    fa0 = mod.instances["fa0"]
    assert fa0.cell_type == "sky130_fd_sc_hd__fa_1"
    assert fa0.connections["A"] == "a[0]"
    assert fa0.connections["B"] == "b[0]"
    assert fa0.connections["COUT"] == "c_mid"


def test_netlist_connectivity_and_library_linking():
    lib = parse_liberty_text(SAMPLE_LIB)
    netlist = parse_netlist_text(SAMPLE_VERILOG)
    netlist.link_library(lib)

    mod = netlist["simple_adder"]

    # Verify c_mid driver and loads
    c_mid_drivers = mod.get_drivers("c_mid")
    assert ("fa0", "COUT") in c_mid_drivers

    c_mid_loads = mod.get_loads("c_mid")
    assert ("fa1", "CIN") in c_mid_loads

    # Verify clk loads
    clk_loads = mod.get_loads("clk")
    assert ("dff0", "CLK") in clk_loads
    assert ("dff1", "CLK") in clk_loads

    # Verify summary
    summary = mod.get_summary()
    assert summary["total_instances"] == 4
    assert summary["sequential_instances"] == 2
    assert summary["combinational_instances"] == 2
    assert summary["gate_types"]["FA"] == 2
    assert summary["gate_types"]["DFF"] == 2
