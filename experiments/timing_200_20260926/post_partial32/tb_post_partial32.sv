`timescale 1ns / 1ps

// Three independent checks: exact original output delayed by one clock,
// a nine-stage valid/data model, and signed 64-bit mathematical arithmetic.
module post_partial32_scalar_checker #(
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
    reg [OUT_W-1:0] reference_delayed=0;
    reg reference_valid_delayed=0;
    reg [8:0] expected_valid=0;
    reg [OUT_W-1:0] expected_data[0:8];
    reg [OUT_W-1:0] expected_hold=0;
    // Independent full multiplication checks the recombined register before
    // rounding/saturation can hide a signed partial-product error.
    reg [1:0] expected_product_valid=0;
    reg signed [47:0] expected_product[0:1];
    reg signed [47:0] expected_product_hold=0;
    integer product_checked=0;
    integer checked=0, accepted=0, bubbles=0, resets_inflight=0;
    integer split_lo_ffff=0, split_negative_hi=0, split_negative_alpha=0;
    integer split_mixed_sign=0;
    // Sample actual stage-4 operands before NBA, then compare the complete
    // stage-6 product after the second edge. This oracle uses one signed64
    // multiplication and shares no partial-product/CSA equations with RTL.
    reg [1:0] expected_q31_valid=0;
    reg signed [63:0] expected_q31_product[0:1];
    reg signed [63:0] expected_q31_hold=0;
    integer q31_checked=0, q31_hold_cycles=0, q31_resets_inflight=0;
    integer q31_a_min=0, q31_a_max=0, q31_b_min=0, q31_b_max=0;
    integer q31_both_low_high=0;
    reg [3:0] q31_sign_pairs=0;
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

    function automatic signed [47:0] full_product_model;
        input signed [31:0] a;
        input signed [15:0] p;
        reg signed [63:0] wide_a,wide_p,product_value;
        begin
            wide_a=a; wide_p=p;
            product_value=wide_a*wide_p;
            full_product_model=product_value[47:0];
        end
    endfunction

    function automatic signed [63:0] q31_product_model;
        input signed [31:0] a, b;
        reg signed [63:0] wide_a, wide_b;
        begin
            wide_a=a; wide_b=b;
            q31_product_model=wide_a*wide_b;
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
                15: edge_value=-1073741824;
                // Explicit mixed signed-high / unsigned-low boundaries.
                // lo[15]=1 must remain positive after zero-extending to 17 bits.
                16: edge_value=32'sh8000ffff;
                17: edge_value=32'shffff0001;
                18: edge_value=32'shfffeffff;
                19: edge_value=32'sh7fff8000;
                20: edge_value=32'sh0000ffff;
                21: edge_value=32'sh80008000;
                22: edge_value=32'sh80000001;
                default: edge_value=32'shffff8001;
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
                10: edge_multiplier=-1073741825;
                11: edge_multiplier=32'sh8000ffff;
                12: edge_multiplier=32'shffff0001;
                13: edge_multiplier=32'shfffeffff;
                14: edge_multiplier=32'sh7fff8000;
                15: edge_multiplier=32'sh0000ffff;
                16: edge_multiplier=32'sh80008000;
                17: edge_multiplier=32'sh80000001;
                default: edge_multiplier=32'shffff8001;
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
            for(i=0;i<9;i=i+1) expected_data[i]=0;
            expected_product_valid=0; expected_product_hold=0;
            expected_product[0]=0; expected_product[1]=0;
            if(expected_q31_valid!=0) q31_resets_inflight=q31_resets_inflight+1;
            expected_q31_valid=0; expected_q31_hold=0;
            expected_q31_product[0]=0; expected_q31_product[1]=0;
            reference_delayed<=0; reference_valid_delayed<=0;
        end else begin
            reference_delayed<=reference;
            reference_valid_delayed<=reference_valid;
            for(i=8;i>0;i=i-1) begin
                expected_valid[i]=expected_valid[i-1];
                expected_data[i]=expected_data[i-1];
            end
            expected_valid[0]=in_valid;
            expected_data[0]=model(accumulator,alpha,multiplier);
            expected_product_valid[1]=expected_product_valid[0];
            expected_product_valid[0]=in_valid;
            expected_product[1]=expected_product[0];
            expected_product[0]=full_product_model(accumulator,alpha);
            if(expected_product_valid[1]) begin
                expected_product_hold=expected_product[1];
                product_checked=product_checked+1;
            end
            expected_q31_valid[1]=expected_q31_valid[0];
            expected_q31_valid[0]=dut.valid_s4;
            expected_q31_product[1]=expected_q31_product[0];
            expected_q31_product[0]=q31_product_model(dut.prelu_value_s4,dut.multiplier_s4);
            if(expected_q31_valid[1]) begin
                expected_q31_hold=expected_q31_product[1];
                q31_checked=q31_checked+1;
            end else q31_hold_cycles=q31_hold_cycles+1;
            if(dut.valid_s4) begin
                q31_sign_pairs[{dut.prelu_value_s4[31],dut.multiplier_s4[31]}]=1'b1;
                if(dut.prelu_value_s4==32'sh80000000) q31_a_min=q31_a_min+1;
                if(dut.prelu_value_s4==32'sh7fffffff) q31_a_max=q31_a_max+1;
                if(dut.multiplier_s4==32'sh80000000) q31_b_min=q31_b_min+1;
                if(dut.multiplier_s4==32'sh7fffffff) q31_b_max=q31_b_max+1;
                if(dut.prelu_value_s4[15] && dut.multiplier_s4[15])
                    q31_both_low_high=q31_both_low_high+1;
            end
            if(in_valid) begin
                accepted=accepted+1;
                if(accumulator[15:0]==16'hffff) split_lo_ffff=split_lo_ffff+1;
                if(accumulator[31]) split_negative_hi=split_negative_hi+1;
                if(alpha[15]) split_negative_alpha=split_negative_alpha+1;
                if(accumulator[31]&&accumulator[15]&&alpha[15])
                    split_mixed_sign=split_mixed_sign+1;
            end
            if(expected_valid[8]) begin
                expected_hold=expected_data[8]; checked=checked+1;
            end else bubbles=bubbles+1;
        end
        #1;
        if(dut.prelu_product_s1b!==expected_product_hold)
            $fatal(1,"full48 product/latency/hold id=%0d expected=%h actual=%h",ID,expected_product_hold,dut.prelu_product_s1b);
        if(dut.requant_product_full_s6!==expected_q31_hold || dut.valid_full_s6!==expected_q31_valid[1])
            $fatal(1,"full64 product/latency/hold id=%0d expected=%h/%b actual=%h/%b",ID,expected_q31_hold,expected_q31_valid[1],dut.requant_product_full_s6,dut.valid_full_s6);
        if(actual_valid!==expected_valid[8])
            $fatal(1,"scalar valid latency id=%0d expected=%b actual=%b",ID,expected_valid[8],actual_valid);
        if(actual!==expected_hold)
            $fatal(1,"scalar mathematics/hold id=%0d expected=%h actual=%h",ID,expected_hold,actual);
        if(actual_valid!==reference_valid_delayed || actual!==reference_delayed)
            $fatal(1,"scalar original+1 equivalence id=%0d ref=%h/%b actual=%h/%b",ID,reference_delayed,reference_valid_delayed,actual,actual_valid);
    end

    initial begin
        drive(1,0,0,0,0); drive(1,0,0,0,0);
        // Half-LSB ties and neighbours of signed/unsigned saturation limits.
        for(aidx=0;aidx<24;aidx=aidx+1)
            for(midx=0;midx<19;midx=midx+1)
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
                // Fill beyond stage 4 so each reset exercises the new
                // two-edge product checker as well as end-to-end flushing.
                repeat(8) drive(0,1,-3,16384,1073741824);
                drive(1,0,0,0,0);
                drive(0,0,0,0,0);
            end
        end
        for(n=0;n<16;n=n+1) drive(0,0,32'sh7fffffff,32767,32'sh7fffffff);
        #2;
        if(checked<3200 || product_checked<3200 || bubbles<30 || resets_inflight!=3 ||
           expected_valid!=0 || expected_product_valid!=0 || expected_q31_valid!=0 ||
           split_lo_ffff==0 || split_negative_hi==0 || split_negative_alpha==0 || split_mixed_sign==0)
            $fatal(1,"scalar coverage id=%0d checked=%0d bubbles=%0d resets=%0d",ID,checked,bubbles,resets_inflight);
        // APPLY_PRELU=1 cannot reach MIN32 after Q1.15 saturation for this
        // legal alpha range; the bypass configurations cover MIN32 products.
        if(q31_checked<5000 || q31_hold_cycles<30 || q31_resets_inflight!=3 ||
           q31_sign_pairs!=4'b1111 || q31_both_low_high==0 || q31_a_max==0 ||
           q31_b_min==0 || q31_b_max==0 || (APPLY_PRELU==0 && q31_a_min==0))
            $fatal(1,"full64 coverage id=%0d checked=%0d hold=%0d resets=%0d signs=%b",ID,q31_checked,q31_hold_cycles,q31_resets_inflight,q31_sign_pairs);
        $display("POST_PARTIAL32_SCALAR_CONFIG_PASS id=%0d checked=%0d accepted=%0d full48_checked=%0d lo_ffff=%0d negative_hi=%0d negative_alpha=%0d mixed_sign=%0d full64_checked=%0d full64_hold=%0d full64_resets=%0d signs=%0d a_min=%0d a_max=%0d b_min=%0d b_max=%0d both_low_high=%0d",
                 ID,checked,accepted,product_checked,split_lo_ffff,split_negative_hi,split_negative_alpha,split_mixed_sign,
                 q31_checked,q31_hold_cycles,q31_resets_inflight,q31_sign_pairs,q31_a_min,q31_a_max,q31_b_min,q31_b_max,q31_both_low_high);
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

module tb_post_partial32;
    wire [6:0] done;
    post_partial32_scalar_checker #(.ID(0),.OUT_W(16),.OUT_SIGNED(1),.APPLY_PRELU(1)) c0(done[0]);
    post_partial32_scalar_checker #(.ID(1),.OUT_W(16),.OUT_SIGNED(1),.APPLY_PRELU(0)) c1(done[1]);
    post_partial32_scalar_checker #(.ID(2),.OUT_W(8),.OUT_SIGNED(0),.APPLY_PRELU(0)) c2(done[2]);
    post_partial32_scalar_checker #(.ID(3),.OUT_W(31),.OUT_SIGNED(1),.APPLY_PRELU(1)) c3(done[3]);
    post_partial32_scalar_checker #(.ID(4),.OUT_W(31),.OUT_SIGNED(0),.APPLY_PRELU(0)) c4(done[4]);
    post_partial32_scalar_checker #(.ID(5),.OUT_W(1),.OUT_SIGNED(1),.APPLY_PRELU(1)) c5(done[5]);
    requant_round64_probe c6(done[6]);
    initial begin
        wait(&done);
        $display("POST_PARTIAL32_SCALAR_ALL_CONFIGS_PASS");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"scalar/probe timeout");
    end
endmodule
