"""
Unit tests for the dynamic Boolean function classifier and IEEE symbol mapper.
"""

import pytest
from openvision.ingestion.liberty_parser import LibertyCell, LibertyPin, LibertyFF, LibertyLatch
from openvision.ingestion.symbol_classifier import classify_cell, GateType, PinRole


def make_cell(name: str, pin_funcs: dict, ff=None, latch=None) -> LibertyCell:
    """Helper to create a mock LibertyCell."""
    pins = {}
    for pname, (direction, func, is_clk) in pin_funcs.items():
        pins[pname] = LibertyPin(name=pname, direction=direction, function=func, clock=is_clk)
    return LibertyCell(name=name, pins=pins, ff=ff, latch=latch)


def test_classify_inverter():
    cell = make_cell("inv_gate", {"A": ("input", None, False), "Y": ("output", "(!A)", False)})
    res = classify_cell(cell)
    assert res.gate_type == GateType.INV
    assert res.pin_roles["Y"] == PinRole.OUTPUT
    assert res.pin_roles["A"] == PinRole.INPUT
    assert "Y" in res.bubble_pins


def test_classify_buffer():
    cell = make_cell("buf_gate", {"A": ("input", None, False), "Y": ("output", "(A)", False)})
    res = classify_cell(cell)
    assert res.gate_type == GateType.BUF
    assert len(res.bubble_pins) == 0


def test_classify_nand():
    cell = make_cell("nand_gate", {
        "A": ("input", None, False),
        "B": ("input", None, False),
        "Y": ("output", "(!A) | (!B)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.NAND
    assert "Y" in res.bubble_pins


def test_classify_nor():
    cell = make_cell("nor_gate", {
        "A": ("input", None, False),
        "B": ("input", None, False),
        "Y": ("output", "(!A&!B)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.NOR
    assert "Y" in res.bubble_pins


def test_classify_xor():
    cell = make_cell("xor_gate", {
        "A": ("input", None, False),
        "B": ("input", None, False),
        "Y": ("output", "(A&!B) | (!A&B)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.XOR
    assert len(res.bubble_pins) == 0


def test_classify_xnor():
    cell = make_cell("xnor_gate", {
        "A": ("input", None, False),
        "B": ("input", None, False),
        "Y": ("output", "(!A&!B) | (A&B)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.XNOR
    assert "Y" in res.bubble_pins


def test_classify_mux2():
    cell = make_cell("mux_gate", {
        "A0": ("input", None, False),
        "A1": ("input", None, False),
        "S":  ("input", None, False),
        "X":  ("output", "(A0&!S) | (A1&S)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.MUX2
    assert res.pin_roles["S"] == PinRole.SELECT
    assert res.pin_roles["A0"] == PinRole.DATA0
    assert res.pin_roles["A1"] == PinRole.DATA1
    assert res.pin_roles["X"] == PinRole.OUTPUT


def test_classify_dff():
    ff = LibertyFF(clocked_on="CLK", next_state="D", clear="!RESET_B")
    cell = make_cell("dff_gate", {
        "CLK":     ("input", None, True),
        "D":       ("input", None, False),
        "RESET_B": ("input", None, False),
        "Q":       ("output", "IQ", False),
    }, ff=ff)
    res = classify_cell(cell)
    assert res.gate_type == GateType.DFF
    assert res.pin_roles["CLK"] == PinRole.CLOCK
    assert res.pin_roles["D"] == PinRole.DATA
    assert res.pin_roles["RESET_B"] == PinRole.RESET
    assert res.pin_roles["Q"] == PinRole.Q
    assert "RESET_B" in res.bubble_pins


def test_classify_full_adder():
    cell = make_cell("fa_gate", {
        "A":    ("input", None, False),
        "B":    ("input", None, False),
        "CIN":  ("input", None, False),
        "COUT": ("output", "(A&B) | (A&CIN) | (B&CIN)", False),
        "SUM":  ("output", "(A&!B&!CIN) | (!A&B&!CIN) | (!A&!B&CIN) | (A&B&CIN)", False),
    })
    res = classify_cell(cell)
    assert res.gate_type == GateType.FA
    assert res.pin_roles["SUM"] == PinRole.SUM
    assert res.pin_roles["COUT"] == PinRole.COUT
    assert res.pin_roles["CIN"] == PinRole.CIN
