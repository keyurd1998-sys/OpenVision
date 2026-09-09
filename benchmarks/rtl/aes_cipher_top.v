// ============================================================================
// Multi-Hierarchy AES-128 Cryptographic Core
// Top-Level Module: aes_cipher_top
// Architecture:
//   Level 0: aes_cipher_top
//     Level 1: aes_controller
//     Level 1: aes_key_schedule
//       Level 2: aes_rcon
//       Level 2: aes_sub_word
//         Level 3: aes_sbox_lut (x4)
//     Level 1: aes_datapath
//       Level 2: aes_sub_bytes
//         Level 3: aes_sbox_lut (x16)
//       Level 2: aes_shift_rows
//       Level 2: aes_mix_columns
//         Level 3: aes_mix_single_column (x4)
//       Level 2: aes_add_round_key
// ============================================================================

// ----------------------------------------------------------------------------
// Level 3 Submodule: S-Box Byte Substitution LUT
// ----------------------------------------------------------------------------
module aes_sbox_lut (
    input  wire [7:0] in_byte,
    output reg  [7:0] out_byte
);
    always @(*) begin
        case (in_byte)
            8'h00: out_byte = 8'h63; 8'h01: out_byte = 8'h7c; 8'h02: out_byte = 8'h77; 8'h03: out_byte = 8'h7b;
            8'h04: out_byte = 8'hf2; 8'h05: out_byte = 8'h6b; 8'h06: out_byte = 8'h6f; 8'h07: out_byte = 8'hc5;
            8'h08: out_byte = 8'h30; 8'h09: out_byte = 8'h01; 8'h0a: out_byte = 8'h67; 8'h0b: out_byte = 8'h2b;
            8'h0c: out_byte = 8'hfe; 8'h0d: out_byte = 8'hd7; 8'h0e: out_byte = 8'hab; 8'h0f: out_byte = 8'h76;
            8'h10: out_byte = 8'hca; 8'h11: out_byte = 8'h82; 8'h12: out_byte = 8'hc9; 8'h13: out_byte = 8'h7d;
            8'h14: out_byte = 8'hfa; 8'h15: out_byte = 8'h59; 8'h16: out_byte = 8'h47; 8'h17: out_byte = 8'hf0;
            8'h18: out_byte = 8'had; 8'h19: out_byte = 8'hd4; 8'h1a: out_byte = 8'ha2; 8'h1b: out_byte = 8'haf;
            8'h1c: out_byte = 8'h9c; 8'h1d: out_byte = 8'ha4; 8'h1e: out_byte = 8'h72; 8'h1f: out_byte = 8'hc0;
            8'h20: out_byte = 8'hb7; 8'h21: out_byte = 8'hfd; 8'h22: out_byte = 8'h93; 8'h23: out_byte = 8'h26;
            8'h24: out_byte = 8'h36; 8'h25: out_byte = 8'h3f; 8'h26: out_byte = 8'hf7; 8'h27: out_byte = 8'hcc;
            8'h28: out_byte = 8'h34; 8'h29: out_byte = 8'ha5; 8'h2a: out_byte = 8'he5; 8'h2b: out_byte = 8'hf1;
            8'h2c: out_byte = 8'h71; 8'h2d: out_byte = 8'hd8; 8'h2e: out_byte = 8'h31; 8'h2f: out_byte = 8'h15;
            8'h30: out_byte = 8'h04; 8'h31: out_byte = 8'hc7; 8'h32: out_byte = 8'h23; 8'h33: out_byte = 8'hc3;
            8'h34: out_byte = 8'h18; 8'h35: out_byte = 8'h96; 8'h36: out_byte = 8'h05; 8'h37: out_byte = 8'h9a;
            8'h38: out_byte = 8'h07; 8'h39: out_byte = 8'h12; 8'h3a: out_byte = 8'h80; 8'h3b: out_byte = 8'he2;
            8'h3c: out_byte = 8'heb; 8'h3d: out_byte = 8'h27; 8'h3e: out_byte = 8'hb2; 8'h3f: out_byte = 8'h75;
            8'h40: out_byte = 8'h09; 8'h41: out_byte = 8'h83; 8'h42: out_byte = 8'h2c; 8'h43: out_byte = 8'h1a;
            8'h44: out_byte = 8'h1b; 8'h45: out_byte = 8'h6e; 8'h46: out_byte = 8'h5a; 8'h47: out_byte = 8'ha0;
            8'h48: out_byte = 8'h52; 8'h49: out_byte = 8'h3b; 8'h4a: out_byte = 8'hd6; 8'h4b: out_byte = 8'hb3;
            8'h4c: out_byte = 8'h29; 8'h4d: out_byte = 8'he3; 8'h4e: out_byte = 8'h2f; 8'h4f: out_byte = 8'h84;
            8'h50: out_byte = 8'h53; 8'h51: out_byte = 8'hd1; 8'h52: out_byte = 8'h00; 8'h53: out_byte = 8'hed;
            8'h54: out_byte = 8'h20; 8'h55: out_byte = 8'hfc; 8'h56: out_byte = 8'hb1; 8'h57: out_byte = 8'h5b;
            8'h58: out_byte = 8'h6a; 8'h59: out_byte = 8'hcb; 8'h5a: out_byte = 8'hbe; 8'h5b: out_byte = 8'h39;
            8'h5c: out_byte = 8'h4a; 8'h5d: out_byte = 8'h4c; 8'h5e: out_byte = 8'h58; 8'h5f: out_byte = 8'hcf;
            8'h60: out_byte = 8'hd0; 8'h61: out_byte = 8'hef; 8'h62: out_byte = 8'haa; 8'h63: out_byte = 8'hfb;
            8'h64: out_byte = 8'h43; 8'h65: out_byte = 8'h4d; 8'h66: out_byte = 8'h33; 8'h67: out_byte = 8'h85;
            8'h68: out_byte = 8'h45; 8'h69: out_byte = 8'hf9; 8'h6a: out_byte = 8'h02; 8'h6b: out_byte = 8'h7f;
            8'h6c: out_byte = 8'h50; 8'h6d: out_byte = 8'h3c; 8'h6e: out_byte = 8'h9f; 8'h6f: out_byte = 8'ha8;
            8'h70: out_byte = 8'h51; 8'h71: out_byte = 8'ha3; 8'h72: out_byte = 8'h40; 8'h73: out_byte = 8'h8f;
            8'h74: out_byte = 8'h92; 8'h75: out_byte = 8'h9d; 8'h76: out_byte = 8'h38; 8'h77: out_byte = 8'hf5;
            8'h78: out_byte = 8'hbc; 8'h79: out_byte = 8'hb6; 8'h7a: out_byte = 8'hda; 8'h7b: out_byte = 8'h21;
            8'h7c: out_byte = 8'h10; 8'h7d: out_byte = 8'hff; 8'h7e: out_byte = 8'hf3; 8'h7f: out_byte = 8'hd2;
            8'h80: out_byte = 8'hcd; 8'h81: out_byte = 8'h0c; 8'h82: out_byte = 8'h13; 8'h83: out_byte = 8'hec;
            8'h84: out_byte = 8'h5f; 8'h85: out_byte = 8'h97; 8'h86: out_byte = 8'h44; 8'h87: out_byte = 8'h17;
            8'h88: out_byte = 8'hc4; 8'h89: out_byte = 8'ha7; 8'h8a: out_byte = 8'h7e; 8'h8b: out_byte = 8'h3d;
            8'h8c: out_byte = 8'h64; 8'h8d: out_byte = 8'h5d; 8'h8e: out_byte = 8'h19; 8'h8f: out_byte = 8'h73;
            8'h90: out_byte = 8'h60; 8'h91: out_byte = 8'h81; 8'h92: out_byte = 8'h4f; 8'h93: out_byte = 8'hdc;
            8'h94: out_byte = 8'h22; 8'h95: out_byte = 8'h2a; 8'h96: out_byte = 8'h90; 8'h97: out_byte = 8'h88;
            8'h98: out_byte = 8'h46; 8'h99: out_byte = 8'hee; 8'h9a: out_byte = 8'hb8; 8'h9b: out_byte = 8'h14;
            8'h9c: out_byte = 8'hde; 8'h9d: out_byte = 8'h5e; 8'h9e: out_byte = 8'h0b; 8'h9f: out_byte = 8'hdb;
            8'ha0: out_byte = 8'he0; 8'ha1: out_byte = 8'h32; 8'ha2: out_byte = 8'h3a; 8'ha3: out_byte = 8'h0a;
            8'ha4: out_byte = 8'h49; 8'ha5: out_byte = 8'h06; 8'ha6: out_byte = 8'h24; 8'ha7: out_byte = 8'h5c;
            8'ha8: out_byte = 8'hc2; 8'ha9: out_byte = 8'hd3; 8'haa: out_byte = 8'hac; 8'hab: out_byte = 8'h62;
            8'hac: out_byte = 8'h91; 8'had: out_byte = 8'h95; 8'hae: out_byte = 8'he4; 8'haf: out_byte = 8'h79;
            8'hb0: out_byte = 8'he7; 8'hb1: out_byte = 8'hc8; 8'hb2: out_byte = 8'h37; 8'hb3: out_byte = 8'h6d;
            8'hb4: out_byte = 8'h8d; 8'hb5: out_byte = 8'hd5; 8'hb6: out_byte = 8'h4e; 8'hb7: out_byte = 8'ha9;
            8'hb8: out_byte = 8'h6c; 8'hb9: out_byte = 8'h56; 8'hba: out_byte = 8'hf4; 8'hbb: out_byte = 8'hea;
            8'hbc: out_byte = 8'h65; 8'hbd: out_byte = 8'h7a; 8'hbe: out_byte = 8'hae; 8'hbf: out_byte = 8'h08;
            8'hc0: out_byte = 8'hba; 8'hc1: out_byte = 8'h78; 8'hc2: out_byte = 8'h25; 8'hc3: out_byte = 8'h2e;
            8'hc4: out_byte = 8'h1c; 8'hc5: out_byte = 8'ha6; 8'hc6: out_byte = 8'hb4; 8'hc7: out_byte = 8'hc6;
            8'hc8: out_byte = 8'he8; 8'hc9: out_byte = 8'hdd; 8'hca: out_byte = 8'h74; 8'hcb: out_byte = 8'h1f;
            8'hcc: out_byte = 8'h4b; 8'hcd: out_byte = 8'hbd; 8'hce: out_byte = 8'h8b; 8'hcf: out_byte = 8'h8a;
            8'hd0: out_byte = 8'h70; 8'hd1: out_byte = 8'h3e; 8'hd2: out_byte = 8'hb5; 8'hd3: out_byte = 8'h66;
            8'hd4: out_byte = 8'h48; 8'hd5: out_byte = 8'h03; 8'hd6: out_byte = 8'hf6; 8'hd7: out_byte = 8'h0e;
            8'hd8: out_byte = 8'h61; 8'hd9: out_byte = 8'h35; 8'hda: out_byte = 8'h57; 8'hdb: out_byte = 8'hb9;
            8'hdc: out_byte = 8'h86; 8'hdd: out_byte = 8'hc1; 8'hde: out_byte = 8'h1d; 8'hdf: out_byte = 8'h9e;
            8'he0: out_byte = 8'he1; 8'he1: out_byte = 8'hf8; 8'he2: out_byte = 8'h98; 8'he3: out_byte = 8'h11;
            8'he4: out_byte = 8'h69; 8'he5: out_byte = 8'hd9; 8'he6: out_byte = 8'h8e; 8'he7: out_byte = 8'h94;
            8'he8: out_byte = 8'h9b; 8'he9: out_byte = 8'h1e; 8'hea: out_byte = 8'h87; 8'heb: out_byte = 8'he9;
            8'hec: out_byte = 8'hce; 8'hed: out_byte = 8'h55; 8'hee: out_byte = 8'h28; 8'hef: out_byte = 8'hdf;
            8'hf0: out_byte = 8'h8c; 8'hf1: out_byte = 8'ha1; 8'hf2: out_byte = 8'h89; 8'hf3: out_byte = 8'h0d;
            8'hf4: out_byte = 8'hbf; 8'hf5: out_byte = 8'he6; 8'hf6: out_byte = 8'h42; 8'hf7: out_byte = 8'h68;
            8'hf8: out_byte = 8'h41; 8'hf9: out_byte = 8'h99; 8'hfa: out_byte = 8'h2d; 8'hfb: out_byte = 8'h0f;
            8'hfc: out_byte = 8'hb0; 8'hfd: out_byte = 8'h54; 8'hfe: out_byte = 8'hbb; 8'hff: out_byte = 8'h16;
        endcase
    end
endmodule

// ----------------------------------------------------------------------------
// Level 3 Submodule: MixColumns Single Column Multiplier in GF(2^8)
// ----------------------------------------------------------------------------
module aes_mix_single_column (
    input  wire [31:0] col_in,
    output wire [31:0] col_out
);
    wire [7:0] a0 = col_in[31:24];
    wire [7:0] a1 = col_in[23:16];
    wire [7:0] a2 = col_in[15:8];
    wire [7:0] a3 = col_in[7:0];

    // xtime multiplication by {02} in GF(2^8) with irreducible poly x^8 + x^4 + x^3 + x + 1 (0x1b)
    function [7:0] xtime(input [7:0] b);
        xtime = b[7] ? ((b << 1) ^ 8'h1b) : (b << 1);
    endfunction

    // {02}*a ^ {03}*b = xtime(a) ^ xtime(b) ^ b
    assign col_out[31:24] = xtime(a0) ^ (xtime(a1) ^ a1) ^ a2 ^ a3;
    assign col_out[23:16] = a0 ^ xtime(a1) ^ (xtime(a2) ^ a2) ^ a3;
    assign col_out[15:8]  = a0 ^ a1 ^ xtime(a2) ^ (xtime(a3) ^ a3);
    assign col_out[7:0]   = (xtime(a0) ^ a0) ^ a1 ^ a2 ^ xtime(a3);
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: Round Constant Generator
// ----------------------------------------------------------------------------
module aes_rcon (
    input  wire [3:0]  round_idx,
    output reg  [31:0] rcon_word
);
    always @(*) begin
        case (round_idx)
            4'd1:  rcon_word = 32'h01000000;
            4'd2:  rcon_word = 32'h02000000;
            4'd3:  rcon_word = 32'h04000000;
            4'd4:  rcon_word = 32'h08000000;
            4'd5:  rcon_word = 32'h10000000;
            4'd6:  rcon_word = 32'h20000000;
            4'd7:  rcon_word = 32'h40000000;
            4'd8:  rcon_word = 32'h80000000;
            4'd9:  rcon_word = 32'h1b000000;
            4'd10: rcon_word = 32'h36000000;
            default: rcon_word = 32'h00000000;
        endcase
    end
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: SubWord (instantiating 4x aes_sbox_lut)
// ----------------------------------------------------------------------------
module aes_sub_word (
    input  wire [31:0] word_in,
    output wire [31:0] word_out
);
    aes_sbox_lut sb0 (.in_byte(word_in[31:24]), .out_byte(word_out[31:24]));
    aes_sbox_lut sb1 (.in_byte(word_in[23:16]), .out_byte(word_out[23:16]));
    aes_sbox_lut sb2 (.in_byte(word_in[15:8]),  .out_byte(word_out[15:8]));
    aes_sbox_lut sb3 (.in_byte(word_in[7:0]),   .out_byte(word_out[7:0]));
endmodule

// ----------------------------------------------------------------------------
// Level 1 Submodule: Key Schedule Engine (instantiating aes_rcon and aes_sub_word)
// ----------------------------------------------------------------------------
module aes_key_schedule (
    input  wire         clk,
    input  wire         rst,
    input  wire         ld_key,
    input  wire         next_key,
    input  wire [3:0]   round_idx,
    input  wire [127:0] key_in,
    output reg  [127:0] current_key
);
    wire [31:0] rcon;
    aes_rcon rcon_gen (
        .round_idx(round_idx),
        .rcon_word(rcon)
    );

    // RotWord: circular byte shift left [b0,b1,b2,b3] -> [b1,b2,b3,b0]
    wire [31:0] w3 = current_key[31:0];
    wire [31:0] rot_w = {w3[23:0], w3[31:24]};

    wire [31:0] sub_rot_w;
    aes_sub_word subw_inst (
        .word_in(rot_w),
        .word_out(sub_rot_w)
    );

    wire [31:0] next_w0 = current_key[127:96] ^ sub_rot_w ^ rcon;
    wire [31:0] next_w1 = current_key[95:64]  ^ next_w0;
    wire [31:0] next_w2 = current_key[63:32]  ^ next_w1;
    wire [31:0] next_w3 = current_key[31:0]   ^ next_w2;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            current_key <= 128'b0;
        end else if (ld_key) begin
            current_key <= key_in;
        end else if (next_key) begin
            current_key <= {next_w0, next_w1, next_w2, next_w3};
        end
    end
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: SubBytes Unit (instantiating 16x aes_sbox_lut)
// ----------------------------------------------------------------------------
module aes_sub_bytes (
    input  wire [127:0] state_in,
    output wire [127:0] state_out
);
    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : gen_sbox
            aes_sbox_lut sb (
                .in_byte(state_in[i*8 +: 8]),
                .out_byte(state_out[i*8 +: 8])
            );
        end
    endgenerate
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: ShiftRows Unit (128-bit Row Permutation)
// ----------------------------------------------------------------------------
module aes_shift_rows (
    input  wire [127:0] state_in,
    output wire [127:0] state_out
);
    // 4x4 matrix indexing: Row 0 unchanged, Row 1 shift 1, Row 2 shift 2, Row 3 shift 3
    assign state_out[127:120] = state_in[127:120];
    assign state_out[119:112] = state_in[87:80];
    assign state_out[111:104] = state_in[47:40];
    assign state_out[103:96]  = state_in[7:0];

    assign state_out[95:88]   = state_in[95:88];
    assign state_out[87:80]   = state_in[55:48];
    assign state_out[79:72]   = state_in[15:8];
    assign state_out[71:64]   = state_in[103:96];

    assign state_out[63:56]   = state_in[63:56];
    assign state_out[55:48]   = state_in[23:16];
    assign state_out[47:40]   = state_in[111:104];
    assign state_out[39:32]   = state_in[71:64];

    assign state_out[31:24]   = state_in[31:24];
    assign state_out[23:16]   = state_in[119:112];
    assign state_out[15:8]    = state_in[79:72];
    assign state_out[7:0]     = state_in[39:32];
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: MixColumns Unit (instantiating 4x aes_mix_single_column)
// ----------------------------------------------------------------------------
module aes_mix_columns (
    input  wire [127:0] state_in,
    output wire [127:0] state_out
);
    aes_mix_single_column mc0 (.col_in(state_in[127:96]), .col_out(state_out[127:96]));
    aes_mix_single_column mc1 (.col_in(state_in[95:64]),  .col_out(state_out[95:64]));
    aes_mix_single_column mc2 (.col_in(state_in[63:32]),  .col_out(state_out[63:32]));
    aes_mix_single_column mc3 (.col_in(state_in[31:0]),   .col_out(state_out[31:0]));
endmodule

// ----------------------------------------------------------------------------
// Level 2 Submodule: AddRoundKey Unit
// ----------------------------------------------------------------------------
module aes_add_round_key (
    input  wire [127:0] state_in,
    input  wire [127:0] key_in,
    output wire [127:0] state_out
);
    assign state_out = state_in ^ key_in;
endmodule

// ----------------------------------------------------------------------------
// Level 1 Submodule: Encryption Datapath Pipeline
// ----------------------------------------------------------------------------
module aes_datapath (
    input  wire         clk,
    input  wire         rst,
    input  wire         ld_state,
    input  wire         sel_initial,
    input  wire         sel_final,
    input  wire [127:0] text_in,
    input  wire [127:0] round_key,
    output wire [127:0] cipher_text
);
    reg  [127:0] state_reg;
    wire [127:0] sub_bytes_out;
    wire [127:0] shift_rows_out;
    wire [127:0] mix_columns_out;
    wire [127:0] round_in_mux;
    wire [127:0] add_key_in;
    wire [127:0] add_key_out;

    // SubBytes
    aes_sub_bytes u_sub_bytes (
        .state_in(state_reg),
        .state_out(sub_bytes_out)
    );

    // ShiftRows
    aes_shift_rows u_shift_rows (
        .state_in(sub_bytes_out),
        .state_out(shift_rows_out)
    );

    // MixColumns
    aes_mix_columns u_mix_columns (
        .state_in(shift_rows_out),
        .state_out(mix_columns_out)
    );

    // Round Multiplexing (Initial XOR vs Normal Rounds vs Final Round without MixColumns)
    assign add_key_in = sel_initial ? text_in : (sel_final ? shift_rows_out : mix_columns_out);

    // AddRoundKey
    aes_add_round_key u_add_round_key (
        .state_in(add_key_in),
        .key_in(round_key),
        .state_out(add_key_out)
    );

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_reg <= 128'b0;
        end else if (ld_state) begin
            state_reg <= add_key_out;
        end
    end

    assign cipher_text = state_reg;
endmodule

// ----------------------------------------------------------------------------
// Level 1 Submodule: Sequence Controller FSM
// ----------------------------------------------------------------------------
module aes_controller (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,
    output reg  [3:0] round_idx,
    output reg        ld_key,
    output reg        next_key,
    output reg        ld_state,
    output reg        sel_initial,
    output reg        sel_final,
    output reg        done
);
    localparam [2:0]
        ST_IDLE   = 3'd0,
        ST_INIT   = 3'd1,
        ST_ROUND  = 3'd2,
        ST_FINAL  = 3'd3,
        ST_DONE   = 3'd4;

    reg [2:0] state, next_state;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state     <= ST_IDLE;
            round_idx <= 4'd0;
        end else begin
            state <= next_state;
            if (state == ST_INIT)
                round_idx <= 4'd1;
            else if (state == ST_ROUND)
                round_idx <= round_idx + 4'd1;
        end
    end

    always @(*) begin
        next_state  = state;
        ld_key      = 1'b0;
        next_key    = 1'b0;
        ld_state    = 1'b0;
        sel_initial = 1'b0;
        sel_final   = 1'b0;
        done        = 1'b0;

        case (state)
            ST_IDLE: begin
                if (start) begin
                    ld_key     = 1'b1;
                    next_state = ST_INIT;
                end
            end
            ST_INIT: begin
                ld_state    = 1'b1;
                sel_initial = 1'b1;
                next_key    = 1'b1;
                next_state  = ST_ROUND;
            end
            ST_ROUND: begin
                ld_state = 1'b1;
                next_key = 1'b1;
                if (round_idx == 4'd9)
                    next_state = ST_FINAL;
                else
                    next_state = ST_ROUND;
            end
            ST_FINAL: begin
                ld_state  = 1'b1;
                sel_final = 1'b1;
                next_state = ST_DONE;
            end
            ST_DONE: begin
                done = 1'b1;
                if (!start)
                    next_state = ST_IDLE;
            end
            default: next_state = ST_IDLE;
        endcase
    end
endmodule

// ----------------------------------------------------------------------------
// Level 0: Top-Level AES-128 Module
// ----------------------------------------------------------------------------
module aes_cipher_top (
    input  wire         clk,
    input  wire         rst,
    input  wire         ld,
    input  wire [127:0] key,
    input  wire [127:0] text_in,
    output reg  [127:0] text_out,
    output reg          done
);
    // Registered Primary Inputs and Outputs
    reg  [127:0] key_reg;
    reg  [127:0] text_in_reg;
    reg          ld_reg;
    wire [127:0] cipher_text_out;
    wire         ctrl_done;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            key_reg     <= 128'b0;
            text_in_reg <= 128'b0;
            ld_reg      <= 1'b0;
            text_out    <= 128'b0;
            done        <= 1'b0;
        end else begin
            key_reg     <= key;
            text_in_reg <= text_in;
            ld_reg      <= ld;
            text_out    <= cipher_text_out;
            done        <= ctrl_done;
        end
    end

    wire [3:0]   round_idx;
    wire         ld_key;
    wire         next_key;
    wire         ld_state;
    wire         sel_initial;
    wire         sel_final;
    wire [127:0] current_key;

    // Controller
    aes_controller u_controller (
        .clk(clk),
        .rst(rst),
        .start(ld_reg),
        .round_idx(round_idx),
        .ld_key(ld_key),
        .next_key(next_key),
        .ld_state(ld_state),
        .sel_initial(sel_initial),
        .sel_final(sel_final),
        .done(ctrl_done)
    );

    // Key Schedule
    aes_key_schedule u_key_schedule (
        .clk(clk),
        .rst(rst),
        .ld_key(ld_key),
        .next_key(next_key),
        .round_idx(round_idx),
        .key_in(key_reg),
        .current_key(current_key)
    );

    // Datapath
    aes_datapath u_datapath (
        .clk(clk),
        .rst(rst),
        .ld_state(ld_state),
        .sel_initial(sel_initial),
        .sel_final(sel_final),
        .text_in(text_in_reg),
        .round_key(current_key),
        .cipher_text(cipher_text_out)
    );

endmodule
