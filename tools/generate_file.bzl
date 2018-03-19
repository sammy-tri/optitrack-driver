# -*- python -*-

# Based on commit 64bf3351a633c805ada9a06b53f77aefe63a93ce of
# https://github.com/RobotLocomotion/drake/blob/master/tools/workspace/generate_file.bzl

def _generate_file_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.write(out, ctx.attr.content, ctx.attr.is_executable)
    return [DefaultInfo(
        files = depset([out]),
        data_runfiles = ctx.runfiles(files = [out]),
    )]

generate_file = rule(
    attrs = {
        "content": attr.string(mandatory = True),
        "is_executable": attr.bool(default = False),
    },
    output_to_genfiles = True,
    implementation = _generate_file_impl,
)

"""Generate a file with specified content.

This creates a rule to generate a file with specified content (which is either
static or has been previously computed).

Args:
    content (:obj:`str`): Desired content of the generated file.
"""
