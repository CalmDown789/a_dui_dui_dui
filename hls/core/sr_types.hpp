#ifndef SR_TYPES_HPP
#define SR_TYPES_HPP

#include <ap_int.h>

namespace sr {

constexpr int KERNEL_SIZE = 3;
constexpr int MAX_INPUT_CHANNELS = 16;
constexpr int UPSCALE = 2;
constexpr int SUBPIXEL_CHANNELS = UPSCALE * UPSCALE;

using activation_t = ap_int<8>;
using weight_t = ap_int<8>;
using accumulator_t = ap_int<32>;
using channel_count_t = ap_uint<5>;

}  // namespace sr

#endif
