`timescale 1ns/1ps
// 成员B工作：验证实验 bank16 ROM 与 A 冻结的 524288 字节原始 ROM 完全一致。
module tb_input_rom_real_member_b;
    reg clk = 0;
    always #5 clk = ~clk;
    reg en = 0;
    reg [18:0] addr = 0;
    wire [7:0] dout;
    reg [7:0] golden [0:524287];
    reg [7:0] held;
    integer n = 0;
    integer i;

    input_rom #(.ADDR_W(19), .DATA_W(8), .MEM_DEPTH(524288),
                .INIT_MODE(0), .INIT_EN(1)) dut (
        .clk(clk), .en(en), .addr(addr), .dout(dout)
    );

    task automatic read_check(input integer a);
        begin
            @(negedge clk);
            en = 1;
            addr = a[18:0];
            @(posedge clk); #1;
            if (dout !== golden[a])
                $fatal(1, "ROM mismatch addr=%0d got=%02x expected=%02x", a, dout, golden[a]);
            n = n + 1;
            held = dout;
            @(negedge clk);
            en = 0;
            addr = (a + 32768) & 19'h7ffff;
            @(posedge clk); #1;
            if (dout !== held)
                $fatal(1, "ROM hold violation after addr=%0d", a);
        end
    endtask

    initial begin
        $readmemh("input_rom_2p19_u8.mem", golden);
        read_check(0);
        read_check(1);
        read_check(32767);
        read_check(32768);
        read_check(65535);
        read_check(65536);
        read_check(518399);
        read_check(518400);
        read_check(524287);
        for (i = 0; i < 128; i = i + 1)
            read_check($urandom_range(0, 524287));
        $display("MEMBER_B_REAL_BANKED_ROM_PASS reads=%0d banks=16 depth=32768", n);
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "ROM test timeout");
    end
endmodule
