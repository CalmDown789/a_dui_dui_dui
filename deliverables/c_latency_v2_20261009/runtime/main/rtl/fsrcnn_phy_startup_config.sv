`timescale 1ns/1ps
`default_nettype none
// One-shot RTL8211F startup sequence. This reset MUST be configuration/GSR
// initialization only; never connect the user's video S0 reset to it.
// The parent supplies an uninterrupted 50 MHz clock and boot_ready after
// >=100 ms of PHY boot time. No BMCR access and no PHY hardware-reset output.
module fsrcnn_phy_startup_config #(
    parameter integer MDIO_HALF_CYCLES = 250
)(
    input  wire clk_50,
    input  wire cfg_rst_n,
    input  wire boot_ready,
    output wire mdc,
    inout  wire mdio,
    output reg  cfg_done,
    output reg  cfg_ok,
    output reg  cfg_failed,
    output reg  [7:0] failure_code,
    output reg  [7:0] restore_failure_code,
    output reg  [7:0] diag_valid,
    output reg  identity_ok,
    output reg  page_saved,
    output reg  tx_write_attempted,
    output reg  restore_verified,
    output reg  [1:0] restore_attempts,
    output reg  [15:0] id2,
    output reg  [15:0] id3,
    output reg  [15:0] original_page,
    output reg  [15:0] restored_page,
    output reg  [15:0] rx_old,
    output reg  [15:0] rx_actual,
    output reg  [15:0] tx_old,
    output reg  [15:0] tx_actual,
    output wire [7:0] diag_state
);
    // Every command is unicast address 5, not broadcast address 0.
    localparam [4:0] PHY_ADDR = 5'd5;
    localparam [15:0] RGMII_PAGE = 16'h0d08;
    localparam [7:0] S_BOOT=0, S_ID2=1, S_ID3=2, S_PAGE_SAVE=3,
        S_PAGE_SELECT=4, S_PAGE_CHECK=5, S_RX_OLD=6, S_TX_OLD=7,
        S_TX_WRITE=8, S_TX_CHECK=9, S_RX_CHECK=10,
        S_PAGE_RESTORE=11, S_RESTORE_CHECK=12, S_FINAL=13;
    reg [7:0] state_q;
    reg waiting_q;
    reg [15:0] tx_target_q;
    wire cmd_ready, done, no_read_ack;
    wire [15:0] read_data;
    reg cmd_read;
    reg [4:0] cmd_reg;
    reg [15:0] cmd_data;
    wire cmd_valid = (state_q >= S_ID2 && state_q <= S_RESTORE_CHECK)
                     && !waiting_q;
    assign diag_state = state_q;

    // Command fields remain stable from acceptance until done.
    always @* begin
        cmd_read=1'b1; cmd_reg=5'd2; cmd_data=16'h0000;
        case (state_q)
            S_ID2:          cmd_reg=5'd2;
            S_ID3:          cmd_reg=5'd3;
            S_PAGE_SAVE:    cmd_reg=5'd31;
            S_PAGE_SELECT:  begin cmd_read=0; cmd_reg=31; cmd_data=RGMII_PAGE; end
            S_PAGE_CHECK:   cmd_reg=5'd31;
            S_RX_OLD:       cmd_reg=5'h15;
            S_TX_OLD:       cmd_reg=5'h11;
            S_TX_WRITE:     begin cmd_read=0; cmd_reg=5'h11; cmd_data=tx_target_q; end
            S_TX_CHECK:     cmd_reg=5'h11;
            S_RX_CHECK:     cmd_reg=5'h15;
            S_PAGE_RESTORE: begin cmd_read=0; cmd_reg=31; cmd_data=original_page; end
            S_RESTORE_CHECK:cmd_reg=5'd31;
            default: ;
        endcase
    end

    // This engine is a module-name-only copy of the independently verified C
    // source. Clause22 write has no ACK: writes are proved by following reads.
    fsrcnn_phy_mdio_c22_transaction #(.HALF_CYCLES(MDIO_HALF_CYCLES)) u_mdio (
        .clk(clk_50), .rst_n(cfg_rst_n),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_read(cmd_read), .cmd_phy(PHY_ADDR), .cmd_reg(cmd_reg), .cmd_data(cmd_data),
        .done(done), .read_data(read_data), .no_read_ack(no_read_ack),
        .early_trace(), .late_trace(), .mdc(mdc), .mdio(mdio)
    );

    // Fail immediately closes permission. Page recovery is not reset/aborted;
    // cfg_done rises only when recovery has completed or exhausted two tries.
    task automatic reject(input [7:0] code);
    begin
        cfg_failed <= 1'b1;
        cfg_ok <= 1'b0;
        if (failure_code == 0) failure_code <= code;
        if (identity_ok && page_saved) state_q <= S_PAGE_RESTORE;
        else begin cfg_done <= 1'b1; state_q <= S_FINAL; end
    end
    endtask

    always @(posedge clk_50 or negedge cfg_rst_n) begin
        if (!cfg_rst_n) begin
            state_q<=S_BOOT; waiting_q<=0; tx_target_q<=0;
            cfg_done<=0; cfg_ok<=0; cfg_failed<=0;
            failure_code<=0; restore_failure_code<=0; diag_valid<=0;
            identity_ok<=0; page_saved<=0; tx_write_attempted<=0;
            restore_verified<=0; restore_attempts<=0;
            id2<=0; id3<=0; original_page<=0; restored_page<=0;
            rx_old<=0; rx_actual<=0; tx_old<=0; tx_actual<=0;
        end else begin
            if (state_q==S_BOOT && boot_ready) state_q<=S_ID2;
            if (cmd_valid && cmd_ready) begin
                waiting_q<=1;
                if (state_q==S_TX_WRITE) tx_write_attempted<=1;
                if (state_q==S_PAGE_RESTORE) restore_attempts<=restore_attempts+1'b1;
            end
            if (waiting_q && done) begin
                waiting_q<=0;
                case (state_q)
                    S_ID2: begin
                        id2<=read_data;
                        if (no_read_ack) reject(8'h01);
                        else begin diag_valid[0]<=1; state_q<=S_ID3; end
                    end
                    S_ID3: begin
                        id3<=read_data;
                        if (no_read_ack) reject(8'h02);
                        else begin
                            diag_valid[1]<=1;
                            if (id2!==16'h001c || read_data!==16'hc916) reject(8'h03);
                            else begin identity_ok<=1; state_q<=S_PAGE_SAVE; end
                        end
                    end
                    S_PAGE_SAVE: begin
                        original_page<=read_data;
                        if (no_read_ack) reject(8'h04);
                        else begin page_saved<=1; diag_valid[2]<=1; state_q<=S_PAGE_SELECT; end
                    end
                    S_PAGE_SELECT: state_q<=S_PAGE_CHECK;
                    S_PAGE_CHECK: begin
                        if (no_read_ack) reject(8'h05);
                        else if (read_data!==RGMII_PAGE) reject(8'h06);
                        else state_q<=S_RX_OLD;
                    end
                    S_RX_OLD: begin
                        rx_old<=read_data;
                        if (no_read_ack) reject(8'h07);
                        else begin
                            diag_valid[3]<=1;
                            if (read_data[3]!==1'b1) reject(8'h08);
                            else state_q<=S_TX_OLD;
                        end
                    end
                    S_TX_OLD: begin
                        tx_old<=read_data;
                        if (no_read_ack) reject(8'h09);
                        else begin
                            diag_valid[4]<=1;
                            tx_target_q<=read_data & 16'hfeff;
                            if (read_data[8]) state_q<=S_TX_WRITE;
                            else state_q<=S_TX_CHECK; // idempotent: no redundant write
                        end
                    end
                    S_TX_WRITE: state_q<=S_TX_CHECK;
                    S_TX_CHECK: begin
                        tx_actual<=read_data;
                        if (no_read_ack) reject(8'h0a);
                        else begin
                            diag_valid[5]<=1;
                            if (read_data!==tx_target_q) reject(8'h0b); // compare ALL 16 bits
                            else state_q<=S_RX_CHECK;
                        end
                    end
                    S_RX_CHECK: begin
                        rx_actual<=read_data;
                        if (no_read_ack) reject(8'h0c);
                        else begin
                            diag_valid[6]<=1;
                            if (read_data[3]!==1'b1) reject(8'h0d);
                            else state_q<=S_PAGE_RESTORE;
                        end
                    end
                    S_PAGE_RESTORE: state_q<=S_RESTORE_CHECK;
                    S_RESTORE_CHECK: begin
                        restored_page<=read_data;
                        diag_valid[7]<=!no_read_ack; // validity of the LATEST restore read
                        if (no_read_ack || read_data!==original_page) begin
                            cfg_failed<=1; cfg_ok<=0;
                            if (restore_failure_code==0)
                                restore_failure_code<=no_read_ack ? 8'h01 : 8'h02;
                            if (failure_code==0)
                                failure_code<=no_read_ack ? 8'h0e : 8'h0f;
                            if (restore_attempts<2) state_q<=S_PAGE_RESTORE;
                            else begin cfg_done<=1; state_q<=S_FINAL; end
                        end else begin
                            restore_verified<=1;
                            cfg_done<=1;
                            // All success checks precede here; a recovered fault
                            // remains a fault and cannot accidentally enable video.
                            cfg_ok<=!cfg_failed;
                            state_q<=S_FINAL;
                        end
                    end
                    default: begin cfg_failed<=1; cfg_ok<=0; cfg_done<=1;
                        failure_code<=8'hff; state_q<=S_FINAL; end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
