`timescale 1ns/1ps
`default_nettype none
// Independent Clause22 engine. Send 46 command clocks, release MDIO,
// then one receive clock for ACK, 16 receive clocks for DATA, one idle clock.
// This follows Linux mdiobb_read_common, not the former extra TA clock.
// PHY updates after rising MDC; sample near falling after 5us settling.
module fsrcnn_phy_mdio_c22_transaction #(parameter integer HALF_CYCLES=250)(
 input wire clk,rst_n,cmd_valid,output wire cmd_ready,
 input wire cmd_read,input wire[4:0]cmd_phy,cmd_reg,input wire[15:0]cmd_data,
 output reg done,output reg[15:0]read_data,output reg no_read_ack,
 output reg[17:0]early_trace,late_trace,output wire mdc,inout wire mdio
);
 reg busy_q,read_q,mdc_q,mdio_oe_q,mdio_out_q;
 reg[4:0]phy_q,reg_q; reg[15:0]data_q;
 reg[6:0]bit_q; reg[31:0]half_count_q;
 (* ASYNC_REG="TRUE" *) reg mdio_meta_q,mdio_sync_q;
 always @(posedge clk)begin mdio_meta_q<=mdio;mdio_sync_q<=mdio_meta_q;end
 assign cmd_ready=rst_n&&!busy_q;
 assign mdc=mdc_q;
 assign mdio=mdio_oe_q?mdio_out_q:1'bz;
 function automatic bit_value(input[6:0]i,input rd,input[4:0]pa,ra,input[15:0]v);
 begin
  if(i<32)bit_value=1;
  else case(i)
   32:bit_value=0;33:bit_value=1;34:bit_value=rd;35:bit_value=!rd;
   46:bit_value=1;47:bit_value=0;
   default:if(i<=40)bit_value=pa[40-i];else if(i<=45)bit_value=ra[45-i];else bit_value=v[63-i];
  endcase
 end endfunction
 initial if(HALF_CYCLES<25)$fatal(1,"At50MHz require >=500ns half-period");
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   busy_q<=0;read_q<=0;mdc_q<=0;mdio_oe_q<=0;mdio_out_q<=1;
   phy_q<=0;reg_q<=0;data_q<=0;bit_q<=0;half_count_q<=0;
   done<=0;read_data<=0;no_read_ack<=0;early_trace<=0;late_trace<=0;
  end else begin
   done<=0;
   if(cmd_valid&&cmd_ready)begin
    busy_q<=1;read_q<=cmd_read;phy_q<=cmd_phy;reg_q<=cmd_reg;data_q<=cmd_data;
    bit_q<=0;half_count_q<=0;mdc_q<=0;mdio_oe_q<=1;mdio_out_q<=1;
    read_data<=0;no_read_ack<=0;early_trace<=0;late_trace<=0;
   end else if(busy_q)begin
    if(half_count_q==HALF_CYCLES-1)begin
     half_count_q<=0;mdc_q<=!mdc_q;
     if(!mdc_q)begin
      if(read_q&&bit_q>=46)early_trace<={early_trace[16:0],mdio_sync_q};
     end else begin
      if(read_q&&bit_q>=46)late_trace<={late_trace[16:0],mdio_sync_q};
      if(read_q&&bit_q==46)no_read_ack<=(mdio_sync_q!==1'b0);
      if(read_q&&bit_q>=47&&bit_q<=62)read_data<={read_data[14:0],mdio_sync_q};
      if(bit_q==63)begin busy_q<=0;done<=1;mdio_oe_q<=0;mdio_out_q<=1;end
      else begin
       bit_q<=bit_q+1;
       mdio_oe_q<=!(read_q&&bit_q>=45);
       mdio_out_q<=bit_value(bit_q+1,read_q,phy_q,reg_q,data_q);
      end
     end
    end else half_count_q<=half_count_q+1;
   end
  end
 end
endmodule
`default_nettype wire
