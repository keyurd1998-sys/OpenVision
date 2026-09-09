// 8-State Moore/Mealy Finite State Machine
// Top module: fsm_8state
module fsm_8state (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire [3:0]  data_in,
    input  wire        mode,
    output reg         ready,
    output reg         valid,
    output reg  [3:0]  data_out,
    output wire [2:0]  state_out
);

    // 8 State Encodings
    localparam [2:0]
        S_IDLE     = 3'b000,
        S_LOAD     = 3'b001,
        S_DECODE   = 3'b010,
        S_EXECUTE  = 3'b011,
        S_BRANCH   = 3'b100,
        S_ACCUM    = 3'b101,
        S_WRITE    = 3'b110,
        S_DONE     = 3'b111;

    reg [2:0] current_state, next_state;
    reg [3:0] accumulator;

    assign state_out = current_state;

    // State Register & Datapath
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            current_state <= S_IDLE;
            accumulator   <= 4'b0000;
        end else begin
            current_state <= next_state;
            if (current_state == S_LOAD)
                accumulator <= data_in;
            else if (current_state == S_ACCUM)
                accumulator <= accumulator + data_in;
        end
    end

    // Next State Logic
    always @(*) begin
        next_state = current_state;
        case (current_state)
            S_IDLE: begin
                if (start)
                    next_state = S_LOAD;
                else
                    next_state = S_IDLE;
            end
            S_LOAD: begin
                next_state = S_DECODE;
            end
            S_DECODE: begin
                if (mode)
                    next_state = S_EXECUTE;
                else
                    next_state = S_BRANCH;
            end
            S_EXECUTE: begin
                next_state = S_ACCUM;
            end
            S_BRANCH: begin
                if (data_in[0])
                    next_state = S_ACCUM;
                else
                    next_state = S_WRITE;
            end
            S_ACCUM: begin
                next_state = S_WRITE;
            end
            S_WRITE: begin
                next_state = S_DONE;
            end
            S_DONE: begin
                if (!start)
                    next_state = S_IDLE;
                else
                    next_state = S_DONE;
            end
            default: next_state = S_IDLE;
        endcase
    end

    // Output Logic
    always @(*) begin
        ready    = (current_state == S_IDLE);
        valid    = (current_state == S_DONE);
        data_out = (current_state == S_DONE) ? accumulator : 4'b0000;
    end

endmodule
