# -*- python -*-
# This file contains rules for Bazel; see drake/doc/bazel.rst.

package(default_visibility = ["//visibility:public"])

py_binary(
    name = "optitrack_client",
    srcs = ["optitrack_client.py"],
    deps = ["@lcm//:lcm-python",
            "//lcmtypes:py_optitrack_lcmtypes"],
)
