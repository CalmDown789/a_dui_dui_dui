`timescale 1ns / 1ps

// 成员B工作 / Team member B: A input bytes in C's exact synchronous ROM.
module member_b_c_input_rom_tb;
    reg clk=0,en=0;
    reg [18:0] addr=0;
    wire [7:0] dout;
    always #5 clk=~clk;
    input_rom #(.ADDR_W(19),.DATA_W(8),.MEM_DEPTH(524288),
        .INIT_MODE(0),.INIT_EN(1),
        .INIT_FILE("member_a_input_960x540_y_u8.mem")) dut (
        .clk(clk),.en(en),.addr(addr),.dout(dout)
    );
    task automatic check(input [18:0] address,input [7:0] expected);
        begin
            @(negedge clk);en=1;addr=address;
            @(negedge clk);
            if(dout!==expected)
                $fatal(1,"C ROM addr=%0d got=%h expected=%h",address,dout,expected);
        end
    endtask
    initial begin
        check(19'd0,8'h56);
        check(19'd959,8'h5a);
        check(19'd518399,8'h2b);
        check(19'd518400,8'h00);
        check(19'd524287,8'h00);
        $display("ACX750_MEMBER_B_C_INPUT_ROM_PASS pixels=518400 padding=5888");
        $finish;
    end
endmodule
