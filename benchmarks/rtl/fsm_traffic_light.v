// Traffic Light Controller FSM
// Finite State Machine (state registers + next-state logic + output decoding).
module fsm_traffic_light (
    input  wire       clk,
    input  wire       reset,
    input  wire       car_detected,
    output reg  [1:0] highway_light, // 2'b00=Red, 2'b01=Yellow, 2'b10=Green
    output reg  [1:0] farm_light     // 2'b00=Red, 2'b01=Yellow, 2'b10=Green
);

    localparam S_HW_GREEN  = 2'd0;
    localparam S_HW_YELLOW = 2'd1;
    localparam S_FM_GREEN  = 2'd2;
    localparam S_FM_YELLOW = 2'd3;

    localparam LIGHT_RED    = 2'b00;
    localparam LIGHT_YELLOW = 2'b01;
    localparam LIGHT_GREEN  = 2'b10;

    reg [1:0] current_state, next_state;

    // State register
    always @(posedge clk) begin
        if (reset)
            current_state <= S_HW_GREEN;
        else
            current_state <= next_state;
    end

    // Next-state logic
    always @(*) begin
        case (current_state)
            S_HW_GREEN: begin
                if (car_detected)
                    next_state = S_HW_YELLOW;
                else
                    next_state = S_HW_GREEN;
            end
            S_HW_YELLOW: begin
                next_state = S_FM_GREEN;
            end
            S_FM_GREEN: begin
                if (!car_detected)
                    next_state = S_FM_YELLOW;
                else
                    next_state = S_FM_GREEN;
            end
            S_FM_YELLOW: begin
                next_state = S_HW_GREEN;
            end
            default: next_state = S_HW_GREEN;
        endcase
    end

    // Output decoding logic
    always @(*) begin
        case (current_state)
            S_HW_GREEN: begin
                highway_light = LIGHT_GREEN;
                farm_light    = LIGHT_RED;
            end
            S_HW_YELLOW: begin
                highway_light = LIGHT_YELLOW;
                farm_light    = LIGHT_RED;
            end
            S_FM_GREEN: begin
                highway_light = LIGHT_RED;
                farm_light    = LIGHT_GREEN;
            end
            S_FM_YELLOW: begin
                highway_light = LIGHT_RED;
                farm_light    = LIGHT_YELLOW;
            end
            default: begin
                highway_light = LIGHT_RED;
                farm_light    = LIGHT_RED;
            end
        endcase
    end

endmodule
