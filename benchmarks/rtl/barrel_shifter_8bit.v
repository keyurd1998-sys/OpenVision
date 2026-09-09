// 8-bit Barrel Shifter
// Complex routing mesh with multi-stage multiplexers and high cross-wiring.
module barrel_shifter_8bit (
    input  wire [7:0] data_in,
    input  wire [2:0] shift_amt,
    input  wire       dir,           // 0: left, 1: right
    input  wire       arith_logical, // 0: logical, 1: arithmetic (preserves sign on right shift)
    output reg  [7:0] data_out
);

    always @(*) begin
        if (dir == 1'b0) begin
            // Left shift
            data_out = data_in << shift_amt;
        end else begin
            // Right shift
            if (arith_logical) begin
                // Arithmetic right shift
                data_out = $signed(data_in) >>> shift_amt;
            end else begin
                // Logical right shift
                data_out = data_in >> shift_amt;
            end
        end
    end

endmodule
