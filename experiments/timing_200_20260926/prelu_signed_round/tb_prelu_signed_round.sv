`timescale 1ns / 1ps

// Three independent checks: exact current original output in the same clock,
// an eight-stage valid/data model, and signed 64-bit mathematical arithmetic.
module prelu_signed_scalar_checker #(
    parameter integer ID=0,
    parameter integer OUT_W=16,
    parameter integer OUT_SIGNED=1,
    parameter integer APPLY_PRELU=1
)(output reg done=0);
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, in_valid=0;
    reg signed [31:0] accumulator=0, multiplier=0;
    reg signed [15:0] alpha=0;
    wire [OUT_W-1:0] actual, reference;
    wire actual_valid, reference_valid;
    reg [7:0] expected_valid=0;
    reg [OUT_W-1:0] expected_data[0:7];
    reg [OUT_W-1:0] expected_hold=0;
    integer checked=0, accepted=0, bubbles=0, resets_inflight=0;
    integer i, n, aidx, midx;
    reg [31:0] seed=32'h6d2b79f5 ^ ID;
    reg [31:0] rv1, rv2, rv3;

    prelu_requantize #(.OUT_W(OUT_W),.OUT_SIGNED(OUT_SIGNED),
        .APPLY_PRELU(APPLY_PRELU)) dut (
        .clk(clk),.rst(rst),.in_valid(in_valid),
        .accumulator_int32(accumulator),.prelu_q15(alpha),
        .multiplier_q31(multiplier),.out_data(actual),.out_valid(actual_valid));
    prelu_requantize_reference #(.OUT_W(OUT_W),.OUT_SIGNED(OUT_SIGNED),
        .APPLY_PRELU(APPLY_PRELU)) original (
        .clk(clk),.rst(rst),.in_valid(in_valid),
        .accumulator_int32(accumulator),.prelu_q15(alpha),
        .multiplier_q31(multiplier),.out_data(reference),.out_valid(reference_valid));

    // Magnitude arithmetic is intentionally different from the RTL's floor
    // quotient plus guard/sticky increment. Unsigned magnitude handles MIN64.
    function automatic signed [63:0] round_away;
        input signed [63:0] value;
        input integer shift;
        reg [63:0] magnitude, rounded;
        begin
            magnitude=value[63] ? (~$unsigned(value)+64'd1) : $unsigned(value);
            rounded=(magnitude+(64'd1<<(shift-1)))>>shift;
            round_away=value[63] ? -$signed(rounded) : $signed(rounded);
        end
    endfunction

    function automatic [OUT_W-1:0] model;
        input signed [31:0] a;
        input signed [15:0] p;
        input signed [31:0] m;
        reg signed [63:0] a64, p64, m64, value, maximum, minimum;
        begin
            a64=a; p64=p; m64=m;
            value=a64;
            if(APPLY_PRELU!=0 && a64<0) begin
                value=round_away(a64*p64,15);
                if(value>64'sd2147483647) value=64'sd2147483647;
                if(value< -64'sd2147483648) value= -64'sd2147483648;
            end
            value=round_away(value*m64,31);
            maximum=OUT_SIGNED!=0 ? (64'sd1<<(OUT_W-1))-1 : (64'sd1<<OUT_W)-1;
            minimum=OUT_SIGNED!=0 ? -(64'sd1<<(OUT_W-1)) : 0;
            if(value>maximum) value=maximum;
            if(value<minimum) value=minimum;
            model=value[OUT_W-1:0];
        end
    endfunction

    function automatic [31:0] random_word;
        input [31:0] x;
        reg [31:0] y;
        begin
            y=x^(x<<13); y=y^(y>>17); y=y^(y<<5); random_word=y;
        end
    endfunction
    function automatic signed [31:0] edge_value;
        input integer index;
        begin
            case(index)
                0: edge_value=32'sh80000000;
                1: edge_value=32'sh7fffffff;
                2: edge_value=0;
                3: edge_value=1;
                4: edge_value=-1;
                5: edge_value=3;
                6: edge_value=-3;
                7: edge_value=32767;
                8: edge_value=32768;
                9: edge_value=-32768;
                10: edge_value=-32769;
                11: edge_value=255;
                12: edge_value=256;
                13: edge_value=1073741823;
                14: edge_value=1073741824;
                default: edge_value=-1073741824;
            endcase
        end
    endfunction
    function automatic signed [31:0] edge_multiplier;
        input integer index;
        begin
            case(index)
                0: edge_multiplier=32'sh80000000;
                1: edge_multiplier=32'sh7fffffff;
                2: edge_multiplier=0;
                3: edge_multiplier=1;
                4: edge_multiplier=-1;
                5: edge_multiplier=1073741823;
                6: edge_multiplier=1073741824;
                7: edge_multiplier=1073741825;
                8: edge_multiplier=-1073741823;
                9: edge_multiplier=-1073741824;
                default: edge_multiplier=-1073741825;
            endcase
        end
    endfunction
    function automatic signed [15:0] edge_alpha;
        input integer index;
        begin
            case(index%8)
                0: edge_alpha=0;
                1: edge_alpha=1;
                2: edge_alpha=-1;
                3: edge_alpha=16384;
                4: edge_alpha=-16384;
                5: edge_alpha=32767;
                6: edge_alpha=-32768;
                default: edge_alpha=8192;
            endcase
        end
    endfunction

    task drive;
        input reset_value, valid_value;
        input signed [31:0] a;
        input signed [15:0] p;
        input signed [31:0] m;
        begin
            @(negedge clk);
            rst=reset_value; in_valid=valid_value;
            accumulator=a; alpha=p; multiplier=m;
        end
    endtask

    always @(posedge clk) begin
        if(rst) begin
            if(expected_valid!=0) resets_inflight=resets_inflight+1;
            expected_valid=0; expected_hold=0;
            for(i=0;i<8;i=i+1) expected_data[i]=0;
        end else begin
            for(i=7;i>0;i=i-1) begin
                expected_valid[i]=expected_valid[i-1];
                expected_data[i]=expected_data[i-1];
            end
            expected_valid[0]=in_valid;
            expected_data[0]=model(accumulator,alpha,multiplier);
            if(in_valid) accepted=accepted+1;
            if(expected_valid[7]) begin
                expected_hold=expected_data[7]; checked=checked+1;
            end else bubbles=bubbles+1;
        end
        #1;
        if(actual_valid!==expected_valid[7])
            $fatal(1,"scalar valid latency id=%0d expected=%b actual=%b",ID,expected_valid[7],actual_valid);
        if(actual!==expected_hold)
            $fatal(1,"scalar mathematics/hold id=%0d expected=%h actual=%h",ID,expected_hold,actual);
        if(actual_valid!==reference_valid || actual!==reference)
            $fatal(1,"scalar same-cycle equivalence id=%0d ref=%h/%b actual=%h/%b",ID,reference,reference_valid,actual,actual_valid);
    end

    initial begin
        drive(1,0,0,0,0); drive(1,0,0,0,0);
        // Half-LSB ties and neighbours of signed/unsigned saturation limits.
        for(aidx=0;aidx<16;aidx=aidx+1)
            for(midx=0;midx<11;midx=midx+1)
                for(n=0;n<8;n=n+1)
                    drive(0,1,edge_value(aidx),edge_alpha(n),edge_multiplier(midx));
        for(n=0;n<20;n=n+1) drive(0,0,0,0,0);
        for(n=0;n<2000;n=n+1) begin
            seed=random_word(seed); rv1=seed;
            seed=random_word(seed); rv2=seed;
            seed=random_word(seed); rv3=seed;
            drive(0,(rv1[2:0]!=0),$signed(rv1),$signed(rv2[15:0]),$signed(rv3));
            if(n==173 || n==927 || n==1551) begin
                drive(0,1,32'sh80000000,16'sh8000,32'sh80000000);
                drive(0,1,-3,16384,1073741824);
                drive(1,0,0,0,0);
                drive(0,0,0,0,0);
            end
        end
        for(n=0;n<16;n=n+1) drive(0,0,32'sh7fffffff,32767,32'sh7fffffff);
        #2;
        if(checked<2500 || bubbles<30 || resets_inflight!=3 || expected_valid!=0)
            $fatal(1,"scalar coverage id=%0d checked=%0d bubbles=%0d resets=%0d",ID,checked,bubbles,resets_inflight);
        $display("PRELU_SIGNED_SCALAR_CONFIG_PASS id=%0d checked=%0d accepted=%0d",ID,checked,accepted);
        done=1;
    end
endmodule

// Directly probe the actual post-register combinational expression for the
// full INT64 domain. Some values (e.g. MIN64) cannot be a signed32* signed32
// product, so this complements rather than replaces end-to-end tests above.
module requant_round64_probe(output reg done=0);
    reg clk=0;
    always #5 clk=~clk;
    reg [63:0] injected=0;
    reg [31:0] seed=32'h7e572001;
    reg signed [63:0] value, expected, saturated;
    reg [63:0] magnitude, rounded;
    integer n, sign_index, quotient_index, fraction_index;
    integer checked=0;
    reg signed [63:0] quotient, remainder;
    prelu_requantize #(.OUT_W(31),.OUT_SIGNED(1),.APPLY_PRELU(0)) dut (
        .clk(clk),.rst(1'b0),.in_valid(1'b0),
        .accumulator_int32(32'sd0),.prelu_q15(16'sd0),
        .multiplier_q31(32'sd0),.out_data(),.out_valid());

    task check_value;
        input signed [63:0] v;
        begin
            injected=v;
            // Force RHS is a module static variable, portable to XSim.
            force dut.requant_product_full_s6=injected;
            #1;
            magnitude=v[63] ? (~$unsigned(v)+64'd1) : $unsigned(v);
            rounded=(magnitude+64'd1073741824)>>31;
            expected=v[63] ? -$signed(rounded) : $signed(rounded);
            if($signed(dut.requant_rounded_s6)!==expected)
                $fatal(1,"round64 mismatch input=%h expected=%0d actual=%0d",v,expected,$signed(dut.requant_rounded_s6));
            saturated=expected;
            if(saturated>64'sd1073741823) saturated=64'sd1073741823;
            if(saturated< -64'sd1073741824) saturated= -64'sd1073741824;
            if(dut.saturate_q31_output(dut.requant_rounded_s6)!==saturated[30:0])
                $fatal(1,"round64 signed31 saturation input=%h expected=%h",v,saturated[30:0]);
            checked=checked+1;
            release dut.requant_product_full_s6;
        end
    endtask

    initial begin
        check_value(64'sh8000000000000000);
        check_value(64'sh8000000000000001);
        check_value(64'sh7fffffffffffffff);
        check_value(64'sh7fffffff00000000);
        for(sign_index=0;sign_index<2;sign_index=sign_index+1)
            for(quotient_index=0;quotient_index<9;quotient_index=quotient_index+1)
                for(fraction_index=0;fraction_index<5;fraction_index=fraction_index+1) begin
                    case(quotient_index)
                        0: quotient=0;
                        1: quotient=1;
                        2: quotient=255;
                        3: quotient=32767;
                        4: quotient=32768;
                        5: quotient=64'sd1073741823;
                        6: quotient=64'sd1073741824;
                        7: quotient=64'sd2147483647;
                        default: quotient=64'sd4294967295;
                    endcase
                    case(fraction_index)
                        0: remainder=0;
                        1: remainder=1073741823;
                        2: remainder=1073741824;
                        3: remainder=1073741825;
                        default: remainder=2147483647;
                    endcase
                    value=(quotient<<31)+remainder;
                    if(sign_index) value=-value;
                    check_value(value);
                end
        for(n=0;n<1000;n=n+1) begin
            seed=seed^(seed<<13);seed=seed^(seed>>17);seed=seed^(seed<<5);
            value[63:32]=seed;
            seed=seed^(seed<<13);seed=seed^(seed>>17);seed=seed^(seed<<5);
            value[31:0]=seed;
            check_value(value);
        end
        $display("REQUANT_ROUND64_PROBE_PASS checked=%0d",checked);
        done=1;
    end
endmodule

// Probe the actual signed48 post-register expression. MIN48/MAX48 are useful
// width tests even though they exceed the reachable signed32*signed16 product
// range. This is a finite boundary/random test, not an exhaustive-domain proof.
module prelu_signed_round48_probe(output reg done=0);
    reg clk=0;
    always #5 clk=~clk;
    reg [47:0] injected=0;
    reg [31:0] seed=32'h63491f27;
    reg signed [47:0] random_value;
    reg signed [63:0] quotient, remainder, vector_value;
    reg signed [63:0] accumulator_wide, alpha_wide, product_wide;
    integer sign_index, quotient_index, fraction_index, aidx, pidx, n;
    integer checked=0, negative_ties=0, positive_ties=0;
    prelu_requantize #(.OUT_W(31),.OUT_SIGNED(1),.APPLY_PRELU(1)) dut (
        .clk(clk),.rst(1'b0),.in_valid(1'b0),
        .accumulator_int32(32'sd0),.prelu_q15(16'sd0),
        .multiplier_q31(32'sd0),.out_data(),.out_valid());

    function automatic signed [31:0] accumulator_edge(input integer index);
        case(index)
            0: accumulator_edge=32'sh80000000;
            1: accumulator_edge=32'sh7fffffff;
            2: accumulator_edge=32'sh80000001;
            3: accumulator_edge=-32'sd32769;
            4: accumulator_edge=-32'sd1;
            5: accumulator_edge=32'sd0;
            6: accumulator_edge=32'sd1;
            default: accumulator_edge=32'sd32769;
        endcase
    endfunction
    function automatic signed [15:0] alpha_edge(input integer index);
        case(index)
            0: alpha_edge=16'sh8000;
            1: alpha_edge=16'sh7fff;
            2: alpha_edge=-16'sd16384;
            3: alpha_edge=16'sd16384;
            4: alpha_edge=-16'sd1;
            5: alpha_edge=16'sd0;
            6: alpha_edge=16'sd1;
            default: alpha_edge=16'sd8192;
        endcase
    endfunction

    task check_value(input signed [47:0] value);
        reg signed [63:0] extended, expected;
        reg [63:0] magnitude, rounded;
        begin
            injected=value;
            // A static module variable on force RHS is portable to XSim.
            force dut.prelu_product_full_s2=injected;
            #1;
            extended=value;
            magnitude=(extended<0) ? $unsigned(-extended) : $unsigned(extended);
            rounded=(magnitude+64'd16384)/64'd32768;
            expected=(extended<0) ? -$signed(rounded) : $signed(rounded);
            if($signed(dut.prelu_rounded_s2)!==expected)
                $fatal(1,"prelu48 rounding input=%h expected=%0d actual=%0d",
                       value,expected,$signed(dut.prelu_rounded_s2));
            if(magnitude%64'd32768==64'd16384) begin
                if(extended<0) negative_ties=negative_ties+1;
                else positive_ties=positive_ties+1;
            end
            checked=checked+1;
            release dut.prelu_product_full_s2;
        end
    endtask

    initial begin
        if($bits(dut.prelu_product_full_s2)!=48 || $bits(dut.prelu_rounded_s2)!=34)
            $fatal(1,"prelu48 probe requires signed48 product and signed34 rounded wire");
        check_value(48'sh800000000000);
        check_value(48'sh800000000001);
        check_value(48'sh7fffffffffff);
        check_value(48'sh7ffffffffffe);
        check_value(48'sd0);
        check_value(48'sd1);
        check_value(-48'sd1);
        check_value(48'sd16383);
        check_value(-48'sd16383);
        check_value(48'sd16384);
        check_value(-48'sd16384);
        check_value(48'sd16385);
        check_value(-48'sd16385);
        for(sign_index=0;sign_index<2;sign_index=sign_index+1)
            for(quotient_index=0;quotient_index<8;quotient_index=quotient_index+1)
                for(fraction_index=0;fraction_index<7;fraction_index=fraction_index+1) begin
                    case(quotient_index)
                        0: quotient=0;
                        1: quotient=1;
                        2: quotient=255;
                        3: quotient=32767;
                        4: quotient=32768;
                        5: quotient=64'sd2147483647;
                        6: quotient=64'sd2147483648;
                        default: quotient=64'sd4294967295;
                    endcase
                    case(fraction_index)
                        0: remainder=0;
                        1: remainder=1;
                        2: remainder=16383;
                        3: remainder=16384;
                        4: remainder=16385;
                        5: remainder=32766;
                        default: remainder=32767;
                    endcase
                    vector_value=quotient*64'sd32768+remainder;
                    if(sign_index) vector_value=-vector_value;
                    check_value(vector_value[47:0]);
                end
        // Actual full-range signed32*signed16 boundaries, before any rounding.
        for(aidx=0;aidx<8;aidx=aidx+1)
            for(pidx=0;pidx<8;pidx=pidx+1) begin
                accumulator_wide=accumulator_edge(aidx);
                alpha_wide=alpha_edge(pidx);
                product_wide=accumulator_wide*alpha_wide;
                check_value(product_wide[47:0]);
            end
        for(n=0;n<2000;n=n+1) begin
            seed=seed^(seed<<13);seed=seed^(seed>>17);seed=seed^(seed<<5);
            random_value[47:32]=seed[15:0];
            seed=seed^(seed<<13);seed=seed^(seed>>17);seed=seed^(seed<<5);
            random_value[31:0]=seed;
            check_value(random_value);
        end
        if(checked!=2189 || negative_ties==0 || positive_ties==0)
            $fatal(1,"prelu48 probe coverage checked=%0d negative_ties=%0d positive_ties=%0d",
                   checked,negative_ties,positive_ties);
        $display("PRELU_SIGNED_ROUND48_PROBE_PASS checked=%0d negative_ties=%0d positive_ties=%0d",
                 checked,negative_ties,positive_ties);
        done=1;
    end
endmodule

module tb_prelu_signed_round;
    wire [7:0] done;
    prelu_signed_scalar_checker #(.ID(0),.OUT_W(16),.OUT_SIGNED(1),.APPLY_PRELU(1)) c0(done[0]);
    prelu_signed_scalar_checker #(.ID(1),.OUT_W(16),.OUT_SIGNED(1),.APPLY_PRELU(0)) c1(done[1]);
    prelu_signed_scalar_checker #(.ID(2),.OUT_W(8),.OUT_SIGNED(0),.APPLY_PRELU(0)) c2(done[2]);
    prelu_signed_scalar_checker #(.ID(3),.OUT_W(31),.OUT_SIGNED(1),.APPLY_PRELU(1)) c3(done[3]);
    prelu_signed_scalar_checker #(.ID(4),.OUT_W(31),.OUT_SIGNED(0),.APPLY_PRELU(0)) c4(done[4]);
    prelu_signed_scalar_checker #(.ID(5),.OUT_W(1),.OUT_SIGNED(1),.APPLY_PRELU(1)) c5(done[5]);
    requant_round64_probe c6(done[6]);
    prelu_signed_round48_probe c7(done[7]);
    initial begin
        wait(&done);
        $display("PRELU_SIGNED_SCALAR_ALL_CONFIGS_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"scalar/probe timeout");
    end
endmodule
