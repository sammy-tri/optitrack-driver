# -*- python -*-
# This file contains rules for Bazel; see drake/doc/bazel.rst.

package(default_visibility = ["//visibility:public"])

load("//tools:lcm.bzl", "lcm_cc_library", "lcm_py_library")

LCM_SRCS = [
    "optitrack_data_descriptions_t.lcm",
    "optitrack_frame_t.lcm",
    "optitrack_marker_set_description_t.lcm",
    "optitrack_marker_set_t.lcm",
    "optitrack_marker_t.lcm",
    "optitrack_rigid_body_t.lcm",
    "optitrack_rigid_body_description_t.lcm",
]

lcm_cc_library(
    name = "optitrack_lcmtypes",
    lcm_package = "optitrack",
    lcm_srcs = LCM_SRCS,
    linkstatic = 1,
)

lcm_py_library(
    name = "py_optitrack_lcmtypes",
    lcm_package = "optitrack",
    lcm_srcs = LCM_SRCS,
)
