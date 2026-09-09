// 4-bit Synchronous Up/Down Counter
// Sequential feedback loop testing registers feeding back into logic.
module up_down_counter_4bit (
    input  wire       clk,
    input  wire       reset,
    input  wire       enable,
    input  wire       up_down, // 1 = count up, 0 = count down
    output reg  [3:0] count
);

    always @(posedge clk) begin
        if (reset) begin
            count <= 4'b0000;
        end else if (enable) begin
            if (up_down)
                count <= count + 1'b1;
            else
                count <= count - 1'b1;
        end
    end

endmodule
