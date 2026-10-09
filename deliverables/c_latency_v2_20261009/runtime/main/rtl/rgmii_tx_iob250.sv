`timescale 1ns/1ps
`default_nettype none
module rgmii_tx_iob250 #(
 parameter bit RESET_PHASE=1'b0
)(
 input wire clk250,reset_request,
 input wire[7:0]gmii_txd,input wire gmii_txen,gmii_txerr,
 output wire[3:0]rgmii_txd,output wire rgmii_txctl,rgmii_txc,
 output wire reset250,phase_debug
);
 (* ASYNC_REG="TRUE" *)reg[1:0]release_sync=2'b11;
 always @(posedge clk250 or posedge reset_request)
  if(reset_request)release_sync<=2'b11;else release_sync<={release_sync[0],1'b0};
 assign reset250=release_sync[1];
 reg phase_q=RESET_PHASE;
 reg[7:0]byte_q=0;
 reg en_q=0,err_q=0;
 always @(posedge clk250 or posedge reset250)begin
  if(reset250)begin phase_q<=RESET_PHASE;byte_q<=0;en_q<=0;err_q<=0;end
  else begin
   phase_q<=~phase_q;
   if(!phase_q)begin byte_q<=gmii_txd;en_q<=gmii_txen;err_q<=gmii_txerr;end
  end
 end
 assign phase_debug=phase_q;
 wire[4:0]output_d=phase_q?{en_q^err_q,byte_q[7:4]}:{gmii_txen,gmii_txd[3:0]};
 wire[4:0]output_q;
 for(genvar k=0;k<5;k=k+1)begin:g_iob
  (* IOB="TRUE" *)FDCE #(.INIT(1'b0))u_ff(
   .C(clk250),.CE(1'b1),.CLR(reset250),.D(output_d[k]),.Q(output_q[k]));
 end
 // Native falling C -> Q arc exists. D1/D2 capture the old phase together.
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0))u_forward(
  .C(clk250),.CE(1'b1),.R(reset250),.S(1'b0),
  .D1(phase_q),.D2(~phase_q),.Q(rgmii_txc));
 assign rgmii_txd=output_q[3:0];
 assign rgmii_txctl=output_q[4];
endmodule
`default_nettype wire
