// Fibonacci Sequence Generator
// Dual-register arithmetic loop with comparator and control logic.
module fibonacci_generator (
    input  wire       clk,
    input  wire       reset,
    input  wire       start,
    input  wire [4:0] n,
    output reg  [7:0] fib_out,
    output reg        done
);

    localparam IDLE    = 2'b00;
    localparam COMPUTE = 2'b01;
    localparam FINISH  = 2'b10;

    reg [1:0] state;
    reg [7:0] a;
    reg [7:0] b;
    reg [4:0] count;

    always @(posedge clk) begin
        if (reset) begin
            state   <= IDLE;
            a       <= 8'd0;
            b       <= 8'd1;
            count   <= 5'd0;
            fib_out <= 8'd0;
            done    <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        if (n == 5'd0) begin
                            fib_out <= 8'd0;
                            state   <= FINISH;
                        end else if (n == 5'd1) begin
                            fib_out <= 8'd1;
                            state   <= FINISH;
                        end else begin
                            a       <= 8'd0;
                            b       <= 8'd1;
                            count   <= 5'd2;
                            state   <= COMPUTE;
                        end
                    end
                end

                COMPUTE: begin
                    a <= b;
                    b <= a + b;
                    if (count >= n) begin
                        fib_out <= a + b;
                        state   <= FINISH;
                    end else begin
                        count <= count + 1'b1;
                    end
                end

                FINISH: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
