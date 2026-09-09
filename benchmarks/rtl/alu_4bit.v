// 4-bit Arithmetic Logic Unit
// Arithmetic and logic unit (ADD, SUB, AND, OR, XOR) with zero and carry flags.
module alu_4bit (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [2:0] opcode,
    output reg  [3:0] result,
    output reg        carry_out,
    output wire       zero
);

    reg [4:0] arith_res;

    always @(*) begin
        carry_out = 1'b0;
        arith_res = 5'b0;
        case (opcode)
            3'b000: begin // ADD
                arith_res = {1'b0, a} + {1'b0, b};
                result    = arith_res[3:0];
                carry_out = arith_res[4];
            end
            3'b001: begin // SUB
                arith_res = {1'b0, a} - {1'b0, b};
                result    = arith_res[3:0];
                carry_out = arith_res[4];
            end
            3'b010: begin // AND
                result    = a & b;
            end
            3'b011: begin // OR
                result    = a | b;
            end
            3'b100: begin // XOR
                result    = a ^ b;
            end
            3'b101: begin // NOT A
                result    = ~a;
            end
            3'b110: begin // SLT (Set on Less Than)
                result    = (a < b) ? 4'b0001 : 4'b0000;
            end
            default: begin
                result    = 4'b0000;
            end
        endcase
    end

    assign zero = (result == 4'b0000);

endmodule
