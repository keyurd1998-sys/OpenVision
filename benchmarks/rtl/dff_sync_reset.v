// D Flip-Flop with Synchronous Reset
// Basic sequential storage element with clock and reset.
module dff_sync_reset (
    input  wire clk,
    input  wire reset,
    input  wire d,
    output reg  q
);

    always @(posedge clk) begin
        if (reset)
            q <= 1'b0;
        else
            q <= d;
    end

endmodule
