// 8-bit Serial-In Parallel-Out Shift Register
// Pure pipeline shift chain for horizontal register-to-register alignment.
module shift_register_8bit (
    input  wire       clk,
    input  wire       reset,
    input  wire       shift_in,
    output wire       shift_out,
    output wire [7:0] parallel_out
);

    reg [7:0] q;

    always @(posedge clk) begin
        if (reset)
            q <= 8'b00000000;
        else
            q <= {q[6:0], shift_in};
    end

    assign parallel_out = q;
    assign shift_out    = q[7];

endmodule
