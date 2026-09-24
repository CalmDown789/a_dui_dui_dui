`timescale 1ns / 1ps

module sync_parameter_rom_tb;
    reg clk;
    reg enable;
    reg [1:0] address;
    wire [31:0] data;
    integer errors;

    sync_parameter_rom #(
        .DATA_W(32), .DEPTH(4), .MEM_FILE("parameter_rom_test.mem")
    ) dut (
        .clk(clk), .enable(enable), .address(address), .data(data)
    );

    initial begin clk=0; forever #5 clk=~clk; end

    task read_and_check;
        input [1:0] requested_address;
        input [31:0] expected;
        begin
            @(negedge clk); address=requested_address; enable=1;
            @(posedge clk); #1;
            if(data!==expected) begin
                $display("PARAMETER_ROM_MISMATCH address=%0d got=%h expected=%h",
                         requested_address, data, expected);
                errors=errors+1;
            end
        end
    endtask

    initial begin
        enable=0; address=0; errors=0;
        read_and_check(0,32'h00000011);
        read_and_check(1,32'hFFFFFFFE);
        read_and_check(2,32'h7FFFFFFF);
        read_and_check(3,32'h80000000);
        @(negedge clk); enable=0; address=0;
        @(posedge clk); #1;
        if(data!==32'h80000000) begin
            $display("PARAMETER_ROM_HOLD_MISMATCH got=%h",data);
            errors=errors+1;
        end
        if(errors==0)
            $display("ACX750_SYNC_PARAMETER_ROM_TEST_PASS");
        else
            $display("ACX750_SYNC_PARAMETER_ROM_TEST_FAIL errors=%0d",errors);
        $finish;
    end
endmodule
