#include <ap_int.h>
#include <iostream>

void add_one(ap_int<8> input, ap_int<8> &output);

int main() {
    ap_int<8> output = 0;
    add_one(41, output);
    if (output != 42) {
        std::cerr << "HLS_SMOKE_TEST_FAIL: expected 42, got "
                  << output.to_int() << std::endl;
        return 1;
    }
    std::cout << "HLS_SMOKE_TEST_PASS" << std::endl;
    return 0;
}
