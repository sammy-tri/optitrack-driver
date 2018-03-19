# -*- python -*-

# Based on commit 34d8467bb57ede397e53020a88f5b81cd2fdbcef of
# https://github.com/RobotLocomotion/drake/blob/master/tools/workspace/python/repository.bzl

"""
Finds local system Python headers and libraries using python-config and
makes them available to be used as a C/C++ dependency. On macOS, Python
libraries should not typically be directly linked, so the :python target passes
the "-undefined dynamic_lookup" linker flag, however in the rare cases that
this would cause an undefined symbol error, a :python_direct_link target is
provided. On Linux, these targets are identical.

Example:
    WORKSPACE:
        load("//tools:python.bzl", "python_repository")
        python_repository(
            name = "foo",
            version = "2",
        )

    BUILD:
        cc_library(
            name = "foobar",
            deps = ["@foo//:python"],
            srcs = ["bar.cc"],
        )

Arguments:
    name: A unique name for this rule.
    version: The major or major.minor version of Python headers and libraries
    to be found.
"""

load("//tools:os.bzl", "determine_os")

def _impl(repository_ctx):
    python_config = repository_ctx.which("python{}-config".format(
        repository_ctx.attr.version))

    if not python_config:
        fail("Could NOT find python{}-config".format(
            repository_ctx.attr.version))

    result = repository_ctx.execute([python_config, "--includes"])

    if result.return_code != 0:
        fail("Could NOT determine Python includes", attr = result.stderr)

    cflags = result.stdout.strip().split(" ")
    cflags = [cflag for cflag in cflags if cflag]

    root = repository_ctx.path("")
    root_len = len(str(root)) + 1
    base = root.get_child("include")

    includes = []

    for cflag in cflags:
        if cflag.startswith("-I"):
            source = repository_ctx.path(cflag[2:])
            destination = base.get_child(str(source).replace("/", "_"))
            include = str(destination)[root_len:]

            if include not in includes:
                repository_ctx.symlink(source, destination)
                includes += [include]

    result = repository_ctx.execute([python_config, "--ldflags"])

    if result.return_code != 0:
        fail("Could NOT determine Python linkopts", attr = result.stderr)

    linkopts = result.stdout.strip().split(" ")
    linkopts = [linkopt for linkopt in linkopts if linkopt]

    for i in reversed(range(len(linkopts))):
        if not linkopts[i].startswith("-"):
            linkopts[i - 1] += " " + linkopts.pop(i)

    linkopts_direct_link = list(linkopts)

    os_result = determine_os(repository_ctx)
    if os_result.error != None:
        fail(os_result.error)

    if os_result.is_macos:
        for i in reversed(range(len(linkopts))):
            if linkopts[i].find("python{}".format(
                    repository_ctx.attr.version)) != -1:
                linkopts.pop(i)
        linkopts = ["-undefined dynamic_lookup"] + linkopts

    file_content = """# -*- python -*-
# This file contains rules for the Bazel build system; see https://bazel.build.

licenses(["notice"])

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "python",
    hdrs = glob(["include/**"]),
    includes = {},
    linkopts = {},
)
""".format(includes, linkopts, linkopts_direct_link)

    repository_ctx.file("BUILD.bazel",
        content = file_content,
        executable = False
    )

python_repository = repository_rule(
    _impl,
    attrs = {"version": attr.string(default = "2")},
    local = True,
)
