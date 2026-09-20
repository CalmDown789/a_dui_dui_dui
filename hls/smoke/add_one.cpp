#include <ap_int.h>

void add_one(ap_int<8> input, ap_int<8> &output) {
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    output = input + 1;
}
