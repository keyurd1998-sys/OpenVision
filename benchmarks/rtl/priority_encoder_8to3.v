// 8-to-3 Priority Encoder with Enable
// Cascaded combinational priority logic.
module priority_encoder_8to3 (
    input  wire       enable,
    input  wire [7:0] in,
    output reg  [2:0] code,
    output reg        valid
);

    always @(*) begin
        if (!enable) begin
            code  = 3'b000;
            valid = 1'b0;
        end else begin
            valid = 1'b1;
            if (in[7])      code = 3'd7;
            else if (in[6]) code = 3'd6;
            else if (in[5]) code = 3'd5;
            else if (in[4]) code = 3'd4;
            else if (in[3]) code = 3'd3;
            else if (in[2]) code = 3'd2;
            else if (in[1]) code = 3'd1;
            else if (in[0]) code = 3'd0;
            else begin
                code  = 3'b000;
                valid = 1'b0;
            end
        end
    end

endmodule
