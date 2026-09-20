#ifndef LAYER_VECTOR_HPP
#define LAYER_VECTOR_HPP

#include <cstdint>

namespace layer_vector {

constexpr int ROWS = 4;
constexpr int COLS = 5;
constexpr int INPUT_CHANNELS = 2;
constexpr int OUTPUT_CHANNELS = 3;
constexpr int OUTPUT_ROWS = 2;
constexpr int OUTPUT_COLS = 3;

constexpr std::int8_t INPUT[ROWS][COLS][INPUT_CHANNELS] =
    {
        {
            {1, 2},
            {2, 2},
            {3, 2},
            {4, 2},
            {5, 2}
        },
        {
            {6, 2},
            {7, 2},
            {8, 2},
            {9, 2},
            {10, 2}
        },
        {
            {11, 2},
            {12, 2},
            {13, 2},
            {14, 2},
            {15, 2}
        },
        {
            {16, 2},
            {17, 2},
            {18, 2},
            {19, 2},
            {20, 2}
        }
    };

constexpr std::int8_t WEIGHTS[OUTPUT_CHANNELS][INPUT_CHANNELS][3][3] =
    {
        {
            {
                {1, 1, 1},
                {1, 1, 1},
                {1, 1, 1}
            },
            {
                {-1, -1, -1},
                {-1, -1, -1},
                {-1, -1, -1}
            }
        },
        {
            {
                {-1, -1, -1},
                {-1, -1, -1},
                {-1, -1, -1}
            },
            {
                {1, 1, 1},
                {1, 1, 1},
                {1, 1, 1}
            }
        },
        {
            {
                {0, 0, 0},
                {0, 0, 0},
                {0, 0, 0}
            },
            {
                {0, 0, 0},
                {0, 0, 0},
                {0, 0, 0}
            }
        }
    };

constexpr std::int32_t BIAS[OUTPUT_CHANNELS] =
    {7, -3, 42};

constexpr std::int32_t EXPECTED[OUTPUT_ROWS][OUTPUT_COLS][OUTPUT_CHANNELS] =
    {
        {
            {52, -48, 42},
            {61, -57, 42},
            {70, -66, 42}
        },
        {
            {97, -93, 42},
            {106, -102, 42},
            {115, -111, 42}
        }
    };

}  // namespace layer_vector

#endif
