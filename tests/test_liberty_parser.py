"""
Unit tests for the Liberty (.lib) technology parser.
"""

import pytest
from openvision.ingestion.liberty_parser import parse_liberty_text, LibertyLibrary

SAMPLE_LIBERTY_TEXT = """
library ("test_lib") {
    technology("cmos");
    delay_model : "table_lookup";

    /* Sample Inverter */
    cell ("my_inv") {
        area : 1.5;
        cell_footprint : "inv_fp";
        pg_pin ("VPWR") { pg_type : "primary_power"; }
        pg_pin ("VGND") { pg_type : "primary_ground"; }
        pin ("A") {
            direction : "input";
            clock : "false";
        }
        pin ("Y") {
            direction : "output";
            function : "(!A)";
            power_down_function : "(!VPWR + VGND)";
        }
    }

    /* Sample 2-input NAND */
    cell ("my_nand2") {
        area : 2.5;
        pin ("A") { direction : "input"; }
        pin ("B") { direction : "input"; }
        pin ("Y") {
            direction : "output";
            function : "(!A) | (!B)";
        }
    }

    /* Sample D-Flip-Flop */
    cell ("my_dff") {
        area : 12.0;
        ff ("IQ", "IQ_N") {
            clocked_on : "CLK";
            next_state : "D";
            clear : "!RESET_B";
        }
        pin ("CLK") {
            direction : "input";
            clock : "true";
        }
        pin ("D") {
            direction : "input";
        }
        pin ("RESET_B") {
            direction : "input";
        }
        pin ("Q") {
            direction : "output";
            function : "IQ";
        }
    }
}
"""

def test_parse_liberty_text():
    lib = parse_liberty_text(SAMPLE_LIBERTY_TEXT)
    assert lib.name == "test_lib"
    assert len(lib) == 3
    assert "my_inv" in lib
    assert "my_nand2" in lib
    assert "my_dff" in lib

    # Test Inverter
    inv = lib["my_inv"]
    assert inv.area == 1.5
    assert inv.cell_footprint == "inv_fp"
    assert "VPWR" in inv.pg_pins
    assert "VGND" in inv.pg_pins
    assert inv.input_pins == ["A"]
    assert inv.output_pins == ["Y"]
    assert not inv.is_sequential
    assert inv.pins["Y"].function == "(!A)"

    # Test NAND2
    nand = lib["my_nand2"]
    assert nand.input_pins == ["A", "B"]
    assert nand.output_pins == ["Y"]
    assert nand.pins["Y"].function == "(!A) | (!B)"

    # Test DFF
    dff = lib["my_dff"]
    assert dff.is_sequential
    assert dff.clock_pin == "CLK"
    assert dff.ff is not None
    assert dff.ff.clocked_on == "CLK"
    assert dff.ff.next_state == "D"
    assert dff.ff.clear == "!RESET_B"
    assert dff.pins["CLK"].clock is True
    assert dff.pins["Q"].function == "IQ"
